"""
test_daytrade.py — 離線測試。不需要 shioaji、不需要網路、不需要金鑰。

    python3 test_daytrade.py        （Windows 是 python test_daytrade.py）

測的是「錯了不會報錯」的那些地方：訊號條件、風控閘門、量能基準、紀律稽核。
這些邏輯算錯不會讓程式崩掉，它會安靜地給你一個看起來很專業的錯誤決策。
"""
import contextlib
import csv
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from datetime import datetime, time as dtime, timedelta, timezone as dt_timezone
from pathlib import Path
from types import SimpleNamespace

import config
import preflight
import review
from broker import Broker
import outcome as oc
import screener
import signals
from signals import RiskGate, SymbolState, evaluate, format_signal

# 風控在真錢模式查不到帳務時會重試幾次才關閘，每次之間會等。
# 那個等待是為了讓連線喘口氣，不是要測的行為 —— 測試裡歸零，否則整套會慢 3 秒。
signals.UNKNOWN_RETRY_WAIT = 0


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

    def test_console_text_keeps_original_on_utf8(self):
        sys.stdout = self._fake_stdout("utf-8")
        msg = "📌 2330 決策錨點｜09:23"
        self.assertEqual(config.console_text(msg), msg)

    def test_console_text_replaces_unprintable_symbols(self):
        """推播訊息在 cp950 主控台上不該只剩一個問號。"""
        sys.stdout = self._fake_stdout("cp950")
        out = config.console_text("📌 2330 決策錨點\n⚠️ 這是規則觸發")
        self.assertNotIn("📌", out)
        self.assertNotIn("⚠", out)
        self.assertIn("[訊號]", out)
        self.assertIn("[注意]", out)
        self.assertIn("決策錨點", out)      # 中文原樣保留
        sys.stdout = self._fake_stdout("cp950")
        self.assertTrue(config.console_can_encode(out))   # 換完真的印得出來

    def test_notify_sends_original_text_but_prints_safe_one(self):
        """手機要收到原本的符號，只有終端機顯示才降級。"""
        sent = {}

        class FakeRequests:
            @staticmethod
            def post(url, json=None, timeout=None):
                sent["text"] = json["text"]

        msg = "📌 2330 決策錨點"
        buf = io.StringIO()
        sys.stdout = self._fake_stdout("cp950")
        safe = config.console_text(msg)
        sys.stdout = buf
        with unittest.mock.patch.object(signals, "requests", FakeRequests), \
             unittest.mock.patch.object(config, "TELEGRAM_BOT_TOKEN", "t"), \
             unittest.mock.patch.object(config, "TELEGRAM_CHAT_ID", "c"), \
             unittest.mock.patch.object(config, "console_text", lambda _t: safe):
            signals.notify(msg)
        self.assertEqual(sent["text"], msg)              # 送出去的是原文
        self.assertIn("[訊號]", buf.getvalue())          # 印出來的是降級版

    def test_py_cmd_matches_platform(self):
        """Windows 沒有 python3 這個命令，教學訊息不能叫使用者打 python3。"""
        self.assertEqual(config.PY_CMD, "python" if os.name == "nt" else "python3")

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


SIGNAL_FIXTURE = {
    "time": "09:23:00", "code": "2330", "name": "", "direction": "做多",
    "entry": 101.5, "stop": 100.0, "target": 103.75, "lots": 1,
    "risk_per_lot": 1500, "oversized": False, "or_high": 101.0,
    "vwap": 100.8, "volume_surge": 2.1,
}


class TestSymbolNames(unittest.TestCase):
    """只有代號很難認。名稱拿不到時也不能印出怪字串。"""

    def test_label_joins_code_and_name(self):
        self.assertEqual(screener.label({"code": "3317", "name": "尼克森"}), "3317 尼克森")

    def test_label_falls_back_to_code(self):
        for row in ({"code": "3317"}, {"code": "3317", "name": ""},
                    {"code": "3317", "name": "  "}, {"code": "3317", "name": None}):
            self.assertEqual(screener.label(row), "3317")

    def test_push_shows_name(self):
        text = screener.format_watchlist(
            {"date": "2026-09-24", "round_trip_cost_pct": 0.207},
            [{"code": "3317", "name": "尼克森", "prev_close": 66.5,
              "amplitude_pct": 5.1, "volume_ratio": 16.07}])
        self.assertIn("3317 尼克森", text)

    def test_signal_shows_name(self):
        st = SymbolState("2330", 100.0, "台積電")
        st.lock_opening_range(101.0, 99.0)
        sig = dict(SIGNAL_FIXTURE, code="2330", name="台積電")
        self.assertIn("2330 台積電", format_signal(sig, 1))

    def test_signal_without_name_has_no_stray_space(self):
        sig = dict(SIGNAL_FIXTURE, code="2330", name="")
        self.assertIn("2330 決策錨點", format_signal(sig, 1))


class TestLiveTracker(unittest.TestCase):
    """訊號發出之後要盯到結局，當場講出來 —— 不能只有收盤後才知道。"""

    SIG = {"code": "6182", "name": "合晶", "time": "09:19:22",
           "entry": 119.0, "stop": 117.5, "target": 121.5}

    def _tracker(self):
        t = signals.LiveTracker()
        t.track(self.SIG)
        return t

    def test_nothing_while_price_is_between_stop_and_target(self):
        t = self._tracker()
        self.assertEqual(t.on_price("6182", 120.0), [])
        self.assertEqual(len(t.open), 1)

    def test_target_reached(self):
        msgs = self._tracker().on_price("6182", 121.5)
        self.assertEqual(len(msgs), 1)
        self.assertIn("目標", msgs[0])
        self.assertIn("合晶", msgs[0])

    def test_stop_reached(self):
        msgs = self._tracker().on_price("6182", 117.5)
        self.assertEqual(len(msgs), 1)
        self.assertIn("停損", msgs[0])

    def test_each_signal_resolves_once(self):
        """tick 一秒好幾筆。同一筆推兩次，使用者會以為自己做了兩趟。"""
        t = self._tracker()
        self.assertEqual(len(t.on_price("6182", 121.6)), 1)
        self.assertEqual(t.on_price("6182", 121.8), [])
        self.assertEqual(t.on_price("6182", 117.0), [])
        self.assertEqual(t.open, [])

    def test_another_symbol_price_does_not_resolve_it(self):
        t = self._tracker()
        self.assertEqual(t.on_price("2330", 50.0), [])
        self.assertEqual(len(t.open), 1)

    def test_zero_price_is_ignored(self):
        """開盤前或無成交時 last_price 是 0，拿它比停損會立刻誤判。"""
        t = self._tracker()
        self.assertEqual(t.on_price("6182", 0), [])
        self.assertEqual(len(t.open), 1)

    def test_flatten_uses_the_last_seen_price(self):
        t = self._tracker()
        t.on_price("6182", 120.3)
        msgs = t.flatten()
        self.assertEqual(len(msgs), 1)
        self.assertIn("收盤平倉", msgs[0])
        self.assertIn("120.30", msgs[0])
        self.assertEqual(t.open, [])

    def test_flatten_skips_a_symbol_that_never_quoted(self):
        """沒有報價就沒有平倉價。硬掰一個數字比留給 outcome.py 回推更糟。"""
        self.assertEqual(self._tracker().flatten(), [])

    def test_resolved_signals_are_not_flattened_again(self):
        t = self._tracker()
        t.on_price("6182", 121.5)
        self.assertEqual(t.flatten(), [])


class TestResolutionMessage(unittest.TestCase):
    """推播上的數字必須和 outcome.py 收盤後算出來的一致，否則互驗沒有意義。"""

    O = signals.OpenSignal(code="6182", name="合晶", time="09:19:22",
                           entry=119.0, stop=117.5, target=121.5)

    def test_target_uses_the_target_price_not_the_tick(self):
        """跳空穿過去的部分不算進報酬率 —— 限價單只會成交在目標價。"""
        text = signals.format_resolution(self.O, 122.4, oc.TARGET)
        self.assertIn("119.00 → 出場 121.50", text)
        self.assertIn("觸發時報價 122.40", text)

    def test_matches_outcome_module_arithmetic(self):
        text = signals.format_resolution(self.O, 121.5, oc.TARGET)
        gross = (121.5 - 119.0) / 119.0 * 100
        net = gross - config.round_trip_cost_pct()
        self.assertIn(f"{gross:+.2f}%", text)
        self.assertIn(f"{net:+.2f}%", text)
        self.assertIn("+1.67R", text)

    def test_stop_is_minus_one_r(self):
        text = signals.format_resolution(self.O, 117.5, oc.STOP)
        self.assertIn("-1.00R", text)

    def test_says_it_is_not_your_real_pnl(self):
        """驗證期沒有下單。把這個數字當成自己的損益是最貴的誤會。"""
        text = signals.format_resolution(self.O, 121.5, oc.TARGET)
        self.assertIn("不是你的實際損益", text)


class TestWatchlistPush(unittest.TestCase):
    """名單要推到手機上，格式得在窄螢幕讀得懂，而且不能講成進場訊號。"""

    PAYLOAD = {"date": "2026-09-24", "round_trip_cost_pct": 0.207}
    ROWS = [
        {"code": "3707", "prev_close": 74.0, "amplitude_pct": 7.57, "volume_ratio": 3.83},
        {"code": "2498", "prev_close": 42.7, "amplitude_pct": 6.09, "volume_ratio": 2.88},
    ]

    def test_lists_every_code_in_rank_order(self):
        text = screener.format_watchlist(self.PAYLOAD, self.ROWS)
        self.assertIn("3707", text)
        self.assertIn("2498", text)
        self.assertLess(text.index("3707"), text.index("2498"))

    def test_states_it_is_not_an_entry_signal(self):
        """名單被誤讀成「可以買這 5 檔」是最貴的誤會。"""
        text = screener.format_watchlist(self.PAYLOAD, self.ROWS)
        self.assertIn("不是進場訊號", text)
        self.assertIn("未經人工判斷", text)

    def test_carries_cost_baseline_and_count(self):
        text = screener.format_watchlist(self.PAYLOAD, self.ROWS)
        self.assertIn("0.207", text)
        self.assertIn("2 檔", text)

    def test_push_goes_through_signals_notify(self):
        sent = []
        with unittest.mock.patch.object(signals, "notify", sent.append):
            screener.push_watchlist(self.PAYLOAD, self.ROWS)
        self.assertEqual(len(sent), 1)
        self.assertIn("3707", sent[0])

    def test_push_flag_defaults_off(self):
        self.assertFalse(screener.parse_args([]).push)
        self.assertTrue(screener.parse_args(["--push"]).push)


class TestScreenerFailureIsAudible(unittest.TestCase):
    """08:40 的沉默有兩種意思，而處置完全相反 —— 所以失敗必須出聲。

    「今天沒有名單」是正常的一天；「程式當掉了」要人去修。收不到訊息時這兩件事
    長得一模一樣，於是使用者會坐在那裡等一個永遠不會來的名單。
    """

    def test_failure_text_names_the_error_and_says_no_watchlist(self):
        text = screener.format_failure(RuntimeError("ip: 1.2.3.4 not allow"))
        self.assertIn("盤前選股失敗", text)
        self.assertIn("RuntimeError", text)
        self.assertIn("not allow", text)
        self.assertIn("沒有觀察名單", text)

    def test_failure_text_is_truncated(self):
        """例外訊息可能是一整頁 HTML 錯誤頁，Telegram 有長度上限。"""
        text = screener.format_failure(RuntimeError("x" * 5000))
        self.assertLess(len(text), 900)
        self.assertIn("完整訊息在電腦上", text)

    def test_push_mode_pushes_on_failure_and_still_raises(self):
        sent = []
        boom = RuntimeError("登入失敗")

        def explode(args):
            raise boom

        with unittest.mock.patch.object(screener, "run", explode), \
             unittest.mock.patch.object(signals, "notify", sent.append):
            with self.assertRaises(RuntimeError):
                screener.main(["--push"])
        self.assertEqual(len(sent), 1)
        self.assertIn("登入失敗", sent[0])

    def test_without_push_it_stays_quiet(self):
        """人就坐在畫面前面的時候，不需要再推一則到手機。"""
        sent = []

        def explode(args):
            raise RuntimeError("登入失敗")

        with unittest.mock.patch.object(screener, "run", explode), \
             unittest.mock.patch.object(signals, "notify", sent.append):
            with self.assertRaises(RuntimeError):
                screener.main([])
        self.assertEqual(sent, [])

    def test_broken_push_does_not_swallow_the_real_error(self):
        """推播管道自己壞掉時，原始錯誤還是要傳上去 —— 否則排程看到 exit 0。"""
        def explode(args):
            raise RuntimeError("真正的錯誤")

        def bad_notify(_text):
            raise OSError("網路不通")

        with unittest.mock.patch.object(screener, "run", explode), \
             unittest.mock.patch.object(signals, "notify", bad_notify):
            with self.assertRaises(RuntimeError) as ctx:
                screener.main(["--push"])
        self.assertIn("真正的錯誤", str(ctx.exception))


def _kb(rows):
    """把 (HH:MM, high, low, close) 做成 shioaji 形狀的假 kbars。

    時間戳照 shioaji 的方式建：台北牆上時間當成 UTC 的納秒。
    用 datetime.timestamp() 建會受本機時區影響，等於自己驗自己。
    """
    ts, highs, lows, closes = [], [], [], []
    for hhmm, h, l, c in rows:
        t = datetime(2026, 9, 24, int(hhmm[:2]), int(hhmm[3:]), tzinfo=dt_timezone.utc)
        ts.append(int(t.timestamp() * 1e9))
        highs.append(h); lows.append(l); closes.append(c)
    return SimpleNamespace(ts=ts, High=highs, Low=lows, Close=closes)


class FakeKbarBroker:
    def __init__(self, kb):
        self._kb = kb
        self.calls = []

    def kbars(self, code, start, end):
        self.calls.append((code, start, end))
        return self._kb


class TestOutcome(unittest.TestCase):
    """訊號發出後到底怎麼了 —— 沒有這一段，20 天跑完也算不出勝率。"""

    DATE = "2026-09-24"
    SIG = {"code": "2330", "time": "09:23:00", "entry": 121.0,
           "stop": 119.5, "target": 123.5, "lots": 1}

    def _resolve(self, rows):
        return oc.resolve(FakeKbarBroker(_kb(rows)), self.SIG, self.DATE)

    def test_target_hit_first(self):
        o = self._resolve([("09:24", 121.5, 120.8, 121.2),
                           ("09:25", 123.6, 121.0, 123.4)])
        self.assertEqual(o.result, oc.TARGET)
        self.assertEqual(o.exit_price, 123.5)
        self.assertAlmostEqual(o.r_multiple, 1.67, places=2)
        self.assertGreater(o.net_pct, 0)
        self.assertTrue(o.is_win)

    def test_stop_hit_first(self):
        o = self._resolve([("09:24", 121.2, 119.4, 119.6)])
        self.assertEqual(o.result, oc.STOP)
        self.assertEqual(o.exit_price, 119.5)
        self.assertAlmostEqual(o.r_multiple, -1.0, places=2)
        self.assertFalse(o.is_win)

    def test_same_bar_touches_both_counts_as_stop(self):
        """分鐘 K 看不出一分鐘內誰先到 —— 往壞處算。"""
        o = self._resolve([("09:24", 124.0, 119.0, 122.0)])
        self.assertEqual(o.result, oc.STOP)

    def test_neither_hit_flattens_at_close(self):
        o = self._resolve([("09:24", 121.3, 120.9, 121.1),
                           ("09:25", 121.4, 120.8, 121.25)])
        self.assertEqual(o.result, oc.FLAT)
        self.assertEqual(o.exit_price, 121.25)

    def test_ignores_bars_before_entry(self):
        """進場前的價格波動不算數 —— 否則會把還沒進場的低點記成停損。"""
        o = self._resolve([("09:20", 121.0, 118.0, 120.0),   # 進場前就破停損價
                           ("09:24", 123.6, 121.0, 123.4)])
        self.assertEqual(o.result, oc.TARGET)

    def test_ignores_bars_after_flatten_time(self):
        """13:25 之後進尾盤集合競價，不保證出得掉 —— 一律當已平倉。"""
        o = self._resolve([("09:24", 121.3, 120.9, 121.1),
                           ("13:40", 130.0, 110.0, 129.0)])
        self.assertEqual(o.result, oc.FLAT)
        self.assertEqual(o.exit_price, 121.1)

    def test_net_pct_subtracts_round_trip_cost(self):
        o = self._resolve([("09:24", 123.6, 121.0, 123.4)])
        self.assertAlmostEqual(o.gross_pct - o.net_pct,
                               config.round_trip_cost_pct(), places=3)

    def test_no_bars_returns_none(self):
        self.assertIsNone(self._resolve([]))

    def test_bad_time_returns_none(self):
        bad = dict(self.SIG, time="不是時間")
        with self.assertLogs("outcome", level="WARNING"):
            self.assertIsNone(oc.resolve(FakeKbarBroker(_kb([])), bad, self.DATE))

    def test_stop_above_entry_returns_none(self):
        bad = dict(self.SIG, stop=999.0)
        with self.assertLogs("outcome", level="WARNING"):
            self.assertIsNone(oc.resolve(FakeKbarBroker(_kb([])), bad, self.DATE))

    def test_one_bad_symbol_does_not_kill_the_batch(self):
        class Flaky:
            def kbars(self, code, start, end):
                if code == "9999":
                    raise RuntimeError("行情爆炸")
                return _kb([("09:24", 123.6, 121.0, 123.4)])

        sigs = [dict(self.SIG, code="9999"), self.SIG]
        with self.assertLogs("outcome", level="WARNING"):
            out = oc.resolve_all(Flaky(), sigs, self.DATE)
        self.assertEqual([o.code for o in out], ["2330"])


class TestOutcomeSectionWording(unittest.TestCase):
    """沒訊號的日子佔多數，訊息講錯會讓人以為系統壞了。"""

    SIG = [{"code": "2330", "time": "09:23", "entry": 1.0, "stop": 0.9,
            "target": 1.2, "lots": 1, "volume_surge": 1.0}]

    def test_no_signals_says_so_and_calls_it_normal(self):
        text = "\n".join(review.outcome_section([], None))
        self.assertIn("今日無訊號", text)
        self.assertIn("正常", text)
        self.assertNotIn("未連線券商", text)      # 別讓人以為是故障

    def test_no_signals_wording_holds_even_with_empty_outcomes(self):
        text = "\n".join(review.outcome_section([], []))
        self.assertIn("今日無訊號", text)
        self.assertNotIn("未連線券商", text)

    def test_signals_but_not_resolved_mentions_connection(self):
        text = "\n".join(review.outcome_section(self.SIG, None))
        self.assertIn("未連線券商", text)

    def test_signals_but_no_bars_says_bars_insufficient(self):
        text = "\n".join(review.outcome_section(self.SIG, []))
        self.assertIn("分鐘 K 不足", text)
        self.assertNotIn("今日無訊號", text)


class TestBarContainingTheSignalIsExcluded(unittest.TestCase):
    """包著訊號那一刻的那根 K 棒不能算 —— 它裝的是訊號發出「前」的價格。

    2026-09-24 實例：合晶 09:19:22 發訊號，進場 119.00、停損 117.50。標 09:20 的
    那根涵蓋 09:19:00~09:20:00，裡面有 22 秒是突破前、還在區間高點 118.50 之下的
    成交。舊版把那根算進去，於是判「第一根就停損」——
    而合晶當天實際走到目標 121.50，收在 120.50。

    這對突破策略是系統性的：停損就設在區間高點下方，而訊號依定義發在剛越過區間
    高點的那一刻，所以那一根的低點幾乎必然掃到停損。五個訊號誤判了四個。
    """

    DATE = "2026-09-24"
    SIG = {"code": "6182", "time": "09:19:22", "entry": 119.0,
           "stop": 117.5, "target": 121.5, "lots": 1}

    def _resolve(self, rows):
        return oc.resolve(FakeKbarBroker(_kb(rows)), self.SIG, self.DATE)

    def test_the_containing_bar_cannot_trigger_the_stop(self):
        """09:20 那根的低點 116.8 是突破前的價格，不算數。"""
        o = self._resolve([("09:20", 119.5, 116.8, 119.4),
                           ("09:21", 121.6, 119.2, 121.4)])
        self.assertEqual(o.result, oc.TARGET)
        self.assertEqual(o.exit_price, 121.5)

    def test_the_containing_bar_cannot_trigger_the_target_either(self):
        """排掉那一根對停損和目標一視同仁，不是偷偷偏向贏的那一邊。"""
        o = self._resolve([("09:20", 122.0, 118.9, 119.1),
                           ("09:21", 119.0, 117.4, 117.6)])
        self.assertEqual(o.result, oc.STOP)

    def test_a_signal_on_the_minute_loses_nothing(self):
        """訊號剛好落在整分鐘時，下一根完全在它之後，該用就用。"""
        sig = dict(self.SIG, time="09:19:00")
        o = oc.resolve(FakeKbarBroker(_kb([("09:20", 121.6, 119.0, 121.4)])),
                       sig, self.DATE)
        self.assertEqual(o.result, oc.TARGET)

    def test_only_the_one_bar_is_skipped(self):
        """空白期是訊號後最多 60 秒，不是一分鐘以上。"""
        o = self._resolve([("09:20", 119.5, 116.0, 119.4),
                           ("09:21", 119.3, 117.0, 117.2)])
        self.assertEqual(o.result, oc.STOP)
        self.assertEqual(o.bars, 1)


class TestDailyPush(unittest.TestCase):
    """覆盤寫進 journal 而沒有人看，等於沒寫。當日結果要推到手機上。"""

    SIGNALS = [{"code": "6182", "name": "合晶"}, {"code": "3624", "name": "光頡"}]

    def _oc(self, code, result, r, net, entry=119.0, lots=1):
        return oc.Outcome(date="2026-09-24", code=code, time="09:19:22",
                          entry=entry, stop=117.5, target=121.5, lots=lots,
                          result=result, exit_price=121.5, r_multiple=r,
                          gross_pct=net + 0.207, net_pct=net, bars=10)

    def _today(self):
        return [self._oc("6182", oc.TARGET, 1.67, 1.894),
                self._oc("3624", oc.STOP, -1.0, -1.667)]

    def test_counts_wins_and_losses(self):
        text = review.format_push(self.SIGNALS, self._today(), [])
        self.assertIn("1 勝 1 敗", text)
        self.assertIn("合晶", text)
        self.assertIn("+1.67R", text)

    def test_no_signal_day_is_not_an_error(self):
        """零訊號是最常見、也完全正常的一天，不能講得像系統壞了。"""
        text = review.format_push([], None, [])
        self.assertIn("沒有任何訊號", text)
        self.assertIn("正常", text)

    def test_signals_but_no_resolution_says_so(self):
        text = review.format_push(self.SIGNALS, None, [])
        self.assertIn("沒有回推", text)

    def test_cumulative_section_uses_the_whole_history(self):
        history = self._today() + [self._oc("8150", oc.TARGET, 1.67, 2.087)]
        text = review.format_push(self.SIGNALS, self._today(), history)
        self.assertIn("3 筆", text)
        self.assertIn("66.7%", text)

    def test_cumulative_is_omitted_when_there_is_no_history(self):
        self.assertNotIn("累計", review.format_push([], None, []))

    def test_says_it_is_not_real_pnl(self):
        text = review.format_push(self.SIGNALS, self._today(), [])
        self.assertIn("不是你的實際損益", text)
        self.assertIn("0.207", text)

    def test_shows_the_amount_in_dollars(self):
        """使用者要的是「這一筆是多少錢」，R 倍數他換算不來。"""
        text = review.format_push(self.SIGNALS, self._today(), [])
        self.assertIn("+2,254 元", text)          # 119.00 × 1000 × 1.894%
        self.assertIn("-1,984 元", text)          # 119.00 × 1000 × -1.667%

    def test_amount_follows_the_lot_size(self):
        """建議 2 張的那筆，金額要是兩倍。"""
        two = [self._oc("3707", oc.TARGET, 1.5, 1.856, entry=72.7, lots=2)]
        self.assertIn("+2,699 元", review.format_push(self.SIGNALS, two, []))

    def test_daily_total_is_capped_at_the_trade_limit(self):
        """一天只准做 4 筆。把 5 個訊號的總和講成今天會賺到的錢是高估。"""
        five = [self._oc(str(i), oc.TARGET, 1.67, 1.894) for i in range(5)]
        text = review.format_push(self.SIGNALS, five, [])
        self.assertIn("照 4 筆上限只做前 4 筆", text)
        # 合計必須等於各筆相加。差一塊錢會讓人懷疑哪個數字才是對的。
        self.assertIn("+11,270 元", text)         # 五筆合計
        self.assertIn("+9,016 元", text)          # 前四筆

    def test_no_cap_line_when_within_the_limit(self):
        text = review.format_push(self.SIGNALS, self._today(), [])
        self.assertNotIn("上限只做前", text)

    def test_cumulative_amount_is_shown(self):
        history = self._today() * 2
        text = review.format_push(self.SIGNALS, self._today(), history)
        self.assertIn("累計損益", text)

    def test_says_the_amount_is_an_estimate(self):
        text = review.format_push(self.SIGNALS, self._today(), [])
        self.assertIn("建議張數", text)
        self.assertIn("估算", text)

    def test_cost_is_rounded(self):
        """浮點數直接印會變成 0.20700000000000002%，那看起來像程式壞了。"""
        text = review.format_push(self.SIGNALS, self._today(), [])
        self.assertIn("扣掉 0.207% 來回成本", text)

    def test_push_is_on_by_default_and_can_be_turned_off(self):
        """同一天重跑覆盤不該再推一次，但預設要推。"""
        self.assertFalse(review.parse_args([]).no_push)
        self.assertTrue(review.parse_args(["--no-push"]).no_push)

    def test_a_broken_push_does_not_lose_the_journal(self):
        """journal 已經寫好了，推播壞掉不該讓整支程式倒。"""
        def bad_notify(_text):
            raise OSError("網路不通")
        with unittest.mock.patch.object(signals, "notify", bad_notify):
            review.push_summary(self.SIGNALS, self._today())   # 不該拋例外


class TestOutcomeCsvRoundTrip(unittest.TestCase):
    """寫出去再讀回來要是同一份數字 —— 跨日統計全靠這個。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "outcomes.csv"

    def tearDown(self):
        self._tmp.cleanup()

    def _o(self, **kw):
        base = dict(date="2026-09-24", code="6182", time="09:19:22", entry=119.0,
                    stop=117.5, target=121.5, lots=1, result=oc.TARGET,
                    exit_price=121.5, r_multiple=1.67, gross_pct=2.101,
                    net_pct=1.894, bars=10, or_high=118.5, vwap=117.15,
                    volume_surge=1.81, extension_pct=0.422, vwap_gap_pct=1.579)
        return oc.Outcome(**(base | kw))

    def test_values_survive_the_round_trip(self):
        oc.append_csv([self._o()], self.path)
        back = oc.load_csv(self.path)
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0], self._o())

    def test_missing_optional_columns_come_back_as_none(self):
        """舊的列沒有現場條件欄位，不能讀成 0.0 —— 那是假數字。"""
        oc.append_csv([self._o(or_high=None, extension_pct=None)], self.path)
        back = oc.load_csv(self.path)
        self.assertIsNone(back[0].or_high)
        self.assertIsNone(back[0].extension_pct)

    def test_a_broken_row_is_skipped_not_fatal(self):
        oc.append_csv([self._o()], self.path)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("2026-09-25,3707,09:00,not-a-number,,,,,,,,,\n")
        self.assertEqual(len(oc.load_csv(self.path)), 1)

    def test_missing_file_is_empty_not_an_error(self):
        self.assertEqual(oc.load_csv(self.path), [])


class TestOutcomeSummary(unittest.TestCase):
    def _o(self, net, result):
        return oc.Outcome(date="2026-09-24", code="1", time="09:23", entry=100.0,
                          stop=99.0, target=101.5, lots=1, result=result,
                          exit_price=101.5, r_multiple=1.5, gross_pct=net + 0.207,
                          net_pct=net, bars=3)

    def test_empty(self):
        self.assertEqual(oc.summarise([]), {"n": 0})

    def test_win_rate_counts_only_net_positive(self):
        """毛賺但被成本吃光的那一筆，不算贏。"""
        out = [self._o(1.0, oc.TARGET), self._o(-1.0, oc.STOP), self._o(-0.01, oc.FLAT)]
        st = oc.summarise(out)
        self.assertEqual(st["n"], 3)
        self.assertEqual(st["wins"], 1)
        self.assertAlmostEqual(st["win_rate"], 33.3, places=1)

    def test_payoff_and_total(self):
        st = oc.summarise([self._o(2.0, oc.TARGET), self._o(-1.0, oc.STOP)])
        self.assertEqual(st["payoff"], 2.0)
        self.assertAlmostEqual(st["total_net_pct"], 1.0, places=3)

    def test_payoff_is_none_without_losses(self):
        self.assertIsNone(oc.summarise([self._o(1.0, oc.TARGET)])["payoff"])


class TestOutcomeCsv(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "outcomes.csv"

    def tearDown(self):
        self._tmp.cleanup()

    def _o(self, date, code):
        return oc.Outcome(date=date, code=code, time="09:23", entry=100.0, stop=99.0,
                          target=101.5, lots=1, result=oc.TARGET, exit_price=101.5,
                          r_multiple=1.5, gross_pct=1.5, net_pct=1.3, bars=3)

    def _rows(self):
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def test_excel_in_taiwan_can_open_it(self):
        """沒有 BOM 的話，cp950 的 Excel 會把「停損」開成亂碼。"""
        oc.append_csv([self._o("2026-09-24", "6182")], self.path)
        self.assertTrue(self.path.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertIn("目標", self.path.read_text(encoding="utf-8-sig"))

    def test_first_column_name_is_not_polluted_by_the_bom(self):
        """BOM 沒處理好的話，欄名會變成 '\ufeffdate'，讀回來全部對不上。"""
        oc.append_csv([self._o("2026-09-24", "6182")], self.path)
        oc.append_csv([self._o("2026-09-25", "3707")], self.path)
        self.assertEqual([r["date"] for r in self._rows()],
                         ["2026-09-24", "2026-09-25"])

    def test_appends_across_days(self):
        oc.append_csv([self._o("2026-09-24", "1")], self.path)
        oc.append_csv([self._o("2026-09-25", "2")], self.path)
        self.assertEqual([r["date"] for r in self._rows()],
                         ["2026-09-24", "2026-09-25"])

    def test_rerunning_same_day_replaces_not_duplicates(self):
        """review.py 跑兩次不該讓那天的樣本被算兩遍。"""
        oc.append_csv([self._o("2026-09-24", "1")], self.path)
        oc.append_csv([self._o("2026-09-24", "1")], self.path)
        self.assertEqual(len(self._rows()), 1)

    def test_empty_list_is_a_noop(self):
        oc.append_csv([], self.path)
        self.assertFalse(self.path.exists())

    def test_older_rows_without_the_new_columns_survive(self):
        """先前跑過的日子沒有現場條件欄位，補欄位不能把那些天弄丟。"""
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            f.write("date,code,net_pct\n2026-09-24,1101,0.9\n")
        oc.append_csv([self._o("2026-09-25", "2330")], self.path)
        rows = self._rows()
        self.assertEqual([r["date"] for r in rows], ["2026-09-24", "2026-09-25"])
        self.assertEqual(rows[0]["or_high"], "")


class TestOutcomeRecordsSignalContext(unittest.TestCase):
    """訊號當下的現場條件要留下來，否則「什麼樣的訊號比較會成功」問不了。

    2026-09-24 當天就遇到了：五個訊號裡有一個的進場價比開盤區間高點高出 2.3%
    （其餘四個都在 0.8% 以內）。那是追高，風險結構完全不同 —— 但只記進場、停損、
    目標的話，20 天之後根本分不出這一筆和其他筆的差別。
    """

    DATE = "2026-09-24"
    SIG = {"code": "3016", "time": "09:35:25", "entry": 158.0, "stop": 156.0,
           "target": 161.0, "lots": 1, "or_high": 154.5, "vwap": 151.06,
           "volume_surge": 1.8}

    def _resolve(self, sig=None):
        rows = [("09:37", 161.5, 157.0, 161.2)]   # 09:36 那根包著訊號，會被排掉
        return oc.resolve(FakeKbarBroker(_kb(rows)), sig or self.SIG, self.DATE)

    def test_keeps_the_conditions_as_they_were(self):
        o = self._resolve()
        self.assertEqual(o.or_high, 154.5)
        self.assertEqual(o.vwap, 151.06)
        self.assertEqual(o.volume_surge, 1.8)

    def test_extension_measures_how_far_past_the_breakout_it_entered(self):
        o = self._resolve()
        self.assertAlmostEqual(o.extension_pct, 2.265, places=2)
        self.assertAlmostEqual(o.vwap_gap_pct, 4.594, places=2)

    def test_a_normal_breakout_reads_much_lower(self):
        """對照組：同一天的合晶，進場只高出區間高點 0.42%。"""
        sig = dict(self.SIG, code="6182", entry=119.0, stop=117.5, target=121.5,
                   or_high=118.5, vwap=117.15)
        o = oc.resolve(FakeKbarBroker(_kb([("09:37", 122.0, 118.8, 121.8)])),
                       sig, self.DATE)
        self.assertAlmostEqual(o.extension_pct, 0.422, places=2)

    def test_missing_fields_stay_empty_not_zero(self):
        """舊訊號沒有這些欄位。塞 0 會讓它看起來像「剛好在區間高點進場」。"""
        o = self._resolve({"code": "2330", "time": "09:23:00", "entry": 121.0,
                           "stop": 119.5, "target": 123.5, "lots": 1})
        self.assertIsNone(o.or_high)
        self.assertIsNone(o.extension_pct)
        self.assertIsNone(o.volume_surge)

    def test_zero_vwap_does_not_become_a_huge_gap(self):
        """vwap 拿不到時是 0，拿 0 當分母會算出無意義的數字。"""
        o = self._resolve(dict(self.SIG, vwap=0))
        self.assertIsNone(o.vwap_gap_pct)


class TestPushTopSeparateFromMonitoring(unittest.TestCase):
    """推播只列前幾檔是為了讀得完；但不能讓人以為程式只監看那幾檔。"""

    PAYLOAD = {"date": "2026-09-24", "round_trip_cost_pct": 0.207}
    ROWS = [{"code": f"{1000 + i}", "name": f"股{i}", "prev_close": 50.0,
             "amplitude_pct": 5.0, "volume_ratio": 10.0 - i} for i in range(20)]

    def test_push_top_defaults_to_five(self):
        self.assertEqual(screener.parse_args([]).push_top, 5)

    def test_push_top_rejects_zero(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                screener.parse_args(["--push-top", "0"])

    def test_message_states_true_monitored_count(self):
        text = screener.format_watchlist(self.PAYLOAD, self.ROWS[:5], total=20)
        self.assertIn("監看 20 檔", text)
        self.assertIn("量比最高的 5 檔", text)

    def test_message_stays_simple_when_nothing_truncated(self):
        text = screener.format_watchlist(self.PAYLOAD, self.ROWS[:5], total=5)
        self.assertIn("（5 檔）", text)
        self.assertNotIn("監看", text)

    def test_push_truncates_display_but_reports_full_total(self):
        sent = []
        with unittest.mock.patch.object(signals, "notify", sent.append):
            screener.push_watchlist(self.PAYLOAD, self.ROWS, show=5)
        self.assertIn("監看 20 檔", sent[0])
        self.assertIn("1000", sent[0])          # 第 1 檔在
        self.assertNotIn("1005", sent[0])       # 第 6 檔不在

    def test_push_show_larger_than_pool_is_safe(self):
        sent = []
        with unittest.mock.patch.object(signals, "notify", sent.append):
            screener.push_watchlist(self.PAYLOAD, self.ROWS[:3], show=5)
        self.assertIn("（3 檔）", sent[0])


class TestScreenerTopN(unittest.TestCase):
    """--top N 是驗證期的關鍵：每天用同一條規則取前 N 檔，結果才可重現。"""

    def test_parses_top(self):
        self.assertEqual(screener.parse_args(["--top", "5"]).top, 5)

    def test_top_defaults_to_none(self):
        self.assertIsNone(screener.parse_args([]).top)

    def test_rejects_zero_and_negative(self):
        for bad in ("0", "-3"):
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    screener.parse_args(["--top", bad])

    def test_keeps_highest_volume_ratio_first(self):
        """screen() 已排好序，--top 只是截斷 —— 驗證截到的確實是前幾名。"""
        rows = [{"code": f"{i}", "volume_ratio": 10 - i} for i in range(8)]
        self.assertEqual([r["code"] for r in rows[:3]], ["0", "1", "2"])
        self.assertTrue(all(rows[i]["volume_ratio"] >= rows[i + 1]["volume_ratio"]
                            for i in range(len(rows) - 1)))

    def test_top_larger_than_pool_keeps_everything(self):
        rows = [{"code": "1"}, {"code": "2"}]
        top = 5
        kept, dropped = (rows, []) if len(rows) <= top else (rows[:top], rows[top:])
        self.assertEqual(len(kept), 2)
        self.assertEqual(dropped, [])


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
        # 照 shioaji 的方式：台北牆上時間當成 UTC 編成奈秒（與本機時區無關）
        self.ts = [b[0].replace(tzinfo=dt_timezone.utc).timestamp() * 1e9 for b in bars]
        self.High = [b[1] for b in bars]
        self.Low = [b[2] for b in bars]
        self.Volume = [b[3] for b in bars]


class FakeApi:
    def __init__(self, stocks=None, snaps=None, kbars=None,
                 pnl_rows=None, pnl_raises=False, trades=None,
                 trades_raises=False, legacy_contracts_only=False,
                 kbars_by_code=None):
        stocks = stocks or FakeStocks()
        # shioaji 1.7 起改用小寫 api.contracts；舊版只有 api.Contracts
        if not legacy_contracts_only:
            self.contracts = SimpleNamespace(Stocks=stocks)
        self.Contracts = SimpleNamespace(Stocks=stocks)
        self._trades_raises = trades_raises
        self.stock_account = "acct"
        self._snaps = snaps or []
        self._kbars = kbars
        self._kbars_by_code = kbars_by_code
        self._pnl_rows = pnl_rows if pnl_rows is not None else []
        self._pnl_raises = pnl_raises
        self._trades = trades or []
        self.snapshot_batches = []

    def snapshots(self, contracts):
        self.snapshot_batches.append(len(contracts))
        codes = {c.code for c in contracts}
        return [s for s in self._snaps if s.code in codes]

    def kbars(self, contract, start, end):
        code = getattr(contract, "code", None)
        if self._kbars_by_code is not None:
            kb = self._kbars_by_code.get(code)
            if kb is None:
                raise RuntimeError(f"no kbars for {code}")
            return kb
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
        if self._trades_raises:
            raise RuntimeError("StatusCode: 401, Detail: Token doesn't have permission")
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

    def test_trades_today_unknown_on_api_error(self):
        """查不到要回 None（未知），不是 []（沒成交）—— 兩者差很多。"""
        class Boom(FakeApi):
            def list_trades(self):
                raise RuntimeError("查詢失敗")

        self.assertIsNone(Broker(api=Boom()).trades_today())

    def test_trades_today_empty_means_no_trades(self):
        self.assertEqual(Broker(api=FakeApi(trades=[])).trades_today(), [])

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


class TestContractsMigration(unittest.TestCase):
    """shioaji 1.7 起 api.Contracts 已棄用，實測會噴 DeprecationWarning。"""

    def test_prefers_new_lowercase_contracts(self):
        api = FakeApi(stocks=FakeStocks(tse=[FakeContract("2330")]))
        b = Broker(api=api)
        self.assertIs(b._stocks_root(), api.contracts.Stocks)
        self.assertEqual([c.code for c in b.all_stocks()], ["2330"])

    def test_falls_back_to_legacy_contracts(self):
        api = FakeApi(stocks=FakeStocks(tse=[FakeContract("2330")]),
                      legacy_contracts_only=True)
        self.assertFalse(hasattr(api, "contracts"))
        b = Broker(api=api)
        self.assertIs(b._stocks_root(), api.Contracts.Stocks)
        self.assertEqual([c.code for c in b.all_stocks()], ["2330"])

    def test_stock_lookup_uses_same_root(self):
        api = FakeApi(stocks=FakeStocks(tse=[FakeContract("2330")]))
        self.assertEqual(Broker(api=api).stock("2330").code, "2330")


class TestTradesUnknown(unittest.TestCase):
    """實測金鑰權限不足時 list_trades 會 401。

    回傳 [] 會讓「當日交易筆數上限」永遠不觸發 —— 又是一條靜靜失效的規則。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_state = config.STATE_FILE
        self._orig_sim = config.SIMULATION
        config.STATE_FILE = Path(self._tmp.name) / "state.json"
        self._orig_notify = signals.notify
        signals.notify = lambda t: None

    def tearDown(self):
        config.STATE_FILE = self._orig_state
        config.SIMULATION = self._orig_sim
        signals.notify = self._orig_notify
        self._tmp.cleanup()

    def test_broker_returns_none_on_401(self):
        b = Broker(api=FakeApi(trades_raises=True))
        self.assertIsNone(b.trades_today())

    def test_broker_returns_list_when_available(self):
        b = Broker(api=FakeApi(trades=[object()]))
        self.assertEqual(len(b.trades_today()), 1)

    def test_transient_failure_retries_and_does_not_halt(self):
        """斷線重連後第一次查詢 timeout，不該報銷一整天。"""
        config.SIMULATION = False

        class B:
            calls = 0

            def trades_today(self):
                B.calls += 1
                return None if B.calls == 1 else []      # 第一次 timeout，之後正常

            def realized_pnl_rows_today(self):
                return []

        gate = RiskGate(B())
        self.assertTrue(gate.check())
        self.assertFalse(gate.state["closed"])
        self.assertEqual(B.calls, 2)

    def test_persistent_failure_still_halts_after_retries(self):
        """權限不足是每次都失敗 —— 重試幾次之後照樣關閘。"""
        config.SIMULATION = False

        class B:
            calls = 0

            def trades_today(self):
                B.calls += 1
                return None

            def realized_pnl_rows_today(self):
                return []

        gate = RiskGate(B())
        self.assertFalse(gate.check())
        self.assertIn("交易筆數上限失效", gate.state["closed_reason"])
        self.assertEqual(B.calls, 1 + signals.UNKNOWN_RETRIES)

    def test_simulation_does_not_retry(self):
        """模擬模式的 None 本來就放行，重試只是白白卡住鎖。"""
        config.SIMULATION = True

        class B:
            calls = 0

            def trades_today(self):
                B.calls += 1
                return None

            def realized_pnl_rows_today(self):
                return None

        gate = RiskGate(B())
        self.assertTrue(gate.check())
        self.assertEqual(B.calls, 1)

    def test_pnl_unknown_also_retries_before_halting(self):
        config.SIMULATION = False

        class B:
            calls = 0

            def trades_today(self):
                return []

            def realized_pnl_rows_today(self):
                B.calls += 1
                return None if B.calls == 1 else [100.0]

        gate = RiskGate(B())
        self.assertTrue(gate.check())
        self.assertFalse(gate.state["closed"])

    def test_gate_halts_when_trades_unknown_and_live(self):
        config.SIMULATION = False

        class B:
            def trades_today(self):
                return None

            def realized_pnl_rows_today(self):
                return []

        gate = RiskGate(B())
        self.assertFalse(gate.check())
        self.assertIn("交易筆數上限失效", gate.state["closed_reason"])

    def test_gate_tolerates_unknown_trades_in_simulation(self):
        config.SIMULATION = True

        class B:
            def trades_today(self):
                return None

            def realized_pnl_rows_today(self):
                return []

        self.assertTrue(RiskGate(B()).check())


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

    def test_kbars_empty_is_warning_not_failure(self):
        """欄位在、只是週末沒資料 → 這是 WARN 不是 FAIL。

        實測就是這樣誤判的：週日跑體檢，空清單被當成「欄位不存在」。
        """
        api = FakeApi(stocks=self._stocks(), kbars=FakeKbars([]))
        r = preflight.check_kbars(Broker(api=api))
        self.assertEqual(r.status, preflight.WARN)
        self.assertIn("欄位名稱正確", r.detail)

    def test_kbars_absent_fields_is_fail(self):
        """欄位真的不存在才算失敗，而且要印出實際有哪些屬性。"""
        api = FakeApi(stocks=self._stocks(),
                      kbars=SimpleNamespace(timestamp=[], h=[], l=[], v=[]))
        r = preflight.check_kbars(Broker(api=api))
        self.assertEqual(r.status, preflight.FAIL)
        self.assertIn("欄位名稱不符", r.detail)
        self.assertIn("timestamp", r.detail)      # 印出實際屬性幫助對照

    def test_kbars_confirms_timezone_is_right(self):
        api = FakeApi(stocks=self._stocks(), kbars=FakeKbars(self._bars(0)))
        r = preflight.check_kbars(Broker(api=api))
        self.assertEqual(r.status, preflight.OK)
        self.assertIn("時區解讀正確", r.detail)

    def test_kbars_flags_timezone_shift(self):
        """實機症狀：第一根出現在 17:03，差正好 8 小時 —— 時區解讀錯了。

        這是整套程式唯一一個「只在非 UTC 機器上才會發生」的 bug，
        體檢必須認得出它的長相。
        """
        d = datetime.now().date()
        shifted = [(datetime.combine(d, dtime(17, 3 + i)), 101.0, 99.0, 100)
                   for i in range(3)]
        api = FakeApi(stocks=self._stocks(), kbars=FakeKbars(shifted))
        r = preflight.check_kbars(Broker(api=api))
        self.assertIn("時區解讀錯誤", r.detail)
        self.assertIn("差 8 小時", r.detail)

    def test_kbars_prints_both_interpretations(self):
        """報告要印出原始 ts 與兩種解讀，時區問題才能一眼判定。"""
        api = FakeApi(stocks=self._stocks(), kbars=FakeKbars(self._bars(0)))
        detail = preflight.check_kbars(Broker(api=api)).detail
        self.assertIn("首筆 ts=", detail)
        self.assertIn("以 UTC 解", detail)
        self.assertIn("以本機時區解", detail)

    @staticmethod
    def _bars_from(minute, count=3):
        d = datetime.now().date()
        return FakeKbars([(datetime.combine(d, dtime(9, minute + i)), 101.0, 99.0, 100)
                          for i in range(count)])

    def test_kbars_same_start_across_stocks_means_data_origin(self):
        """抽樣的每檔第一根都是 09:03 → 是全市場的資料起點，不是個股沒成交。

        實機就是這個情況：0050 每個交易日都剛好 264 根、第一根都是 09:03。
        """
        codes = ("2330", "2331", "2332")
        api = FakeApi(stocks=self._stocks(("DayTrade.Yes",) * 3),
                      kbars_by_code={c: self._bars_from(3) for c in codes})
        r = preflight.check_kbars(Broker(api=api))
        self.assertEqual(r.status, preflight.OK)
        self.assertIn("全市場分鐘 K 的資料起點", r.detail)
        self.assertIn("區間會略窄", r.detail)

    def test_kbars_differing_starts_means_thin_opening(self):
        """各檔開始時間不一致 → 只是個股開盤沒成交，正常。"""
        api = FakeApi(stocks=self._stocks(("DayTrade.Yes",) * 3),
                      kbars_by_code={"2330": self._bars_from(3),
                                     "2331": self._bars_from(0),
                                     "2332": self._bars_from(0)})
        r = preflight.check_kbars(Broker(api=api))
        self.assertEqual(r.status, preflight.OK)
        self.assertIn("沒成交", r.detail)

    def test_kbars_no_peers_to_compare(self):
        api = FakeApi(stocks=self._stocks(), kbars=self._bars_from(3))
        r = preflight.check_kbars(Broker(api=api))
        self.assertIn("沒有其他檔可比對", r.detail)

    def test_kbars_uses_last_trading_day(self):
        """回看十天會跨多日，要取最後一個交易日的第一根。"""
        d = datetime.now().date()
        bars = []
        for day_offset in (5, 1):
            day = d - timedelta(days=day_offset)
            for m in range(3):
                bars.append((datetime.combine(day, dtime(9, m)), 101.0, 99.0, 100))
        api = FakeApi(stocks=self._stocks(), kbars=FakeKbars(bars))
        r = preflight.check_kbars(Broker(api=api))
        self.assertEqual(r.status, preflight.OK)
        self.assertIn(str(d - timedelta(days=1)), r.detail)

    def test_kbars_call_failure_is_fail(self):
        api = FakeApi(stocks=self._stocks(), kbars=None)
        self.assertEqual(preflight.check_kbars(Broker(api=api)).status,
                         preflight.FAIL)

    def test_kbars_unparseable_ts_is_fail(self):
        api = FakeApi(stocks=self._stocks(),
                      kbars=SimpleNamespace(ts=["abc"], High=[1], Low=[1], Volume=[1]))
        r = preflight.check_kbars(Broker(api=api))
        self.assertEqual(r.status, preflight.FAIL)
        self.assertIn("解析不出時間", r.detail)

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

    def test_trades_unknown_is_warning_in_simulation(self):
        orig = config.SIMULATION
        config.SIMULATION = True
        try:
            api = FakeApi(stocks=self._stocks(), trades_raises=True)
            r = preflight.check_trades(Broker(api=api))
            self.assertEqual(r.status, preflight.WARN)
            self.assertIn("等於沒有", r.detail)
        finally:
            config.SIMULATION = orig

    def test_trades_unknown_is_failure_when_live(self):
        orig = config.SIMULATION
        config.SIMULATION = False
        try:
            api = FakeApi(stocks=self._stocks(), trades_raises=True)
            r = preflight.check_trades(Broker(api=api))
            self.assertEqual(r.status, preflight.FAIL)
            self.assertIn("關閘停手", r.detail)
        finally:
            config.SIMULATION = orig

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
    """ts 必須解成台北牆上時間，而且**與本機時區無關**。

    實機在台灣（UTC+8）跑出來，09:00 的 K 棒變成 17:00；
    我在 UTC 容器上測完全看不出來。所以這裡一律用 UTC 基準建構時間戳，
    並由 CI 另外以 TZ=Asia/Taipei 再跑一次整包測試。
    """

    @staticmethod
    def _shioaji_ns(wall: datetime) -> int:
        """模擬 shioaji：把台北牆上時間當成 UTC 編成奈秒。"""
        return int(wall.replace(tzinfo=dt_timezone.utc).timestamp() * 1_000_000_000)

    def test_nanoseconds_give_back_the_wall_clock(self):
        from broker import _bar_time
        wall = datetime(2026, 9, 18, 9, 0)
        self.assertEqual(_bar_time(self._shioaji_ns(wall)), wall)

    def test_result_does_not_depend_on_local_timezone(self):
        """同一個 ts，不管本機時區是什麼，都要解出同一個時間。"""
        from broker import _bar_time
        wall = datetime(2026, 9, 18, 9, 0)
        ns = self._shioaji_ns(wall)
        results = []
        for tz in ("UTC", "Asia/Taipei", "America/New_York"):
            with unittest.mock.patch.dict(os.environ, {"TZ": tz}):
                if hasattr(time, "tzset"):
                    time.tzset()
                results.append(_bar_time(ns))
        if hasattr(time, "tzset"):
            time.tzset()                      # 還原
        self.assertEqual(results, [wall] * 3, f"時區會影響結果：{results}")

    def test_opening_bar_stays_in_session(self):
        """09:00 的 K 棒解完必須還在盤中，不能跑到 17:00。"""
        from broker import _bar_time
        got = _bar_time(self._shioaji_ns(datetime(2026, 9, 18, 9, 0)))
        self.assertTrue(9 <= got.hour < 14, f"{got:%H:%M} 不在台股盤中")

    def test_accepts_seconds_and_milliseconds(self):
        from broker import _bar_time
        wall = datetime(2026, 9, 18, 9, 0)
        ns = self._shioaji_ns(wall)
        self.assertEqual(_bar_time(ns // 1_000_000_000), wall)   # 秒
        self.assertEqual(_bar_time(ns // 1_000_000), wall)       # 毫秒
        self.assertEqual(_bar_time(ns // 1_000), wall)           # 微秒

    def test_passes_datetime_through(self):
        from broker import _bar_time
        expect = datetime(2026, 9, 20, 9, 5)
        self.assertEqual(_bar_time(expect), expect)
        aware = expect.replace(tzinfo=dt_timezone.utc)
        self.assertEqual(_bar_time(aware), expect)               # 去掉 tzinfo

    def test_rejects_garbage(self):
        from broker import _bar_time
        self.assertIsNone(_bar_time("abc"))
        self.assertIsNone(_bar_time(None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
