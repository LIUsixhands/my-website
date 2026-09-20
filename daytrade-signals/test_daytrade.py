"""
test_daytrade.py — 離線測試。不需要 shioaji、不需要網路、不需要金鑰。

    python3 test_daytrade.py

測的是「錯了不會報錯」的那些地方：訊號條件、風控閘門、量能基準、紀律稽核。
這些邏輯算錯不會讓程式崩掉，它會安靜地給你一個看起來很專業的錯誤決策。
"""
import contextlib
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, time as dtime
from pathlib import Path
from types import SimpleNamespace

import config
import preflight
import review
from broker import Broker
import screener
import signals
from signals import RiskGate, SymbolState, evaluate, format_signal


# ── 測試替身 ──────────────────────────────────────────
class FakeBroker:
    """只提供風控閘門會用到的那幾個方法。"""

    def __init__(self, trades=None, pnl_rows=None):
        self._trades = trades if trades is not None else []
        self._pnl_rows = pnl_rows          # None = 查詢失敗

    def trades_today(self):
        return self._trades

    def realized_pnl_rows_today(self):
        return self._pnl_rows


def tick(close, high=None, low=None, avg_price=0, total_volume=0, at="09:05:00"):
    return SimpleNamespace(
        close=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        avg_price=avg_price,
        total_volume=total_volume,
        datetime=datetime.strptime(f"2026-01-02 {at}", "%Y-%m-%d %H:%M:%S"),
    )


def snap(code="2330", close=100.0, high=104.0, low=100.0, volume=9000, avg=101.0):
    return SimpleNamespace(code=code, close=close, high=high, low=low,
                           total_volume=volume, average_price=avg)


def ready_state(code="2330", or_high=100.0, last=101.0, vwap=100.5, surge_ratio=3.0):
    """造一個「萬事俱備」的個股狀態：區間已鎖、價格突破、站上均價、量能達標。"""
    st = SymbolState(code, prev_close=99.0)
    st.lock_opening_range(or_high, or_high - 2)
    st.last_price = last
    st.vwap = vwap
    # vol_marks 每 60 秒一筆，橫跨 15 分鐘：
    # 最後 5 分鐘的量能速率是 surge_ratio 張/秒，之前是 1 張/秒。
    now = 10_000.0
    marks, vol = [], 0.0
    for offset in range(-900, 1, 60):
        marks.append((now + offset, int(round(vol))))
        vol += 60 * (1.0 if offset < -300 else surge_ratio)
    st.vol_marks = marks
    return st


class TestConfig(unittest.TestCase):
    def test_round_trip_cost(self):
        # 手續費 0.001425 × 2折 × 來回 + 當沖稅 0.0015 = 0.00207 → 0.207%
        self.assertAlmostEqual(config.round_trip_cost_pct(), 0.207, places=4)

    def test_shipped_config_is_valid(self):
        self.assertEqual(config.validate(), [])

    def test_validate_catches_bad_params(self):
        cases = [
            (config.SIGNAL, "stop_loss_pct", 0, "stop_loss_pct"),
            (config.SIGNAL, "reward_risk", -1, "reward_risk"),
            (config.SIGNAL, "allow_short", True, "allow_short"),
            (config.SIGNAL, "or_end", "08:00:00", "時間順序"),
            (config.RISK, "max_daily_loss", 0, "max_daily_loss"),
            (config.RISK, "max_consecutive_losses", 0, "max_consecutive_losses"),
            (config.RISK, "poll_interval_sec", 5, "poll_interval_sec"),
            (config.SIGNAL, "market_close", "11:00:00", "時間順序"),
            (config.SCREEN, "min_price", 999.0, "min_price"),
            (config.COST, "fee_discount", 0, "fee_discount"),
        ]
        for section, key, bad, expect in cases:
            with self.subTest(key=key):
                original = section[key]
                section[key] = bad
                try:
                    errs = " / ".join(config.validate())
                    self.assertIn(expect, errs)
                finally:
                    section[key] = original

    def test_validate_catches_contradicting_red_lines(self):
        original = config.RISK["max_daily_loss"]
        config.RISK["max_daily_loss"] = 999_999
        try:
            self.assertTrue(any("形同虛設" in e for e in config.validate()))
        finally:
            config.RISK["max_daily_loss"] = original

    def test_load_env_parses_and_does_not_overwrite(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text(
                "# comment\n"
                "\n"
                "PLAIN=abc\n"
                'QUOTED="with space"\n'
                "SINGLE='sq'\n"
                "export EXPORTED=ex\n"
                "NOEQUALS\n"
                "ALREADY_SET=from_file\n",
                encoding="utf-8")
            os.environ["ALREADY_SET"] = "from_environ"
            for k in ("PLAIN", "QUOTED", "SINGLE", "EXPORTED"):
                os.environ.pop(k, None)
            config.load_env(p)
            self.assertEqual(os.environ["PLAIN"], "abc")
            self.assertEqual(os.environ["QUOTED"], "with space")
            self.assertEqual(os.environ["SINGLE"], "sq")
            self.assertEqual(os.environ["EXPORTED"], "ex")
            # 已存在的環境變數不被檔案覆寫
            self.assertEqual(os.environ["ALREADY_SET"], "from_environ")

    def test_load_env_missing_file_is_noop(self):
        config.load_env(Path("/nonexistent/.env"))   # 不應拋出


class TestTickSize(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(config.tick_size(9.99), 0.01)
        self.assertEqual(config.tick_size(10.0), 0.05)
        self.assertEqual(config.tick_size(49.99), 0.05)
        self.assertEqual(config.tick_size(50.0), 0.1)
        self.assertEqual(config.tick_size(99.99), 0.1)
        self.assertEqual(config.tick_size(100.0), 0.5)
        self.assertEqual(config.tick_size(499.5), 0.5)
        self.assertEqual(config.tick_size(500.0), 1.0)
        self.assertEqual(config.tick_size(1000.0), 5.0)

    def test_rounding_modes(self):
        self.assertEqual(config.round_to_tick(99.485, "up"), 99.5)
        self.assertEqual(config.round_to_tick(99.485, "down"), 99.4)
        self.assertEqual(config.round_to_tick(45.67, "up"), 45.7)
        self.assertEqual(config.round_to_tick(45.67, "down"), 45.65)
        self.assertEqual(config.round_to_tick(278.755, "up"), 279.0)

    def test_already_on_tick_is_unchanged(self):
        for p in (10.0, 45.65, 99.5, 100.5, 283.0, 1200.0):
            for mode in ("up", "down", "nearest"):
                self.assertAlmostEqual(config.round_to_tick(p, mode), p, msg=f"{p}/{mode}")


class TestConsoleEncoding(unittest.TestCase):
    """Windows 繁中主控台是 cp950，印 emoji 會直接讓程式當掉。"""

    def setUp(self):
        self._stdout = sys.stdout

    def tearDown(self):
        sys.stdout = self._stdout

    @staticmethod
    def _fake_stdout(encoding):
        return SimpleNamespace(encoding=encoding)

    def test_detects_cp950_cannot_encode_emoji(self):
        sys.stdout = self._fake_stdout("cp950")
        self.assertFalse(config.console_can_encode("✅"))
        self.assertTrue(config.console_can_encode("當沖訊號"))   # 中文 cp950 印得出來

    def test_detects_utf8_can_encode_everything(self):
        sys.stdout = self._fake_stdout("utf-8")
        self.assertTrue(config.console_can_encode("✅"))
        self.assertTrue(config.console_can_encode("當沖訊號"))

    def test_unknown_encoding_falls_back(self):
        sys.stdout = self._fake_stdout("not-a-real-codec")
        self.assertFalse(config.console_can_encode("✅"))
        sys.stdout = SimpleNamespace()                 # 連 encoding 屬性都沒有
        self.assertFalse(config.console_can_encode("✅"))

    def test_symbol_picks_fallback_on_cp950(self):
        sys.stdout = self._fake_stdout("cp950")
        self.assertEqual(config.symbol("✅", "[ OK ]"), "[ OK ]")
        sys.stdout = self._fake_stdout("utf-8")
        self.assertEqual(config.symbol("✅", "[ OK ]"), "✅")

    def test_enable_console_fallback_tolerates_odd_streams(self):
        sys.stdout = io.StringIO()                     # 沒有 reconfigure
        config.enable_console_fallback()               # 不應拋出
        sys.stdout = SimpleNamespace(reconfigure=lambda **kw: (_ for _ in ()).throw(ValueError))
        config.enable_console_fallback()               # 也不應拋出

    def test_preflight_markers_are_printable(self):
        """不管終端機是什麼編碼，體檢的狀態標記都要印得出來。"""
        for marker in (preflight.OK, preflight.WARN, preflight.FAIL):
            self.assertTrue(marker.strip(), "狀態標記不可為空")


class TestOpeningRange(unittest.TestCase):
    def test_accumulates_then_locks(self):
        st = SymbolState("2330", 99.0)
        st.update(tick(100.0, high=100.5, low=99.5, at="09:01:00"))
        st.update(tick(101.0, high=101.5, low=99.0, at="09:10:00"))
        self.assertFalse(st.or_locked)
        self.assertAlmostEqual(st.or_high, 101.5)
        self.assertAlmostEqual(st.or_low, 99.0)

        st.update(tick(102.0, high=103.0, low=98.0, at="09:16:00"))
        self.assertTrue(st.or_locked)
        # 鎖定後不再被盤中新高低污染
        self.assertAlmostEqual(st.or_high, 101.5)
        self.assertAlmostEqual(st.or_low, 99.0)

    def test_locked_range_survives_later_ticks(self):
        st = SymbolState("2330", 99.0)
        st.lock_opening_range(100.0, 98.0, source="test")
        st.update(tick(120.0, high=120.0, low=90.0, at="10:00:00"))
        self.assertAlmostEqual(st.or_high, 100.0)
        self.assertAlmostEqual(st.or_low, 98.0)

    def test_backfilled_range_is_locked(self):
        st = SymbolState("2330", 99.0)
        st.lock_opening_range(105.0, 103.0, source="分鐘K補算")
        self.assertTrue(st.or_locked)
        self.assertAlmostEqual(st.or_high, 105.0)


class TestVolumeSurge(unittest.TestCase):
    def test_insufficient_samples(self):
        st = SymbolState("2330", 99.0)
        self.assertEqual(st.volume_surge(), 0.0)
        st.vol_marks = [(0.0, 0), (30.0, 100)]
        self.assertEqual(st.volume_surge(), 0.0)

    def test_short_baseline_window_returns_zero(self):
        """基準樣本只有 2 分鐘 → 不給倍數。

        這是原本開盤前幾分鐘失真的來源：基準太短卻照樣算，
        結果人人都是爆量。
        """
        st = SymbolState("2330", 99.0)
        now = 1000.0
        st.vol_marks = [(now - 420, 0), (now - 360, 60),      # older 只橫跨 60 秒
                        (now - 200, 500), (now - 100, 900), (now, 1500)]
        self.assertEqual(st.volume_surge(), 0.0)

    def test_detects_genuine_surge(self):
        st = ready_state(surge_ratio=3.0)
        self.assertAlmostEqual(st.volume_surge(), 3.0, places=1)

    def test_flat_volume_is_about_one(self):
        st = ready_state(surge_ratio=1.0)
        self.assertAlmostEqual(st.volume_surge(), 1.0, places=1)

    def test_no_baseline_volume_returns_zero(self):
        st = SymbolState("2330", 99.0)
        now = 1000.0
        st.vol_marks = ([(now - 900 + i * 60, 0) for i in range(11)]
                        + [(now - 200, 100), (now, 400)])
        self.assertEqual(st.volume_surge(), 0.0)


class TestEvaluate(unittest.TestCase):
    NOON = dtime(10, 0)

    def test_fires_on_all_conditions_met(self):
        sig = evaluate(ready_state(or_high=100.0, last=101.0, vwap=100.5), now=self.NOON)
        self.assertIsNotNone(sig)
        self.assertEqual(sig["code"], "2330")
        self.assertEqual(sig["direction"], "做多")
        self.assertAlmostEqual(sig["entry"], 101.0)
        # 101 × (1-1.5%) = 99.485 → 進位到 0.1 檔位 = 99.5
        self.assertAlmostEqual(sig["stop"], 99.5)
        # 101 + 1.5 × 1.5 = 103.25 → 進位到 0.5 檔位 = 103.5
        self.assertAlmostEqual(sig["target"], 103.5)
        self.assertFalse(sig["oversized"])

    def test_lot_sizing_from_per_trade_risk(self):
        sig = evaluate(ready_state(or_high=100.0, last=101.0, vwap=100.5), now=self.NOON)
        # 一張風險 = (101 - 99.5) × 1000 = 1500 元；2000 / 1500 → 1 張
        self.assertEqual(sig["risk_per_lot"], 1500)
        self.assertEqual(sig["lots"], 1)

        cheap = ready_state(or_high=20.0, last=20.2, vwap=20.1)
        sig2 = evaluate(cheap, now=self.NOON)
        # 20.2 × (1-1.5%) = 19.897 → 進位到 0.05 檔位 = 19.90
        self.assertAlmostEqual(sig2["stop"], 19.9)
        # 一張風險 = 300 元；2000 / 300 → 6 張
        self.assertEqual(sig2["risk_per_lot"], 300)
        self.assertEqual(sig2["lots"], 6)
        self.assertFalse(sig2["oversized"])

    def test_prices_land_on_legal_ticks(self):
        """停損／目標必須是可以真的下出去的價位。"""
        for or_high, last in ((20.0, 20.2), (60.0, 60.5), (100.0, 101.0), (280.0, 283.0)):
            with self.subTest(last=last):
                sig = evaluate(ready_state(or_high=or_high, last=last, vwap=last - 0.5),
                               now=self.NOON)
                self.assertIsNotNone(sig)
                for field in ("stop", "target"):
                    price = sig[field]
                    tick = config.tick_size(price)
                    self.assertAlmostEqual(price / tick, round(price / tick), places=6,
                                           msg=f"{field}={price} 不在 {tick} 檔位上")

    def test_actual_risk_never_exceeds_configured_pct(self):
        """停損往緊的方向進位 → 實際風險 % 不會超過設定值。"""
        for or_high, last in ((20.0, 20.2), (60.0, 60.5), (100.0, 101.0), (280.0, 283.0)):
            with self.subTest(last=last):
                sig = evaluate(ready_state(or_high=or_high, last=last, vwap=last - 0.5),
                               now=self.NOON)
                actual_pct = (sig["entry"] - sig["stop"]) / sig["entry"] * 100
                self.assertLessEqual(actual_pct, config.SIGNAL["stop_loss_pct"] + 1e-9)

    def test_reward_risk_never_below_configured(self):
        for or_high, last in ((20.0, 20.2), (60.0, 60.5), (100.0, 101.0), (280.0, 283.0)):
            with self.subTest(last=last):
                sig = evaluate(ready_state(or_high=or_high, last=last, vwap=last - 0.5),
                               now=self.NOON)
                r = (sig["target"] - sig["entry"]) / (sig["entry"] - sig["stop"])
                self.assertGreaterEqual(r, config.SIGNAL["reward_risk"] - 1e-9)

    def test_flags_oversized_single_lot(self):
        """高價股一張的停損金額就超過單筆上限 → 必須標記，不能假裝 1 張沒事。"""
        pricey = ready_state(or_high=280.0, last=283.0, vwap=281.0)
        sig = evaluate(pricey, now=self.NOON)
        self.assertEqual(sig["lots"], 1)
        self.assertTrue(sig["oversized"])
        self.assertGreater(sig["risk_per_lot"], config.RISK["per_trade_risk"])
        self.assertIn("超過單筆上限", format_signal(sig, 1))

    def test_blocked_before_range_locked(self):
        st = ready_state()
        st.or_locked = False
        self.assertIsNone(evaluate(st, now=self.NOON))

    def test_blocked_below_breakout_buffer(self):
        # 區間高 100 → 觸發價 100.10；100.05 不算突破
        st = ready_state(or_high=100.0, last=100.05, vwap=99.0)
        self.assertIsNone(evaluate(st, now=self.NOON))

    def test_blocked_below_vwap(self):
        st = ready_state(or_high=100.0, last=101.0, vwap=101.5)
        self.assertIsNone(evaluate(st, now=self.NOON))

    def test_missing_vwap_blocks_instead_of_skipping_the_rule(self):
        """均價線拿不到 → 不發訊號，而不是把這條規則靜靜跳過。

        原本 `require_above_vwap and st.vwap and ...` 在 vwap=0 時整條短路，
        規則你以為開著，其實整天沒作用。
        """
        st = ready_state(or_high=100.0, last=101.0, vwap=0.0)
        self.assertTrue(config.SIGNAL["require_above_vwap"])
        with self.assertLogs(signals.log, level="WARNING") as cm:
            self.assertIsNone(evaluate(st, now=self.NOON))
        self.assertIn("沒有均價線", "".join(cm.output))
        self.assertTrue(st.vwap_warned)

    def test_missing_vwap_warns_only_once(self):
        st = ready_state(or_high=100.0, last=101.0, vwap=0.0)
        with self.assertLogs(signals.log, level="WARNING"):
            evaluate(st, now=self.NOON)
        with self.assertNoLogs(signals.log, level="WARNING"):
            self.assertIsNone(evaluate(st, now=self.NOON))

    def test_missing_vwap_is_allowed_when_rule_is_off(self):
        original = config.SIGNAL["require_above_vwap"]
        config.SIGNAL["require_above_vwap"] = False
        try:
            st = ready_state(or_high=100.0, last=101.0, vwap=0.0)
            self.assertIsNotNone(evaluate(st, now=self.NOON))
        finally:
            config.SIGNAL["require_above_vwap"] = original

    def test_blocked_on_weak_volume(self):
        st = ready_state(or_high=100.0, last=101.0, vwap=100.5, surge_ratio=1.2)
        self.assertIsNone(evaluate(st, now=self.NOON))

    def test_blocked_after_entry_window(self):
        st = ready_state()
        self.assertIsNone(evaluate(st, now=dtime(12, 31)))

    def test_one_signal_per_symbol(self):
        st = ready_state()
        st.signaled = config.SIGNAL["max_signals_per_symbol"]
        self.assertIsNone(evaluate(st, now=self.NOON))


class TestRiskGate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_state_file = config.STATE_FILE
        config.STATE_FILE = Path(self._tmp.name) / "state.json"
        self._orig_sim = config.SIMULATION
        self._sent = []
        self._orig_notify = signals.notify
        signals.notify = self._sent.append

    def tearDown(self):
        config.STATE_FILE = self._orig_state_file
        config.SIMULATION = self._orig_sim
        signals.notify = self._orig_notify
        self._tmp.cleanup()

    def test_open_when_nothing_tripped(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        self.assertTrue(gate.check())
        self.assertFalse(gate.state["closed"])

    def test_signal_ordinal_starts_at_one(self):
        """第一個訊號必須顯示「今日第 1 個」。

        原本 record() 先加一、format 再 +1，第一個訊號會印成 2/5。
        """
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        sig = evaluate(ready_state(), now=dtime(10, 0))
        ordinal = gate.record(sig)
        self.assertEqual(ordinal, 1)
        self.assertIn(f"今日第 1/{config.RISK['max_signals_per_day']} 個訊號",
                      format_signal(sig, ordinal))
        self.assertEqual(gate.record(sig), 2)

    def test_closes_on_daily_signal_limit(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        gate.state["signals_sent"] = config.RISK["max_signals_per_day"]
        self.assertFalse(gate.check())
        self.assertIn("訊號上限", gate.state["closed_reason"])

    def test_closes_on_trade_count_limit(self):
        trades = [object()] * (config.RISK["max_trades_per_day"] * 2)
        gate = RiskGate(FakeBroker(trades=trades, pnl_rows=[]))
        self.assertFalse(gate.check())
        self.assertIn("交易筆數上限", gate.state["closed_reason"])

    def test_closes_on_daily_loss(self):
        gate = RiskGate(FakeBroker(pnl_rows=[-5000.0, -3000.0]))
        self.assertFalse(gate.check())
        self.assertIn("觸及上限", gate.state["closed_reason"])

    def test_daily_loss_just_under_limit_stays_open(self):
        gate = RiskGate(FakeBroker(pnl_rows=[-7999.0]))
        self.assertTrue(gate.check())

    def test_closes_on_consecutive_losses(self):
        """連三敗停手：config 與 README 都寫了，但原本完全沒有實作。"""
        gate = RiskGate(FakeBroker(pnl_rows=[500.0, -100.0, -200.0, -300.0]))
        self.assertFalse(gate.check())
        self.assertIn("連續 3 筆虧損", gate.state["closed_reason"])

    def test_win_resets_loss_streak(self):
        gate = RiskGate(FakeBroker(pnl_rows=[-100.0, -200.0, 50.0]))
        self.assertTrue(gate.check())

    def test_unknown_pnl_halts_when_live(self):
        """真錢模式查不到損益 = 沒有煞車 → 停手。

        原本查不到回傳 0.0，日虧上限與連敗停手會同時失效。
        """
        config.SIMULATION = False
        gate = RiskGate(FakeBroker(pnl_rows=None))
        self.assertFalse(gate.check())
        self.assertIn("沒有煞車", gate.state["closed_reason"])
        self.assertTrue(any("今日停手" in m for m in self._sent))

    def test_unknown_pnl_tolerated_in_simulation(self):
        """模擬模式本來就沒有損益可查，硬停手會讓第一個月跑不出訊號品質數據。"""
        config.SIMULATION = True
        gate = RiskGate(FakeBroker(pnl_rows=None))
        self.assertTrue(gate.check())

    def test_closed_gate_stays_closed(self):
        gate = RiskGate(FakeBroker(pnl_rows=[-99999.0]))
        self.assertFalse(gate.check())
        gate.broker = FakeBroker(pnl_rows=[])      # 就算損益變好也不重開
        self.assertFalse(gate.check())

    def test_state_persists_across_restart(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        gate.record(evaluate(ready_state(), now=dtime(10, 0)))
        gate._close("測試")
        reloaded = RiskGate(FakeBroker(pnl_rows=[]))
        self.assertTrue(reloaded.state["closed"])
        self.assertEqual(reloaded.state["signals_sent"], 1)
        self.assertEqual(len(reloaded.state["signals"]), 1)

    def test_stale_state_file_is_discarded(self):
        config.STATE_FILE.write_text(json.dumps(
            {"date": "2000-01-01", "signals_sent": 5, "closed": True,
             "closed_reason": "昨天的", "signals": [{}]}), encoding="utf-8")
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        self.assertFalse(gate.state["closed"])
        self.assertEqual(gate.state["signals_sent"], 0)

    def test_trailing_losses(self):
        f = RiskGate._trailing_losses
        self.assertEqual(f([]), 0)
        self.assertEqual(f([100.0]), 0)
        self.assertEqual(f([-1.0]), 1)
        self.assertEqual(f([100.0, -1.0, -2.0]), 2)
        self.assertEqual(f([-1.0, -2.0, 100.0]), 0)
        self.assertEqual(f([0.0, -1.0]), 1)          # 0 不算虧，打斷連敗


class TestNotify(unittest.TestCase):
    """推播是選配相依：缺 requests 仍要能跑，但不能安靜地吞掉訊號。"""

    def setUp(self):
        self._orig = (signals.requests, config.TELEGRAM_BOT_TOKEN,
                      config.TELEGRAM_CHAT_ID, signals._push_warned)

    def tearDown(self):
        (signals.requests, config.TELEGRAM_BOT_TOKEN,
         config.TELEGRAM_CHAT_ID, signals._push_warned) = self._orig

    def test_prints_without_requests_installed(self):
        signals.requests = None
        config.TELEGRAM_BOT_TOKEN = config.TELEGRAM_CHAT_ID = ""
        with contextlib.redirect_stdout(io.StringIO()) as out:
            signals.notify("測試訊號")
        self.assertIn("測試訊號", out.getvalue())

    def test_logs_error_when_push_configured_but_requests_missing(self):
        signals.requests = None
        config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID = "tok", "chat"
        signals._push_warned = False
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertLogs(signals.log, level="ERROR") as cm:
                signals.notify("測試訊號")
        self.assertIn("不會推到手機", "".join(cm.output))

    def test_posts_when_requests_available(self):
        sent = {}

        class FakeRequests:
            @staticmethod
            def post(url, json, timeout):
                sent.update(url=url, json=json, timeout=timeout)

        signals.requests = FakeRequests
        config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID = "tok", "chat"
        with contextlib.redirect_stdout(io.StringIO()):
            signals.notify("測試訊號")
        self.assertIn("bottok/sendMessage", sent["url"])
        self.assertEqual(sent["json"]["chat_id"], "chat")
        self.assertEqual(sent["json"]["text"], "測試訊號")

    def test_push_failure_does_not_raise(self):
        class Boom:
            @staticmethod
            def post(*a, **k):
                raise RuntimeError("網路斷了")

        signals.requests = Boom
        config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID = "tok", "chat"
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertLogs(signals.log, level="WARNING"):
                signals.notify("測試訊號")     # 推播失敗不能讓引擎掛掉


class TestConcurrentEmit(unittest.TestCase):
    """行情回呼在背景執行緒上跑 —— 訊號上限必須擋得住並行。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = config.STATE_FILE
        config.STATE_FILE = Path(self._tmp.name) / "state.json"

    def tearDown(self):
        config.STATE_FILE = self._orig
        self._tmp.cleanup()

    @staticmethod
    def _widen_race_window(gate):
        """把延遲塞進 check() 與 record() 之間 —— 那才是真正的競態窗口。

        不加這個，這些測試在真鎖與無鎖之下都會過（GIL 讓臨界區短到撞不上），
        等於白測。實測：拿掉鎖時上限 5 個會變成發出 36 個。
        """
        real_check = gate.check

        def slow_check():
            ok = real_check()
            time.sleep(0.002)
            return ok

        gate.check = slow_check
        return gate

    def _hammer(self, states, gate, threads=24):
        self._widen_race_window(gate)
        lock = threading.Lock()
        sent = []
        sent_lock = threading.Lock()
        barrier = threading.Barrier(threads)

        def worker(st):
            sig = evaluate(st, now=dtime(10, 0))
            barrier.wait()                       # 盡量讓大家同時進來
            if sig:
                msg = signals.try_emit(st, gate, lock, sig)
                if msg:
                    with sent_lock:
                        sent.append(msg)

        pool = [threading.Thread(target=worker, args=(states[i % len(states)],))
                for i in range(threads)]
        for t in pool:
            t.start()
        for t in pool:
            t.join()
        return sent

    def test_one_symbol_emits_once_under_concurrency(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        st = ready_state("2330")
        sent = self._hammer([st], gate)
        self.assertEqual(len(sent), config.SIGNAL["max_signals_per_symbol"])
        self.assertEqual(st.signaled, config.SIGNAL["max_signals_per_symbol"])
        self.assertEqual(gate.state["signals_sent"], len(sent))

    def test_daily_cap_holds_across_symbols_under_concurrency(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        cap = config.RISK["max_signals_per_day"]
        states = [ready_state(str(2330 + i)) for i in range(cap + 4)]
        sent = self._hammer(states, gate, threads=(cap + 4) * 4)
        self.assertLessEqual(len(sent), cap)
        self.assertLessEqual(gate.state["signals_sent"], cap)
        self.assertEqual(len(gate.state["signals"]), gate.state["signals_sent"])

    def test_ordinals_are_unique_and_sequential(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        states = [ready_state(str(2330 + i)) for i in range(4)]
        sent = self._hammer(states, gate, threads=16)
        ordinals = sorted(int(m.split("今日第 ")[1].split("/")[0]) for m in sent)
        self.assertEqual(ordinals, list(range(1, len(sent) + 1)))

    def test_closed_gate_emits_nothing(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        gate._close("測試")
        self.assertEqual(self._hammer([ready_state("2330")], gate), [])


class TestRestoreSignaled(unittest.TestCase):
    """盤中重開後，已經發過訊號的那檔不能再發一次。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = config.STATE_FILE
        config.STATE_FILE = Path(self._tmp.name) / "state.json"

    def tearDown(self):
        config.STATE_FILE = self._orig
        self._tmp.cleanup()

    def test_restores_per_symbol_counts(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        gate.state["signals"] = [{"code": "2330"}, {"code": "2317"}]
        states = {c: SymbolState(c, 100.0) for c in ("2330", "2317", "2454")}
        self.assertEqual(signals.restore_signaled(states, gate), 2)
        self.assertEqual(states["2330"].signaled, 1)
        self.assertEqual(states["2317"].signaled, 1)
        self.assertEqual(states["2454"].signaled, 0)

    def test_restored_symbol_cannot_signal_again(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        gate.state["signals"] = [{"code": "2330"}]
        st = ready_state("2330")
        states = {"2330": st}
        signals.restore_signaled(states, gate)
        self.assertIsNone(evaluate(st, now=dtime(10, 0)))

    def test_ignores_codes_not_in_watchlist(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        gate.state["signals"] = [{"code": "9999"}]
        states = {"2330": SymbolState("2330", 100.0)}
        self.assertEqual(signals.restore_signaled(states, gate), 0)
        self.assertEqual(states["2330"].signaled, 0)


class TestScreener(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(config.SCREEN)

    def test_accepts_qualifying_stock(self):
        row = screener.passes_basic(snap(close=100.0, high=104.0, low=100.0, volume=9000),
                                    self.cfg)
        self.assertIsNotNone(row)
        self.assertEqual(row["prev_volume"], 9000)
        self.assertAlmostEqual(row["amplitude_pct"], 4.0)

    def test_price_bounds(self):
        self.assertIsNone(screener.passes_basic(
            snap(close=15.0, high=16.0, low=15.0), self.cfg))
        self.assertIsNone(screener.passes_basic(
            snap(close=500.0, high=530.0, low=500.0), self.cfg))

    def test_volume_floor(self):
        self.assertIsNone(screener.passes_basic(snap(volume=100), self.cfg))

    def test_amplitude_floor(self):
        self.assertIsNone(screener.passes_basic(
            snap(close=100.0, high=101.0, low=100.0), self.cfg))

    def test_rejects_garbage_rows(self):
        for bad in (snap(close=0), snap(volume=0), snap(high=0), snap(low=0)):
            self.assertIsNone(screener.passes_basic(bad, self.cfg))

    def test_volume_baseline_groups_by_day_and_excludes_last(self):
        ts, vol = [], []
        for day, v in [(15, 100), (16, 200), (17, 150), (18, 250), (19, 9000)]:
            for minute in (0, 1):
                ts.append(datetime(2026, 9, day, 9, minute))
                vol.append(v)
        # 每天 2 根 K → 200/400/300/500，第 5 天（被比較的那天）排除
        self.assertEqual(screener.volume_baseline(ts, vol, 4), 350.0)
        # lookback 2 天 → 只取 300 與 500
        self.assertEqual(screener.volume_baseline(ts, vol, 2), 400.0)

    def test_volume_baseline_needs_two_days(self):
        ts = [datetime(2026, 9, 19, 9, 0)]
        self.assertEqual(screener.volume_baseline(ts, [500], 5), 0.0)
        self.assertEqual(screener.volume_baseline([], [], 5), 0.0)

    def test_volume_ratio_is_same_order_of_magnitude(self):
        """量比要落在「倍數」的量級。

        原本的公式除了 1000，量比會變成四位數，排序等於亂排。
        """
        ts, vol = [], []
        for day in (15, 16, 17, 18):
            for minute in range(10):
                ts.append(datetime(2026, 9, day, 9, minute))
                vol.append(100)              # 每天 1000 張
        ts.append(datetime(2026, 9, 19, 9, 0))
        vol.append(2000)
        base = screener.volume_baseline(ts, vol, 5)
        self.assertEqual(base, 1000.0)
        self.assertAlmostEqual(6000 / base, 6.0)     # 昨量 6000 張 → 6 倍，不是 6000 倍


class TestReviewAudit(unittest.TestCase):
    @staticmethod
    def _trade(code, action="Buy", price=100.0, qty=1, status="Filled"):
        return SimpleNamespace(
            contract=SimpleNamespace(code=code),
            order=SimpleNamespace(action=action, price=price),
            status=SimpleNamespace(deal_quantity=qty, status=status, deal_price=price))

    def test_clean_day(self):
        issues = review.audit([{"code": "2330"}], [self._trade("2330")], {})
        self.assertEqual(issues, ["✅ 今日無違規紀錄。"])

    def test_flags_off_plan_trade(self):
        issues = review.audit([{"code": "2330"}], [self._trade("1234")], {})
        self.assertTrue(any("計畫外的標的" in i and "1234" in i for i in issues))

    def test_flags_trading_after_gate_closed(self):
        issues = review.audit([{"code": "2330"}], [self._trade("2330")],
                              {"closed": True, "closed_reason": "日虧上限"})
        self.assertTrue(any("最危險的一條" in i for i in issues))

    def test_flags_too_many_codes(self):
        trades = [self._trade(str(1000 + i))
                  for i in range(config.RISK["max_trades_per_day"] + 1)]
        signals_ = [{"code": str(1000 + i)}
                    for i in range(config.RISK["max_trades_per_day"] + 1)]
        issues = review.audit(signals_, trades, {})
        self.assertTrue(any("超過上限" in i for i in issues))

    def test_flags_signal_limit_breach(self):
        sigs = [{"code": f"{i}"} for i in range(config.RISK["max_signals_per_day"] + 1)]
        issues = review.audit(sigs, [], {})
        self.assertTrue(any("風控閘門沒有生效" in i for i in issues))

    def test_notes_skipped_signal(self):
        issues = review.audit([{"code": "2330"}, {"code": "2317"}],
                              [self._trade("2330")], {})
        self.assertTrue(any("有訊號但沒做" in i and "2317" in i for i in issues))

    def test_notes_oversized_signal(self):
        issues = review.audit([{"code": "2330", "oversized": True}], [], {})
        self.assertTrue(any("單筆風險超標" in i for i in issues))

    def test_deal_price_prefers_actual_fill(self):
        t = self._trade("2330", price=100.0)
        t.status.deal_price = 101.5
        self.assertAlmostEqual(review._deal_price(t), 101.5)

    def test_deal_price_falls_back_to_order_price(self):
        t = self._trade("2330", price=100.0)
        t.status = SimpleNamespace(deal_quantity=0, status="Cancelled")
        self.assertAlmostEqual(review._deal_price(t), 100.0)


class TestLoadSignals(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = config.STATE_FILE
        config.STATE_FILE = Path(self._tmp.name) / "state.json"

    def tearDown(self):
        config.STATE_FILE = self._orig
        self._tmp.cleanup()

    def test_missing_state_returns_pair(self):
        """沒有 state.json 的日子（今天沒發任何訊號）也要產得出覆盤。"""
        signals_, state = review.load_signals()
        self.assertEqual(signals_, [])
        self.assertEqual(state, {})

    def test_reads_today_state(self):
        today = datetime.now().strftime("%Y-%m-%d")
        config.STATE_FILE.write_text(json.dumps(
            {"date": today, "signals": [{"code": "2330"}], "closed": False}),
            encoding="utf-8")
        signals_, state = review.load_signals()
        self.assertEqual(len(signals_), 1)
        self.assertEqual(state["date"], today)

    def test_ignores_stale_state(self):
        config.STATE_FILE.write_text(json.dumps(
            {"date": "2000-01-01", "signals": [{"code": "2330"}]}), encoding="utf-8")
        signals_, state = review.load_signals()
        self.assertEqual(signals_, [])
        self.assertEqual(state, {})


# ── 假的 Shioaji api，形狀依官方文件 ────────────────────
class FakeContract:
    def __init__(self, code, day_trade="DayTrade.Yes"):
        self.code = code
        self.day_trade = day_trade


class FakeStocks:
    def __init__(self, tse=(), otc=()):
        self.TSE = list(tse)
        self.OTC = list(otc)
        self._all = {c.code: c for c in list(tse) + list(otc)}

    def __getitem__(self, code):
        return self._all[code]


class FakeKbars:
    def __init__(self, bars):
        # bars: [(datetime, high, low, volume)]
        self.ts = [b[0].timestamp() * 1e9 for b in bars]
        self.High = [b[1] for b in bars]
        self.Low = [b[2] for b in bars]
        self.Volume = [b[3] for b in bars]


class FakeApi:
    def __init__(self, stocks=None, snaps=None, kbars=None,
                 pnl_rows=None, pnl_raises=False, trades=None):
        self.Contracts = SimpleNamespace(Stocks=stocks or FakeStocks())
        self.stock_account = "acct"
        self._snaps = snaps or []
        self._kbars = kbars
        self._pnl_rows = pnl_rows if pnl_rows is not None else []
        self._pnl_raises = pnl_raises
        self._trades = trades or []
        self.snapshot_batches = []

    def snapshots(self, contracts):
        self.snapshot_batches.append(len(contracts))
        codes = {c.code for c in contracts}
        return [s for s in self._snaps if s.code in codes]

    def kbars(self, contract, start, end):
        if self._kbars is None:
            raise RuntimeError("no kbars")
        return self._kbars

    def list_profit_loss(self, acct, begin_date, end_date):
        if self._pnl_raises:
            raise RuntimeError("需要電子憑證")
        return [SimpleNamespace(pnl=v) for v in self._pnl_rows]

    def update_status(self, acct):
        pass

    def list_trades(self):
        return self._trades


class TestBrokerWrappers(unittest.TestCase):
    """這一層原本完全沒有測試，而它承載了所有對 Shioaji 回傳格式的假設。"""

    def test_all_stocks_merges_tse_and_otc(self):
        api = FakeApi(stocks=FakeStocks(tse=[FakeContract("2330")],
                                        otc=[FakeContract("6488")]))
        codes = [c.code for c in Broker(api=api).all_stocks()]
        self.assertEqual(sorted(codes), ["2330", "6488"])

    def test_all_stocks_tolerates_missing_exchange(self):
        stocks = FakeStocks(tse=[FakeContract("2330")])
        stocks.OTC = []
        self.assertEqual(len(Broker(api=FakeApi(stocks=stocks)).all_stocks()), 1)

    def test_day_trade_flag_parsing(self):
        f = Broker.day_trade_flag
        self.assertEqual(f(FakeContract("2330", "DayTrade.Yes")), "Yes")
        self.assertEqual(f(FakeContract("2330", "DayTrade.No")), "No")
        self.assertEqual(f(FakeContract("2330", "DayTrade.OnlyBuy")), "OnlyBuy")
        self.assertEqual(f(FakeContract("2330", "Yes")), "Yes")        # 裸字串也認
        self.assertEqual(f(FakeContract("2330", "DayTrade.Weird")), "未知")
        self.assertEqual(f(SimpleNamespace(code="2330")), "未知")

    def test_only_buy_is_tradable_for_a_long_only_system(self):
        """OnlyBuy = 只能先買後賣。v1 只做多，所以它完全可用。"""
        b = Broker(api=FakeApi())
        only_buy = FakeContract("2330", "DayTrade.OnlyBuy")
        self.assertTrue(b.is_day_tradable(only_buy, allow_short=False))
        self.assertFalse(b.is_day_tradable(only_buy, allow_short=True))

    def test_day_tradable_follows_config_by_default(self):
        b = Broker(api=FakeApi())
        original = config.SIGNAL["allow_short"]
        try:
            config.SIGNAL["allow_short"] = False
            self.assertTrue(b.is_day_tradable(FakeContract("2330", "DayTrade.OnlyBuy")))
            config.SIGNAL["allow_short"] = True
            self.assertFalse(b.is_day_tradable(FakeContract("2330", "DayTrade.OnlyBuy")))
        finally:
            config.SIGNAL["allow_short"] = original

    def test_unknown_flag_fails_closed(self):
        b = Broker(api=FakeApi())
        self.assertFalse(b.is_day_tradable(FakeContract("2330", "DayTrade.Weird")))
        self.assertFalse(b.is_day_tradable(SimpleNamespace(code="2330")))
        self.assertFalse(b.is_day_tradable(FakeContract("2330", "DayTrade.No")))

    def test_snapshots_batches_at_500(self):
        """一次最多 500 檔是官方限制；分批錯了會整批失敗。"""
        contracts = [FakeContract(str(1000 + i)) for i in range(1201)]
        api = FakeApi(snaps=[SimpleNamespace(code=c.code) for c in contracts])
        out = Broker(api=api).snapshots(contracts)
        self.assertEqual(api.snapshot_batches, [500, 500, 201])
        self.assertEqual(len(out), 1201)

    def test_snapshots_empty_input(self):
        api = FakeApi()
        self.assertEqual(Broker(api=api).snapshots([]), [])
        self.assertEqual(api.snapshot_batches, [])

    def _or_broker(self, bars):
        return Broker(api=FakeApi(stocks=FakeStocks(tse=[FakeContract("2330")]),
                                  kbars=FakeKbars(bars)))

    def test_opening_range_uses_only_the_window(self):
        d = datetime.now().date()
        bars = [
            (datetime.combine(d, dtime(8, 59)), 999.0, 998.0, 10),   # 盤前，不算
            (datetime.combine(d, dtime(9, 0)), 101.0, 99.0, 100),
            (datetime.combine(d, dtime(9, 14)), 102.0, 100.0, 100),
            (datetime.combine(d, dtime(9, 15)), 500.0, 1.0, 100),    # 區間外，不算
            (datetime.combine(d, dtime(10, 0)), 600.0, 2.0, 100),
        ]
        rng = self._or_broker(bars).opening_range("2330", "09:00:00", "09:15:00")
        self.assertEqual(rng, (102.0, 99.0))

    def test_opening_range_none_when_no_bars_in_window(self):
        d = datetime.now().date()
        bars = [(datetime.combine(d, dtime(10, 0)), 105.0, 104.0, 100)]
        self.assertIsNone(self._or_broker(bars).opening_range("2330", "09:00:00", "09:15:00"))

    def test_opening_range_none_when_kbars_raises(self):
        api = FakeApi(stocks=FakeStocks(tse=[FakeContract("2330")]), kbars=None)
        self.assertIsNone(Broker(api=api).opening_range("2330", "09:00:00", "09:15:00"))

    def test_pnl_rows_sums_and_preserves_order(self):
        b = Broker(api=FakeApi(pnl_rows=[300.0, -100.0, -250.0]))
        self.assertEqual(b.realized_pnl_rows_today(), [300.0, -100.0, -250.0])
        self.assertAlmostEqual(b.realized_pnl_today(), -50.0)

    def test_pnl_empty_is_zero_not_unknown(self):
        """沒有平倉紀錄 → 0 元（已知）；查詢失敗 → None（未知）。兩者不能混。"""
        b = Broker(api=FakeApi(pnl_rows=[]))
        self.assertEqual(b.realized_pnl_rows_today(), [])
        self.assertEqual(b.realized_pnl_today(), 0.0)

    def test_pnl_unknown_on_exception(self):
        b = Broker(api=FakeApi(pnl_raises=True))
        self.assertIsNone(b.realized_pnl_rows_today())
        self.assertIsNone(b.realized_pnl_today())

    def test_trades_today_survives_api_error(self):
        class Boom(FakeApi):
            def list_trades(self):
                raise RuntimeError("查詢失敗")

        self.assertEqual(Broker(api=Boom()).trades_today(), [])

    def test_activate_ca_skipped_in_simulation(self):
        orig = config.SIMULATION
        config.SIMULATION = True
        try:
            self.assertIsNone(Broker(api=FakeApi()).activate_ca())
        finally:
            config.SIMULATION = orig

    def test_activate_ca_warns_when_live_without_cert(self):
        orig = (config.SIMULATION, config.CA_PATH)
        config.SIMULATION, config.CA_PATH = False, ""
        try:
            b = Broker(api=FakeApi())
            with self.assertLogs("broker", level="WARNING") as cm:
                self.assertIsNone(b.activate_ca())
            self.assertIn("關閘停手", "".join(cm.output))
        finally:
            config.SIMULATION, config.CA_PATH = orig

    def test_activate_ca_raises_on_rejection(self):
        """憑證被拒要在登入時就炸開，不要等到盤中查不到損益才發現。"""
        orig = (config.SIMULATION, config.CA_PATH)
        config.SIMULATION, config.CA_PATH = False, "/tmp/x.pfx"
        try:
            api = FakeApi()
            api.activate_ca = lambda **kw: False
            with self.assertRaises(RuntimeError) as cm:
                Broker(api=api).activate_ca()
            self.assertIn("憑證", str(cm.exception))
        finally:
            config.SIMULATION, config.CA_PATH = orig

    def test_activate_ca_passes_credentials(self):
        orig = (config.SIMULATION, config.CA_PATH, config.CA_PASSWD, config.PERSON_ID)
        config.SIMULATION, config.CA_PATH = False, "/tmp/x.pfx"
        config.CA_PASSWD, config.PERSON_ID = "pw", "A123456789"
        got = {}
        try:
            api = FakeApi()
            api.activate_ca = lambda **kw: got.update(kw) or True
            self.assertTrue(Broker(api=api).activate_ca())
            self.assertEqual(got["ca_path"], "/tmp/x.pfx")
            self.assertEqual(got["ca_passwd"], "pw")
            self.assertEqual(got["person_id"], "A123456789")
        finally:
            (config.SIMULATION, config.CA_PATH,
             config.CA_PASSWD, config.PERSON_ID) = orig

    def test_ensure_session_relogins_after_20h(self):
        from datetime import timedelta
        b = Broker(api=FakeApi())
        b._login_at = datetime.now() - timedelta(hours=21)
        calls = []
        b.login = lambda: calls.append("login") or setattr(b, "_login_at", datetime.now())
        b.api.logout = lambda: calls.append("logout")
        b.ensure_session()
        self.assertEqual(calls, ["logout", "login"])

    def test_ensure_session_noop_when_fresh(self):
        b = Broker(api=FakeApi())
        b.login = lambda: self.fail("不該重新登入")
        b.ensure_session()


class TestPreflight(unittest.TestCase):
    """preflight 是上線前的守門人 —— 它自己判斷錯了比沒有它更糟。"""

    @staticmethod
    def _stocks(flags=("DayTrade.Yes",)):
        return FakeStocks(tse=[FakeContract(str(2330 + i), f)
                               for i, f in enumerate(flags)])

    @staticmethod
    def _snap(code="2330", **over):
        base = dict(close=100.0, high=104.0, low=99.0,
                    total_volume=9000, average_price=101.0)
        base.update(over)
        return SimpleNamespace(code=code, **base)

    @staticmethod
    def _bars(first_minute=0):
        d = datetime.now().date()
        return [(datetime.combine(d, dtime(9, first_minute + i)),
                 101.0 + i, 99.0 - i, 100) for i in range(3)]

    def test_config_check_passes_and_fails(self):
        self.assertEqual(preflight.check_config().status, preflight.OK)
        original = config.SIGNAL["reward_risk"]
        config.SIGNAL["reward_risk"] = -1
        try:
            r = preflight.check_config()
            self.assertEqual(r.status, preflight.FAIL)
            self.assertIn("reward_risk", r.detail)
        finally:
            config.SIGNAL["reward_risk"] = original

    def test_contracts_empty_is_fail(self):
        r = preflight.check_contracts(Broker(api=FakeApi()))
        self.assertEqual(r.status, preflight.FAIL)

    def test_contracts_counts_four_digit(self):
        stocks = FakeStocks(tse=[FakeContract("2330"), FakeContract("00632R"),
                                 FakeContract("2317")])
        r = preflight.check_contracts(Broker(api=FakeApi(stocks=stocks)))
        self.assertEqual(r.status, preflight.OK)
        self.assertIn("四碼普通股 2 檔", r.detail)

    def test_day_trade_all_unknown_is_fail(self):
        """旗標認不出來 → screener 會篩出 0 檔，而且不會報錯。"""
        api = FakeApi(stocks=self._stocks(("DayTrade.Weird", "DayTrade.Weird")))
        r = preflight.check_day_trade_flag(Broker(api=api))
        self.assertEqual(r.status, preflight.FAIL)
        self.assertIn("篩出 0 檔", r.detail)

    def test_day_trade_none_tradable_is_fail(self):
        api = FakeApi(stocks=self._stocks(("DayTrade.No", "DayTrade.No")))
        r = preflight.check_day_trade_flag(Broker(api=api))
        self.assertEqual(r.status, preflight.FAIL)

    def test_day_trade_reports_distribution(self):
        api = FakeApi(stocks=self._stocks(("DayTrade.Yes", "DayTrade.No",
                                           "DayTrade.OnlyBuy")))
        r = preflight.check_day_trade_flag(Broker(api=api))
        self.assertEqual(r.status, preflight.OK)
        for part in ("Yes=1", "No=1", "OnlyBuy=1"):
            self.assertIn(part, r.detail)

    def test_snapshots_empty_is_fail(self):
        api = FakeApi(stocks=self._stocks(), snaps=[])
        self.assertEqual(preflight.check_snapshots(Broker(api=api)).status,
                         preflight.FAIL)

    def test_snapshots_missing_field_is_fail(self):
        snap = SimpleNamespace(code="2330", close=100.0, high=104.0, low=99.0,
                               total_volume=9000)          # 少了 average_price
        api = FakeApi(stocks=self._stocks(), snaps=[snap])
        r = preflight.check_snapshots(Broker(api=api))
        self.assertEqual(r.status, preflight.FAIL)
        self.assertIn("average_price", r.detail)

    def test_snapshots_zero_field_is_warning(self):
        api = FakeApi(stocks=self._stocks(), snaps=[self._snap(total_volume=0)])
        r = preflight.check_snapshots(Broker(api=api))
        self.assertEqual(r.status, preflight.WARN)
        self.assertIn("total_volume", r.detail)

    def test_snapshots_healthy_is_ok(self):
        api = FakeApi(stocks=self._stocks(), snaps=[self._snap()])
        self.assertEqual(preflight.check_snapshots(Broker(api=api)).status,
                         preflight.OK)

    def test_kbars_missing_fields_is_fail(self):
        empty = FakeKbars([])
        api = FakeApi(stocks=self._stocks(), kbars=empty)
        r = preflight.check_kbars(Broker(api=api))
        self.assertEqual(r.status, preflight.FAIL)

    def test_kbars_confirms_ts_is_bar_start(self):
        api = FakeApi(stocks=self._stocks(), kbars=FakeKbars(self._bars(0)))
        r = preflight.check_kbars(Broker(api=api))
        self.assertEqual(r.status, preflight.OK)
        self.assertIn("與 opening_range() 的假設一致", r.detail)

    def test_kbars_flags_unexpected_first_bar(self):
        """第一根不是 09:00 → ts 語意可能是終點，必須提醒。"""
        api = FakeApi(stocks=self._stocks(), kbars=FakeKbars(self._bars(1)))
        r = preflight.check_kbars(Broker(api=api))
        self.assertIn("請確認 ts 是起點還是終點", r.detail)

    def test_kbars_unavailable_is_warning_not_failure(self):
        api = FakeApi(stocks=self._stocks(), kbars=None)
        self.assertEqual(preflight.check_kbars(Broker(api=api)).status,
                         preflight.WARN)

    def test_pnl_available_is_ok(self):
        api = FakeApi(stocks=self._stocks(), pnl_rows=[300.0, -100.0])
        r = preflight.check_pnl(Broker(api=api))
        self.assertEqual(r.status, preflight.OK)
        self.assertIn("200", r.detail)

    def test_pnl_unknown_is_warning_in_simulation(self):
        original = config.SIMULATION
        config.SIMULATION = True
        try:
            api = FakeApi(stocks=self._stocks(), pnl_raises=True)
            r = preflight.check_pnl(Broker(api=api))
            self.assertEqual(r.status, preflight.WARN)
        finally:
            config.SIMULATION = original

    def test_pnl_unknown_is_failure_when_live(self):
        """真錢模式查不到損益 = 沒有煞車，這是最該擋下來的一項。"""
        original = config.SIMULATION
        config.SIMULATION = False
        try:
            api = FakeApi(stocks=self._stocks(), pnl_raises=True)
            r = preflight.check_pnl(Broker(api=api))
            self.assertEqual(r.status, preflight.FAIL)
            self.assertIn("關閘停手", r.detail)
        finally:
            config.SIMULATION = original

    def test_ca_not_needed_in_simulation(self):
        orig = config.SIMULATION
        config.SIMULATION = True
        try:
            self.assertEqual(preflight.check_ca(None).status, preflight.OK)
        finally:
            config.SIMULATION = orig

    def test_ca_missing_path_is_failure_when_live(self):
        orig = (config.SIMULATION, config.CA_PATH)
        config.SIMULATION, config.CA_PATH = False, ""
        try:
            r = preflight.check_ca(None)
            self.assertEqual(r.status, preflight.FAIL)
            self.assertIn("關閘停手", r.detail)
        finally:
            config.SIMULATION, config.CA_PATH = orig

    def test_ca_nonexistent_file_is_failure(self):
        orig = (config.SIMULATION, config.CA_PATH)
        config.SIMULATION, config.CA_PATH = False, "/nonexistent/Sinopac.pfx"
        try:
            self.assertEqual(preflight.check_ca(None).status, preflight.FAIL)
        finally:
            config.SIMULATION, config.CA_PATH = orig

    def test_ca_present_is_ok(self):
        orig = (config.SIMULATION, config.CA_PATH, config.PERSON_ID)
        with tempfile.NamedTemporaryFile(suffix=".pfx") as f:
            config.SIMULATION, config.CA_PATH = False, f.name
            config.PERSON_ID = "A123456789"
            try:
                self.assertEqual(preflight.check_ca(None).status, preflight.OK)
            finally:
                config.SIMULATION, config.CA_PATH, config.PERSON_ID = orig

    def test_trades_empty_is_warning(self):
        api = FakeApi(stocks=self._stocks())
        self.assertEqual(preflight.check_trades(Broker(api=api)).status,
                         preflight.WARN)

    def test_trades_reports_fields(self):
        trade = SimpleNamespace(
            contract=SimpleNamespace(code="2330"),
            order=SimpleNamespace(action="Buy", price=100.0),
            status=SimpleNamespace(deal_quantity=1, status="Filled", deal_price=101.5))
        api = FakeApi(stocks=self._stocks(), trades=[trade])
        r = preflight.check_trades(Broker(api=api))
        self.assertEqual(r.status, preflight.OK)
        self.assertIn("101.50", r.detail)

    def test_telegram_unconfigured_is_warning(self):
        orig = (config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
        config.TELEGRAM_BOT_TOKEN = config.TELEGRAM_CHAT_ID = ""
        try:
            self.assertEqual(preflight.check_telegram().status, preflight.WARN)
        finally:
            config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID = orig

    def test_telegram_configured_without_requests_is_fail(self):
        orig = (config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, signals.requests)
        config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID = "tok", "chat"
        signals.requests = None
        try:
            self.assertEqual(preflight.check_telegram().status, preflight.FAIL)
        finally:
            (config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID,
             signals.requests) = orig

    def test_telegram_sends_test_message(self):
        orig = (config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, signals.requests)
        sent = []

        class FakeRequests:
            @staticmethod
            def post(url, json, timeout):
                sent.append(json["text"])

        config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID = "tok", "chat"
        signals.requests = FakeRequests
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                r = preflight.check_telegram()
            self.assertEqual(r.status, preflight.OK)
            self.assertTrue(sent and "preflight" in sent[0])
        finally:
            (config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID,
             signals.requests) = orig

    def test_every_check_is_listed(self):
        """新增檢查卻忘了掛進 CHECKS，體檢就會安靜地少做一項。"""
        defined = {v for k, v in vars(preflight).items()
                   if k.startswith("check_") and callable(v)}
        self.assertEqual(defined, set(preflight.CHECKS))


class TestBarTime(unittest.TestCase):
    def test_handles_datetime_and_epochs(self):
        from broker import _bar_time
        expect = datetime(2026, 9, 20, 9, 5)
        self.assertEqual(_bar_time(expect), expect)
        sec = expect.timestamp()
        self.assertEqual(_bar_time(sec), expect)
        self.assertEqual(_bar_time(sec * 1000), expect)          # 毫秒
        self.assertEqual(_bar_time(int(sec * 1_000_000_000)), expect)  # 奈秒
        self.assertIsNone(_bar_time("abc"))
        self.assertIsNone(_bar_time(None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
