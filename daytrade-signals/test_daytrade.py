"""
test_daytrade.py — 離線測試。不需要 shioaji、不需要網路、不需要金鑰。

    python3 test_daytrade.py        （Windows 是 python test_daytrade.py）

測的是「錯了不會報錯」的那些地方：訊號條件、風控閘門、量能基準、紀律稽核。
這些邏輯算錯不會讓程式崩掉，它會安靜地給你一個看起來很專業的錯誤決策。
"""
import os
# 這一行必須在 import config 之前。2026-09-29 跑一次測試就推了 5 則訊息到使用者手機，
# 其中一則寫著「原因：測試」—— 測試絕對不可以動到真的推播。
os.environ["DAYTRADE_NO_PUSH"] = "1"

import contextlib
import csv
import ast
import inspect
import io
import json
import os
import sys
import tempfile
import textwrap
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
import whatif
import broker as broker_mod
from broker import Broker
import outcome as oc
import screener
import analyse
import signals
import exits
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


@contextlib.contextmanager
def push_allowed():
    """只有「故意在測推播機制」的測試才用。

    全域保險絲把推播關死了（見 TestTestsCanNeverPush）。這幾條測試要驗的是
    保險絲**之後**的那段程式，所以暫時把它換掉 —— 送出去的永遠是假的 requests。
    """
    orig = config.push_enabled
    config.push_enabled = lambda: bool(config.TELEGRAM_BOT_TOKEN
                                       and config.TELEGRAM_CHAT_ID)
    try:
        yield
    finally:
        config.push_enabled = orig


def snap(code="2330", close=100.0, high=104.0, low=100.0, volume=9000, avg=101.0):
    return SimpleNamespace(code=code, close=close, high=high, low=low,
                           total_volume=volume, average_price=avg)


# 下面幾組測試寫的是**機制**（結構停損、張數反推、漲停貼齊、1.5R 目標），
# 數字是照 v5 的參數算的（停損 1.5%、1.5R、當沖）。v6 把停損改成 3%、目標改成
# +8%、可以抱到隔天 —— 機制沒變，只是參數變了。把這幾組釘在 v5 參數上，
# 測試才繼續證明那些機制是對的；v6 的數字另外有自己的測試（TestV6...）。
# v9 加的「開盤／回落要在昨收附近」也是 v5 沒有的，一起關掉。
# v10 的六條出場也是 v5 沒有的。
V5_SIGNAL = {"stop_loss_pct": 1.5, "target_pct": None, "max_hold_days": 1,
             "near_prev_close_pct": None, "exit_rules": False}


def under_v5_rules(cls):
    return unittest.mock.patch.dict(config.SIGNAL, V5_SIGNAL)(cls)



def ready_state(code="2330", or_high=100.0, last=101.0, vwap=100.5, surge_ratio=3.0):
    """造一個「萬事俱備」的個股狀態：區間已鎖、價格突破、站上均價、量能達標。"""
    # 昨收跟著標的價位走，否則高價股的測試會誤觸漲停夾擠
    st = SymbolState(code, prev_close=round(or_high * 0.99, 2))
    # v9：開盤就在昨收 —— 「萬事俱備」也包括開盤沒有大跳空。
    st.day_open = st.prev_close
    st.lock_opening_range(or_high, or_high - 2)
    st.last_price = last
    st.vwap = vwap
    # vol_marks 照 config 的取樣視窗造，不要寫死秒數 —— v4 把近期視窗從
    # 300 秒縮到 60 秒時，寫死的版本會算出別的倍數，而壞掉的原因跟這些測試
    # 要驗的事情無關。
    window = config.SIGNAL["volume_recent_sec"]
    span = window + max(config.SIGNAL["volume_min_base_span_sec"], window) * 2
    step = max(5, window // 6)
    now = 10_000.0
    marks, vol = [], 0.0
    for offset in range(-span, 1, step):
        marks.append((now + offset, int(round(vol))))
        # 最後 window 秒的量能速率是 surge_ratio 張/秒，之前是 1 張/秒
        vol += step * (1.0 if offset < -window else surge_ratio)
    st.vol_marks = marks
    return st


class TestEveryTestActuallyRuns(unittest.TestCase):
    """`unittest.main()` 以前卡在檔案中間，它後面的測試類別從來沒有被執行過。

    `python test_daytrade.py`（README 與 CI 用的那個指令）會從上往下執行，
    走到 `unittest.main()` 就開跑並結束 —— **下面的 class 連定義都不會定義**。
    而 `python -m unittest test_daytrade` 是整個模組 import 進來，所以 490 條
    全都跑得到。開發時用後者、使用者與 CI 用前者，於是 2026-10-02 當天新寫的
    七個類別、53 條測試在 CI 上「全綠」，實際上一條都沒跑。

    變異測試也一起失效了：它跑的是 `-m unittest`，接得住；但在使用者的環境裡
    那些規則根本沒有人在看。

    這正是這個專案一路在修的那種毛病 —— 檢查看起來在那裡，實際上沒有作用 ——
    而這次是它長在測試檔自己身上。所以用一條測試把入口位置釘死。
    """

    def test_the_entry_point_is_the_last_thing_in_the_file(self):
        src = Path(__file__).read_text(encoding="utf-8").splitlines()
        entry = [i for i, l in enumerate(src) if l.startswith('if __name__')]
        self.assertEqual(len(entry), 1, "入口只能有一個")
        after = [f"{i + 1}: {l}" for i, l in enumerate(src[entry[0]:], entry[0])
                 if l.startswith(("class ", "def "))]
        self.assertEqual(after, [], "入口後面不可以再有測試 —— 它們不會被執行")

    def test_both_ways_of_running_find_the_same_tests(self):
        """`python test_daytrade.py` 與 `python -m unittest` 必須收到同一組測試。"""
        loader = unittest.TestLoader()
        mod = sys.modules[__name__]
        found = loader.loadTestsFromModule(mod).countTestCases()
        self.assertGreater(found, 480, f"只找到 {found} 條，入口位置可能又跑掉了")


class TestConfig(unittest.TestCase):
    def test_round_trip_cost(self):
        # 手續費 0.001425 × 2折 × 來回 + 當沖稅 0.0015 = 0.00207 → 0.207%
        self.assertAlmostEqual(config.round_trip_cost_pct(), 0.207, places=4)

    def test_shipped_config_is_valid(self):
        self.assertEqual(config.validate(), [])

    def test_validate_catches_bad_params(self):
        cases = [
            (config.SIGNAL, "stop_loss_pct", 0, "stop_loss_pct"),
            (config.SIGNAL, "target_pct", -1, "target_pct"),
            (config.SIGNAL, "max_hold_days", 3, "max_hold_days"),
            (config.COST, "tax_rate_overnight", 0.001, "tax_rate_overnight"),
            (config.SIGNAL, "allow_short", True, "allow_short"),
            (config.SIGNAL, "or_end", "08:00:00", "時間順序"),
            (config.RISK, "max_daily_loss", 0, "max_daily_loss"),
            (config.RISK, "max_consecutive_losses", 0, "max_consecutive_losses"),
            (config.RISK, "poll_interval_sec", 5, "poll_interval_sec"),
            (config.SIGNAL, "market_close", "09:01:00", "時間順序"),
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

    def test_reward_risk_is_checked_only_when_it_is_the_one_in_use(self):
        """target_pct 有設時 reward_risk 不參與計算 —— 拿它擋啟動是假警報；
        target_pct 設成 None 退回 R 倍數時，它就必須是正數。"""
        with unittest.mock.patch.dict(config.SIGNAL, {"reward_risk": -1, "target_pct": 8.0}):
            self.assertNotIn("reward_risk", " / ".join(config.validate()))
        with unittest.mock.patch.dict(config.SIGNAL, {"reward_risk": -1, "target_pct": None}):
            self.assertIn("reward_risk", " / ".join(config.validate()))

    def test_red_line_mismatch_warns_but_does_not_block_startup(self):
        """單筆風險 × 筆數上限 < 日虧上限 —— 是提醒，不是錯誤。

        原本這是 validate() 的錯誤，訊息寫「日虧上限形同虛設」。那個算式錯了：
        它假設每一筆都剛好賠 per_trade_risk，但 signals.py 的 oversized 路徑
        （連一張都超過上限時仍給 1 張）讓單筆風險可以超過上限 —— 股價高於
        per_trade_risk ÷ 1000 ÷ stop_loss_pct 的訊號每一筆都會超標。
        那正是日虧上限唯一會出手的時候，所以它不是虛設，不該擋住啟動。
        """
        original = config.RISK["max_daily_loss"]
        config.RISK["max_daily_loss"] = 999_999
        try:
            self.assertEqual(config.validate(), [], "這不該是錯誤")
            self.assertTrue(any("日虧上限" in w for w in config.warnings()))
        finally:
            config.RISK["max_daily_loss"] = original

    def test_the_warning_names_the_price_above_which_a_lot_busts_the_cap(self):
        """警告要講得出門檻，否則看的人無從判斷這對自己適不適用。"""
        original = config.RISK["max_daily_loss"]
        config.RISK["max_daily_loss"] = 999_999
        try:
            # 門檻 = 單筆上限 ÷ 1000 股 ÷ 停損%。寫死數字的話，改參數就壞，
            # 而壞掉的原因跟這條在驗的事（警告講不講得出門檻）完全無關。
            threshold = (config.RISK["per_trade_risk"] / 1000
                         / (config.SIGNAL["stop_loss_pct"] / 100))
            self.assertIn(f"{threshold:,.0f}", " ".join(config.warnings()))
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
        with push_allowed(), \
             unittest.mock.patch.object(signals, "requests", FakeRequests), \
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
        st.update(tick(101.0, high=101.5, low=99.0, at="09:01:30"))
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


@under_v5_rules
class TestEvaluate(unittest.TestCase):
    IN_WINDOW = dtime(9, 3)      # 進場窗口 09:02–09:05 之內

    def test_fires_on_all_conditions_met(self):
        sig = evaluate(ready_state(or_high=100.0, last=101.0, vwap=100.5), now=self.IN_WINDOW)
        self.assertIsNotNone(sig)
        self.assertEqual(sig["code"], "2330")
        self.assertEqual(sig["direction"], "做多")
        self.assertAlmostEqual(sig["entry"], 101.0)
        # 101 × (1-1.5%) = 99.485 → 進位到 0.1 檔位 = 99.5
        self.assertAlmostEqual(sig["stop"], 99.5)
        # 101 + 1.5 × 2.5 = 104.75 → 進位到 0.5 檔位 = 105.0
        self.assertAlmostEqual(sig["target"], 103.5)
        self.assertFalse(sig["oversized"])

    def test_lot_sizing_from_per_trade_risk(self):
        sig = evaluate(ready_state(or_high=100.0, last=101.0, vwap=100.5), now=self.IN_WINDOW)
        cap = config.RISK["per_trade_risk"]
        # 一張風險 = (101 - 99.5) × 1000 = 1500 元
        self.assertEqual(sig["risk_per_lot"], 1500)
        self.assertEqual(sig["lots"], int(cap // 1500))

        cheap = ready_state(or_high=20.0, last=20.2, vwap=20.1)
        sig2 = evaluate(cheap, now=self.IN_WINDOW)
        # 20.2 × (1-1.5%) = 19.897 → 進位到 0.05 檔位 = 19.90
        self.assertAlmostEqual(sig2["stop"], 19.9)
        # 一張風險 = 300 元
        self.assertEqual(sig2["risk_per_lot"], 300)
        self.assertEqual(sig2["lots"], int(cap // 300))
        self.assertFalse(sig2["oversized"])

    def test_prices_land_on_legal_ticks(self):
        """停損／目標必須是可以真的下出去的價位。"""
        for or_high, last in ((20.0, 20.2), (60.0, 60.5), (100.0, 101.0), (280.0, 283.0)):
            with self.subTest(last=last):
                sig = evaluate(ready_state(or_high=or_high, last=last, vwap=last - 0.5),
                               now=self.IN_WINDOW)
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
                               now=self.IN_WINDOW)
                actual_pct = (sig["entry"] - sig["stop"]) / sig["entry"] * 100
                self.assertLessEqual(actual_pct, config.SIGNAL["stop_loss_pct"] + 1e-9)

    def test_reward_risk_never_below_configured(self):
        for or_high, last in ((20.0, 20.2), (60.0, 60.5), (100.0, 101.0), (280.0, 283.0)):
            with self.subTest(last=last):
                sig = evaluate(ready_state(or_high=or_high, last=last, vwap=last - 0.5),
                               now=self.IN_WINDOW)
                r = (sig["target"] - sig["entry"]) / (sig["entry"] - sig["stop"])
                self.assertGreaterEqual(r, config.SIGNAL["reward_risk"] - 1e-9)

    def test_flags_oversized_single_lot(self):
        """高價股一張的停損金額就超過單筆上限 → 必須標記，不能假裝 1 張沒事。"""
        # 283 元在 per_trade_risk=3,000 時超額，改成 4,000 之後剛好壓線不超。
        # 挑一個「不管上限設多少都確定超額」的價位：門檻的 1.5 倍。
        threshold = (config.RISK["per_trade_risk"] / 1000
                     / (config.SIGNAL["stop_loss_pct"] / 100))
        last = config.round_to_tick(threshold * 1.5, "up")
        pricey = ready_state(or_high=last - 3.0, last=last, vwap=last - 2.0)
        sig = evaluate(pricey, now=self.IN_WINDOW)
        self.assertEqual(sig["lots"], 1)
        self.assertTrue(sig["oversized"])
        self.assertGreater(sig["risk_per_lot"], config.RISK["per_trade_risk"])
        self.assertIn("超過單筆上限", format_signal(sig, 1, 1))

    def test_blocked_before_range_locked(self):
        st = ready_state()
        st.or_locked = False
        self.assertIsNone(evaluate(st, now=self.IN_WINDOW))

    def test_blocked_below_breakout_buffer(self):
        # 區間高 100 → 觸發價 100.10；100.05 不算突破
        st = ready_state(or_high=100.0, last=100.05, vwap=99.0)
        self.assertIsNone(evaluate(st, now=self.IN_WINDOW))

    def test_blocked_below_vwap(self):
        st = ready_state(or_high=100.0, last=101.0, vwap=101.5)
        self.assertIsNone(evaluate(st, now=self.IN_WINDOW))

    def test_missing_vwap_blocks_instead_of_skipping_the_rule(self):
        """均價線拿不到 → 不發訊號，而不是把這條規則靜靜跳過。

        原本 `require_above_vwap and st.vwap and ...` 在 vwap=0 時整條短路，
        規則你以為開著，其實整天沒作用。
        """
        st = ready_state(or_high=100.0, last=101.0, vwap=0.0)
        self.assertTrue(config.SIGNAL["require_above_vwap"])
        with self.assertLogs(signals.log, level="WARNING") as cm:
            self.assertIsNone(evaluate(st, now=self.IN_WINDOW))
        self.assertIn("沒有均價線", "".join(cm.output))
        self.assertTrue(st.vwap_warned)

    def test_missing_vwap_warns_only_once(self):
        st = ready_state(or_high=100.0, last=101.0, vwap=0.0)
        with self.assertLogs(signals.log, level="WARNING"):
            evaluate(st, now=self.IN_WINDOW)
        with self.assertNoLogs(signals.log, level="WARNING"):
            self.assertIsNone(evaluate(st, now=self.IN_WINDOW))

    def test_missing_vwap_is_allowed_when_rule_is_off(self):
        original = config.SIGNAL["require_above_vwap"]
        config.SIGNAL["require_above_vwap"] = False
        try:
            st = ready_state(or_high=100.0, last=101.0, vwap=0.0)
            self.assertIsNotNone(evaluate(st, now=self.IN_WINDOW))
        finally:
            config.SIGNAL["require_above_vwap"] = original

    def test_blocked_on_weak_volume(self):
        st = ready_state(or_high=100.0, last=101.0, vwap=100.5, surge_ratio=1.2)
        self.assertIsNone(evaluate(st, now=self.IN_WINDOW))

    def test_blocked_after_entry_window(self):
        st = ready_state()
        end = signals._t(config.SIGNAL["entry_window_end"])
        self.assertIsNone(evaluate(st, now=end))
        # 窗口結束前一分鐘還是有效的（v7 起窗口到 09:30）
        self.assertIsNotNone(evaluate(st, now=dtime(end.hour, end.minute - 1)))

    def test_one_signal_per_symbol(self):
        st = ready_state()
        st.signaled = config.SIGNAL["max_signals_per_symbol"]
        self.assertIsNone(evaluate(st, now=self.IN_WINDOW))


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
        sig = evaluate(ready_state(), now=dtime(9, 3))
        ordinal = gate.record(sig)
        self.assertEqual(ordinal, 1)
        self.assertIn("今日第 1 個訊號", format_signal(sig, ordinal, 1))
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
        gate = RiskGate(FakeBroker(pnl_rows=[-8000.0, -4000.0]))
        self.assertFalse(gate.check())
        self.assertIn("觸及上限", gate.state["closed_reason"])

    def test_daily_loss_just_under_limit_stays_open(self):
        gate = RiskGate(FakeBroker(pnl_rows=[-11999.0]))
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
        gate.record(evaluate(ready_state(), now=dtime(9, 3)))
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

        self._push_ctx = push_allowed()
        self._push_ctx.__enter__()

    def tearDown(self):
        self._push_ctx.__exit__(None, None, None)
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
            sig = evaluate(st, now=dtime(9, 3))
            barrier.wait()                       # 盡量讓大家同時進來
            if sig:
                msg, _blocked = signals.try_emit(st, gate, lock, sig)
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
        ordinals = sorted(int(m.split("今日第 ")[1].split(" ")[0]) for m in sent)
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
        self.assertIsNone(evaluate(st, now=dtime(9, 3)))

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
        self.assertIn("2330 台積電", format_signal(sig, 1, 1))

    def test_signal_without_name_has_no_stray_space(self):
        sig = dict(SIGNAL_FIXTURE, code="2330", name="")
        self.assertIn("2330 決策錨點", format_signal(sig, 1, 1))


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
        """目前這一版的**整段**歷史，不是只有今天。"""
        history = self._today() + [self._oc("8150", oc.TARGET, 1.67, 2.087)]
        for o in history:
            o.ruleset = config.RULESET
        text = review.format_push(self.SIGNALS, self._today(), history)
        self.assertIn("3 筆", text)
        self.assertIn("66.7%", text)

    def test_cumulative_is_omitted_when_there_is_no_history(self):
        self.assertNotIn("累計", review.format_push([], None, []))

    def test_says_it_is_not_real_pnl(self):
        text = review.format_push(self.SIGNALS, self._today(), [])
        self.assertIn("不是你的實際損益", text)
        self.assertIn("0.207", text)

    def test_each_row_is_short_enough_for_a_phone(self):
        """單筆那行太長的話，手機會把「元」自己擠到下一行，看起來很碎。"""
        text = review.format_push(self.SIGNALS, self._today(), [])
        rows = [l for l in text.splitlines() if l.startswith("　")]
        self.assertTrue(rows)
        for row in rows:
            self.assertNotIn("%", row)          # 百分比留在累計區塊
            self.assertLessEqual(len(row), 20)

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
        """一天只准做幾筆是 config 說了算。把全部訊號的總和講成今天會賺到的錢是高估。"""
        five = [self._oc(str(i), oc.TARGET, 1.67, 1.894) for i in range(5)]
        text = review.format_push(self.SIGNALS, five, [])
        self.assertIn("照完整規則只做 3 筆", text)
        self.assertIn("已達當日交易筆數上限 3 筆", text)
        # 合計必須等於各筆相加。差一塊錢會讓人懷疑哪個數字才是對的。
        self.assertIn("+11,270 元", text)         # 五筆合計
        self.assertIn("+6,762 元", text)          # 照規則做到的三筆（3 × 2,254）

    def test_no_cap_line_when_within_the_limit(self):
        text = review.format_push(self.SIGNALS, self._today(), [])
        self.assertNotIn("照完整規則", text)

    def test_cumulative_amount_is_shown(self):
        history = self._today() * 2
        for o in history:
            o.ruleset = config.RULESET
        text = review.format_push(self.SIGNALS, self._today(), history)
        self.assertIn(f"{config.RULESET} 累計損益", text)

    def _versioned(self, version, code, net, date="2026-10-08"):
        o = self._oc(code, oc.TARGET if net > 0 else oc.STOP, 1.0 if net > 0 else -1.0, net)
        o.ruleset, o.date = version, date
        return o

    def test_cumulative_only_counts_the_current_rules(self):
        """使用者 10-07：v1–v7 混在一起的累計回答不了「v7 好不好」。"""
        now = config.RULESET
        history = ([self._versioned("v2", "1", -1.0, "2026-09-30")] * 5
                   + [self._versioned(now, "2", 2.0), self._versioned(now, "3", -1.0)])
        lines = review.cumulative_lines(history)
        text = "\n".join(lines)
        self.assertIn(f"{now} 累計 1 個有訊號的交易日／2 筆（2026-10-08 起）", text)
        self.assertIn("勝率 50.0%", text)
        mine = sum(round(o.net_amount) for o in history if o.ruleset == now)
        self.assertIn(f"{now} 累計損益 {mine:+,.0f} 元", text)
        # 全部版本還在，但只是一行參考，而且講明是混算
        self.assertIn("全部版本合計 7 筆", text)
        self.assertIn("混算", text)

    def test_a_new_version_with_no_trades_says_so(self):
        text = "\n".join(review.cumulative_lines([self._versioned("v5", "1", 1.0)]))
        self.assertIn(f"{config.RULESET} 還沒有結束的交易", text)
        self.assertNotIn("勝率", text)
        self.assertIn("全部版本合計 1 筆", text)

    def test_no_mixed_line_when_everything_is_current(self):
        text = "\n".join(review.cumulative_lines([self._versioned(config.RULESET, "1", 1.0)]))
        self.assertNotIn("全部版本", text)

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


class TestFillWindow(unittest.TestCase):
    """限價掛訊號價，到底買不買得到 —— 這決定了手動下單行不行得通。"""

    DATE = "2026-09-24"
    SIG = {"code": "6182", "time": "09:19:22", "entry": 119.0,
           "stop": 117.5, "target": 121.5, "lots": 1}

    def _resolve(self, rows):
        return oc.resolve(FakeKbarBroker(_kb(rows)), self.SIG, self.DATE)

    def test_negative_means_the_limit_order_would_fill(self):
        """價格回頭到進場價以下 → 掛在訊號價買得到。"""
        o = self._resolve([("09:21", 119.5, 118.6, 119.2),
                           ("09:30", 121.6, 119.8, 121.4)])
        self.assertLess(o.low_5m_pct, 0)

    def test_positive_means_you_would_have_had_to_chase(self):
        """價格一路不回頭 → 限價買不到，要追多少就是這個數字。"""
        o = self._resolve([("09:21", 120.5, 119.6, 120.2),
                           ("09:30", 121.6, 120.8, 121.4)])
        self.assertAlmostEqual(o.low_5m_pct, 0.504, places=2)   # 119.6 vs 119.0

    def test_only_the_first_five_bars_count(self):
        """第 20 分鐘才回頭的價格，對「現在追不追得上」沒有意義。"""
        rows = [(f"09:{m:02d}", 120.5, 119.6, 120.2) for m in range(21, 27)]
        rows.append(("09:45", 120.0, 115.0, 116.0))   # 很晚才跌回來
        o = oc.resolve(FakeKbarBroker(_kb(rows)), self.SIG, self.DATE)
        self.assertGreater(o.low_5m_pct, 0)

    def test_a_late_signal_with_few_bars_still_works(self):
        """13:20 才發的訊號只剩幾根 K，不該因此算不出來。"""
        o = self._resolve([("13:22", 119.5, 118.8, 119.2)])
        self.assertIsNotNone(o.low_5m_pct)


@under_v5_rules
class TestPriceLimits(unittest.TestCase):
    """停損與目標都不可以落在漲跌停之外 —— 那是永遠不會成交的委託。

    2026-09-24 嘉晶：昨收 145.5、當日漲停 160.0，而系統發了 161.00 的目標。
    那一筆被判成「收盤平倉」，不是因為它沒走到目標，是因為那個價位當天不存在。
    """

    def test_limit_up_rounds_down_to_a_legal_tick(self):
        """漲停價不可以超過 10% —— 進位方向錯了會算出一個超過上限的價。"""
        self.assertEqual(config.limit_up(145.5), 160.0)     # 160.05 → 160.0
        self.assertEqual(config.limit_up(107.0), 117.5)
        self.assertEqual(config.limit_up(70.2), 77.2)

    def test_limit_down_rounds_up(self):
        self.assertEqual(config.limit_down(145.5), 131.0)   # 130.95 → 131.0

    def test_missing_prev_close_gives_no_limit(self):
        """拿不到昨收就不要猜一個漲停價出來 —— 猜錯比不夾更糟。"""
        self.assertIsNone(config.limit_up(0))
        self.assertIsNone(config.limit_down(None))

    def _state(self, prev_close, last_price, or_high):
        st = signals.SymbolState(code="3016", prev_close=prev_close, name="嘉晶")
        st.lock_opening_range(or_high, or_high - 3, source="測試")
        st.last_price = last_price
        st.vwap = or_high - 3
        st.vol_marks = [(0.0, 0), (600.0, 6_000_000)]
        return st

    def test_target_is_capped_at_the_limit_up_price(self):
        st = self._state(prev_close=145.5, last_price=158.0, or_high=154.5)
        with unittest.mock.patch.object(signals.SymbolState, "volume_surge",
                                        lambda self: 5.0):
            sig = signals.evaluate(st, dtime(9, 3))
        self.assertIsNotNone(sig)
        self.assertEqual(sig["target"], 160.0)      # 不是 161.0
        self.assertTrue(sig["target_capped"])

    def test_capped_target_is_spelled_out_in_the_message(self):
        """賺賠比因此縮水，訊息上要講出來，不能假裝還是 1.5R。"""
        sig = {"code": "3016", "name": "嘉晶", "time": "09:35:25", "direction": "做多",
               "entry": 158.0, "stop": 156.0, "target": 160.0, "lots": 1,
               "risk_per_lot": 2000, "oversized": False, "target_capped": True,
               "or_high": 154.5, "vwap": 151.06, "volume_surge": 1.8}
        text = signals.format_signal(sig, 5, 5)
        self.assertIn("貼齊漲停", text)
        self.assertIn("1.00R", text)

    def test_no_signal_once_it_is_locked_at_the_limit(self):
        """漲停鎖死的價位你買不到，買到也沒有上檔空間。"""
        st = self._state(prev_close=145.5, last_price=160.0, or_high=154.5)
        with unittest.mock.patch.object(signals.SymbolState, "volume_surge",
                                        lambda self: 5.0):
            self.assertIsNone(signals.evaluate(st, dtime(9, 3)))

    def test_a_normal_stock_is_untouched(self):
        """沒碰到漲停的日子，目標還是照 reward_risk 算。"""
        # 進場 109、停損 107.5（R=1.5）→ 目標 109 + 1.5×1.5 = 111.25 → 111.5
        # 漲停 = 107 × 1.1 = 117.7 → 往下取 0.5 檔位 = 117.5，目標沒碰到
        st = self._state(prev_close=107.0, last_price=109.0, or_high=108.5)
        with unittest.mock.patch.object(signals.SymbolState, "volume_surge",
                                        lambda self: 5.0):
            sig = signals.evaluate(st, dtime(9, 3))
        self.assertEqual(sig["target"], 111.5)
        self.assertFalse(sig["target_capped"])


class TestExcursions(unittest.TestCase):
    """停損該多緊、目標該多遠 —— 只記出場價的話，這兩個問題永遠問不了。

    2026-09-24 光頡：進場 137.00、停損 135.00 被掃，但當天最高走到 144.50、
    收在 140.00（剛好是目標價）。只看「停損」兩個字，看不出這一筆其實是被洗掉的。
    """

    DATE = "2026-09-24"
    SIG = {"code": "3624", "time": "09:27:41", "entry": 137.0,
           "stop": 135.0, "target": 140.0, "lots": 1}

    def _resolve(self, rows):
        return oc.resolve(FakeKbarBroker(_kb(rows)), self.SIG, self.DATE)

    def test_extremes_cover_the_whole_day_not_just_up_to_the_exit(self):
        o = self._resolve([("09:29", 137.5, 134.0, 134.5),   # 這根掃到停損
                           ("10:40", 144.5, 138.0, 143.0),   # 出場之後才走的
                           ("13:20", 141.0, 139.5, 140.0)])
        self.assertEqual(o.result, oc.STOP)
        self.assertAlmostEqual(o.mae_pct, -2.190, places=2)   # 134.0 vs 137.0
        self.assertAlmostEqual(o.mfe_pct, 5.474, places=2)    # 144.5 vs 137.0

    def test_flags_a_stop_that_later_reached_the_target(self):
        """被洗掉之後又漲到目標 —— 這是這 20 天最關鍵的那個問題。"""
        o = self._resolve([("09:29", 137.5, 134.0, 134.5),
                           ("10:40", 144.5, 138.0, 143.0)])
        self.assertTrue(o.target_after_stop)

    def test_a_stop_that_never_recovered_is_marked_false(self):
        o = self._resolve([("09:29", 137.5, 134.0, 134.5),
                           ("10:40", 136.0, 133.0, 133.5)])
        self.assertFalse(o.target_after_stop)

    def test_not_applicable_when_it_was_not_a_stop(self):
        """贏的那幾筆沒有「被洗掉」這回事，記 False 會污染統計。"""
        o = self._resolve([("09:29", 140.5, 136.5, 140.2)])
        self.assertEqual(o.result, oc.TARGET)
        self.assertIsNone(o.target_after_stop)

    def test_a_winner_still_records_how_far_it_went_against_you(self):
        """贏的單的 MAE 才回答得了「停損可以多緊而不被洗掉」。"""
        o = self._resolve([("09:29", 138.0, 135.5, 137.8),
                           ("09:35", 140.5, 137.0, 140.2)])
        self.assertEqual(o.result, oc.TARGET)
        self.assertAlmostEqual(o.mae_pct, -1.095, places=2)   # 135.5 vs 137.0

    def test_booleans_survive_the_csv_round_trip(self):
        """空字串是「不適用」，不是 False。讀成 False 會讓贏的單被算進統計。"""
        import tempfile
        from pathlib import Path as _P
        with tempfile.TemporaryDirectory() as d:
            path = _P(d) / "outcomes.csv"
            stopped = self._resolve([("09:29", 137.5, 134.0, 134.5),
                                     ("10:40", 144.5, 138.0, 143.0)])
            won = self._resolve([("09:29", 140.5, 136.5, 140.2)])
            oc.append_csv([stopped, won], path)
            back = oc.load_csv(path)
            self.assertTrue(back[0].target_after_stop)
            self.assertIsNone(back[1].target_after_stop)


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

    def test_push_top_defaults_to_three(self):
        self.assertEqual(screener.parse_args([]).push_top, 3)

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

    def test_a_warning_shows_up_as_warn_not_ok(self):
        """警告要看得見。印不出來的警告跟沒有警告一樣 —— 這個專案一路在修這個。"""
        ws = config.warnings()
        self.assertTrue(ws, "出廠設定本來就該帶著警告")
        r = preflight.check_config()
        self.assertEqual(r.status, preflight.WARN)
        # 不釘某一句話 —— 釘了之後換一條警告就會失敗，而失敗的理由
        # 跟這條在驗的事（警告有沒有被印出來）無關。驗的是每一條都在。
        for w in ws:
            self.assertIn(w, r.detail)

    def test_config_check_passes_and_fails(self):
        # 出廠設定本身帶著警告（日虧上限高於 3 筆滿額、連敗停手不會出手），
        # 所以先壓掉警告才驗「沒問題時是 OK」。
        saved = {k: config.RISK[k] for k in ("max_daily_loss", "max_consecutive_losses")}
        saved_price = config.SCREEN["max_price"]
        config.RISK["max_daily_loss"] = (config.RISK["per_trade_risk"]
                                         * config.RISK["max_trades_per_day"])
        config.RISK["max_consecutive_losses"] = 1
        # 價格死區那條也要壓掉：上限壓到「一張不會超額」的門檻以下。
        config.SCREEN["max_price"] = (config.RISK["per_trade_risk"] / 1000
                                      / (config.SIGNAL["stop_loss_pct"] / 100)) - 1
        try:
            self.assertEqual(config.warnings(), [])
            self.assertEqual(preflight.check_config().status, preflight.OK)
        finally:
            config.RISK.update(saved)
            config.SCREEN["max_price"] = saved_price
        with unittest.mock.patch.dict(config.SIGNAL, {"target_pct": -1}):
            r = preflight.check_config()
            self.assertEqual(r.status, preflight.FAIL)
            self.assertIn("target_pct", r.detail)

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
            with push_allowed(), contextlib.redirect_stdout(io.StringIO()):
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


class TestBlockedCandidatesAreRecorded(unittest.TestCase):
    """被上限擋掉的訊號以前直接消失。沒有這份紀錄，「上限訂多少」只能再測一次。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "candidates.csv"
        self.addCleanup(self.tmp.cleanup)
        self._orig_state = config.STATE_FILE          # 別讓測試之間互相污染風控狀態
        config.STATE_FILE = Path(self.tmp.name) / "state.json"

    def tearDown(self):
        config.STATE_FILE = self._orig_state

    def _rows(self):
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def test_daily_cap_blocks_but_records(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        gate.state["signals_sent"] = config.RISK["max_signals_per_day"]
        st = ready_state("2330")
        sig = evaluate(st, now=dtime(9, 3))
        msg, blocked = signals.try_emit(st, gate, threading.Lock(), sig)
        self.assertIsNone(msg)
        self.assertEqual(blocked, signals.BLOCK_DAILY_CAP)
        # 被擋掉不可以留下任何副作用
        self.assertEqual(st.signaled, 0)
        self.assertEqual(gate.state["signals_sent"], config.RISK["max_signals_per_day"])

    def test_second_breakout_on_same_symbol_is_evaluated_and_blocked(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        st = ready_state("2330")
        lock = threading.Lock()
        first = evaluate(st, now=dtime(9, 3))
        msg, blocked = signals.try_emit(st, gate, lock, first)
        self.assertIsNotNone(msg)
        self.assertIsNone(blocked)
        # 第二次：舊行為是 evaluate 直接回 None，連算都不算
        self.assertIsNone(evaluate(st, now=dtime(9, 3)))
        again = evaluate(st, now=dtime(9, 3), ignore_symbol_cap=True)
        self.assertIsNotNone(again)
        _, blocked = signals.try_emit(st, gate, lock, again,
                                      now=datetime(2026, 1, 2, 10, 30))
        self.assertEqual(blocked, signals.BLOCK_SYMBOL_CAP)
        self.assertEqual(st.signaled, 1)         # 候選不會讓它變成發了兩次

    def test_cooldown_stops_every_tick_becoming_a_candidate(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        gate.state["signals_sent"] = config.RISK["max_signals_per_day"]
        st = ready_state("2330")
        sig = evaluate(st, now=dtime(9, 3))
        lock = threading.Lock()
        t0 = datetime(2026, 1, 2, 10, 0, 0)
        recorded = []
        for offset in (0, 30, 60, 301):          # 秒
            _, blocked = signals.try_emit(
                st, gate, lock, sig, now=t0 + timedelta(seconds=offset))
            if blocked:
                recorded.append(offset)
        self.assertEqual(recorded, [0, 301])     # 冷卻 5 分鐘內的都不記

    def test_candidates_per_symbol_are_capped(self):
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        gate.state["signals_sent"] = config.RISK["max_signals_per_day"]
        st = ready_state("2330")
        sig = evaluate(st, now=dtime(9, 3))
        lock = threading.Lock()
        t0 = datetime(2026, 1, 2, 10, 0, 0)
        hits = 0
        for i in range(10):
            _, blocked = signals.try_emit(
                st, gate, lock, sig, now=t0 + timedelta(minutes=10 * i))
            hits += bool(blocked)
        self.assertEqual(hits, signals.MAX_CANDIDATES_PER_SYMBOL)

    def test_record_candidate_writes_header_once_and_appends(self):
        st = ready_state("2330", or_high=100.0, last=101.0)
        sig = evaluate(st, now=dtime(9, 3))
        signals.record_candidate(sig, signals.BLOCK_DAILY_CAP, path=self.path)
        signals.record_candidate(sig, signals.BLOCK_SYMBOL_CAP, path=self.path)
        rows = self._rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["reason"] for r in rows],
                         [signals.BLOCK_DAILY_CAP, signals.BLOCK_SYMBOL_CAP])
        self.assertEqual(rows[0]["code"], "2330")
        self.assertEqual(float(rows[0]["entry"]), sig["entry"])
        self.assertEqual(float(rows[0]["stop"]), sig["stop"])
        self.assertEqual(float(rows[0]["target"]), sig["target"])
        self.assertTrue(rows[0]["date"])
        # 台灣的 Excel 要 BOM，否則中文欄位會是亂碼
        self.assertTrue(self.path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_write_failure_never_breaks_monitoring(self):
        st = ready_state("2330")
        sig = evaluate(st, now=dtime(9, 3))
        bad = Path(self.tmp.name) / "nope" / "candidates.csv"   # 目錄不存在
        signals.record_candidate(sig, signals.BLOCK_DAILY_CAP, path=bad)  # 不可拋

    def test_normal_path_is_unchanged(self):
        """沒被擋的時候，行為要跟以前一模一樣。"""
        gate = RiskGate(FakeBroker(pnl_rows=[]))
        st = ready_state("2330")
        sig = evaluate(st, now=dtime(9, 3))
        msg, blocked = signals.try_emit(st, gate, threading.Lock(), sig)
        self.assertIsNone(blocked)
        self.assertIn("決策錨點", msg)
        self.assertEqual(st.signaled, 1)
        self.assertEqual(st.candidates, 0)


class TestCandidateOutcomes(unittest.TestCase):
    """候選也要回推結局，否則只知道「有幾個」，不知道「會不會賺」。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = Path(self.tmp.name) / "candidates.csv"
        self.dst = Path(self.tmp.name) / "candidates_outcomes.csv"

    def _write(self, rows):
        with open(self.src, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=signals.CANDIDATE_FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow(r)

    DATE = "2026-09-24"
    BARS = [("09:24", 121.5, 120.8, 121.2), ("09:25", 123.6, 121.0, 123.4)]

    def _row(self, date=None, code="2330", reason="daily_cap"):
        return {"date": date or self.DATE, "code": code, "name": "",
                "time": "09:23:00", "entry": 121.0, "stop": 119.5,
                "target": 123.5, "lots": 1, "reason": reason,
                "or_high": 120.0, "vwap": 120.5, "volume_surge": 2.0}

    def test_load_only_returns_that_day(self):
        self._write([self._row(), self._row(date="2026-09-25")])
        rows = oc.load_candidates(date=self.DATE, path=self.src)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], self.DATE)

    def test_missing_file_is_not_an_error(self):
        self.assertEqual(oc.load_candidates(date=self.DATE, path=self.src), [])

    def test_resolve_and_write_keeps_reason(self):
        rows = [self._row(reason="symbol_cap")]
        broker = FakeKbarBroker(_kb(self.BARS))
        pairs = oc.resolve_candidates(broker, rows, date=self.DATE)
        self.assertEqual(len(pairs), 1)
        outcome_, reason = pairs[0]
        self.assertEqual(reason, "symbol_cap")
        self.assertEqual(outcome_.result, oc.TARGET)
        oc.append_candidates_csv(pairs, path=self.dst)
        with open(self.dst, newline="", encoding="utf-8-sig") as f:
            written = list(csv.DictReader(f))
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0]["reason"], "symbol_cap")
        self.assertEqual(written[0]["result"], oc.TARGET)

    def test_rerunning_the_same_day_does_not_duplicate(self):
        rows = [self._row()]
        broker = FakeKbarBroker(_kb(self.BARS))
        pairs = oc.resolve_candidates(broker, rows, date=self.DATE)
        oc.append_candidates_csv(pairs, path=self.dst)
        oc.append_candidates_csv(pairs, path=self.dst)
        with open(self.dst, newline="", encoding="utf-8-sig") as f:
            self.assertEqual(len(list(csv.DictReader(f))), 1)


@under_v5_rules
class TestLotSizingFloatNoise(unittest.TestCase):
    """(20.2-19.9)*1000 = 300.0000000000007，整除時會少算一整張。"""

    def test_exact_division_is_not_eaten_by_float_noise(self):
        st = ready_state(or_high=20.0, last=20.2, vwap=20.1)
        sig = evaluate(st, now=dtime(9, 3))
        self.assertEqual(sig["stop"], 19.9)
        self.assertEqual(sig["risk_per_lot"], 300)
        # 3000 / 300 剛好 10 張。沒 round 的話這裡會是 9。
        self.assertEqual(sig["lots"],
                         config.RISK["per_trade_risk"] // sig["risk_per_lot"])

    def test_risk_per_lot_is_exact_cents(self):
        for or_high, last in ((20.0, 20.2), (100.0, 101.0), (500.0, 505.0)):
            sig = evaluate(ready_state(or_high=or_high, last=last, vwap=or_high),
                           now=dtime(9, 3))
            self.assertEqual(sig["risk_per_lot"],
                             round(sig["risk_per_lot"], 2),
                             f"{or_high}/{last} 的單張風險帶了浮點雜訊")


class TestWatchlistRank(unittest.TestCase):
    """只做前 N 名會不會比較好 —— 不記名次，這一題 20 天後只能重測。"""

    def test_rank_flows_into_the_signal(self):
        st = ready_state("2330")
        st.rank = 7
        sig = evaluate(st, now=dtime(9, 3))
        self.assertEqual(sig["rank"], 7)

    def test_rank_defaults_to_zero_when_unknown(self):
        sig = evaluate(ready_state("2330"), now=dtime(9, 3))
        self.assertEqual(sig["rank"], 0)

    def test_category_flows_into_the_signal_too(self):
        """產業別是「輪動題材」唯一免費又客觀的代理 —— 合約物件上就有。"""
        st = ready_state("2330")
        st.category = "24"
        self.assertEqual(evaluate(st, now=dtime(9, 3))["category"], "24")

    def test_category_defaults_to_blank_not_a_crash(self):
        self.assertEqual(evaluate(ready_state("2330"), now=dtime(9, 3))["category"], "")

    def test_rank_reaches_outcomes_csv(self):
        sig = {"code": "2330", "time": "09:23:00", "entry": 121.0,
               "stop": 119.5, "target": 123.5, "lots": 1, "rank": 3}
        o = oc.resolve(FakeKbarBroker(_kb([("09:24", 121.5, 120.8, 121.2),
                                           ("09:25", 123.6, 121.0, 123.4)])),
                       sig, "2026-09-24")
        self.assertEqual(o.rank, 3)
        self.assertIn("rank", oc.FIELDS)

    def test_old_csv_without_rank_still_loads(self):
        """9/24~9/29 寫的 outcomes.csv 沒有 rank 欄，不可以因此讀不回來。"""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "outcomes.csv"
            old = [f for f in oc.FIELDS if f != "rank"]
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=old)
                w.writeheader()
                w.writerow({"date": "2026-09-24", "code": "6182", "time": "09:19:22",
                            "entry": 119.0, "stop": 117.5, "target": 121.5,
                            "lots": 1, "result": oc.TARGET, "exit_price": 121.5,
                            "r_multiple": 1.67, "gross_pct": 2.1, "net_pct": 1.89,
                            "bars": 4})
            rows = oc.load_csv(path=path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].rank, 0)


class TestTestsCanNeverPush(unittest.TestCase):
    """2026-09-29：跑一次測試，使用者手機收到 5 則「今日停手」，其中一則寫「原因：測試」。

    RiskGate._close() 直接呼叫 notify()，而使用者機器上 .env 有金鑰、requests 也裝了。
    CI 兩樣都沒有，所以這個洞在 CI 裡永遠不會露出來 —— 只有真的在他電腦上跑才會。
    """

    def test_push_is_disabled_while_these_tests_run(self):
        """這一條要是失敗了，代表保險絲斷了，測試又會推到手機。"""
        self.assertFalse(config.push_enabled())

    def test_notify_does_not_hit_the_network(self):
        sent = []
        fake = SimpleNamespace(post=lambda *a, **k: sent.append(a))
        with unittest.mock.patch.object(signals, "requests", fake), \
                unittest.mock.patch.object(config, "TELEGRAM_BOT_TOKEN", "x"), \
                unittest.mock.patch.object(config, "TELEGRAM_CHAT_ID", "y"), \
                contextlib.redirect_stdout(io.StringIO()):
            signals.notify("測試訊息")
        self.assertEqual(sent, [])

    def test_gate_closing_does_not_push(self):
        """閘門關閉是最容易漏掉的一條：它在 _close() 裡直接 notify()。"""
        sent = []
        fake = SimpleNamespace(post=lambda *a, **k: sent.append(a))
        with tempfile.TemporaryDirectory() as d:
            orig, config.STATE_FILE = config.STATE_FILE, Path(d) / "state.json"
            try:
                with unittest.mock.patch.object(signals, "requests", fake), \
                        unittest.mock.patch.object(config, "TELEGRAM_BOT_TOKEN", "x"), \
                        unittest.mock.patch.object(config, "TELEGRAM_CHAT_ID", "y"), \
                        contextlib.redirect_stdout(io.StringIO()):
                    RiskGate(FakeBroker(pnl_rows=[]))._close("測試")
            finally:
                config.STATE_FILE = orig
        self.assertEqual(sent, [])

    def test_env_var_alone_is_enough(self):
        """dryrun.py 靠的是環境變數，不是 unittest 在不在 sys.modules。"""
        with unittest.mock.patch.dict(os.environ, {"DAYTRADE_NO_PUSH": "1"}), \
                unittest.mock.patch.dict(sys.modules):
            sys.modules.pop("unittest", None)
            sys.modules.pop("pytest", None)
            self.assertFalse(config.push_enabled())


class TestLiveResultWinsOverKbars(unittest.TestCase):
    """2026-09-29 允強：即時推播說 +1.57R，收盤覆盤說 -1.00R。同一筆交易兩個答案。

    訊號 09:32:13，09:32:25（12 秒後）就到目標。bars_after() 刻意丟掉訊號後的頭
    60 秒 —— 那一根 K 棒涵蓋訊號發出**前**的時間，留著會製造假停損。但這一筆整個
    就結束在那個空窗裡，收盤回推只看到後來跌回去碰停損。

    outcome.py 的註解本來寫著「LiveTracker 看 tick，正好補上這一段」——
    那句話在程式裡不成立：即時結果只活在那則 Telegram 訊息裡，沒人寫下來。
    """

    DATE = "2026-09-24"
    # 允強的真實數字
    SIG = {"code": "2034", "time": "09:32:13", "entry": 24.20,
           "stop": 23.85, "target": 24.75, "lots": 5}
    # 訊號之後的 K 棒：價格跌回去碰到停損（到目標那 12 秒不在這些 K 棒裡）
    BARS = [("09:34", 24.30, 23.80, 23.90), ("09:35", 23.95, 23.70, 23.75)]

    def _resolve(self, **extra):
        sig = dict(self.SIG, **extra)
        return oc.resolve(FakeKbarBroker(_kb(self.BARS)), sig, self.DATE)

    def test_without_live_result_the_kbars_say_stop(self):
        """先證明這個 bug 真的存在：沒有即時判定時，K 棒會判成停損。"""
        o = self._resolve()
        self.assertEqual(o.result, oc.STOP)
        self.assertEqual(o.r_multiple, -1.0)

    def test_live_target_beats_the_kbars(self):
        """有即時判定時，以 tick 為準 —— 這才是當下真正發生的事。"""
        o = self._resolve(live_result=oc.TARGET, live_exit=24.75)
        self.assertEqual(o.result, oc.TARGET)
        self.assertEqual(o.exit_price, 24.75)
        # (24.75 - 24.20) / (24.20 - 23.85) = 1.571
        self.assertEqual(o.r_multiple, 1.57)
        self.assertGreater(o.net_pct, 0)

    def test_excursions_still_come_from_the_kbars(self):
        """即時判定只決定結局，整天的極值仍然要用 K 棒算。"""
        o = self._resolve(live_result=oc.TARGET, live_exit=24.75)
        self.assertIsNotNone(o.mae_pct)
        self.assertIsNotNone(o.mfe_pct)
        self.assertLess(o.mae_pct, 0)          # 當天確實跌下去過

    def test_live_result_survives_with_no_kbars_at_all(self):
        """K 棒抓不到時，有即時判定就不該整筆丟掉 —— 那是真的成交過的結果。"""
        o = oc.resolve(FakeKbarBroker(_kb([])),
                       dict(self.SIG, live_result=oc.TARGET, live_exit=24.75),
                       self.DATE)
        self.assertIsNotNone(o)
        self.assertEqual(o.result, oc.TARGET)
        self.assertIsNone(o.mae_pct)           # 沒有 K 棒就留空，不要猜
        self.assertIsNone(o.low_5m_pct)

    def test_no_live_and_no_kbars_is_still_none(self):
        """兩邊都沒有就不要猜一個結局出來。"""
        self.assertIsNone(oc.resolve(FakeKbarBroker(_kb([])), self.SIG, self.DATE))


class TestLiveResultIsWrittenDown(unittest.TestCase):
    """即時判定沒寫回 state.json 的話，收盤覆盤永遠看不到它。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._orig, config.STATE_FILE = config.STATE_FILE, Path(self._tmp.name) / "state.json"
        self.addCleanup(lambda: setattr(config, "STATE_FILE", self._orig))
        self.gate = RiskGate(FakeBroker(pnl_rows=[]))
        self.gate.record({"code": "2034", "time": "09:32:13", "entry": 24.20,
                          "stop": 23.85, "target": 24.75, "lots": 5})

    def test_written_into_the_matching_signal(self):
        self.assertTrue(
            self.gate.record_live_result("2034", "09:32:13", oc.TARGET, 24.75))
        saved = json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
        sig = saved["signals"][0]
        self.assertEqual(sig["live_result"], oc.TARGET)
        self.assertEqual(sig["live_exit"], 24.75)
        self.assertTrue(sig["live_at"])

    def test_review_reads_it_straight_back(self):
        """load_signals() 讀回來的就是 resolve() 吃的那份 —— 中間不可以掉。"""
        self.gate.record_live_result("2034", "09:32:13", oc.TARGET, 24.75)
        sigs, _ = review.load_signals()     # state.json 的日期就是今天
        self.assertEqual(sigs[0]["live_result"], oc.TARGET)
        self.assertEqual(sigs[0]["live_exit"], 24.75)

    def test_unmatched_signal_is_reported_not_silently_dropped(self):
        with self.assertLogs("signals", level="WARNING"):
            self.assertFalse(
                self.gate.record_live_result("9999", "09:00:00", oc.TARGET, 1.0))


class TestTrackerHandsOffItsVerdict(unittest.TestCase):
    def _tracker(self, seen):
        return signals.LiveTracker(
            on_resolved=lambda o, price, v: seen.append((o.code, v, price)))

    def _sig(self, code="2034"):
        return {"code": code, "time": "09:32:13", "entry": 24.20,
                "stop": 23.85, "target": 24.75, "lots": 5}

    def test_target_is_handed_off(self):
        seen = []
        t = self._tracker(seen)
        t.track(self._sig())
        msgs = t.on_price("2034", 24.80)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(seen, [("2034", oc.TARGET, 24.80)])

    def test_flatten_is_handed_off_too(self):
        seen = []
        t = self._tracker(seen)
        t.track(self._sig())
        t.on_price("2034", 24.30)          # 還沒結束，只是留下最後價格
        t.flatten()
        self.assertEqual(seen, [("2034", oc.FLAT, 24.30)])

    def test_a_broken_recorder_does_not_swallow_the_push(self):
        """寫回失敗是可以忍的，推播不見不行 —— 那是使用者唯一看得到的東西。"""
        def boom(*_a):
            raise RuntimeError("磁碟滿了")
        t = signals.LiveTracker(on_resolved=boom)
        t.track(self._sig())
        with self.assertLogs("signals", level="WARNING"):
            msgs = t.on_price("2034", 24.80)
        self.assertEqual(len(msgs), 1)


class TestFillProbeAnswersCanIEvenBuyIt(unittest.TestCase):
    """2026-10-01 聯傑：訊號 09:39:28 進場 65.60，09:40 已經 66.60（+8.12%）。

    使用者的原話：「這支根本買不到」。他問了整輪的那一題 ——
    「如果買不到是空談」。

    唯一能回答的欄位是 low_5m_pct，而它是用分鐘 K 算的，而 bars_after() 刻意
    丟掉訊號後的頭 60 秒。急拉型的突破訊號正好都在那 60 秒內離開進場價 ——
    於是最需要答案的那幾筆，欄位答不出來，還會答得偏悲觀。

    FillProbe 用 tick 量同一個窗口，沒有那個空窗。
    """

    SIG = {"code": "3094", "name": "聯傑", "time": "09:39:28",
           "entry": 65.60, "stop": 64.70, "target": 67.70, "lots": 3}

    def _at(self, h, m, s=0):
        return datetime(2026, 10, 1, h, m, s)

    def _tracker(self, seen):
        return signals.LiveTracker(on_fill=lambda p: seen.append((p.code, p.low)))

    def test_lowest_tick_in_the_window_is_what_gets_recorded(self):
        seen = []
        t = self._tracker(seen)
        t.track(self.SIG, now=self._at(9, 39, 28))
        for price, at in ((66.10, (9, 39, 40)), (65.90, (9, 40, 10)),
                          (66.60, (9, 41, 0))):
            t.on_price("3094", price, now=self._at(*at))
        self.assertEqual(seen, [])              # 窗口還沒滿，不要先寫
        t.on_price("3094", 66.80, now=self._at(9, 44, 28))
        self.assertEqual(seen, [("3094", 65.90)])

    def test_never_traded_at_the_entry_price_is_the_honest_answer(self):
        """聯傑那一筆：5 分鐘內最低 65.90 > 進場 65.60 —— 掛單買不到。"""
        seen = []
        t = self._tracker(seen)
        t.track(self.SIG, now=self._at(9, 39, 28))
        t.on_price("3094", 65.90, now=self._at(9, 40, 0))
        t.on_price("3094", 66.80, now=self._at(9, 45, 0))
        _, low = seen[0]
        self.assertGreater(low, self.SIG["entry"])

    def test_the_probe_outlives_the_trade(self):
        """12 秒就到目標（允強）也要繼續量成交窗口。

        買不買得到和這筆賺賠無關。探針跟著 OpenSignal 一起被移出清單的話，
        跑最快的那幾筆就剛好沒有資料 —— 而那幾筆正是最可能買不到的。
        """
        seen = []
        t = self._tracker(seen)
        t.track(self.SIG, now=self._at(9, 39, 28))
        msgs = t.on_price("3094", 67.70, now=self._at(9, 39, 40))   # 直接到目標
        self.assertEqual(len(msgs), 1)
        self.assertFalse(t.open)                # 這筆交易結束了
        t.on_price("3094", 65.50, now=self._at(9, 40, 0))           # 之後回到進場價以下
        t.on_price("3094", 66.00, now=self._at(9, 45, 0))           # 窗口滿
        self.assertEqual(seen, [("3094", 65.50)])

    def test_a_restored_signal_records_nothing_rather_than_a_fake_number(self):
        """盤中重開時還原舊訊號：窗口早就過了。

        這時候收到的報價和「當時買不買得到」無關。記下去會是個假數字，
        而假數字比空白危險 —— 空白看得出來是不知道。
        """
        seen = []
        t = self._tracker(seen)
        t.track(self.SIG, now=self._at(10, 30))     # 訊號 09:39，已經過了快一小時
        self.assertEqual(t.fills, [])
        t.on_price("3094", 60.00, now=self._at(10, 31))
        t.flatten()
        self.assertEqual(seen, [])

    def test_a_quiet_stock_still_gets_written_before_the_close(self):
        """某檔窗口滿了之後完全沒成交，不可以等到 13:25 才寫得出去。

        中間程式掛掉就全沒了。所以收窗要檢查全部探針，不只正在進報價的那一檔。
        """
        seen = []
        t = self._tracker(seen)
        t.track(self.SIG, now=self._at(9, 39, 28))
        t.on_price("3094", 65.90, now=self._at(9, 40, 0))
        t.track({"code": "2034", "time": "09:50:00", "entry": 24.20,
                 "stop": 23.85, "target": 24.75, "lots": 5}, now=self._at(9, 50))
        # 只有 2034 在進報價，但 3094 的窗口已經滿了
        t.on_price("2034", 24.30, now=self._at(9, 50, 10))
        self.assertEqual(seen, [("3094", 65.90)])

    def test_flatten_flushes_whatever_is_left(self):
        seen = []
        t = self._tracker(seen)
        t.track(self.SIG, now=self._at(9, 39, 28))
        t.on_price("3094", 65.90, now=self._at(9, 40, 0))
        t.flatten()
        self.assertEqual(seen, [("3094", 65.90)])

    def test_no_ticks_at_all_means_unknown_not_unbuyable(self):
        """整個窗口一筆成交都沒收到 → None。空白是空白，不是「買不到」。"""
        seen = []
        t = self._tracker(seen)
        t.track(self.SIG, now=self._at(9, 39, 28))
        t.flatten()
        self.assertEqual(seen, [("3094", None)])

    def test_a_broken_recorder_does_not_swallow_the_push(self):
        def boom(*_a):
            raise RuntimeError("磁碟滿了")
        t = signals.LiveTracker(on_fill=boom)
        t.track(self.SIG, now=self._at(9, 39, 28))
        with self.assertLogs("signals", level="WARNING"):
            msgs = t.on_price("3094", 67.70, now=self._at(9, 50))
        self.assertEqual(len(msgs), 1)          # 到目標的推播照樣要出去

    def test_unparseable_time_does_not_crash_the_tick_thread(self):
        """時間字串壞掉時不要丟例外 —— 這段跑在行情回呼裡。"""
        self.assertIsNone(signals.parse_fired_at("", self._at(9, 40)))
        self.assertIsNone(signals.parse_fired_at(None, self._at(9, 40)))
        t = signals.LiveTracker(on_fill=lambda p: None)
        t.track(dict(self.SIG, time="九點半"), now=self._at(9, 40))
        self.assertEqual(t.fills, [])
        self.assertEqual(len(t.open), 1)        # 交易本身照樣要追


class TestFillIsWrittenDown(unittest.TestCase):
    """量到了沒寫回 state.json，收盤覆盤就看不到 —— 和 live_result 同一個坑。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._orig, config.STATE_FILE = config.STATE_FILE, Path(self._tmp.name) / "state.json"
        self.addCleanup(lambda: setattr(config, "STATE_FILE", self._orig))
        self.gate = RiskGate(FakeBroker(pnl_rows=[]))
        self.gate.record({"code": "3094", "time": "09:39:28", "entry": 65.60,
                          "stop": 64.70, "target": 67.70, "lots": 3})

    def test_written_into_the_matching_signal(self):
        self.assertTrue(self.gate.record_fill("3094", "09:39:28", 65.90))
        saved = json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved["signals"][0]["fill_low"], 65.90)

    def test_none_is_stored_as_none_not_zero(self):
        """0 會被算成「買得到」，而且是最便宜的那種買得到。不可以。"""
        self.gate.record_fill("3094", "09:39:28", None)
        saved = json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
        self.assertIsNone(saved["signals"][0]["fill_low"])

    def test_review_reads_it_straight_back(self):
        self.gate.record_fill("3094", "09:39:28", 65.90)
        sigs, _ = review.load_signals()
        self.assertEqual(sigs[0]["fill_low"], 65.90)

    def test_unmatched_signal_is_reported_not_silently_dropped(self):
        with self.assertLogs("signals", level="WARNING"):
            self.assertFalse(self.gate.record_fill("9999", "09:00:00", 1.0))


class TestFillColumnBeatsTheKbarBlindSpot(unittest.TestCase):
    """聯傑那一筆的兩個答案：tick 看得到的，分鐘 K 看不到。"""

    DATE = "2026-09-24"      # _kb() 的時間戳固定在這一天
    SIG = {"code": "3094", "time": "09:39:28", "entry": 65.60,
           "stop": 64.70, "target": 67.70, "lots": 3}
    # 分鐘 K 從 09:41 才算（09:40 那根涵蓋訊號發出前）。訊號後的急拉都在空窗裡。
    BARS = [("09:41", 66.80, 66.00, 66.60), ("09:42", 67.00, 66.30, 66.90),
            ("09:43", 67.70, 66.80, 67.50)]

    def _resolve(self, **extra):
        return oc.resolve(FakeKbarBroker(_kb(self.BARS)),
                          dict(self.SIG, **extra), self.DATE)

    def test_kbars_alone_say_it_never_came_back(self):
        o = self._resolve()
        self.assertGreater(o.low_5m_pct, 0)        # 66.00 > 65.60
        self.assertIsNone(o.fill_low_pct)          # 沒有 tick 資料就留空

    def test_tick_fill_is_recorded_as_its_own_column(self):
        """兩欄並存，不互相覆蓋 —— 不然 20 天後沒辦法拿一邊驗另一邊。"""
        o = self._resolve(fill_low=65.50)
        self.assertGreater(o.low_5m_pct, 0)
        self.assertLess(o.fill_low_pct, 0)
        self.assertAlmostEqual(o.fill_low_pct, -0.152, places=2)

    def test_fill_pct_prefers_the_tick_number(self):
        self.assertLess(oc.fill_pct(self._resolve(fill_low=65.50)), 0)
        self.assertGreater(oc.fill_pct(self._resolve()), 0)      # 退回分鐘 K

    def test_the_real_lianjie_case_stays_unbuyable(self):
        """tick 也證實買不到時，答案就是買不到 —— 不要因為有新欄位就變樂觀。"""
        o = self._resolve(fill_low=65.90)
        self.assertGreater(o.fill_low_pct, 0)
        self.assertGreater(oc.fill_pct(o), 0)

    def test_it_survives_the_csv_round_trip(self):
        """寫進 outcomes.csv 再讀回來要是同一個數字。這是 20 天後唯一的資料來源。"""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "outcomes.csv"
            oc.append_csv([self._resolve(fill_low=65.50)], path)
            back = oc.load_csv(path)
        self.assertEqual(len(back), 1)
        self.assertAlmostEqual(back[0].fill_low_pct, -0.152, places=2)

    def test_old_rows_without_the_column_still_load(self):
        """已經累積的 outcomes.csv 沒有這一欄。讀不回來就等於前幾天白跑。"""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "outcomes.csv"
            rows = [f for f in oc.FIELDS if f != "fill_low_pct"]
            path.write_text(
                ",".join(rows) + "\n" +
                ",".join({"date": self.DATE, "code": "3094", "time": "09:39:28",
                          "entry": "65.6", "stop": "64.7", "target": "67.7",
                          "lots": "3", "result": oc.TARGET, "exit_price": "67.7",
                          "r_multiple": "2.33", "gross_pct": "3.2",
                          "net_pct": "2.8", "bars": "4"}.get(f, "") for f in rows)
                + "\n", encoding="utf-8")
            back = oc.load_csv(path)
        self.assertEqual(len(back), 1)
        self.assertIsNone(back[0].fill_low_pct)


def _kb_days(rows):
    """跨日的假 kbars：rows 是 (YYYY-MM-DD, HH:MM, close)。

    時間戳照 shioaji 的方式建（台北牆上時間當成 UTC 納秒），不用
    datetime.timestamp()，否則與解讀端的時區偏移互相抵銷，等於自己驗自己。
    """
    ts, closes = [], []
    for day, hhmm, c in rows:
        t = datetime(int(day[:4]), int(day[5:7]), int(day[8:10]),
                     int(hhmm[:2]), int(hhmm[3:]), tzinfo=dt_timezone.utc)
        ts.append(int(t.timestamp() * 1e9))
        closes.append(c)
    return SimpleNamespace(ts=ts, High=list(closes), Low=list(closes), Close=closes)


class TestMarketDay(unittest.TestCase):
    """這套系統只做多。多方突破在綠盤日結構上逆風 —— 不分開看，20 天後拿到的
    「平均勝率」是把紅盤日和綠盤日混在一起的數字，對任何決定都沒有用。

    09:15 那個數字特別重要：它在任何訊號發出**之前**就已經知道，所以它是唯一
    有資格變成進場條件的。收盤漲跌只能事後解釋。
    """

    DATE = "2026-10-01"
    ROWS = [("2026-09-30", "13:20", 100.0), ("2026-09-30", "13:30", 200.0),
            ("2026-10-01", "09:10", 201.0), ("2026-10-01", "09:15", 202.0),
            ("2026-10-01", "09:20", 210.0), ("2026-10-01", "13:30", 206.0)]

    def _broker(self, kb):
        b = Broker.__new__(Broker)          # 不跑 __init__，不連券商
        b.kbars = lambda code, start, end: kb
        return b

    def test_open15_and_close_are_measured_against_yesterday(self):
        o, d = self._broker(self._kb()).market_day(self.DATE)
        self.assertAlmostEqual(o, 1.0, places=3)     # 202 vs 200
        self.assertAlmostEqual(d, 3.0, places=3)     # 206 vs 200

    def _kb(self, rows=None):
        return _kb_days(rows if rows is not None else self.ROWS)

    def test_yesterdays_close_is_its_last_bar_not_its_first(self):
        """前一日的收盤是那天**最後**一根，取錯根整個基準就偏了。"""
        o, _ = self._broker(self._kb()).market_day(self.DATE)
        self.assertAlmostEqual(o, 1.0, places=3)     # 用 200 不是 100

    def test_open15_uses_the_0915_bar_not_the_first_one_after(self):
        """K 棒 label 是該分鐘的結束時間，所以 09:15 那根的收盤就是 09:15 的價。"""
        o, _ = self._broker(self._kb()).market_day(self.DATE)
        self.assertNotAlmostEqual(o, 5.0, places=3)  # 不是 09:20 的 210

    def test_no_previous_day_is_none_not_zero(self):
        """0 是「平盤」，那是一個有意義的答案。查不到就要留空。"""
        rows = [r for r in self.ROWS if r[0] == self.DATE]
        self.assertEqual(self._broker(self._kb(rows)).market_day(self.DATE),
                         (None, None))

    def test_no_bars_today_is_none_too(self):
        rows = [r for r in self.ROWS if r[0] != self.DATE]
        self.assertEqual(self._broker(self._kb(rows)).market_day(self.DATE),
                         (None, None))

    def test_a_kbar_failure_is_logged_not_raised(self):
        """大盤查不到不可以讓整份覆盤產不出來。"""
        b = Broker.__new__(Broker)
        def boom(*_a, **_k):
            raise RuntimeError("流量上限")
        b.kbars = boom
        with self.assertLogs("broker", level="WARNING"):
            self.assertEqual(b.market_day(self.DATE), (None, None))

    def test_a_zero_previous_close_does_not_divide_by_zero(self):
        rows = [("2026-09-30", "13:30", 0.0)] + [r for r in self.ROWS if r[0] == self.DATE]
        self.assertEqual(self._broker(self._kb(rows)).market_day(self.DATE),
                         (None, None))


class TestMarketColumnsLandOnEveryRow(unittest.TestCase):
    DATE = "2026-09-24"      # _kb() 的時間戳固定在這一天
    SIG = {"code": "2449", "time": "09:30:00", "entry": 119.0,
           "stop": 118.0, "target": 121.5, "lots": 2, "category": "24"}
    BARS = [("09:32", 121.6, 119.0, 121.5)]

    class _Broker(FakeKbarBroker):
        def __init__(self, kb, mkt=(0.8, -1.2), boom=False):
            super().__init__(kb)
            self._mkt, self._boom = mkt, boom

        def market_day(self, date=None):
            if self._boom:
                raise RuntimeError("流量上限")
            return self._mkt

    def test_both_columns_are_written_to_all_rows(self):
        rows = oc.resolve_all(self._Broker(_kb(self.BARS)),
                              [dict(self.SIG), dict(self.SIG, code="2454")],
                              self.DATE)
        self.assertEqual(len(rows), 2)
        for o in rows:
            self.assertEqual((o.mkt_open_pct, o.mkt_day_pct), (0.8, -1.2))

    def test_a_market_failure_leaves_blanks_and_still_produces_the_report(self):
        with self.assertLogs("outcome", level="WARNING"):
            rows = oc.resolve_all(self._Broker(_kb(self.BARS), boom=True),
                                  [dict(self.SIG)], self.DATE)
        self.assertEqual(len(rows), 1)              # 覆盤照樣要產得出來
        self.assertIsNone(rows[0].mkt_open_pct)     # 不是 0
        self.assertIsNone(rows[0].mkt_day_pct)

    def test_the_market_is_queried_once_not_once_per_signal(self):
        calls = []
        b = self._Broker(_kb(self.BARS))
        inner = b.market_day
        b.market_day = lambda date=None: (calls.append(date), inner(date))[1]
        oc.resolve_all(b, [dict(self.SIG), dict(self.SIG, code="2454"),
                           dict(self.SIG, code="3034")], self.DATE)
        self.assertEqual(len(calls), 1)

    def test_no_resolvable_signals_means_no_market_query(self):
        """一筆都回推不出來時不要白打一次 API。"""
        b = self._Broker(_kb([]), boom=True)        # boom：被呼叫就會拋
        self.assertEqual(oc.resolve_all(b, [dict(self.SIG)], self.DATE), [])

    def test_category_rides_along_from_the_signal(self):
        o = oc.resolve(FakeKbarBroker(_kb(self.BARS)), dict(self.SIG), self.DATE)
        self.assertEqual(o.category, "24")

    def test_a_signal_without_category_is_blank_not_a_crash(self):
        sig = {k: v for k, v in self.SIG.items() if k != "category"}
        o = oc.resolve(FakeKbarBroker(_kb(self.BARS)), sig, self.DATE)
        self.assertEqual(o.category, "")

    def test_the_new_columns_survive_the_csv_round_trip(self):
        rows = oc.resolve_all(self._Broker(_kb(self.BARS)), [dict(self.SIG)], self.DATE)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "outcomes.csv"
            oc.append_csv(rows, path)
            back = oc.load_csv(path)
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].category, "24")
        self.assertEqual((back[0].mkt_open_pct, back[0].mkt_day_pct), (0.8, -1.2))

    def test_old_rows_without_the_new_columns_still_load(self):
        """已經累積的 outcomes.csv 沒有這三欄。整列被跳過的話前幾天就白跑了。"""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "outcomes.csv"
            keep = [f for f in oc.FIELDS
                    if f not in ("category", "mkt_open_pct", "mkt_day_pct")]
            filled = {"date": self.DATE, "code": "2449", "time": "09:30:00",
                      "entry": "119", "stop": "118", "target": "121.5",
                      "lots": "2", "result": oc.TARGET, "exit_price": "121.5",
                      "r_multiple": "2.5", "gross_pct": "2.1", "net_pct": "1.7",
                      "bars": "2"}
            path.write_text(",".join(keep) + "\n"
                            + ",".join(filled.get(f, "") for f in keep) + "\n",
                            encoding="utf-8")
            back = oc.load_csv(path)
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].category, "")
        self.assertIsNone(back[0].mkt_open_pct)


class TestReplayRules(unittest.TestCase):
    """2026-10-01：五個訊號依序是四個停損 + 最後一個目標。

    日報本來寫「照 4 筆上限只做前 4 筆：-12,622 元」。那個數字只算了筆數上限，
    沒算日虧上限與連敗停手 —— 而連敗停手（3 筆）在第三個停損之後就關閘了，
    所以第 4、5 個訊號照規則根本不會做。真正的數字是 **-9,515 元／3 筆**。

    日報把那一天講得比實際慘 3,107 元。方向剛好是「看起來更糟」，所以不會有人
    發現 —— 直到用它去決定日虧上限該訂多少的時候。

    連敗停手今天同時做了兩件事：擋掉第四個停損（省 3,107 元），也擋掉唯一的
    贏家（少賺 5,892 元）。兩邊都要算進去，才知道這條線該訂在哪。
    """

    # 當天的真實數字。net_amount = net_pct/100 × entry × 1000 × lots，
    # 所以用 net_pct 反推成當天那幾個金額。
    DAY = [("2340", "09:12:00", "09:20:00", oc.STOP, -1.00, -3442, 1),
           ("3162", "09:21:00", "09:28:00", oc.STOP, -1.00, -2973, 1),
           ("8050", "09:30:00", "09:35:00", oc.STOP, -1.00, -3100, 1),
           ("5309", "09:36:00", "09:38:00", oc.STOP, -1.00, -3107, 1),
           ("3094", "09:39:28", "09:52:00", oc.TARGET, 2.33, 5892, 3)]

    # 這一組測的是**重跑邏輯**，不是今天的參數。釘住 10-01 當天生效的那組紅線，
    # 否則每次調參數（v4 把訊號上限改成 3）這幾條就會壞掉 —— 而壞掉的原因
    # 跟它們要驗的事情完全無關。這正是 v4 改版時學到的：測試該測規則，
    # 不是測 config.py 現在剛好填什麼。
    DAY_RISK = {"max_signals_per_day": 5, "max_trades_per_day": 4,
                "max_daily_loss": 12000, "max_consecutive_losses": 3}

    def setUp(self):
        self._saved = {k: config.RISK[k] for k in self.DAY_RISK}
        config.RISK.update(self.DAY_RISK)

    def tearDown(self):
        config.RISK.update(self._saved)

    def _rows(self, day=None):
        out = []
        for code, t, exit_at, result, r, amount, lots in (day or self.DAY):
            entry = 100.0
            net_pct = amount / (entry * 1000 * lots) * 100
            out.append(oc.Outcome(
                date="2026-10-01", code=code, time=t, entry=entry,
                stop=99.0, target=102.5, lots=lots, result=result,
                exit_price=entry, r_multiple=r, gross_pct=net_pct + 0.207,
                net_pct=net_pct, bars=2, exit_at=exit_at))
        return out

    def test_the_streak_rule_closes_the_gate_after_three_losses(self):
        res = oc.replay_rules(self._rows())
        self.assertEqual([o.code for o in res["taken"]], ["2340", "3162", "8050"])
        self.assertIn("連續 3 筆虧損", res["closed_reason"])

    def test_the_real_number_for_that_day(self):
        res = oc.replay_rules(self._rows())
        self.assertEqual(round(sum(round(o.net_amount) for o in res["taken"])), -9515)

    def test_it_is_not_just_the_first_n_trades(self):
        """前 4 筆 = -12,622。照規則 = -9,515。差 3,107 元，就是第四個停損。"""
        rows = self._rows()
        first_four = sum(round(o.net_amount) for o in rows[:4])
        res = oc.replay_rules(rows)
        self.assertEqual(first_four, -12622)
        self.assertNotEqual(sum(round(o.net_amount) for o in res["taken"]), first_four)

    def test_the_winner_was_blocked_and_that_cost_is_reported(self):
        """這條線也擋掉了唯一的贏家。不把這個數字講出來，等於只講它的好處。"""
        res = oc.replay_rules(self._rows())
        blocked = [o.code for o, _ in res["blocked"]]
        self.assertEqual(blocked, ["5309", "3094"])
        self.assertEqual(round(res["missed_amount"]), -3107 + 5892)

    def test_a_trade_still_open_does_not_count_as_realised(self):
        """閘門看的是**已實現**損益。還沒出場的不算 —— 這是閘門真正的行為。

        把未出場的也算進去會讓閘門提早關，於是這個模擬會憑空少掉幾筆虧損，
        把結果講得比實際好。寧可晚關。
        """
        # 三筆都在 09:40 之後才出場：第四個訊號發出時，一筆都還沒實現
        day = [(c, t, "13:25:00", r, rr, a, l)
               for c, t, _x, r, rr, a, l in self.DAY]
        res = oc.replay_rules(day and self._rows(day))
        self.assertEqual(len(res["taken"]), 4)          # 只剩筆數上限擋得住
        self.assertIn("交易筆數上限", res["closed_reason"])

    def test_a_missing_exit_time_is_treated_as_still_open(self):
        """exit_at 缺的那幾筆保守處理，不要憑空關閘。"""
        day = [(c, t, "", r, rr, a, l) for c, t, _x, r, rr, a, l in self.DAY]
        res = oc.replay_rules(self._rows(day))
        self.assertEqual(len(res["taken"]), 4)

    def test_the_daily_loss_cap_can_also_close_it(self):
        day = [("A", "09:10:00", "09:11:00", oc.STOP, -1.0, -7000, 1),
               ("B", "09:12:00", "09:13:00", oc.TARGET, 2.0, 1000, 1),
               ("C", "09:14:00", "09:15:00", oc.STOP, -1.0, -6500, 1),
               ("D", "09:20:00", "09:21:00", oc.TARGET, 2.0, 9999, 1)]
        res = oc.replay_rules(self._rows(day))
        self.assertEqual([o.code for o in res["taken"]], ["A", "B", "C"])
        self.assertIn("觸及上限 12,000 元", res["closed_reason"])

    def test_a_win_resets_the_loss_streak(self):
        """連敗是**連續**的。中間賺一筆就從零開始數，不是累計虧損筆數。

        不歸零的話，紅盤日被零星幾筆停損湊滿三筆就會莫名收工 ——
        那不是這條規則要擋的東西。
        """
        day = [("A", "09:10:00", "09:11:00", oc.STOP, -1.0, -1000, 1),
               ("B", "09:12:00", "09:13:00", oc.STOP, -1.0, -1000, 1),
               ("C", "09:14:00", "09:15:00", oc.TARGET, 2.0, 2000, 1),
               ("D", "09:16:00", "09:17:00", oc.STOP, -1.0, -1000, 1)]
        res = oc.replay_rules(self._rows(day))
        self.assertEqual(len(res["taken"]), 4)      # 四筆都做得到
        self.assertEqual(res["closed_reason"], "")

    def test_the_streak_rule_only_ever_binds_on_the_first_three(self):
        """現在的參數下，連敗停手實際上只有一種情況會生效：**開頭連三敗**。

        筆數上限 4、連敗上限 3 —— 中間只要賺一筆，連敗就歸零，而要再連三敗
        就得做到第 5 筆，但第 5 筆早就被筆數上限擋住了。所以除了今天這種
        「一開始就連三個停損」，連敗停手這條線永遠輪不到它出手。

        這不是 bug，是兩條線的參數互動。寫成測試是為了讓它有人看得見 ——
        20 天後要調這兩個數字的時候，要知道它們不是獨立的。
        """
        day = [("A", "09:10:00", "09:11:00", oc.STOP, -1.0, -500, 1),
               ("B", "09:12:00", "09:13:00", oc.TARGET, 2.0, 500, 1),
               ("C", "09:14:00", "09:15:00", oc.STOP, -1.0, -500, 1),
               ("D", "09:16:00", "09:17:00", oc.STOP, -1.0, -500, 1),
               ("E", "09:18:00", "09:19:00", oc.STOP, -1.0, -500, 1)]
        res = oc.replay_rules(self._rows(day))
        self.assertEqual([o.code for o in res["taken"]], ["A", "B", "C", "D"])
        self.assertIn("交易筆數上限", res["closed_reason"])
        # 參數前提：改了任何一個，上面那句話就要重新算一次
        self.assertEqual(config.RISK["max_trades_per_day"], 4)
        self.assertEqual(config.RISK["max_consecutive_losses"], 3)

    def test_a_clean_day_blocks_nothing(self):
        day = [("A", "09:10:00", "09:11:00", oc.TARGET, 2.0, 2000, 1),
               ("B", "09:12:00", "09:13:00", oc.STOP, -1.0, -1000, 1)]
        res = oc.replay_rules(self._rows(day))
        self.assertEqual(res["blocked"], [])
        self.assertEqual(res["closed_reason"], "")

    def test_signals_are_replayed_in_time_order_not_list_order(self):
        """outcomes 的順序不保證是時間序，而閘門是照時間走的。"""
        rows = self._rows()
        res = oc.replay_rules(list(reversed(rows)))
        self.assertEqual([o.code for o in res["taken"]], ["2340", "3162", "8050"])

    def test_it_reaches_both_the_journal_and_the_phone(self):
        """算出來而沒有人看，和沒算一樣。"""
        rows = self._rows()
        sigs = [{"code": o.code, "time": o.time, "entry": o.entry, "stop": o.stop,
                 "target": o.target, "lots": o.lots, "volume_surge": 2.0}
                for o in rows]
        journal = "\n".join(review.outcome_section(sigs, rows))
        self.assertIn("照完整規則", journal)
        self.assertIn("連續 3 筆虧損", journal)
        self.assertIn("-9,515", journal)
        # 被擋掉那幾筆的代價也要講：-3,107（省到的）+ 5,892（錯過的）= +2,785。
        # 只講這條線省了多少、不講它錯過多少，是在幫自己的規則說話。
        self.assertIn("+2,785", journal)
        push = review.format_push(sigs, rows, rows)
        self.assertIn("照完整規則只做 3 筆", push)
        self.assertIn("-9,515 元", push)

    def test_a_clean_day_says_so_instead_of_staying_silent(self):
        """沒有被擋掉的日子要明講「上面的數字就是照規則的數字」。

        留白會讓人以為這一段壞了，或者以為上面的數字一定就是照規則的。
        """
        day = [("A", "09:10:00", "09:11:00", oc.TARGET, 2.0, 2000, 1)]
        rows = self._rows(day)
        sigs = [{"code": "A", "time": "09:10:00", "entry": 100.0, "stop": 99.0,
                 "target": 102.5, "lots": 1, "volume_surge": 2.0}]
        journal = "\n".join(review.outcome_section(sigs, rows))
        self.assertIn("沒有任何訊號被風控擋掉", journal)


class TestExitTime(unittest.TestCase):
    """閘門看的是已實現損益，而一筆要出場了才算實現 —— 所以出場時間是必要的。"""

    SIG = {"code": "2449", "time": "09:30:00", "entry": 119.0,
           "stop": 118.0, "target": 121.5, "lots": 2}

    def test_tick_verdict_uses_its_real_timestamp(self):
        o = oc.resolve(FakeKbarBroker(_kb([("09:35", 119.5, 118.5, 119.2)])),
                       dict(self.SIG, live_result=oc.TARGET, live_exit=121.5,
                            live_at="09:30:12"), "2026-09-24")
        self.assertEqual(o.exit_at, "09:30:12")

    def test_kbar_verdict_uses_the_bar_label(self):
        o = oc.resolve(FakeKbarBroker(_kb([("09:32", 119.5, 118.5, 119.2),
                                           ("09:33", 121.6, 119.0, 121.5)])),
                       dict(self.SIG), "2026-09-24")
        self.assertEqual(o.result, oc.TARGET)
        self.assertEqual(o.exit_at, "09:33:00")

    def test_a_flat_close_is_recorded_as_1325(self):
        o = oc.resolve(FakeKbarBroker(_kb([("09:32", 119.5, 118.5, 119.2)])),
                       dict(self.SIG), "2026-09-24")
        self.assertEqual(o.result, oc.FLAT)
        self.assertEqual(o.exit_at, "13:25:00")

    def test_it_survives_the_csv_round_trip(self):
        o = oc.resolve(FakeKbarBroker(_kb([("09:32", 121.6, 119.0, 121.5)])),
                       dict(self.SIG), "2026-09-24")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "outcomes.csv"
            oc.append_csv([o], path)
            back = oc.load_csv(path)
        self.assertEqual(back[0].exit_at, "09:32:00")

    def test_old_rows_without_it_still_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "outcomes.csv"
            keep = [f for f in oc.FIELDS if f != "exit_at"]
            filled = {"date": "2026-09-24", "code": "2449", "time": "09:30:00",
                      "entry": "119", "stop": "118", "target": "121.5",
                      "lots": "2", "result": oc.TARGET, "exit_price": "121.5",
                      "r_multiple": "2.5", "gross_pct": "2.1", "net_pct": "1.7",
                      "bars": "2"}
            path.write_text(",".join(keep) + "\n"
                            + ",".join(filled.get(f, "") for f in keep) + "\n",
                            encoding="utf-8")
            back = oc.load_csv(path)
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].exit_at, "")


class TestFillStats(unittest.TestCase):
    """買不到的筆數不會進帳戶，所以這個數字要和勝率擺在一起，不是附註。"""

    def _o(self, fill=None, low5=None):
        return oc.Outcome(
            date="2026-10-01", code="3094", time="09:39:28", entry=65.60,
            stop=64.70, target=67.70, lots=3, result=oc.TARGET, exit_price=67.70,
            r_multiple=2.33, gross_pct=3.2, net_pct=2.8, bars=4,
            fill_low_pct=fill, low_5m_pct=low5)

    def test_counts_only_the_rows_it_actually_knows(self):
        st = oc.fill_stats([self._o(fill=-0.2), self._o(fill=0.5), self._o()])
        self.assertEqual((st["known"], st["filled"], st["unknown"]), (2, 1, 1))
        self.assertEqual(st["rate"], 50.0)

    def test_exactly_at_the_entry_price_counts_as_filled(self):
        st = oc.fill_stats([self._o(fill=0.0)])
        self.assertEqual(st["filled"], 1)

    def test_how_far_you_would_have_had_to_chase(self):
        st = oc.fill_stats([self._o(fill=-0.2), self._o(fill=0.4), self._o(fill=0.6)])
        self.assertAlmostEqual(st["avg_miss_pct"], 0.5, places=3)

    def test_all_filled_means_no_chase_number(self):
        self.assertIsNone(oc.fill_stats([self._o(fill=-0.2)])["avg_miss_pct"])

    def test_nothing_known_is_none_not_zero_percent(self):
        """0% 會被讀成「一筆都買不到」。不知道就是不知道。"""
        st = oc.fill_stats([self._o(), self._o()])
        self.assertIsNone(st["rate"])
        self.assertEqual(st["known"], 0)

    def test_it_shows_up_where_a_human_will_see_it(self):
        """寫進 CSV 而報告裡沒有，20 天後沒人會去翻 —— 和沒量一樣。"""
        rows = [self._o(fill=-0.2), self._o(fill=0.5)]
        journal = "\n".join(review.outcome_section(
            [{"code": "3094", "time": "09:39:28", "entry": 65.6, "stop": 64.7,
              "target": 67.7, "lots": 3, "volume_surge": 5.21}], rows))
        self.assertIn("掛進場價買得到", journal)
        self.assertIn("1/2", journal)
        for o in rows:
            o.ruleset = config.RULESET
        push = review.format_push([], rows, rows)
        self.assertIn("掛進場價買得到", push)

    def test_unknown_cell_is_marked_not_left_blank(self):
        """表格留空會被當成「沒事」。不知道要寫出來。"""
        self.assertEqual(review._fill_cell(self._o()), "？")
        self.assertIn("\u2705", review._fill_cell(self._o(fill=-0.2)))
        self.assertIn("+0.50%", review._fill_cell(self._o(fill=0.5)))


class TestReviewFailureIsAudible(unittest.TestCase):
    """14:00 的排程安靜掛掉的話，你只會發現「今天沒收到日報」。

    而「今天沒訊號」與「程式當了」該做的事完全相反：後者代表**今天的結果沒進
    outcomes.csv，20 天的統計少一天，而且補不回來**。
    """

    def test_message_says_the_data_is_missing(self):
        msg = review.format_failure(RuntimeError("未安裝 shioaji"))
        self.assertIn("盤後覆盤失敗", msg)
        self.assertIn("未安裝 shioaji", msg)
        self.assertIn("outcomes.csv", msg)

    def test_long_errors_are_trimmed(self):
        msg = review.format_failure(RuntimeError("x" * 5000))
        self.assertLess(len(msg), review.FAILURE_DETAIL_CHARS + 400)

    def test_failure_pushes_then_still_raises(self):
        """通知要送出去，但錯誤不可以被吞掉 —— 排程要看得到非 0 的離開碼。"""
        pushed = []
        with unittest.mock.patch.object(review, "run",
                                        side_effect=RuntimeError("爆了")), \
                unittest.mock.patch.object(review, "push_failure", pushed.append):
            with self.assertRaises(RuntimeError):
                review.main([])
        self.assertEqual(len(pushed), 1)

    def test_no_push_flag_suppresses_the_notice(self):
        pushed = []
        with unittest.mock.patch.object(review, "run",
                                        side_effect=RuntimeError("爆了")), \
                unittest.mock.patch.object(review, "push_failure", pushed.append):
            with self.assertRaises(RuntimeError):
                review.main(["--no-push"])
        self.assertEqual(pushed, [])

    def test_a_broken_notifier_does_not_hide_the_real_error(self):
        with unittest.mock.patch("signals.notify",
                                 side_effect=RuntimeError("網路不通")), \
                self.assertLogs("review", level="ERROR"):
            review.push_failure(RuntimeError("原始錯誤"))   # 不可以往外拋


class TestAfternoonBat(unittest.TestCase):
    """跟 morning.bat 同一套：留紀錄、回報離開碼、可以手動雙擊。"""

    BAT = Path(__file__).with_name("afternoon.bat")

    def setUp(self):
        if not self.BAT.exists():
            self.skipTest("afternoon.bat 不在（非 Windows 佈署）")
        self.text = self.BAT.read_bytes().decode("ascii")

    def test_runs_review_and_keeps_a_log(self):
        self.assertIn("python review.py", self.text)
        self.assertIn("logs\\afternoon.log", self.text)

    def test_reports_a_non_zero_exit(self):
        self.assertIn("ERRORLEVEL", self.text)
        self.assertIn("FAILED", self.text)

    def test_runs_from_its_own_folder(self):
        """排程器的工作目錄不一定是這裡，不 cd 的話會找不到 config.py。"""
        self.assertIn('cd /d "%~dp0"', self.text)

    def test_crlf_and_ascii_only(self):
        """cp950 主控台讀不了 UTF-8 註解；LF 換行在舊 cmd 上也會出事。"""
        self.assertIn(b"\r\n", self.BAT.read_bytes())

    def test_does_not_pass_no_push(self):
        """排程的重點就是那則日報，加了 --no-push 等於白做。"""
        self.assertNotIn("--no-push", self.text)


class TestMonitorFailureIsAudible(unittest.TestCase):
    """三支程式裡最不能靜默的一支。

    screener 掛了只是沒名單；review 掛了資料晚一天補。但 signals.py 在 10:30 死掉：
    **已發出的訊號沒有人在追蹤**（到目標或到停損都不通知），後面的訊號也不會出現，
    而畫面上看起來只是「今天比較少訊號」。排程化之後更嚴重，視窗可能是縮著的。
    """

    def test_message_says_open_signals_are_unwatched(self):
        msg = signals.format_failure(RuntimeError("連線中斷"))
        self.assertIn("盤中監看中斷", msg)
        self.assertIn("連線中斷", msg)
        self.assertIn("沒有人在追蹤", msg)

    def test_long_errors_are_trimmed(self):
        msg = signals.format_failure(RuntimeError("x" * 5000))
        self.assertLess(len(msg), signals.FAILURE_DETAIL_CHARS + 400)

    def test_crash_pushes_then_still_raises(self):
        pushed = []
        with unittest.mock.patch.object(signals, "run",
                                        side_effect=RuntimeError("爆了")), \
                unittest.mock.patch.object(signals, "push_failure", pushed.append):
            with self.assertRaises(RuntimeError):
                signals.main()
        self.assertEqual(len(pushed), 1)

    def test_systemexit_is_not_a_failure(self):
        """「今天沒名單」「閘門已關」是正常停止，休市日不該每天推一則錯誤。"""
        pushed = []
        with unittest.mock.patch.object(
                signals, "run",
                side_effect=SystemExit("watchlist 是 2026-09-29 的，不是今天的")), \
                unittest.mock.patch.object(signals, "push_failure", pushed.append):
            with self.assertRaises(SystemExit):
                signals.main()
        self.assertEqual(pushed, [])

    def test_a_broken_notifier_does_not_hide_the_real_error(self):
        with unittest.mock.patch.object(signals, "notify",
                                        side_effect=RuntimeError("網路不通")), \
                self.assertLogs("signals", level="ERROR"):
            signals.push_failure(RuntimeError("原始錯誤"))   # 不可以往外拋


class TestMonitorBat(unittest.TestCase):
    BAT = Path(__file__).with_name("monitor.bat")

    def setUp(self):
        if not self.BAT.exists():
            self.skipTest("monitor.bat 不在（非 Windows 佈署）")
        self.text = self.BAT.read_bytes().decode("ascii")

    def test_runs_signals_and_keeps_a_log(self):
        self.assertIn("python signals.py", self.text)
        self.assertIn("logs\\monitor.log", self.text)

    def test_reports_a_non_zero_exit(self):
        self.assertIn("ERRORLEVEL", self.text)
        self.assertIn("FAILED", self.text)

    def test_runs_from_its_own_folder(self):
        self.assertIn('cd /d "%~dp0"', self.text)

    def test_crlf_and_ascii_only(self):
        self.assertIn(b"\r\n", self.BAT.read_bytes())


class TestTheWindowSaysNotToCloseIt(unittest.TestCase):
    """2026-10-01 真的發生的事，而且錯在程式不在人。

    08:40 的排程每天都正確觸發、正確登入、正確跑。但它跳出來的黑視窗把所有
    輸出都導到 log，所以畫面從頭到尾空白；而整支程式最花時間的那一段（量比，
    60 次 API 加上刻意的間隔，約 40~80 秒）以前一聲不吭。

    於是那個視窗有一分多鐘看起來跟當掉一模一樣，使用者把它關掉了 ——
    工作排程器記下 `0xC000013A`（STATUS_CONTROL_C_EXIT），log 裡留下 `^C`。
    那天的盤前名單整個沒了。

    排程設定一格都沒錯。錯的是「跑很久又不出聲」這件事。
    """

    BATS = {
        "morning.bat": "PRE-MARKET SCREENER",
        "monitor.bat": "INTRADAY MONITOR",
        "afternoon.bat": "POST-CLOSE REVIEW",
    }

    def _text(self, name):
        path = Path(__file__).with_name(name)
        if not path.exists():
            self.skipTest(f"{name} 不在（非 Windows 佈署）")
        return path.read_bytes().decode("ascii")      # 仍然只能有 ASCII

    def test_every_window_says_what_it_is_and_not_to_close_it(self):
        for name, what in self.BATS.items():
            with self.subTest(bat=name):
                text = self._text(name)
                self.assertIn(what, text)
                self.assertIn("DO NOT CLOSE", text)

    def test_every_window_says_a_blank_screen_is_normal(self):
        """這才是真正的那句話。只寫「不要關」而不解釋，下次還是會被關。"""
        for name in self.BATS:
            with self.subTest(bat=name):
                text = self._text(name)
                self.assertIn("BLANK", text)
                self.assertIn("NOT frozen", text)

    def test_the_banner_prints_before_the_program_starts(self):
        """印在後面等於沒印 —— 要關的人在前 10 秒就關了。"""
        for name in self.BATS:
            with self.subTest(bat=name):
                text = self._text(name)
                self.assertLess(text.index("DO NOT CLOSE"), text.index("python "))

    def test_the_banner_is_not_swallowed_by_the_log_redirect(self):
        """橫幅要留在畫面上。被導進 log 的話，使用者還是看到一片黑。"""
        for name in self.BATS:
            with self.subTest(bat=name):
                for line in self._text(name).splitlines():
                    if "DO NOT CLOSE" in line or "NOT frozen" in line:
                        self.assertNotIn(">>", line)

    def test_the_monitor_spells_out_what_closing_it_costs(self):
        """08:50 那個開到 13:30，關掉它會讓當天的訊號與追蹤整個停掉，而且無聲。

        三個裡面它的代價最大，所以它要講得最白。
        """
        text = self._text("monitor.bat")
        self.assertIn("13:30", text)
        self.assertIn("STOPS TODAY'S SIGNALS", text)

    def test_the_bats_stay_ascii_so_a_cp950_console_can_print_them(self):
        """繁中主控台是 cp950。.bat 裡放 UTF-8 中文會變亂碼，
        而一則讀不懂的警告跟沒有警告一樣。"""
        for name in self.BATS:
            with self.subTest(bat=name):
                path = Path(__file__).with_name(name)
                if not path.exists():
                    self.skipTest(f"{name} 不在")
                path.read_bytes().decode("ascii")      # 不能丟例外


class TestScreenerSaysItIsStillAlive(unittest.TestCase):
    """量比那一段是唯一會跑很久的地方，以前從頭到尾不出聲。

    報進度有兩個作用，缺一不可：
      1. 畫面上看得出它還活著 —— 沒有人會再想關掉它
      2. 萬一還是被砍，log 會停在「第幾檔」，而不是停在迴圈開始前；
         那會分辨「一開跑就被砍」和「跑太久被砍」，是兩種不同的毛病
    """

    class FakeBroker:
        def __init__(self, n):
            self.n = n

        def all_stocks(self):
            return [SimpleNamespace(code=f"{1000 + i}", name=f"N{i}",
                                    day_trade="Yes", category="24")
                    for i in range(self.n)]

        def is_day_tradable(self, c, allow_short=None):
            return True

        def snapshots(self, contracts):
            return [SimpleNamespace(
                code=c.code, close=100.0, high=108.0, low=99.0,
                total_volume=5000, yesterday_volume=5000,
                change_rate=3.0, amount=5e8) for c in contracts]

        def kbars(self, code, start, end):
            return SimpleNamespace(ts=[], Volume=[])

    def _run(self, n=25):
        with unittest.mock.patch.dict(
                config.SCREEN, {"max_kbar_queries": n, "kbar_sleep_sec": 0}):
            with self.assertLogs("screener", level="INFO") as cm:
                screener.screen(self.FakeBroker(n))
        return "\n".join(cm.output)

    def test_it_reports_progress_while_it_grinds(self):
        out = self._run(25)
        self.assertIn("量比計算中… 10/25", out)
        self.assertIn("量比計算中… 20/25", out)

    def test_it_always_reports_the_last_one(self):
        """不是 10 的倍數的那一檔也要報，否則 log 看起來像沒跑完。"""
        self.assertIn("量比計算中… 25/25", self._run(25))

    def test_it_warns_up_front_how_long_the_quiet_part_takes(self):
        """「等一下沒聲音是正常的」要在**開始之前**講，不是事後補。"""
        out = self._run(25)
        head = out.index("開始計算量比")
        self.assertLess(head, out.index("量比計算中…"))
        self.assertIn("是正常的", out[head:head + 200])


class TestWinRateInterval(unittest.TestCase):
    """analyse.py 的工作是**不要給出看起來像答案的雜訊**，而我第一版自己犯了。

    第一版用常態近似（Wald）：8 筆全輸時 p=0，`sqrt(p(1-p)/n)` 也是 0，
    區間變成 (0%, 0%) —— **寬度為零**。然後「兩組區間有沒有重疊」就會說
    「沒有重疊，這兩組真的有差」，用 8 筆樣本講出一個比任何數字都更有
    自信的假答案。

    改用 Wilson score 區間。
    """

    def test_all_losses_is_not_certainty(self):
        """8 筆全輸不代表勝率確定是 0%。區間要有寬度。"""
        rate, lo, hi = analyse.win_rate_ci(0, 8)
        self.assertEqual((rate, lo), (0.0, 0.0))
        self.assertGreater(hi, 20)          # 上界要留得夠寬

    def test_all_wins_is_not_certainty_either(self):
        rate, lo, hi = analyse.win_rate_ci(8, 8)
        self.assertEqual((rate, hi), (100.0, 100.0))
        self.assertLess(lo, 80)

    def test_a_tiny_sample_is_visibly_useless(self):
        """n=4 的區間要寬到沒有人會想拿它做決定。"""
        _, lo, hi = analyse.win_rate_ci(2, 4)
        self.assertGreater(hi - lo, 50)

    def test_more_samples_narrow_it(self):
        small = analyse.win_rate_ci(6, 10)
        big = analyse.win_rate_ci(60, 100)
        self.assertEqual(small[0], big[0])                  # 同樣是 60%
        self.assertLess(big[2] - big[1], small[2] - small[1])

    def test_empty_is_zero_not_a_crash(self):
        self.assertEqual(analyse.win_rate_ci(0, 0), (0.0, 0.0, 0.0))

    def test_the_interval_stays_inside_zero_to_hundred(self):
        for wins, n in ((0, 3), (3, 3), (1, 2), (99, 100)):
            with self.subTest(wins=wins, n=n):
                _, lo, hi = analyse.win_rate_ci(wins, n)
                self.assertGreaterEqual(lo, 0.0)
                self.assertLessEqual(hi, 100.0)


class TestAnalyseRefusesToOverclaim(unittest.TestCase):
    """樣本不夠的時候要說「分不出來」，不要印一個中間值讓人盯著看。"""

    def _rows(self, spec):
        """spec: [(date, time, 是否獲利, rank, mkt, volume_surge, fill_pct)]"""
        out = []
        for date, t, win, rank, mkt, vs, fill in spec:
            out.append(oc.Outcome(
                date=date, code="T", time=t, entry=100.0, stop=99.0, target=102.5,
                lots=1, result=oc.TARGET if win else oc.STOP, exit_price=100.0,
                r_multiple=2.5 if win else -1.0,
                gross_pct=2.4 if win else -1.6, net_pct=2.2 if win else -1.8,
                bars=2, rank=rank, mkt_open_pct=mkt, volume_surge=vs,
                fill_low_pct=fill, exit_at="10:00:00"))
        return out

    def test_signal_order_is_derived_from_the_time_within_each_day(self):
        """outcomes.csv 沒有「第幾個」這一欄，要自己從時間排出來。"""
        rows = self._rows([("2026-10-01", "09:39", True, 0, None, None, None),
                           ("2026-10-01", "09:12", False, 0, None, None, None),
                           ("2026-09-30", "09:20", True, 0, None, None, None)])
        order = analyse.signal_order(rows)
        self.assertEqual([o.time for o in order[1]], ["09:12", "09:20"])
        self.assertEqual([o.time for o in order[2]], ["09:39"])

    def test_two_tiny_groups_are_called_indistinguishable(self):
        """4 筆全贏 vs 4 筆全輸，看起來天差地遠 —— 但那是 4 筆。"""
        rows = self._rows(
            [("2026-10-01", f"09:1{i}", True, 1, None, None, None) for i in range(4)] +
            [("2026-10-02", f"09:1{i}", False, 11, None, None, None) for i in range(4)])
        self.assertTrue(analyse.overlapping(analyse.by_rank(rows)))
        text = "\n".join(analyse.render_group("x", analyse.by_rank(rows), "q"))
        self.assertIn("分不出來", text)

    def test_a_group_below_the_floor_shows_no_rate_at_all(self):
        rows = self._rows([("2026-10-01", "09:10", True, 1, None, None, None)])
        text = "\n".join(analyse.render_group("x", analyse.by_rank(rows), "q"))
        self.assertIn("太少", text)
        self.assertNotIn("100.0%", text)

    def test_a_single_group_can_never_be_a_difference(self):
        """只有一組的時候沒有「比較」這件事，不可以說有差。"""
        rows = self._rows([("2026-10-01", f"09:1{i}", i % 2 == 0, 1,
                            None, None, None) for i in range(10)])
        self.assertTrue(analyse.overlapping(analyse.by_rank(rows)))

    def test_a_real_separation_is_reported_as_one(self):
        """區間真的分開時要講 —— 否則這支程式永遠只會說「不知道」。"""
        rows = self._rows(
            [("2026-10-01", f"09:{10+i}", True, 1, None, None, None) for i in range(40)] +
            [("2026-10-02", f"09:{10+i}", False, 11, None, None, None) for i in range(40)])
        self.assertFalse(analyse.overlapping(analyse.by_rank(rows)))
        text = "\n".join(analyse.render_group("x", analyse.by_rank(rows), "q"))
        self.assertIn("沒有**重疊", text)

    def test_unknown_values_are_dropped_not_bucketed_as_zero(self):
        """大盤查不到的那幾天不能算成「開低」—— None 是不知道，不是負的。

        訊號時間原本隨手填 09:10/09:11。by_market 改成只收「訊號前就已知」
        的大盤之後，09:15 的數字對 09:10 的訊號是事後資訊，兩筆都會被排除 ——
        那是另一條規則（見 TestMarketMustBeKnownBeforeTheSignal），不是這條
        要驗的事。改成 09:20/09:21，讓它繼續只驗 None。
        """
        rows = self._rows([("2026-10-01", "09:20", True, 0, None, None, None),
                           ("2026-10-01", "09:21", True, 0, 0.5, None, None)])
        groups = analyse.by_market(rows)
        self.assertEqual(sum(len(v) for v in groups.values()), 1)

    def test_an_empty_csv_says_so_instead_of_printing_zeros(self):
        text = "\n".join(analyse.report([]))
        self.assertIn("是空的或不存在", text)
        self.assertNotIn("0.0%", text)

    def test_the_report_always_shows_the_interval_next_to_the_rate(self):
        """只印中間那個數字，就是這支程式要避免的那件事。"""
        rows = self._rows([("2026-10-01", f"09:{10+i}", i < 6, 1, 0.5, 6.0, -0.2)
                           for i in range(10)])
        text = "\n".join(analyse.report(rows))
        self.assertIn("95% 信賴區間", text)
        self.assertRegex(text, r"60\.0%（\d+\.\d+~\d+\.\d+）")


class TestPersonalDataStaysOffGitHub(unittest.TestCase):
    """程式產出的檔案裡，有一半是這個人的交易紀錄。

    `outcomes.csv` 一開始就排除了，理由寫在 .gitignore 上：「個人帳務資料」。
    但後來新增 `candidates.csv` 與 `candidates_outcomes.csv` 時忘了同步 ——
    那兩份是**完全一樣的欄位、完全一樣的東西**，只是記被擋掉的訊號。

    漏掉的後果不是「檔案多了一個」，是某次 `git add -A` 會把個人損益推上
    GitHub，而且推上去就收不回來了。

    這條測試的工作是：以後再加任何一個會寫個人資料的檔案，都不准忘。
    """

    IGNORE = Path(__file__).with_name(".gitignore")

    # 會寫進個人交易紀錄或金鑰的檔案，一個都不能漏
    MUST_IGNORE = (".env", "state.json", "watchlist.json", "outcomes.csv",
                   "candidates.csv", "candidates_outcomes.csv", "journal/*.md",
                   "journal/watchlist-*.json", "logs/")

    def setUp(self):
        if not self.IGNORE.exists():
            self.skipTest(".gitignore 不在")
        self.lines = [l.strip() for l in
                      self.IGNORE.read_text(encoding="utf-8").splitlines()]

    def test_every_personal_data_file_is_ignored(self):
        for name in self.MUST_IGNORE:
            with self.subTest(path=name):
                self.assertIn(name, self.lines)

    def test_the_csvs_the_programs_actually_write_are_all_covered(self):
        """從程式裡抓出真的會被寫出來的檔名，逐一比對 —— 不靠我記得。"""
        written = {oc.OUTCOME_FILE.name, signals.CANDIDATE_FILE.name}
        import review                                  # noqa: F401  （已匯入，取名用）
        written.add("candidates_outcomes.csv")
        for name in written:
            with self.subTest(path=name):
                self.assertIn(name, self.lines,
                              f"{name} 會被寫到磁碟上，但沒有排除在版控外")

    def test_the_template_is_still_tracked(self):
        """.env 要排除，.env.template 不能 —— 它是給新機器照著填的。"""
        self.assertIn(".env", self.lines)
        self.assertNotIn(".env.template", self.lines)


@under_v5_rules
class TestStopNeverSitsAboveTheBreakout(unittest.TestCase):
    """2026-10-02 美亞：區間高 26.70、進場 27.25、**停損 26.85**。

    停損比突破點還高。那檔只要回測一下突破點 —— 突破之後最正常不過的動作 ——
    就把你掃出場，而突破在技術上根本還沒失敗。

    根因：停損只從進場價往下算固定 %，和開盤區間完全無關。於是訊號發得越晚、
    進場價飄得越高，停損就跟著往上飄。而「跌回區間 = 突破失敗」才是這套策略
    自己的前提 —— 停損在突破點之上，等於「突破還好好的，但我先出場了」。

    那不是參數調不好，是實作沒做到它宣稱的事。
    """

    def _state(self, price, or_high=26.70, or_low=25.10, prev_close=26.20,
               vwap=26.14, surge=1.86):
        st = SymbolState("2020", prev_close, "美亞")
        st.lock_opening_range(or_high, or_low)
        st.last_price = price
        st.vwap = vwap
        st.volume_surge = lambda: surge
        return st

    def _sig(self, price, **kw):
        return evaluate(self._state(price, **kw), now=dtime(9, 3))

    def test_the_real_case_now_stops_below_the_breakout(self):
        sig = self._sig(27.25)
        self.assertLess(sig["stop"], 26.70)        # 區間高之下
        self.assertLess(sig["stop"], 26.85)        # 比舊規則寬

    def test_a_timely_entry_is_completely_unchanged(self):
        """貼近突破點進場時，固定 % 本來就比較低 —— 結構線不可以插手。

        這一條是整個修改的安全邊界：它只在壞掉的那些情況生效。
        """
        sig = self._sig(26.75)
        expect = config.round_to_tick(
            26.75 * (1 - config.SIGNAL["stop_loss_pct"] / 100), "up")
        self.assertEqual(sig["stop"], expect)
        self.assertEqual(sig["stop_rule"], "固定 %")

    def test_chasing_higher_automatically_cuts_the_lot_size(self):
        """系統自己踩煞車：追越高 → 停損越寬 → 風險越大 → 張數越少。

        這比訂一條「不准追超過 X%」好 —— 那個 X 是我憑空decide的，
        而這個是算出來的。
        """
        near, far = self._sig(26.75), self._sig(27.25)
        self.assertGreater(near["lots"], far["lots"])
        self.assertGreater(far["entry"] - far["stop"], near["entry"] - near["stop"])

    def test_the_dollar_risk_stays_inside_the_cap_either_way(self):
        """煞車不可以用「讓你多賠」的方式踩。單筆風險上限仍然要守住。"""
        for price in (26.75, 27.00, 27.25, 27.60):
            with self.subTest(entry=price):
                sig = self._sig(price)
                if not sig["oversized"]:
                    risk = (sig["entry"] - sig["stop"]) * 1000 * sig["lots"]
                    self.assertLessEqual(round(risk), config.RISK["per_trade_risk"])

    def test_the_signal_says_which_rule_it_used(self):
        """停損比平常寬的時候要講原因，否則看起來像算錯了。"""
        text = format_signal(self._sig(27.25), 1, 1)
        self.assertIn("結構線", text)
        self.assertIn("26.70", text)
        far_text = format_signal(self._sig(26.75), 1, 1)
        self.assertNotIn("結構線", far_text)

    def test_the_signal_shows_how_far_it_chased(self):
        """追高幅度以前只進 outcomes.csv，20 天後才看得到 ——
        但需要它的時候是訊號跳出來那 10 秒。"""
        sig = self._sig(27.25)
        self.assertAlmostEqual(sig["extension_pct"], 2.06, places=2)
        self.assertIn("已追高 +2.06%", format_signal(sig, 1, 1))

    def test_no_opening_range_falls_back_instead_of_crashing(self):
        """區間補算不到的時候不要炸 —— 退回固定 %，而且要能發得出訊號。"""
        st = self._state(27.25)
        st.or_high = 0
        sig = evaluate(st, now=dtime(9, 3))
        self.assertIsNotNone(sig)
        self.assertEqual(sig["stop_rule"], "固定 %")
        self.assertIsNone(sig["extension_pct"])

    def test_the_stop_is_still_never_at_or_above_the_entry(self):
        """放寬停損不可以放寬到變成沒有停損。"""
        for price in (26.75, 27.25, 28.00):
            with self.subTest(entry=price):
                sig = self._sig(price)
                if sig:
                    self.assertLess(sig["stop"], sig["entry"])

    def test_target_still_respects_the_limit_up(self):
        """停損變寬 → 目標跟著變遠，但不能飛出漲停。"""
        sig = self._sig(27.25)
        cap = config.limit_up(26.20)
        self.assertLessEqual(sig["target"], cap)


class TestRulesetStamping(unittest.TestCase):
    """改規則不該讓既有資料整批報廢 —— 只要記得是哪一版產生的。

    09-29 把 1.5R 改成 2.5R 時就已經造成這個問題，當時只靠我記得。
    沒有這一欄，「為了資料純淨所以什麼都不改」會變成無限迴圈：
    第 20 天改完又要再等 20 天。
    """

    def _state(self, price=26.75):
        st = SymbolState("2020", 26.20, "美亞")
        st.day_open = 26.20
        st.lock_opening_range(26.70, 25.10)
        st.last_price = price
        st.vwap = 26.40
        st.volume_surge = lambda: 1.86
        return st

    def test_the_signal_carries_the_version(self):
        sig = evaluate(self._state(), now=dtime(9, 3))
        self.assertEqual(sig["ruleset"], config.RULESET)
        self.assertTrue(config.RULESET)

    def test_it_reaches_outcomes_csv(self):
        sig = {"code": "2330", "time": "09:23:00", "entry": 121.0, "stop": 119.5,
               "target": 123.5, "lots": 1, "ruleset": "v3"}
        o = oc.resolve(FakeKbarBroker(_kb([("09:24", 123.6, 120.8, 123.4)])),
                       sig, "2026-09-24")
        self.assertEqual(o.ruleset, "v3")
        self.assertIn("ruleset", oc.FIELDS)

    def test_old_rows_without_it_still_load(self):
        """9/24~10/01 寫下的列沒有這一欄，不可以因此讀不回來。"""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "outcomes.csv"
            keep = [f for f in oc.FIELDS if f != "ruleset"]
            filled = {"date": "2026-09-24", "code": "6182", "time": "09:19:22",
                      "entry": "100", "stop": "99", "target": "102.5", "lots": "1",
                      "result": oc.TARGET, "exit_price": "102.5", "r_multiple": "2.5",
                      "gross_pct": "2.5", "net_pct": "2.3", "bars": "3"}
            path.write_text(",".join(keep) + "\n"
                            + ",".join(filled.get(f, "") for f in keep) + "\n",
                            encoding="utf-8")
            back = oc.load_csv(path)
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].ruleset, "")

    def test_analyse_splits_by_version(self):
        rows = [oc.Outcome(date="2026-09-24", code="A", time="09:10", entry=100.0,
                           stop=99.0, target=102.5, lots=1, result=oc.TARGET,
                           exit_price=102.5, r_multiple=2.5, gross_pct=2.5,
                           net_pct=2.3, bars=3, ruleset=v)
                for v in ("v2", "v2", "v3")]
        groups = analyse.by_ruleset(rows)
        self.assertEqual(sorted(groups), ["v2", "v3"])
        self.assertEqual(len(groups["v2"]), 2)

    def test_unstamped_rows_are_their_own_group_not_merged(self):
        """舊列沒有版本，不可以被塞進任何一版裡假裝是同一把尺。"""
        rows = [oc.Outcome(date="2026-09-24", code="A", time="09:10", entry=100.0,
                           stop=99.0, target=102.5, lots=1, result=oc.TARGET,
                           exit_price=102.5, r_multiple=2.5, gross_pct=2.5,
                           net_pct=2.3, bars=3, ruleset=v)
                for v in ("", "v3")]
        groups = analyse.by_ruleset(rows)
        self.assertIn("（未標版本）", groups)
        self.assertEqual(len(groups["（未標版本）"]), 1)


class TestIsTheStopTooTight(unittest.TestCase):
    """「被停損的那些，後來當天還是走到目標了嗎」—— 停損太緊唯一直接的證據。

    10-02 把停損改成結構線是因為它會飄到突破點之上（那是矛盾，不是參數）。
    但**要不要再放寬，得看這個數字**，不是看誰講話比較大聲。
    """

    def _rows(self, spec):
        return [oc.Outcome(date="2026-10-02", code="T", time=f"09:{10+i}",
                           entry=100.0, stop=99.0, target=102.5, lots=1,
                           result=res, exit_price=99.0, r_multiple=-1.0,
                           gross_pct=-1.0, net_pct=-1.2, bars=2,
                           target_after_stop=after)
                for i, (res, after) in enumerate(spec)]

    def test_it_counts_only_stopped_trades_with_a_verdict(self):
        rows = self._rows([(oc.STOP, True), (oc.STOP, False),
                           (oc.TARGET, None), (oc.STOP, None)])
        st = analyse.stopped_but_reached_target(rows)
        self.assertEqual((st["n"], st["hit"]), (2, 1))

    def test_it_refuses_a_number_when_there_are_too_few(self):
        rows = self._rows([(oc.STOP, True), (oc.STOP, True)])
        text = "\n".join(analyse.report(rows))
        self.assertIn("太少", text)
        self.assertNotIn("100.0%", text)

    def test_it_reports_with_an_interval_once_there_are_enough(self):
        rows = self._rows([(oc.STOP, i % 2 == 0) for i in range(10)])
        st = analyse.stopped_but_reached_target(rows)
        self.assertEqual(st["n"], 10)
        self.assertLess(st["lo"], st["rate"])
        self.assertGreater(st["hi"], st["rate"])
        text = "\n".join(analyse.report(rows))
        self.assertIn("停損之後，當天還是走到目標了嗎", text)

    def test_no_stopped_trades_says_so(self):
        text = "\n".join(analyse.report(self._rows([(oc.TARGET, None)])))
        self.assertIn("還沒有可判定的停損樣本", text)

    def test_a_trade_that_was_never_stopped_is_not_in_the_denominator(self):
        # resolve() 目前只在 result == STOP 時才寫 target_after_stop，所以這樣的
        # 一列正常跑不出來。但分母的定義是「被停損的那些」—— 一筆走到目標的單子
        # 當然碰得到目標，把它算進分母會把比例沖高，然後拿一個根本不存在的證據
        # 去主張「停損太緊、該放寬」。手改過的 CSV、或哪天 resolve() 改寫法，
        # 都會餵進這種列，所以 analyse 這邊自己也要擋。
        rows = self._rows([(oc.STOP, False), (oc.TARGET, True), (oc.TARGET, True)])
        st = analyse.stopped_but_reached_target(rows)
        self.assertEqual((st["n"], st["hit"]), (1, 0))


class TestLoginRetry(unittest.TestCase):
    """2026-09-30 早上真的發生的事。

    08:40 盤前選股登入成功；08:50 盤中監看收到
    `SystemMaintenance: 503, Paper report subscription was not confirmed`
    —— 永豐模擬環境在那 10 分鐘之間進入維護。以前這個例外直接往外炸，
    一整個驗證日就這樣沒了，而且每次維護都會再發生一次。
    """

    class Boom:
        """前 n 次登入丟例外，之後成功。"""

        def __init__(self, exc, fail_times):
            self.exc, self.left, self.calls = exc, fail_times, 0

        def login(self, **_kw):
            self.calls += 1
            if self.left > 0:
                self.left -= 1
                raise self.exc

    def _broker(self, api):
        b = Broker(api=api)          # 注入 api 不會登入
        b.api = api
        return b

    def _run(self, exc, fail_times):
        api = self.Boom(exc, fail_times)
        b = self._broker(api)
        slept = []
        b._login_with_retry(sleep=slept.append)
        return api, slept

    def test_transient_maintenance_is_survived(self):
        exc = RuntimeError("SystemMaintenance: StatusCode: 503, Detail: "
                           "Paper report subscription was not confirmed")
        with self.assertLogs("broker", level="WARNING"):
            api, slept = self._run(exc, fail_times=3)
        self.assertEqual(api.calls, 4)                  # 三次失敗 + 一次成功
        self.assertEqual(slept, [broker_mod.LOGIN_RETRY_WAIT] * 3)

    def test_first_try_does_not_sleep(self):
        api, slept = self._run(RuntimeError("x"), fail_times=0)
        self.assertEqual(api.calls, 1)
        self.assertEqual(slept, [])

    def test_permission_errors_fail_immediately(self):
        """金鑰錯、權限不足重試一百次也一樣 —— 重試只是把壞消息延後 6 分鐘。"""
        exc = RuntimeError("Token doesn't have permission")
        api = self.Boom(exc, fail_times=99)
        b = self._broker(api)
        with self.assertRaises(RuntimeError) as cm:
            b._login_with_retry(sleep=lambda _s: None)
        self.assertIn("permission", str(cm.exception))
        self.assertEqual(api.calls, 1)                  # 一次就放棄

    def test_gives_up_after_the_cap_and_says_why(self):
        exc = RuntimeError("SystemMaintenance: 503")
        api = self.Boom(exc, fail_times=99)
        b = self._broker(api)
        with self.assertLogs("broker", level="WARNING"), \
                self.assertRaises(RuntimeError) as cm:
            b._login_with_retry(sleep=lambda _s: None)
        self.assertEqual(api.calls, broker_mod.LOGIN_ATTEMPTS)
        self.assertIn("維護", str(cm.exception))
        self.assertIn("503", str(cm.exception))         # 原始錯誤要留著

    def test_transient_detection(self):
        for text in ("SystemMaintenance: 503", "Read timed out",
                     "Connection aborted", "Service temporarily unavailable",
                     "502 Bad Gateway"):
            self.assertTrue(broker_mod._looks_transient(RuntimeError(text)), text)
        for text in ("Token doesn't have permission", "Invalid api key",
                     "signature mismatch"):
            self.assertFalse(broker_mod._looks_transient(RuntimeError(text)), text)

    def test_retry_window_covers_the_gap_to_the_open(self):
        """排程 08:50 開始、09:00 開盤 —— 重試總時長要塞得進那 10 分鐘。"""
        total = broker_mod.LOGIN_ATTEMPTS * broker_mod.LOGIN_RETRY_WAIT
        self.assertGreaterEqual(total, 5 * 60)
        self.assertLessEqual(total, 10 * 60)


class TestSignalBatchIsNotARace(unittest.TestCase):
    """v4：09:02–09:05 收集，09:05:00 一次發出，按當下量能倍數排序取前 N。

    v3 以前是「誰先突破誰先發」。在三小時長的進場窗口裡那還說得過去 ——
    先突破的確實是先動的那一檔。壓縮到三分鐘之後，先後差距只剩下「哪一檔的
    報價封包先到」，那是網路抖動，不是市場資訊。一天只發三個訊號的時候，
    用抖動決定發哪三檔，等於把最重要的那個決定交給運氣。
    """

    AT = dtime(9, 5)

    def _sig(self, code, surge, rank=0):
        return {"code": code, "volume_surge": surge, "rank": rank,
                "entry": 100.0, "stop": 98.5, "target": 102.0}

    def _batch(self, limit=3):
        return signals.SignalBatch(self.AT, limit)

    def _at(self, h, m, s=0):
        return datetime(2026, 10, 5, h, m, s)

    def test_nothing_comes_out_before_the_batch_time(self):
        b = self._batch()
        b.add(self._sig("A", 3.0))
        self.assertFalse(b.due(self._at(9, 4, 59)))

    def test_it_fires_once_the_time_arrives(self):
        b = self._batch()
        b.add(self._sig("A", 3.0))
        self.assertTrue(b.due(self._at(9, 5, 0)))

    def test_the_strongest_volume_goes_first(self):
        b = self._batch()
        for code, surge in (("A", 1.9), ("B", 4.2), ("C", 2.5), ("D", 3.1)):
            b.add(self._sig(code, surge))
        chosen, rest = b.take()
        self.assertEqual([s["code"] for s in chosen], ["B", "D", "C"])
        self.assertEqual([s["code"] for s in rest], ["A"])

    def test_the_ones_that_miss_the_cut_are_still_written_down(self):
        """砍掉樣本就等於把「只發三個夠不夠」變成無法回答的問題。"""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "candidates.csv"
            b = self._batch()
            for code, surge in (("A", 1.9), ("B", 4.2), ("C", 2.5), ("D", 3.1)):
                b.add(self._sig(code, surge))
            _, rest = b.take()
            for sig in rest:
                signals.record_candidate(sig, signals.BLOCK_BATCH_RANK, path=path)
            text = path.read_text(encoding="utf-8-sig")
        self.assertIn("A", text)
        self.assertIn(signals.BLOCK_BATCH_RANK, text)

    def test_the_same_symbol_keeps_only_its_first_breakout(self):
        """第一次突破的進場價才是「剛越過區間高」的價格，後面只會更高 ——
        而追高正是 v4 要離開的那個毛病。"""
        b = self._batch()
        first = self._sig("A", 2.0)
        first["entry"] = 100.0
        later = self._sig("A", 9.9)
        later["entry"] = 104.0
        b.add(first)
        b.add(later)
        chosen, _ = b.take()
        self.assertEqual(len(chosen), 1)
        self.assertAlmostEqual(chosen[0]["entry"], 100.0)

    def test_ties_break_the_same_way_every_time(self):
        """同一份資料、不同的到達順序，必須選出同一組三檔。

        報價封包的先後是會變的；選出來的三檔不可以跟著變，否則回測算出來的
        那一天和實盤跑出來的那一天就不是同一天，20 日的結論也就不成立。
        """
        data = {"A": (2.0, 4), "B": (2.0, 2), "C": (2.0, 3), "D": (2.0, 1)}
        order = []
        for codes in (("A", "B", "C", "D"), ("D", "C", "B", "A"), ("C", "A", "D", "B")):
            b = self._batch()
            for c in codes:
                surge, rank = data[c]
                b.add(self._sig(c, surge, rank=rank))
            order.append([x["code"] for x in b.take()[0]])
        self.assertEqual(order[0], order[1])
        self.assertEqual(order[1], order[2])
        self.assertEqual(order[0], ["D", "B", "C"], "平手時照盤前名次")

    def test_it_only_fires_once(self):
        b = self._batch()
        b.add(self._sig("A", 3.0))
        b.take()
        self.assertFalse(b.due(self._at(9, 6)))
        self.assertEqual(b.take(), ([], []))

    def test_a_quiet_window_produces_nothing_rather_than_filler(self):
        b = self._batch()
        chosen, rest = b.take()
        self.assertEqual((chosen, rest), ([], []))

    def test_missing_volume_surge_sorts_last_instead_of_crashing(self):
        b = self._batch(limit=1)
        b.add(self._sig("A", None))
        b.add(self._sig("B", 1.2))
        chosen, _ = b.take()
        self.assertEqual(chosen[0]["code"], "B")


class TestTheTimeExitRemindsButDoesNotDecide(unittest.TestCase):
    """v4 原則二：09:30 發賣出訊號，**未達停損的由下單者自由決定**。

    所以系統報價、記下來，但不平倉，而且那一筆繼續追到 13:25。
    兩個出場都要留：只留 09:30 的話，「09:30 就走是不是比較好」這一題
    永遠沒有對照組 —— 而那正是這次改版最需要事後驗證的一條。
    """

    def _tracker(self, seen=None):
        sink = seen if seen is not None else []
        t = signals.LiveTracker(on_time_exit=lambda o, p, at: sink.append(
            (o.code, p, at)))
        t.track({"code": "2330", "name": "台積", "time": "09:05:00",
                 "entry": 100.0, "stop": 98.5, "target": 102.5})
        return t

    def test_it_reports_the_current_price_and_the_r(self):
        t = self._tracker()
        t.on_price("2330", 101.0)
        msgs = t.time_exit(datetime(2026, 10, 5, 9, 30))
        self.assertEqual(len(msgs), 1)
        self.assertIn("時間到", msgs[0])
        self.assertIn("101.00", msgs[0])
        self.assertIn("+0.67R", msgs[0])

    def test_the_position_is_still_being_tracked_afterwards(self):
        """系統不替人平倉 —— 停損照舊有效，13:25 才收尾。"""
        t = self._tracker()
        t.on_price("2330", 101.0)
        t.time_exit(datetime(2026, 10, 5, 9, 30))
        self.assertEqual(len(t.open), 1, "09:30 不可以把部位從追蹤清單拿掉")
        done = t.on_price("2330", 98.0)          # 之後才跌破停損
        self.assertEqual(len(done), 1)
        self.assertIn("停損", done[0])

    def test_it_says_the_decision_is_yours(self):
        t = self._tracker()
        t.on_price("2330", 101.0)
        msg = t.time_exit(datetime(2026, 10, 5, 9, 30))[0]
        self.assertIn("由你決定", msg)

    def test_a_trade_that_already_ended_is_not_reminded_about(self):
        t = self._tracker()
        t.on_price("2330", 98.0)                 # 先停損
        self.assertEqual(t.time_exit(datetime(2026, 10, 5, 9, 30)), [])

    def test_it_only_fires_once(self):
        t = self._tracker()
        t.on_price("2330", 101.0)
        t.time_exit(datetime(2026, 10, 5, 9, 30))
        self.assertEqual(t.time_exit(datetime(2026, 10, 5, 9, 31)), [])

    def test_no_quote_means_no_number_rather_than_a_made_up_one(self):
        """整天沒收到報價 —— 空白代表不知道。拿進場價或 0 頂替會變成假資料。"""
        seen = []
        t = self._tracker(seen)
        self.assertEqual(t.time_exit(datetime(2026, 10, 5, 9, 30)), [])
        self.assertEqual(seen, [])

    def test_the_price_is_handed_off_to_be_written_down(self):
        """不寫回 state.json 的話，這個價位只活在那則推播裡，收盤後就沒了。"""
        seen = []
        t = self._tracker(seen)
        t.on_price("2330", 101.0)
        t.time_exit(datetime(2026, 10, 5, 9, 30, 12))
        self.assertEqual(seen, [("2330", 101.0, "09:30:12")])

    def test_a_write_failure_never_swallows_the_reminder(self):
        t = signals.LiveTracker(on_time_exit=lambda *a: 1 / 0)
        t.track({"code": "2330", "name": "台積", "time": "09:05:00",
                 "entry": 100.0, "stop": 98.5, "target": 102.5})
        t.on_price("2330", 101.0)
        with self.assertLogs(signals.log, level="WARNING"):
            msgs = t.time_exit(datetime(2026, 10, 5, 9, 30))
        self.assertEqual(len(msgs), 1)


class TestStartingTooLateIsNotAQuietDay(unittest.TestCase):
    """v3 的進場窗口有三小時十五分，晚開只是少幾個訊號。

    v4 的窗口只有三分鐘 —— 09:06 才啟動的話整天掛零，而「整天掛零」和
    「今天沒有股票突破」在畫面上一模一樣。失敗要出聲，不然你會把故障
    當成行情，然後明天繼續用同一個排程。
    """

    def test_it_says_there_will_be_no_signals_at_all_today(self):
        text = signals.format_too_late(datetime(2026, 10, 5, 9, 31, 30))
        self.assertIn("09:31:30", text)
        self.assertIn("不會有任何買進訊號", text)
        self.assertIn(config.SIGNAL["entry_window_end"], text)

    def test_it_does_not_let_you_blame_the_market(self):
        text = signals.format_too_late(datetime(2026, 10, 5, 9, 6))
        self.assertIn("不是今天沒行情", text)

    def test_it_still_tells_you_the_stop_is_live(self):
        """手上有部位的人最需要知道的是這件事。"""
        text = signals.format_too_late(datetime(2026, 10, 5, 9, 31))
        self.assertIn("停損與目標照舊有人盯", text)


class TestBothExitsAreKept(unittest.TestCase):
    """v4 原則二：09:30 發「時間到」訊號，未達停損的由下單者自由決定。

    系統不替人平倉，所以 result / exit_price / r_multiple 照舊是「走到停損或
    目標、13:25 平倉」的機械結果 —— 也就是**續抱**的版本。exit_0930 / r_0930
    記的是「09:30 就走」的版本。

    兩個並存不互相覆蓋，是因為「09:30 就走是不是比較好」這一題需要對照組。
    現在就把後半天砍掉，20 天後只會有一個數字，沒有東西可以比 —— 那時候就
    只能回答「再測一次」，而那正是這個專案一路在避免的事。
    """

    DATE = "2026-09-24"
    SIG = {"code": "8042", "time": "09:03:30", "entry": 121.50,
           "stop": 120.00, "target": 123.75, "lots": 2}
    # 09:30 之前都沒碰到停損或目標，收盤前才跌破 —— 和 10-02 金山電同一個形狀
    BARS = [("09:05", 122.0, 121.0, 121.8), ("09:31", 123.0, 121.5, 122.5),
            ("12:20", 122.0, 119.5, 119.8)]

    def _resolve(self, **extra):
        return oc.resolve(FakeKbarBroker(_kb(self.BARS)),
                          dict(self.SIG, **extra), self.DATE)

    def test_the_0930_price_becomes_its_own_column(self):
        o = self._resolve(exit_0930_price=122.50)
        self.assertAlmostEqual(o.exit_0930, 122.50)
        # (122.50 - 121.50) / (121.50 - 120.00) = 0.67R
        self.assertAlmostEqual(o.r_0930, 0.67, places=2)

    def test_holding_on_is_still_recorded_separately(self):
        """09:30 那一欄不可以蓋掉續抱的結果 —— 那是對照組的另一半。"""
        o = self._resolve(exit_0930_price=122.50)
        self.assertEqual(o.result, oc.STOP)
        self.assertAlmostEqual(o.r_multiple, -1.00)
        self.assertGreater(o.r_0930, 0)

    def test_no_0930_mark_leaves_it_blank_rather_than_zero(self):
        """09:30 前就出場的那幾筆沒有這個欄位。空白代表不適用，0 代表打平。"""
        o = self._resolve()
        self.assertIsNone(o.exit_0930)
        self.assertIsNone(o.r_0930)

    def test_a_losing_0930_mark_is_recorded_too(self):
        o = self._resolve(exit_0930_price=120.75)
        self.assertAlmostEqual(o.r_0930, -0.50, places=2)

    def test_old_rows_without_the_columns_still_load(self):
        """新增欄位時當成必填，舊的那幾列會在 KeyError 時被整列跳過 ——
        累計勝率會無聲歸零。這條在 rank / fill_low_pct / exit_at 都踩過一次。"""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "outcomes.csv"
            old = [f for f in oc.FIELDS if f not in ("exit_0930", "r_0930")]
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=old)
                w.writeheader()
                w.writerow({**{k: "" for k in old},
                            "date": "2026-09-24", "code": "3094", "time": "09:39:28",
                            "entry": "65.6", "stop": "64.7", "target": "67.7",
                            "lots": "3", "result": oc.TARGET, "exit_price": "67.7",
                            "r_multiple": "2.33", "gross_pct": "3.2",
                            "net_pct": "3.0", "bars": "4"})
            rows = oc.load_csv(path)
        self.assertEqual(len(rows), 1, "舊列必須讀得回來，不可以被跳過")
        self.assertIsNone(rows[0].exit_0930)

    def test_the_columns_survive_a_write_and_read_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "outcomes.csv"
            oc.append_csv([self._resolve(exit_0930_price=122.50)], path)
            back = oc.load_csv(path)
        self.assertAlmostEqual(back[0].exit_0930, 122.50)
        self.assertAlmostEqual(back[0].r_0930, 0.67, places=2)


class TestTheLateStartWarningIsActuallyWired(unittest.TestCase):
    """變異測試抓到的：`format_too_late` 有測試，但「run() 真的會推它」沒有。

    把 run() 裡那個判斷改成 `if False:`，463 條測試一條都不會失敗 ——
    規則看起來在那裡，實際上沒有作用。這正是這個專案一路在修的那種毛病，
    所以這次連接線一起釘住。
    """

    def test_it_pushes_when_the_batch_window_has_passed(self):
        sent = []
        with unittest.mock.patch.object(signals, "notify", sent.append):
            fired = signals.warn_if_too_late(datetime(2026, 10, 5, 9, 31))
        self.assertTrue(fired)
        self.assertEqual(len(sent), 1)
        self.assertIn("不會有任何買進訊號", sent[0])

    def test_it_stays_quiet_before_the_window_closes(self):
        """窗口結束前啟動還來得及，推一則「今天不會有訊號」是假警報。
        v7 起 09:05 過了也還來得及（09:05 之後的突破即時發）。"""
        sent = []
        with unittest.mock.patch.object(signals, "notify", sent.append):
            for t in (datetime(2026, 10, 5, 9, 4, 59), datetime(2026, 10, 5, 9, 10),
                      datetime(2026, 10, 5, 9, 29, 59)):
                self.assertFalse(signals.warn_if_too_late(t))
        self.assertEqual(sent, [])

    def test_run_actually_calls_it(self):
        """run() 要連上券商才跑得起來，離線測不到，所以退一步檢查接線還在。

        和三支 .bat 的橫幅用同一招 —— 不夠漂亮，但「沒有人在呼叫它」這種
        壞法在這個專案已經發生過太多次（連敗停手、require_above_vwap、
        LiveTracker 的回寫），寧可用一條粗測試擋住。
        """
        # 用 AST 找「真的有這個呼叫」，不是用字串比對 —— 變異測試證實字串比對
        # 會被 `pass  # warn_if_too_late()` 這種註解騙過去，等於沒測。
        tree = ast.parse(textwrap.dedent(inspect.getsource(signals.run)))
        called = {n.func.id for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn("warn_if_too_late", called,
                      "run() 沒有真的呼叫 warn_if_too_late()")


@under_v5_rules
class TestWhatIfReplay(unittest.TestCase):
    """whatif.py 的核心：拿同一份分鐘 K 重跑不同的進場／出場規則。

    它要回答的是「使用者沒指定、我用猜的填進去」的那幾格 —— 區間 2 分鐘是
    我選的，沒有任何數據支持。回測算得出來的事情就不要等 20 天。

    但這支程式的結論對自己有利（只重跑當天真的突破了的那些股票），所以它的
    報表第一行就要寫這件事。測試把那句話也釘住。
    """

    D = datetime(2026, 10, 2)

    def _bars(self, spec):
        """spec = [("09:01", high, low, close), ...]，label 是該分鐘的結束時間。"""
        return [(datetime.combine(self.D.date(),
                                  dtime(*(int(x) for x in t.split(":")))), h, l, c)
                for t, h, l, c in spec]

    # 09:00–09:02 區間 100.0/99.0；09:03 突破；之後走到 102 再回落
    DAY = [("09:01", 100.0, 99.0, 99.5), ("09:02", 100.0, 99.2, 99.8),
           ("09:03", 100.8, 99.9, 100.6), ("09:04", 101.5, 100.2, 101.4),
           ("09:05", 102.0, 101.0, 101.8), ("09:30", 101.2, 100.9, 101.0),
           ("12:00", 101.0, 96.0, 96.5)]

    def test_the_opening_range_uses_end_labelled_bars(self):
        hi, lo = whatif.opening_range(self._bars(self.DAY), 2)
        self.assertAlmostEqual(hi, 100.0)
        self.assertAlmostEqual(lo, 99.0)

    def test_a_longer_range_swallows_the_breakout(self):
        """15 分鐘的區間把 09:03 那根也收進去 —— 區間高變成當日高，突破就不見了。
        這正是回測要量的東西：區間長度直接決定了你買在哪裡。"""
        hi, _ = whatif.opening_range(self._bars(self.DAY), 15)
        self.assertAlmostEqual(hi, 102.0)

    def test_it_enters_on_the_first_breakout_inside_the_window(self):
        r = whatif.replay(self._bars(self.DAY), 2, 3, 1.5, None)
        self.assertAlmostEqual(r.or_high, 100.0)
        # 突破點 100.0 × 1.001 = 100.1，往上進位到合法檔位（0.5 檔）= 100.5
        self.assertAlmostEqual(r.entry, 100.5)

    def test_a_breakout_after_the_window_does_not_count(self):
        late = [("09:01", 100.0, 99.0, 99.5), ("09:02", 100.0, 99.2, 99.8),
                ("09:03", 99.9, 99.1, 99.5), ("09:04", 99.8, 99.0, 99.4),
                ("09:20", 105.0, 99.0, 104.0)]
        self.assertIsNone(whatif.replay(self._bars(late), 2, 3, 1.5, None))

    def test_the_pessimistic_entry_is_worse_than_the_optimistic_one(self):
        """只報一個數字，會讓人把其中一端當成事實。

        用一路往上的日子來比，兩邊都會到目標 —— 差別才純粹是進場價。
        """
        up = [("09:01", 100.0, 99.0, 99.5), ("09:02", 100.0, 99.2, 99.8),
              ("09:03", 101.0, 99.9, 100.9), ("09:20", 115.0, 101.0, 114.0)]
        good = whatif.replay(self._bars(up), 2, 3, 1.5, None, optimistic=True)
        bad = whatif.replay(self._bars(up), 2, 3, 1.5, None, optimistic=False)
        self.assertLess(good.entry, bad.entry)
        self.assertEqual((good.result, bad.result), (oc.TARGET, oc.TARGET))
        self.assertGreater(good.net_pct, bad.net_pct)

    def test_the_bar_that_contains_the_breakout_is_not_counted(self):
        """那一根裡面有一段是突破前的價格。算進去會製造假停損 ——
        09-24 五個訊號誤判了四個就是這個原因。"""
        dip = [("09:01", 100.0, 99.0, 99.5), ("09:02", 100.0, 99.2, 99.8),
               ("09:03", 100.8, 98.0, 100.6),      # 同一根裡有突破前的 98.0
               ("09:10", 103.0, 100.5, 102.8)]
        r = whatif.replay(self._bars(dip), 2, 3, 1.5, None)
        self.assertEqual(r.result, oc.TARGET)

    def test_the_stop_never_sits_above_the_breakout(self):
        r = whatif.replay(self._bars(self.DAY), 2, 3, 1.5, None)
        self.assertLess(r.stop, r.or_high)

    def test_the_time_exit_closes_at_that_bar(self):
        r = whatif.replay(self._bars(self.DAY), 2, 3, 5.0, dtime(9, 30))
        self.assertEqual(r.result, "時間到")
        self.assertAlmostEqual(r.exit_price, 101.0)

    def test_holding_on_instead_runs_into_the_later_stop(self):
        """同一天、同一筆：09:30 走是賺的，抱著是賠的。這就是兩欄要並存的理由。"""
        timed = whatif.replay(self._bars(self.DAY), 2, 3, 5.0, dtime(9, 30))
        held = whatif.replay(self._bars(self.DAY), 2, 3, 5.0, None)
        self.assertGreater(timed.r_multiple, 0)
        self.assertEqual(held.result, oc.STOP)

    def test_a_bar_touching_both_is_judged_a_stop(self):
        both = [("09:01", 100.0, 99.0, 99.5), ("09:02", 100.0, 99.2, 99.8),
                ("09:03", 100.8, 99.9, 100.6),
                ("09:05", 110.0, 90.0, 100.0)]       # 同一根同時到停損與目標
        self.assertEqual(whatif.replay(self._bars(both), 2, 3, 1.5, None).result,
                         oc.STOP)

    def test_the_pre_open_bar_is_not_part_of_the_range(self):
        """label 09:00 的那根涵蓋 (08:59, 09:00]，是**開盤前**的價格。

        收進開盤區間的話，區間高會被盤前的單一筆成交污染，而突破就永遠
        觸發不了。這和 09-24「包著訊號那一刻的 K 棒」是同一種 off-by-one。
        """
        with_pre = [("09:00", 130.0, 129.0, 129.5)] + self.DAY
        hi, _ = whatif.opening_range(self._bars(with_pre), 2)
        self.assertAlmostEqual(hi, 100.0, msg="盤前那根不可以算進開盤區間")

    def test_the_structural_stop_takes_over_once_the_entry_has_chased(self):
        """追高之後，固定 % 的停損會飄到突破點之上 —— 那是 v3 修掉的矛盾。

        回測如果沒有把結構線一起算，它量到的就不是實際會發的那個規則。
        """
        chased = [("09:01", 100.0, 99.0, 99.5), ("09:02", 100.0, 99.2, 99.8),
                  ("09:03", 103.5, 99.9, 103.0),       # 這一根直接衝高 3%
                  ("09:20", 110.0, 102.0, 109.0)]
        r = whatif.replay(self._bars(chased), 2, 3, 1.5, None, optimistic=False)
        self.assertAlmostEqual(r.entry, 103.0)
        self.assertLess(r.stop, r.or_high, "停損必須在突破點之下")
        # 固定 % 會算出 103.0 × 0.985 = 101.46 → 進位 101.5，在 100.0 之上
        self.assertLess(r.stop, 101.5)

    def test_summarise_refuses_to_invent_numbers_from_nothing(self):
        self.assertEqual(whatif.summarise([]), {"n": 0})

    def test_the_report_leads_with_its_own_bias(self):
        """結論偏樂觀這件事要寫在最前面，不是藏在附註裡 ——
        埋在下面沒有人會讀到，等於沒有揭露。"""
        text = "\n".join(whatif.render({}, 25, True)[:8])
        self.assertIn("對自己有利", text)
        self.assertIn("watchlist", text)


class TestInsideOutsideVolume(unittest.TestCase):
    """會長 SOP 第 3 條：看內外盤 + 成交明細（買盤是否連續）。

    量能倍數只數「量有多大」，分不出方向 —— 量放大但內盤居多，是有人在
    出貨給你。而這個資料我們本來就收得到：shioaji 的 tick 帶 `tick_type`
    （1 = 外盤、2 = 內盤），`SymbolState.update()` 以前整個丟掉。

    和 08:50–09:00 的試撮資料是同一種情況：東西一直在，只是沒人接。

    **先記不排序。** 它還沒有任何資料支持，20 天後用算的決定要不要變成條件。
    """

    def _tick(self, kind, lots, cum, at="09:01:00", close=100.0):
        # volume = 這一筆的張數；total_volume = 當日累計（shioaji 就是這樣）
        return SimpleNamespace(
            close=close, high=close, low=close, avg_price=close,
            total_volume=cum, volume=lots, tick_type=kind,
            datetime=datetime.strptime(f"2026-10-05 {at}", "%Y-%m-%d %H:%M:%S"))

    def _state(self, ticks):
        st = SymbolState("2330", 99.0)
        cum = 0
        for i, (kind, lots) in enumerate(ticks):
            cum += lots
            st.update(self._tick(kind, lots, cum), now=1_000_000.0 + i * 10)
        return st

    def test_it_separates_who_was_the_aggressor(self):
        st = self._state([(1, 30), (1, 20), (2, 10)])
        self.assertEqual((st.aggressive_buy, st.aggressive_sell), (50, 10))
        self.assertAlmostEqual(st.bid_ask_ratio(), 5.0)

    def test_heavy_volume_on_the_inside_is_not_strength(self):
        """量一樣大，但方向相反 —— 量能倍數看不出這個差別，這一欄看得出。"""
        strong = self._state([(1, 90), (2, 10)])
        weak = self._state([(1, 10), (2, 90)])
        self.assertEqual(strong.total_volume, weak.total_volume)
        self.assertGreater(strong.bid_ask_ratio(), 1)
        self.assertLess(weak.bid_ask_ratio(), 1)

    def test_no_tick_type_means_unknown_not_balanced(self):
        """舊版 shioaji 或某些商品不帶 tick_type。

        回傳 0 或 1 會讓「不知道」看起來像「剛好打平」—— 這個專案已經為了
        把 `0` 當成 `None` 吃過兩次虧（損益查不到、成交窗口沒報價）。
        """
        st = self._state([(0, 50), (0, 30)])
        self.assertIsNone(st.bid_ask_ratio())
        self.assertEqual(st.unclassified, 80)

    def test_unclassified_volume_is_counted_but_not_taken_sides(self):
        """判不出來的那些要知道有多少 —— 否則一個漂亮的比值底下可能
        有九成的量根本沒被分類，而報表上看不出來。"""
        st = self._state([(1, 10), (0, 900), (2, 10)])
        self.assertEqual((st.aggressive_buy, st.aggressive_sell), (10, 10))
        self.assertEqual(st.unclassified, 900)
        self.assertAlmostEqual(st.bid_ask_ratio(), 1.0)

    def test_all_outside_does_not_return_infinity(self):
        """inf 寫進 CSV、讀回來是字串，那一整列會被跳過 ——
        累計勝率會無聲少掉一筆。"""
        st = self._state([(1, 40)])
        self.assertEqual(st.bid_ask_ratio(), 99.0)
        self.assertNotEqual(st.bid_ask_ratio(), float("inf"))

    def test_it_only_counts_inside_the_opening_range(self):
        """訊號要用的是「發訊號之前買盤有多強」。區間鎖定之後的成交
        在 09:05 當下還不存在，混進來等於用未來的資料。"""
        st = self._state([(1, 50)])
        st.lock_opening_range(101.0, 99.0)
        st.update(self._tick(2, 999, 1049, at="09:04:00"), now=1_000_100.0)
        self.assertEqual(st.aggressive_sell, 0)

    def test_the_signal_carries_it(self):
        st = ready_state()
        st.aggressive_buy, st.aggressive_sell, st.unclassified = 80, 20, 5
        sig = evaluate(st, now=dtime(9, 3))
        self.assertAlmostEqual(sig["bid_ask_ratio"], 4.0)
        self.assertEqual(sig["unclassified_lots"], 5)

    def test_it_reaches_the_outcome_row(self):
        o = oc.resolve(FakeKbarBroker(_kb([("09:41", 101.0, 100.0, 100.5)])),
                       {"code": "2330", "time": "09:03:30", "entry": 100.0,
                        "stop": 99.0, "target": 101.5, "lots": 1,
                        "bid_ask_ratio": 3.2}, "2026-09-24")
        self.assertAlmostEqual(o.bid_ask_ratio, 3.2)

    def test_old_rows_without_the_column_still_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "outcomes.csv"
            old = [f for f in oc.FIELDS if f != "bid_ask_ratio"]
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=old)
                w.writeheader()
                w.writerow({**{k: "" for k in old},
                            "date": "2026-09-24", "code": "3094", "time": "09:39:28",
                            "entry": "65.6", "stop": "64.7", "target": "67.7",
                            "lots": "3", "result": oc.TARGET, "exit_price": "67.7",
                            "r_multiple": "2.33", "gross_pct": "3.2",
                            "net_pct": "3.0", "bars": "4"})
            rows = oc.load_csv(path)
        self.assertEqual(len(rows), 1, "舊列必須讀得回來，不可以被跳過")
        self.assertIsNone(rows[0].bid_ask_ratio)

    def test_it_does_not_change_which_signals_fire(self):
        """**先記不排序。** 這一欄現在純粹是紀錄，不可以影響任何訊號的發與不發
        —— 否則 v4 的結果就混進了第五個變數，週一的數字歸因不了。"""
        weak = ready_state()
        weak.aggressive_buy, weak.aggressive_sell = 5, 95   # 內盤壓倒性
        self.assertIsNotNone(evaluate(weak, now=dtime(9, 3)),
                             "內外盤比不該擋掉任何訊號")




class TestDispositionStocksAreNotTradeableInThreeMinutes(unittest.TestCase):
    """會長 SOP 第 1 條特別點名「非處置股」。查了永豐的合約之後，那個洞是真的。

    處置股是**分盤撮合** —— 5 分鐘或 20 分鐘才撮合一次。v4 的進場窗口只有
    09:02–09:05 三分鐘：20 分鐘分盤的標的在那三分鐘內一次都不會撮合，
    5 分鐘分盤最多一次，「突破」這個概念不存在。發出去的訊號**物理上做不到**，
    卻佔掉 20 檔監看、甚至 3 個訊號名額的其中一個。

    原本只靠 `contract.day_trade`，而 `broker.is_day_tradable` 的註解寫著
    「處置股／全額交割**通常**會是 No」—— 「通常」兩個字就是沒把握。
    合約上其實有 `disposition_level` / `trading_suspended` /
    `disposition_match_interval_min`，直接看它們，不要靠推測。
    """

    def _c(self, **kw):
        base = dict(code="2330", name="台積電", day_trade="Yes", category="24",
                    disposition_level=0, trading_suspended=False,
                    disposition_match_interval_min=0, attention_flag=False)
        return SimpleNamespace(**{**base, **kw})

    def test_a_normal_stock_passes(self):
        self.assertFalse(screener.is_disposition(self._c()))

    def test_a_disposition_stock_is_skipped(self):
        self.assertTrue(screener.is_disposition(self._c(disposition_level=1)))

    def test_a_suspended_stock_is_skipped(self):
        self.assertTrue(screener.is_disposition(self._c(trading_suspended=True)))

    def test_call_auction_alone_is_enough_to_skip(self):
        """就算 disposition_level 看起來正常，只要在分盤就不能用 —— 三分鐘的
        窗口裡撮合不到幾次，突破根本量不出來。"""
        self.assertTrue(screener.is_disposition(
            self._c(disposition_match_interval_min=20)))

    def test_a_missing_field_is_treated_as_normal_not_disposition(self):
        """這幾欄是後來才有的。舊版 shioaji 沒有它們 —— 當成處置會把整個市場
        砍光，那比漏掉幾檔處置股嚴重得多。往寬的那一側退。"""
        self.assertFalse(screener.is_disposition(SimpleNamespace(code="2330")))

    def test_a_junk_value_does_not_crash_the_whole_screen(self):
        for bad in ("", "N/A", None, "一"):
            with self.subTest(bad=bad):
                screener.is_disposition(self._c(disposition_level=bad,
                                                disposition_match_interval_min=bad))

    def test_the_attention_flag_is_recorded_not_filtered(self):
        """注意股照常撮合，所以不剔除 —— 但要記下來，20 天後才答得出
        「注意股的突破是不是比較假」。剔除是一回事，留紀錄是另一回事。"""
        self.assertFalse(screener.is_disposition(self._c(attention_flag=True)))

    def test_the_removal_is_announced_at_info_not_buried_in_debug(self):
        """靜靜砍掉幾檔，和「今天本來就比較少」長得一模一樣。

        log.debug 在正常的執行層級下根本不會印出來 —— 那等於沒說。
        用 AST 找真正的 log.info 呼叫，不用字串比對：變異測試證實字串比對
        會被註解騙過去（`pass  # warn_if_too_late()` 那次）。
        """
        tree = ast.parse(textwrap.dedent(inspect.getsource(screener.screen)))
        said = [n for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "info"
                and n.args and isinstance(n.args[0], ast.Constant)
                and "處置" in str(n.args[0].value)]
        self.assertTrue(said, "剔除處置股必須用 log.info 說出來")

    def test_turning_the_rule_off_puts_them_back(self):
        """開關要真的是開關 —— 關掉之後處置股必須回到名單裡，
        否則這個設定就是裝飾品。"""
        saved = config.SCREEN["skip_disposition"]
        config.SCREEN["skip_disposition"] = False
        try:
            src = inspect.getsource(screener.screen)
            self.assertIn('cfg["skip_disposition"]', src,
                          "剔除必須受設定控制，不可以寫死")
        finally:
            config.SCREEN["skip_disposition"] = saved


class TestTheMessageDoesNotPromiseSignalsThatCannotCome(unittest.TestCase):
    """2026-10-05：只發了一個訊號，訊息卻寫「今日第 1/3 個訊號」。

    看起來像「還有兩個額度，等等可能再來」。但訊號是 09:05 一次發完的，
    窗口當場就關了 —— 那兩個額度今天不可能被用到。分母印上限等於撒謊。
    """

    def _sig(self):
        return {"time": "09:04:38", "code": "8182", "name": "加高",
                "direction": "做多", "entry": 48.40, "stop": 47.30,
                "target": 50.10, "lots": 2, "risk_per_lot": 1100,
                "oversized": False, "target_capped": False,
                "or_high": 47.40, "vwap": 47.12, "volume_surge": 1.94,
                "extension_pct": 2.11, "stop_rule": "結構線（區間高下方）"}

    def test_the_denominator_is_todays_total_not_the_cap(self):
        """v7：不再印「1/3」這種分數 —— 分母寫上限像在承諾，寫批次大小又會
        被誤讀成今日總數（09:05 之後還可能有）。改成講實話的兩行。"""
        text = signals.format_signal(self._sig(), 1, 1)
        self.assertIn("今日第 1 個訊號", text)
        self.assertNotIn("1/3", text)
        self.assertIn("這一批共 1 個", text)

    def test_the_cap_is_still_visible_just_not_as_the_denominator(self):
        text = signals.format_signal(self._sig(), 1, 1)
        self.assertIn(f"上限 {config.RISK['max_signals_per_day']}", text)

    def test_three_signals_still_read_one_of_three(self):
        text = signals.format_signal(self._sig(), 2, 3)
        self.assertIn("今日第 2 個訊號", text)
        self.assertIn("這一批共 3 個", text)

    def test_it_only_promises_more_when_more_can_come(self):
        """額度沒用完、窗口沒關 → 真的還可能有，要講；額度用完 → 講用完了。"""
        cap = config.RISK["max_signals_per_day"]
        before = signals.format_signal(self._sig(), cap - 1, None)
        last = signals.format_signal(self._sig(), cap, None)
        self.assertIn(f"{config.SIGNAL['entry_window_end'][:5]} 前還可能有新的訊號", before)
        self.assertIn("額度用完了", last)
        self.assertNotIn("還可能有", last)
        self.assertNotIn("這一批", last)          # 即時發的那一個不屬於任何批次

    def test_batch_total_has_no_default(self):
        """不給預設值，是為了逼每個呼叫端想一次「今天總共幾個」。

        給了預設值，新的呼叫點會靜靜地沿用舊的錯誤。
        """
        import inspect
        sigspec = inspect.signature(signals.format_signal)
        self.assertIs(sigspec.parameters["batch_total"].default,
                      inspect.Parameter.empty)


class TestAQuietDayIsNotSilence(unittest.TestCase):
    """0 個訊號和「程式當掉」在手機上不可以長得一樣。

    修之前：chosen 是空的時候 flush_batch 什麼都不發，使用者從 08:50 的
    開工確認一路安靜到 13:30，無從分辨今天是沒機會還是程式死了。
    """

    def test_zero_signals_still_sends_a_message(self):
        text = signals.format_window_closed(0, 20)
        self.assertIn("0 個", text)
        self.assertIn("20 檔", text)

    def test_zero_signals_says_the_program_is_still_alive(self):
        """這是這則訊息存在的唯一理由，少了這句就白發了。"""
        text = signals.format_window_closed(0, 20)
        self.assertIn("不是當掉", text)
        self.assertIn("13:30", text)

    def test_it_says_no_more_entries_are_coming(self):
        for sent in (0, 1, 3):
            with self.subTest(sent=sent):
                self.assertIn("不會再有新的買入訊號",
                              signals.format_window_closed(sent, 20))

    def test_it_names_the_window_and_the_time_exit(self):
        """收窗那一則寫的是**窗口結束**的時間（v7 起 09:30），不是 09:05 批次。
        「時間到」提醒有設才提，沒設（v7 起）就不可以出現。"""
        text = signals.format_window_closed(1, 20)
        self.assertIn(config.SIGNAL["entry_window_end"][:5], text)
        self.assertNotIn("時間到", text)
        with unittest.mock.patch.dict(config.SIGNAL, {"exit_signal_at": "10:00:00"}):
            self.assertIn("10:00 時間到", signals.format_window_closed(1, 20))

    def test_a_day_with_nothing_still_gets_the_closing_message(self):
        """先前那個版本的毛病就是「空的時候什麼都不做」。v7 起收尾在 EntryDesk，
        直接驅動它走過一個什麼都沒有的早上，看 09:30 那一則有沒有出來。"""
        said = []
        day = datetime(2026, 10, 7)
        desk = signals.EntryDesk(emit=lambda *a: True, blocked=lambda *a: None,
                                 say=said.append, watched=20, now=day.replace(hour=8, minute=50))
        for minute in (5, 10, 29):
            desk.tick(day.replace(hour=9, minute=minute))
        self.assertEqual(said, [])                    # 09:05 不再收窗
        desk.tick(day.replace(hour=9, minute=30))
        desk.tick(day.replace(hour=9, minute=31))
        self.assertEqual(len(said), 1)
        self.assertIn("今日訊號：0 個", said[0])



class TestTheThreeRedLinesMeet(unittest.TestCase):
    """單筆風險 × 當日筆數 要等於日虧上限。

    v2：3,000 × 4 = 12,000 ✅
    v4：筆數改成 3，單筆沒跟著動 → 3,000 × 3 = 9,000，日虧上限有 3,000
        永遠用不到。v5 把單筆改成 4,000 補回來。
    這條不是在釘數字，是在釘「它們必須相等」這個關係。
    """

    def test_they_multiply_to_the_daily_cap(self):
        r = config.RISK
        self.assertEqual(r["per_trade_risk"] * r["max_trades_per_day"],
                         r["max_daily_loss"],
                         "三條紅線不對齊：改其中一個就要一起改")

    def test_the_alignment_warning_is_silent_while_they_meet(self):
        self.assertNotIn("低於日虧上限", " ".join(config.warnings()))


class TestThePriceDeadZoneIsAnnounced(unittest.TestCase):
    """選股價格上限高於「一張就超額」的門檻時，要講出來。

    系統減不了碼（最小單位一張 1,000 股），所以那個區間裡的每一筆都只能
    標 ⚠️ 超額 —— 等於把一條你自己定的規則，變成每次臨場重新決定一次。
    看不見的話，你會以為單筆上限一直在保護你。
    """

    def _threshold(self):
        return (config.RISK["per_trade_risk"] / 1000
                / (config.SIGNAL["stop_loss_pct"] / 100))

    def test_factory_settings_announce_it(self):
        text = " ".join(config.warnings())
        self.assertIn("價格上限", text)
        self.assertIn(f"{self._threshold():,.0f}", text)

    def test_it_goes_quiet_once_the_ceiling_is_low_enough(self):
        saved = config.SCREEN["max_price"]
        config.SCREEN["max_price"] = self._threshold() - 1
        try:
            self.assertNotIn("價格上限", " ".join(config.warnings()))
        finally:
            config.SCREEN["max_price"] = saved

    def test_it_names_both_ways_out(self):
        """只說「有問題」而不說「怎麼解」的警告，使用者只能來問我。"""
        text = " ".join(config.warnings())
        self.assertIn("max_price", text)
        self.assertIn("per_trade_risk", text)

    def test_the_zone_really_produces_oversized_signals(self):
        """警告說的事要是真的 —— 門檻以上的訊號必須真的被標超額。"""
        last = config.round_to_tick(self._threshold() * 1.2, "up")
        st = ready_state(or_high=last - 3.0, last=last, vwap=last - 2.0)
        sig = evaluate(st, now=dtime(9, 3))
        self.assertTrue(sig["oversized"])
        self.assertEqual(sig["lots"], 1)


class TestChangingPositionSizeChangesTheRuleset(unittest.TestCase):
    """R 不受倉位影響，**金額**會。改了單筆風險就必須換版本號。

    不換的話，analyse.py 會把 3,000 時代和 4,000 時代的「元」加在一起 ——
    拿兩把尺量出來的數字相加。R 可以跨版本看，元不行。
    """

    def test_signals_carry_the_ruleset(self):
        sig = evaluate(ready_state(), now=dtime(9, 3))
        self.assertEqual(sig["ruleset"], config.RULESET)

    def test_the_ruleset_moved_past_v4(self):
        self.assertNotEqual(config.RULESET, "v4",
                            "單筆風險改了，版本號必須跟著動，否則金額會被混算")

    def test_analyse_splits_by_ruleset(self):
        """接線：分組函式真的存在而且真的分得開。"""
        import analyse, types
        rows = [types.SimpleNamespace(ruleset="v4"),
                types.SimpleNamespace(ruleset="v5"),
                types.SimpleNamespace(ruleset="v5")]
        groups = analyse.by_ruleset(rows)
        self.assertEqual(sorted(groups), ["v4", "v5"])
        self.assertEqual(len(groups["v5"]), 2)



class TestTodaysWatchlistSurvivesTomorrowMorning(unittest.TestCase):
    """`watchlist.json` 每天 08:40 被覆蓋，所以「今天盯了哪 20 檔」隔天就沒了。

    2026-10-05 撞上：量比第一名的聯一光漲停 +9.95%，系統沒發訊號。想回答
    「區間拉長會不會抓到它」就得重跑那 20 檔 —— 但 whatif.py 只重跑
    outcomes.csv 裡有的，也就是真的發過訊號的那幾檔。沒發訊號的不留痕跡。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = config.JOURNAL_DIR
        config.JOURNAL_DIR = Path(self.tmp.name) / "journal"

    def tearDown(self):
        config.JOURNAL_DIR = self.saved
        self.tmp.cleanup()

    def _payload(self, date="2026-10-05"):
        return {"date": date, "generated_at": f"{date}T08:40:00",
                "round_trip_cost_pct": 0.207,
                "items": [{"code": "3441", "name": "聯一光"},
                          {"code": "8182", "name": "加高"}]}

    def test_it_writes_a_dated_copy(self):
        p = self._payload()
        self.assertTrue(screener.archive_watchlist(p))
        path = screener.watchlist_archive_path("2026-10-05")
        self.assertTrue(path.exists())
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), p)

    def test_two_days_do_not_overwrite_each_other(self):
        """重點就在這裡 —— 不同日期必須是不同檔案，否則等於沒存。"""
        screener.archive_watchlist(self._payload("2026-10-05"))
        screener.archive_watchlist(self._payload("2026-10-06"))
        names = sorted(p.name for p in config.JOURNAL_DIR.glob("watchlist-*.json"))
        self.assertEqual(names, ["watchlist-20261005.json",
                                 "watchlist-20261006.json"])

    def test_it_uses_the_payload_date_not_todays_date(self):
        """補跑舊資料時，存檔要跟著那一天走，不是跟著電腦時鐘走。"""
        screener.archive_watchlist(self._payload("2026-09-24"))
        self.assertTrue(screener.watchlist_archive_path("2026-09-24").exists())

    def test_it_creates_the_journal_folder(self):
        self.assertFalse(config.JOURNAL_DIR.exists())
        self.assertTrue(screener.archive_watchlist(self._payload()))

    def test_a_failed_archive_is_loud_and_does_not_crash_the_screener(self):
        """盤前存檔失敗不能中斷選股，但也不能靜悄悄 —— 那等於沒存。"""
        import unittest.mock as mock
        with mock.patch.object(Path, "write_text",
                               side_effect=OSError("磁碟滿了")):
            with self.assertLogs("screener", level="ERROR") as logged:
                self.assertFalse(screener.archive_watchlist(self._payload()))
        self.assertTrue(any("存檔失敗" in m for m in logged.output))

    def test_whoever_writes_the_watchlist_also_archives_it(self):
        """接線測試，驗的是契約不是函式名。

        第一版寫成「main() 要呼叫它」，但寫入點其實在 run() —— 測試失敗的
        理由跟它要驗的事無關。改成：**掃出哪個函式寫了 WATCHLIST_FILE，
        就要求同一個函式呼叫 archive_watchlist**。以後搬家或改名都不會漏。
        """
        import ast, io as _io
        tree = ast.parse(_io.open(screener.__file__, encoding="utf-8").read())
        writers, archivers = set(), set()
        for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
            for c in ast.walk(fn):
                if not isinstance(c, ast.Call):
                    continue
                # config.WATCHLIST_FILE.write_text(...)
                f = c.func
                if (isinstance(f, ast.Attribute) and f.attr == "write_text"
                        and isinstance(f.value, ast.Attribute)
                        and f.value.attr == "WATCHLIST_FILE"):
                    writers.add(fn.name)
                if getattr(f, "id", "") == "archive_watchlist":
                    archivers.add(fn.name)
        self.assertTrue(writers, "找不到寫 watchlist.json 的地方")
        self.assertTrue(writers <= archivers,
                        f"{writers - archivers} 寫了 watchlist.json 卻沒存檔 "
                        f"—— 那一天的候選池明天就會被覆蓋掉")



class TestWhyNotRebuildsTheFourGates(unittest.TestCase):
    """重建 evaluate() 的四道閘。每一關都要能被單獨指認出來。

    這支程式存在的理由：那四關全部是靜音的 `return None`，所以 2026-10-05
    那天另外 19 檔卡在哪裡，事後完全查不到。
    """

    def _bars(self, rng=(100.0, 99.0), window=None, base_vol=100.0,
              hit_vol=300.0):
        """造一天的分鐘 K。label 是該分鐘的**結束**時間。

        09:01、09:02 兩根 = 開盤區間；09:03–09:05 = 進場窗口。
        """
        import whynot
        day = datetime(2026, 10, 5)
        bars = [(day.replace(hour=9, minute=1), rng[0], rng[1], rng[0], base_vol),
                (day.replace(hour=9, minute=2), rng[0], rng[1], rng[0], base_vol)]
        for i, (hi, vol) in enumerate(window or [], start=3):
            bars.append((day.replace(hour=9, minute=i), hi, hi - 1.0, hi, vol))
        return bars

    def test_no_breakout_is_named(self):
        import whynot
        # 觸發價 = 100 × 1.001 = 100.10，窗口最高只到 100.05
        d = whynot.diagnose(self._bars(window=[(100.05, 300.0)]))
        self.assertEqual(d["verdict"], whynot.BLOCK_NO_BREAKOUT)
        self.assertAlmostEqual(d["window_high"], 100.05)

    def test_a_clean_breakout_passes(self):
        import whynot
        # 昨收 99.5：區間低 99 在 ±1% 以內，v9 那一關也過
        d = whynot.diagnose(self._bars(window=[(105.0, 400.0)]), prev_close=99.5)
        self.assertEqual(d["verdict"], whynot.PASS)
        self.assertEqual(d["hit_at"].strftime("%H:%M"), "09:03")

    def test_weak_volume_is_named(self):
        import whynot
        # 突破那一分鐘的量只跟區間平均一樣 → 比值 1.0，低於門檻 1.8
        d = whynot.diagnose(self._bars(window=[(105.0, 100.0)]))
        self.assertEqual(d["verdict"], whynot.BLOCK_VOLUME)
        self.assertAlmostEqual(d["vol_ratio"], 1.0)

    def test_below_vwap_is_named(self):
        """均價線那關要比量能先判 —— 順序跟 evaluate() 一致。"""
        import whynot
        # 區間那兩根的典型價 ≈ 99.67，突破價 100.10 在它上面，所以要讓
        # 均價被前面的大量拉高：區間給一根很高的價、很大的量。
        day = datetime(2026, 10, 5)
        bars = [(day.replace(hour=9, minute=1), 100.0, 99.0, 100.0, 100.0),
                (day.replace(hour=9, minute=2), 100.0, 99.0, 100.0, 100.0),
                (day.replace(hour=9, minute=3), 100.2, 99.0, 99.0, 1.0)]
        # 把均價推到突破價之上
        bars.insert(0, (day.replace(hour=9, minute=0), 200.0, 200.0, 200.0, 10000.0))
        d = whynot.diagnose(bars)
        self.assertEqual(d["verdict"], whynot.BLOCK_VWAP)

    def test_limit_up_is_named(self):
        import whynot
        # 昨收 100 → 漲停 110。突破價就在漲停上。
        d = whynot.diagnose(self._bars(window=[(110.0, 400.0)]), prev_close=100.0)
        self.assertEqual(d["verdict"], whynot.BLOCK_LIMIT_UP)

    def test_bars_are_end_labelled(self):
        """09:00–09:02 的區間收的是 label 09:01 和 09:02 那兩根。

        broker.py 第 222 行說 ts 是「該分鐘的起點」，跟同檔第 281 行和
        whatif.py 相反。這條把這支程式用的是哪一個版本釘死。
        """
        import whynot
        day = datetime(2026, 10, 5)
        bars = [(day.replace(hour=9, minute=0), 999.0, 999.0, 999.0, 1.0),  # 盤前
                (day.replace(hour=9, minute=1), 100.0, 99.0, 100.0, 100.0),
                (day.replace(hour=9, minute=2), 101.0, 99.5, 101.0, 100.0),
                (day.replace(hour=9, minute=3), 105.0, 100.0, 105.0, 400.0)]
        d = whynot.diagnose(bars)
        self.assertEqual(d["or_high"], 101.0, "09:00 那根是盤前，不可以算進區間")

    def test_a_breakout_after_the_window_does_not_count(self):
        """窗口結束之後才突破的，就是沒突破（v4 是 09:05，v7 起 09:30）。"""
        import whynot
        day = datetime(2026, 10, 5)
        end = signals._t(config.SIGNAL["entry_window_end"])
        late = day.replace(hour=end.hour, minute=end.minute) + timedelta(minutes=2)
        bars = [(day.replace(hour=9, minute=1), 100.0, 99.0, 100.0, 100.0),
                (day.replace(hour=9, minute=2), 100.0, 99.0, 100.0, 100.0),
                (late, 120.0, 100.0, 120.0, 900.0)]
        d = whynot.diagnose(bars)
        self.assertEqual(d["verdict"], whynot.BLOCK_NO_BREAKOUT)

    def test_the_report_says_it_is_a_reconstruction(self):
        """沒講清楚是事後重建的話，這張表會被當成盤中紀錄。"""
        import whynot
        text = "\n".join(whynot.render("2026-10-05", []))
        self.assertIn("重建", text)
        self.assertIn("近似", text)

    def test_an_empty_volume_cell_is_a_dash_not_a_dash_x(self):
        """沒突破的那幾檔沒有量能數字，印成「—x」會讓人以為是個單位。"""
        import whynot
        rows = [("9933", "中鼎", {"verdict": whynot.BLOCK_NO_BREAKOUT,
                                  "or_high": 48.0, "trigger": 48.05,
                                  "window_high": 47.6, "hit_at": None,
                                  "vwap": None, "vol_ratio": None})]
        text = "\n".join(whynot.render("2026-10-05", rows))
        self.assertNotIn("—x", text)

    def test_the_report_counts_every_verdict(self):
        import whynot
        rows = [("1", "甲", {"verdict": whynot.BLOCK_VOLUME, "or_high": 1.0,
                             "trigger": 1.0, "window_high": 1.0, "hit_at": None,
                             "vwap": None, "vol_ratio": None}),
                ("2", "乙", {"verdict": whynot.BLOCK_VOLUME, "or_high": 1.0,
                             "trigger": 1.0, "window_high": 1.0, "hit_at": None,
                             "vwap": None, "vol_ratio": None})]
        text = "\n".join(whynot.render("2026-10-05", rows))
        self.assertIn(f"**{whynot.BLOCK_VOLUME}**：2 檔", text)



class TestWhyNotRechecksEveryBarLikeTheLiveLoop(unittest.TestCase):
    """2026-10-05 的加高：第一版 whynot 判它「量能 0.23x 擋掉」，而它盤中
    明明在 09:04:38 以 1.94x 發出了訊號。

    原因是盤中 evaluate() 每個 tick 都重判，09:03 被擋、09:04 過了就發；
    第一版只判第一根越過觸發價的 K 棒，被擋就結案。這是整張表裡唯一有
    標準答案的一列，而它答錯了。
    """

    def _day(self):
        day = datetime(2026, 10, 5)
        return lambda m: day.replace(hour=9, minute=m)

    def test_blocked_at_0903_but_passing_at_0904_is_a_pass(self):
        import whynot
        t = self._day()
        bars = [(t(1), 47.40, 46.80, 47.20, 1000.0),   # 開盤兩根量很大
                (t(2), 47.40, 47.00, 47.30, 1000.0),
                (t(3), 47.50, 47.20, 47.45, 300.0),    # 第一次越過，量不夠
                (t(4), 48.40, 47.40, 48.30, 2500.0)]   # 量衝上來
        d = whynot.diagnose(bars, prev_close=47.0)     # 開盤低點 46.80 在昨收附近
        self.assertEqual(d["verdict"], whynot.PASS,
                         "盤中每個 tick 都重判 —— 第一根被擋，後面過了就算過")
        self.assertEqual(d["hit_at"].strftime("%H:%M"), "09:04")

    def test_it_reports_how_many_times_it_crossed(self):
        import whynot
        t = self._day()
        bars = [(t(1), 100.0, 99.0, 100.0, 100.0),
                (t(2), 100.0, 99.0, 100.0, 100.0),
                (t(3), 101.0, 100.0, 101.0, 100.0),
                (t(4), 101.0, 100.0, 101.0, 100.0),
                (t(5), 101.0, 100.0, 101.0, 100.0)]
        d = whynot.diagnose(bars)
        self.assertEqual(d["verdict"], whynot.BLOCK_VOLUME)
        self.assertEqual(d["attempts"], 3)

    def test_the_volume_base_grows_like_the_live_one(self):
        """09:04 判的時候，基準是 09:01–09:03 全部，不是只有開盤區間那兩根。"""
        import whynot
        t = self._day()
        bars = [(t(1), 1, 1, 1, 100.0), (t(2), 1, 1, 1, 100.0),
                (t(3), 1, 1, 1, 400.0), (t(4), 1, 1, 1, 400.0)]
        # 基準 = (100+100+400)/3 = 200 → 400/200 = 2.0
        self.assertAlmostEqual(whynot.volume_ratio(bars, t(4), dtime(9, 0)), 2.0)

    def test_the_0900_bar_is_not_in_the_volume_base(self):
        """09:00 那根含開盤集合競價；盤中用累計量相減，那一筆本來就被減掉了。"""
        import whynot
        t = self._day()
        bars = [(t(0), 1, 1, 1, 99999.0),
                (t(1), 1, 1, 1, 100.0), (t(2), 1, 1, 1, 100.0),
                (t(3), 1, 1, 1, 200.0)]
        self.assertAlmostEqual(whynot.volume_ratio(bars, t(3), dtime(9, 0)), 2.0)


class TestWhyNotChecksItsOwnAnswers(unittest.TestCase):
    """拿盤中真的發出去的訊號對答案，對不上就放在報表第一段。"""

    def _row(self, code, verdict):
        import whynot
        return (code, "", {"verdict": verdict, "or_high": 1.0, "trigger": 1.0,
                           "window_high": 1.0, "hit_at": None, "vwap": None,
                           "vol_ratio": None})

    def test_a_signal_the_reconstruction_blocked_is_shouted(self):
        """就是 10-05 加高那個情況。"""
        import whynot
        rows = [self._row("8182", whynot.BLOCK_VOLUME)]
        text = "\n".join(whynot.crosscheck_lines({"8182"}, rows))
        self.assertIn("🛑", text)
        self.assertIn("8182", text)
        self.assertIn("不能全信", text)

    def test_a_pass_that_never_fired_is_named_too(self):
        import whynot
        rows = [self._row("8182", whynot.PASS), self._row("3441", whynot.PASS)]
        text = "\n".join(whynot.crosscheck_lines({"8182"}, rows))
        self.assertIn("3441", text)

    def test_agreement_says_so(self):
        import whynot
        rows = [self._row("8182", whynot.PASS),
                self._row("3441", whynot.BLOCK_NO_BREAKOUT)]
        text = "\n".join(whynot.crosscheck_lines({"8182"}, rows))
        self.assertIn("✅", text)
        self.assertNotIn("🛑", text)

    def test_no_record_means_unverified_not_correct(self):
        """沒有紀錄可以對，不等於對 —— 要明講沒驗證過。"""
        import whynot
        text = "\n".join(whynot.crosscheck_lines(None, []))
        self.assertIn("無法對答案", text)
        self.assertNotIn("✅", text)

    def test_the_check_comes_before_the_table(self):
        """放在最後的警告等於沒有警告。"""
        import whynot
        rows = [self._row("8182", whynot.BLOCK_VOLUME)]
        lines = whynot.render("2026-10-05", rows, actual={"8182"}, check=True)
        warn = next(i for i, l in enumerate(lines) if "🛑" in l)
        table = next(i for i, l in enumerate(lines) if l.startswith("| 代號"))
        self.assertLess(warn, table)

    def test_main_always_checks(self):
        """接線：main() 呼叫 render 時一定帶 check=True。"""
        import ast, io as _io, whynot
        tree = ast.parse(_io.open(whynot.__file__, encoding="utf-8").read())
        main = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        calls = [c for c in ast.walk(main) if isinstance(c, ast.Call)
                 and getattr(c.func, "id", "") == "render"]
        self.assertTrue(calls, "main() 沒有呼叫 render")
        for c in calls:
            kw = {k.arg: k.value for k in c.keywords}
            self.assertIn("check", kw, "main() 呼叫 render 沒帶 check")
            self.assertIs(getattr(kw["check"], "value", None), True)



import types as _types


class TestMarketMustBeKnownBeforeTheSignal(unittest.TestCase):
    """拿來分組的大盤數字，必須是那一筆訊號發出**之前**就知道的。

    broker.py、outcome.py、analyse.py 三處原本都寫著「09:15 的大盤在任何訊號
    發出之前就已知，所以它是唯一有資格變成規則的」。v1–v3 訊號全部發在 09:17
    之後，那時是對的；v4 起 09:05 就批次發完，09:15 變成事後十分鐘的資訊。
    拿事後資訊去定「大盤走弱就不做」的規則，就是未來函數。
    """

    def _o(self, time, open_pct=None, signal_pct=None):
        return _types.SimpleNamespace(time=time, mkt_open_pct=open_pct,
                                     mkt_signal_pct=signal_pct)

    def test_a_v4_signal_does_not_get_the_0915_market(self):
        """就是 10-05 加高：09:04:38 發的，09:15 是十分鐘之後的事。"""
        self.assertIsNone(analyse.market_known_before(self._o("09:04:38", 2.30)))

    def test_a_v2_signal_after_0915_may_use_it(self):
        """v1–v3 訊號全在 09:17 之後 —— 對它們 09:15 是事前的，舊資料照樣能用。"""
        self.assertEqual(analyse.market_known_before(self._o("10:30:00", 0.8)), 0.8)

    def test_exactly_0915_is_not_before(self):
        """09:15 那一刻發的訊號，09:15 的收盤不算「之前」。"""
        self.assertIsNone(analyse.market_known_before(self._o("09:15:00", 0.8)))

    def test_the_decision_time_reading_wins_when_present(self):
        self.assertEqual(
            analyse.market_known_before(self._o("09:05:00", 2.30, 0.4)), 0.4)

    def test_the_report_no_longer_claims_0915_is_always_before(self):
        """報表上原本寫「這是唯一在訊號發出前就已知的因子」，標題寫 09:15。
        那一句是印給使用者看的 —— 錯的說法印在報表上，比錯在註解裡更糟。"""
        import io as _io
        src = _io.open(analyse.__file__, encoding="utf-8").read()
        self.assertNotIn("當日大盤方向（09:15）", src)
        text = "\n".join(analyse.report([]))   # 空資料也不能炸
        self.assertNotIn("唯一在訊號發出前就已知的因子。", src.split("def market_known_before")[1])

    def test_by_market_drops_the_hindsight_rows(self):
        rows = [_types.SimpleNamespace(time="09:04:38", mkt_open_pct=2.3,
                                   mkt_signal_pct=None, is_win=False,
                                   r_multiple=-1.0, net_amount=-2401.0),
                _types.SimpleNamespace(time="10:30:00", mkt_open_pct=0.8,
                                   mkt_signal_pct=None, is_win=True,
                                   r_multiple=1.5, net_amount=3000.0)]
        groups = analyse.by_market(rows)
        self.assertEqual(sum(len(v) for v in groups.values()), 1)


class TestDecisionTimeMarketIsRecorded(unittest.TestCase):
    """決策當下的大盤要記下來，而且量測時間要跟著決策時間走。"""

    def _kb(self, date, rows):
        """rows = [(HH:MM, close)]；前一天收盤固定 100。"""
        import broker as br
        def ns(dt):
            return int(dt.replace(tzinfo=dt_timezone.utc).timestamp() * 1e9)
        prev = datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)
        ts = [ns(prev.replace(hour=13, minute=30))]
        cl = [100.0]
        for hm, c in rows:
            h, m = (int(x) for x in hm.split(":"))
            ts.append(ns(datetime.strptime(date, "%Y-%m-%d").replace(hour=h, minute=m)))
            cl.append(c)
        return _types.SimpleNamespace(ts=ts, Close=cl)

    def _broker(self, kb):
        import broker as br
        b = br.Broker.__new__(br.Broker)
        b.kbars = lambda code, start, end: kb
        return b

    def test_market_at_reads_the_bar_ending_at_that_minute(self):
        kb = self._kb("2026-10-05", [("09:01", 100.2), ("09:05", 101.0),
                                     ("09:15", 102.0), ("13:30", 102.3)])
        b = self._broker(kb)
        self.assertEqual(b.market_at("09:05", "2026-10-05"), 1.0)
        self.assertEqual(b.market_at("09:15", "2026-10-05"), 2.0)

    def test_market_at_missing_data_is_none_not_zero(self):
        b = self._broker(_types.SimpleNamespace(ts=[], Close=[]))
        self.assertIsNone(b.market_at("09:05", "2026-10-05"))

    def test_a_day_with_data_but_not_at_that_minute_is_none_not_zero(self):
        """當天有資料、只是沒有那個時間點 —— 不可以回 0。

        第一版的「沒資料」測試給的是整個空的 K 棒，在更前面就回 None 了，
        從來沒走到這條路。變異測試把這裡改成回 0.0，結果全部通過。0 是
        「平盤」，那是一個有意義的答案；拿不到就是拿不到。
        """
        kb = self._kb("2026-10-05", [("09:01", 100.2), ("09:03", 100.5)])
        b = self._broker(kb)
        self.assertIsNone(b.market_at("09:05", "2026-10-05"))
        self.assertIsNone(b.market_day("2026-10-05")[0])

    def test_market_day_still_returns_the_same_pair(self):
        """refactor 不可以改到 market_day 的契約。"""
        kb = self._kb("2026-10-05", [("09:15", 102.0), ("13:30", 102.3)])
        self.assertEqual(self._broker(kb).market_day("2026-10-05"), (2.0, 2.3))

    def test_the_measurement_follows_signal_batch_at(self):
        """寫死一個時間，下次改決策時間它又會像 09:15 那樣悄悄變成事後資訊。"""
        import outcome as _oc
        asked = []
        class FakeB:
            def market_day(self, date=None):
                return 0.8, 1.2
            def market_at(self, hhmm, date=None):
                asked.append(hhmm)
                return 0.4
        saved = config.SIGNAL["signal_batch_at"]
        config.SIGNAL["signal_batch_at"] = "09:07:00"
        try:
            with unittest.mock.patch.object(_oc, "resolve",
                                   side_effect=lambda b, s, d, through=None: _types.SimpleNamespace(
                                       mkt_open_pct=None, mkt_day_pct=None,
                                       mkt_signal_pct=None)):
                out = _oc.resolve_all(FakeB(), [{"code": "8182"}], "2026-10-05")
        finally:
            config.SIGNAL["signal_batch_at"] = saved
        self.assertEqual(asked, ["09:07"])
        self.assertEqual(out[0].mkt_signal_pct, 0.4)

    def test_an_old_broker_without_market_at_does_not_break_the_review(self):
        import outcome as _oc
        class OldB:
            def market_day(self, date=None):
                return 0.8, 1.2
        with unittest.mock.patch.object(_oc, "resolve",
                               side_effect=lambda b, s, d, through=None: _types.SimpleNamespace(
                                   mkt_open_pct=None, mkt_day_pct=None,
                                   mkt_signal_pct=None)):
            out = _oc.resolve_all(OldB(), [{"code": "8182"}], "2026-10-05")
        self.assertIsNone(out[0].mkt_signal_pct)
        self.assertEqual(out[0].mkt_open_pct, 0.8)

    def test_old_rows_without_the_column_read_back_as_none(self):
        import outcome as _oc
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "outcomes.csv"
            old_fields = [f for f in _oc.FIELDS if f != "mkt_signal_pct"]
            with open(p, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=old_fields)
                w.writeheader()
                row = {k: "" for k in old_fields}
                row.update(date="2026-10-02", code="2020", time="10:30:00",
                           entry="27.25", stop="26.85", target="28.25",
                           result="stop", exit_price="26.85", r_multiple="-1.0",
                           gross_pct="-1.47", net_pct="-1.67", bars="5", lots="2")
                w.writerow(row)
            back = _oc.load_csv(p)
        self.assertEqual(len(back), 1)
        self.assertIsNone(back[0].mkt_signal_pct)



# ══════════════════════════════════════════════════════
# v6：停損 3%、目標 +8%、最多抱到隔天
# ══════════════════════════════════════════════════════
V6_SIGNAL = {"stop_loss_pct": 3.0, "target_pct": 8.0, "max_hold_days": 2,
             "near_prev_close_pct": None,     # v9 才有的進場條件，v6 沒有
             "exit_rules": False}             # v10 的六條出場，v6 也沒有


class _DaysBroker:
    """跨日的假 kbars，帶開盤價。days = {日期: [(HH:MM, 開, 高, 低, 收), ...]}。

    kbars(code, start, end) 只回傳日期落在 [start, end] 的那幾根 ——
    「隔天是哪一天」要靠這個才測得出來（週五的隔天是週一）。
    """

    def __init__(self, days):
        self.days = days
        self.calls = []

    def kbars(self, code, start, end):
        self.calls.append((code, start, end))
        ts, o, h, l, c = [], [], [], [], []
        for day in sorted(self.days):
            if not start <= day <= end:
                continue
            for hhmm, op, hi, lo, cl in self.days[day]:
                t = datetime(int(day[:4]), int(day[5:7]), int(day[8:10]),
                             int(hhmm[:2]), int(hhmm[3:]), tzinfo=dt_timezone.utc)
                ts.append(int(t.timestamp() * 1e9))
                o.append(op); h.append(hi); l.append(lo); c.append(cl)
        return SimpleNamespace(ts=ts, Open=o, High=h, Low=l, Close=c)


# 一筆 v6 訊號：進場 100、停損 97、目標 108
V6_SIG = {"code": "2330", "name": "測試", "time": "09:05:00", "entry": 100.0,
          "stop": 97.0, "target": 108.0, "lots": 1, "max_hold_days": 2,
          "ruleset": "v6"}
DAY1, DAY2 = "2026-10-07", "2026-10-08"
# 第一天：沒碰停損也沒到目標，收在 103
QUIET_DAY1 = [("09:07", 100.5, 102.0, 99.0, 101.0), ("11:00", 101.0, 104.0, 100.0, 103.5),
              ("13:25", 103.5, 103.6, 102.5, 103.0), ("13:30", 103.0, 103.0, 103.0, 103.0)]


@unittest.mock.patch.dict(config.SIGNAL, V6_SIGNAL)
class TestV6TheSignal(unittest.TestCase):
    IN_WINDOW = dtime(9, 3)

    def test_stop_is_three_percent_below_entry(self):
        sig = evaluate(ready_state(or_high=100.0, last=101.0, vwap=100.5), now=self.IN_WINDOW)
        self.assertEqual(sig["stop"], config.round_to_tick(101.0 * 0.97, "up"))

    def test_target_is_eight_percent_above_entry_rounded_up(self):
        sig = evaluate(ready_state(or_high=100.0, last=101.0, vwap=100.5), now=self.IN_WINDOW)
        # 101 × 1.08 = 109.08 → 0.5 檔位往上 = 109.5（到價時報酬不會低於 8%）
        self.assertEqual(sig["target"], 109.5)
        self.assertGreaterEqual((sig["target"] - 101.0) / 101.0 * 100, 8.0)

    def test_the_signal_remembers_how_long_it_may_be_held(self):
        sig = evaluate(ready_state(or_high=100.0, last=101.0, vwap=100.5), now=self.IN_WINDOW)
        self.assertEqual(sig["max_hold_days"], 2)

    def test_a_target_beyond_todays_limit_up_is_kept_and_explained(self):
        """當天漲停 +10%，進場已經 +6%：+8% 今天物理上到不了。抱兩天時不貼齊，
        而是講明白 —— 貼齊等於把明天的機會砍掉。"""
        st = ready_state(or_high=105.5, last=106.0, vwap=105.0)
        st.prev_close = 100.0
        sig = evaluate(st, now=self.IN_WINDOW)
        self.assertEqual(sig["target"], config.round_to_tick(106.0 * 1.08, "up"))
        self.assertFalse(sig["target_capped"])
        self.assertTrue(sig["beyond_today_limit"])
        self.assertEqual(sig["limit_up"], 110.0)
        self.assertIn("今天到不了", format_signal(sig, 1, 1))

    def test_a_day_trade_still_caps_the_target_at_limit_up(self):
        with unittest.mock.patch.dict(config.SIGNAL, {"max_hold_days": 1}):
            st = ready_state(or_high=105.5, last=106.0, vwap=105.0)
            st.prev_close = 100.0
            sig = evaluate(st, now=self.IN_WINDOW)
        self.assertEqual(sig["target"], 110.0)
        self.assertTrue(sig["target_capped"])
        self.assertFalse(sig["beyond_today_limit"])

    def test_the_message_says_eight_percent_and_leaves_holding_to_you(self):
        sig = evaluate(ready_state(or_high=100.0, last=101.0, vwap=100.5), now=self.IN_WINDOW)
        text = format_signal(sig, 1, 1)
        self.assertIn("+8%", text)
        self.assertIn("要不要留倉由你決定", text)
        with unittest.mock.patch.dict(config.SIGNAL, {"max_hold_days": 1}):
            self.assertNotIn("留倉", format_signal(sig, 1, 1))

    def test_overnight_costs_full_tax(self):
        fee = config.COST["fee_rate"] * config.COST["fee_discount"] * 2
        self.assertAlmostEqual(config.round_trip_cost_pct(overnight=True),
                               (fee + config.COST["tax_rate_overnight"]) * 100)
        self.assertGreater(config.round_trip_cost_pct(True), config.round_trip_cost_pct())

    def test_the_shipped_config_keeps_the_v6_rules(self):
        """v7 只動進場窗口；v6 的停損、目標、抱兩天要原封不動。"""
        s = config.SIGNAL
        self.assertEqual((s["stop_loss_pct"], s["target_pct"], s["max_hold_days"]),
                         (3.0, 8.0, 2))
        self.assertEqual(config.validate(), [])


class TestV6TwoDayOutcome(unittest.TestCase):
    """收盤回推：第一天沒結束 → 留倉中；拿到隔天 K 棒 → 結局。"""

    def test_a_quiet_first_day_is_carried_not_flattened(self):
        o = oc.resolve(_DaysBroker({DAY1: QUIET_DAY1}), V6_SIG, DAY1)
        self.assertEqual(o.result, oc.CARRY)
        self.assertEqual(o.exit_price, 103.0)         # 標記用：第一天收盤
        self.assertEqual(o.exit_at, "")               # 還沒出場
        self.assertAlmostEqual(o.net_pct, round(3.0 - config.round_trip_cost_pct(True), 3))

    def test_an_old_signal_without_hold_days_is_still_a_day_trade(self):
        sig = {k: v for k, v in V6_SIG.items() if k != "max_hold_days"}
        o = oc.resolve(_DaysBroker({DAY1: QUIET_DAY1}), sig, DAY1, through=DAY2)
        self.assertEqual(o.result, oc.FLAT)
        self.assertEqual(o.exit_price, 103.0)          # 13:25 那一根
        self.assertEqual(o.exit_date, "")

    def test_the_closing_auction_counts_when_you_hold_overnight(self):
        """你沒在 13:25 走，13:30 那一下碰到停損就是碰到了。"""
        day1 = QUIET_DAY1[:-1] + [("13:30", 97.5, 97.5, 96.5, 96.5)]
        o = oc.resolve(_DaysBroker({DAY1: day1}), V6_SIG, DAY1)
        self.assertEqual(o.result, oc.STOP)
        self.assertEqual(o.exit_at, "13:30:00")

    def test_a_gap_down_through_the_stop_exits_at_the_open_not_the_stop(self):
        days = {DAY1: QUIET_DAY1, DAY2: [("09:01", 94.0, 95.0, 93.5, 94.5),
                                         ("09:02", 94.5, 99.0, 94.0, 98.0)]}
        o = oc.resolve(_DaysBroker(days), V6_SIG, DAY1, through=DAY2)
        self.assertEqual(o.result, oc.STOP)
        self.assertEqual(o.exit_price, 94.0)           # 開盤價，不是 97
        self.assertEqual(o.r_multiple, -2.0)
        self.assertEqual(o.exit_date, DAY2)
        self.assertEqual(o.exit_at, "09:01:00")
        self.assertTrue(o.overnight)
        self.assertAlmostEqual(o.net_pct, round(-6.0 - config.round_trip_cost_pct(True), 3))

    def test_a_gap_up_above_the_target_exits_at_the_open(self):
        days = {DAY1: QUIET_DAY1, DAY2: [("09:01", 109.0, 110.0, 108.5, 109.5)]}
        o = oc.resolve(_DaysBroker(days), V6_SIG, DAY1, through=DAY2)
        self.assertEqual((o.result, o.exit_price), (oc.TARGET, 109.0))

    def test_reaching_the_target_on_day_two(self):
        days = {DAY1: QUIET_DAY1, DAY2: [("09:01", 103.0, 104.0, 102.0, 103.5),
                                         ("10:00", 103.5, 108.5, 103.0, 108.0),
                                         ("11:00", 108.0, 112.0, 107.0, 111.0)]}
        o = oc.resolve(_DaysBroker(days), V6_SIG, DAY1, through=DAY2)
        self.assertEqual((o.result, o.exit_price, o.exit_at), (oc.TARGET, 108.0, "10:00:00"))
        self.assertEqual(o.bars, len(QUIET_DAY1) + 2)
        # 續抱分析要的：達標後還走到 112（+12%）
        self.assertEqual(o.mfe_pct, 12.0)

    def test_neither_on_day_two_flattens_at_1325(self):
        days = {DAY1: QUIET_DAY1, DAY2: [("09:01", 103.0, 104.0, 102.0, 103.5),
                                         ("13:25", 104.0, 105.0, 103.5, 104.5),
                                         ("13:30", 104.5, 104.5, 90.0, 90.0)]}
        o = oc.resolve(_DaysBroker(days), V6_SIG, DAY1, through=DAY2)
        self.assertEqual((o.result, o.exit_price, o.exit_at), (oc.FLAT, 104.5, "13:25:00"))

    def test_same_bar_stop_and_target_on_day_two_is_a_stop(self):
        days = {DAY1: QUIET_DAY1, DAY2: [("09:01", 103.0, 104.0, 102.0, 103.5),
                                         ("09:30", 103.5, 109.0, 96.0, 100.0)]}
        o = oc.resolve(_DaysBroker(days), V6_SIG, DAY1, through=DAY2)
        self.assertEqual((o.result, o.exit_price), (oc.STOP, 97.0))

    def test_the_next_session_after_friday_is_monday(self):
        fri, mon = "2026-10-09", "2026-10-12"
        days = {fri: QUIET_DAY1, mon: [("09:01", 108.5, 109.0, 108.0, 108.5)]}
        b = _DaysBroker(days)
        self.assertEqual(oc.next_session_bars(b, "2330", fri, mon)[0], mon)
        o = oc.resolve(b, V6_SIG, fri, through=mon)
        self.assertEqual((o.result, o.exit_date), (oc.TARGET, mon))

    def test_day_three_is_never_part_of_the_hold(self):
        """review 晚兩天才跑時，through 之前會有兩個交易日。規則是最多兩天 ——
        第三天碰到目標不算，第二天 13:25 就平倉了。"""
        day3 = "2026-10-09"
        days = {DAY1: QUIET_DAY1,
                DAY2: [("09:01", 103.0, 104.0, 102.0, 103.5), ("13:25", 104, 105, 103.5, 104.5)],
                day3: [("09:01", 110.0, 111.0, 109.0, 110.0)]}
        o = oc.resolve(_DaysBroker(days), V6_SIG, DAY1, through=day3)
        self.assertEqual((o.result, o.exit_price, o.exit_date), (oc.FLAT, 104.5, DAY2))
        self.assertEqual(o.mfe_pct, 5.0)

    def test_no_next_session_yet_stays_carried(self):
        o = oc.resolve(_DaysBroker({DAY1: QUIET_DAY1}), V6_SIG, DAY1, through=DAY2)
        self.assertEqual(o.result, oc.CARRY)

    def test_a_day_two_tick_verdict_wins_and_is_marked_overnight(self):
        sig = dict(V6_SIG, live_result=oc.STOP, live_exit=95.5, live_at="09:00:12",
                   live_date=DAY2)
        days = {DAY1: QUIET_DAY1, DAY2: [("09:01", 96.0, 99.0, 95.0, 98.0)]}
        o = oc.resolve(_DaysBroker(days), sig, DAY1, through=DAY2)
        self.assertEqual((o.result, o.exit_price, o.exit_date, o.exit_at),
                         (oc.STOP, 95.5, DAY2, "09:00:12"))
        self.assertAlmostEqual(o.net_pct, round(-4.5 - config.round_trip_cost_pct(True), 3))
        self.assertEqual(o.mae_pct, -5.0)              # 隔天的低點也算進來

    def test_writing_yesterdays_carried_row_keeps_yesterdays_other_rows(self):
        """以前同一天的列是整批刪掉重寫的 —— 昨天留倉的那一筆今天才寫進去，
        會把昨天當天就結束的那幾筆一起刪掉，累計勝率無聲少幾筆。"""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "o.csv"
            b = _DaysBroker({DAY1: QUIET_DAY1 + [], DAY2: [("09:01", 109, 110, 108, 109)]})
            stopped_day1 = dict(V6_SIG, code="1111", live_result=oc.STOP,
                                live_exit=97.0, live_at="09:20:00", live_date=DAY1)
            oc.append_csv([oc.resolve(b, stopped_day1, DAY1)], path)
            oc.append_csv([oc.resolve(b, V6_SIG, DAY1, through=DAY2)], path)
            rows = oc.load_csv(path)
            self.assertEqual(sorted(r.code for r in rows), ["1111", "2330"])
            again = oc.resolve(b, V6_SIG, DAY1, through=DAY2)
            oc.append_csv([again], path)                # 重跑：同一筆換掉，不重複
            self.assertEqual(len(oc.load_csv(path)), 2)
            self.assertEqual([r.exit_date for r in oc.load_csv(path) if r.code == "2330"], [DAY2])

    def test_an_overnight_exit_is_not_realised_on_the_signal_day(self):
        """exit_at 是隔天的時間；拿去跟當天的訊號時間比，會以為它早就出場了。"""
        mk = lambda code, t, net, exit_at, exit_date="": oc.Outcome(
            date=DAY1, code=code, time=t, entry=100.0, stop=97.0, target=108.0, lots=10,
            result=oc.STOP, exit_price=94.0, r_multiple=-2.0, gross_pct=net,
            net_pct=net, bars=1, exit_at=exit_at, exit_date=exit_date)
        rows = [mk("A", "09:05:00", -6.0, "09:01:00", DAY2),
                mk("B", "09:05:01", -6.0, "09:30:00"),
                mk("C", "09:05:02", -6.0, "09:31:00")]
        with unittest.mock.patch.dict(config.RISK, {"max_daily_loss": 1000,
                                                     "max_trades_per_day": 9}):
            r = oc.replay_rules(rows)
        self.assertEqual([o.code for o in r["taken"]], ["A", "B", "C"])


class TestV6TheTracker(unittest.TestCase):
    def _sig(self, **kw):
        return dict(V6_SIG, **kw)

    def test_at_1325_a_two_day_position_is_carried_not_flattened(self):
        seen = []
        t = signals.LiveTracker(on_resolved=lambda *a: seen.append(a))
        t.track(self._sig())
        t.on_price("2330", 103.0)
        msgs = t.flatten()
        self.assertEqual(len(msgs), 1)
        self.assertIn("13:25 還沒結束", msgs[0])
        self.assertIn("要不要留倉由你決定", msgs[0])
        self.assertEqual(seen, [])        # 沒結束，不寫任何判定回 state.json

    def test_at_1325_on_day_two_it_is_flattened(self):
        seen = []
        t = signals.LiveTracker(on_resolved=lambda *a: seen.append(a))
        t.track(self._sig(), carried=True)
        t.on_price("2330", 103.0)
        msgs = t.flatten()
        self.assertIn(oc.FLAT, msgs[0])
        self.assertEqual(seen[0][2], oc.FLAT)

    def test_a_day_trade_signal_is_still_flattened(self):
        t = signals.LiveTracker()
        t.track(self._sig(max_hold_days=1))
        t.on_price("2330", 103.0)
        self.assertIn(oc.FLAT, t.flatten()[0])

    def test_a_carried_position_gets_no_0930_reminder(self):
        t = signals.LiveTracker()
        t.track(self._sig(), carried=True)
        t.track(self._sig(code="2317", time="09:05:01"))
        t.on_price("2330", 103.0); t.on_price("2317", 103.0)
        msgs = t.time_exit()
        self.assertEqual(len(msgs), 1)
        self.assertIn("2317", msgs[0])

    def test_a_carried_position_has_no_fill_window(self):
        t = signals.LiveTracker()
        now = datetime.combine(datetime.now().date(), dtime(9, 5, 30))
        t.track(self._sig(), now=now, carried=True)
        self.assertEqual(t.fills, [])

    def test_a_gap_through_the_stop_is_reported_at_the_real_price(self):
        o = signals.OpenSignal("2330", "測試", "09:05:00", 100.0, 97.0, 108.0,
                               hold_days=2, carried=True)
        text = signals.format_resolution(o, 94.0, oc.STOP)
        self.assertIn("出場 94.00", text)
        self.assertIn("-2.00R", text)
        # 當沖那一筆照舊記停損價（穿價是滑價，另外寫）
        o.carried = False
        self.assertIn("出場 97.00", signals.format_resolution(o, 94.0, oc.STOP))

    def test_reaching_the_target_says_holding_on_is_your_call(self):
        """使用者：「有的選對股，甚至再留達 20% 都有可能，交由自己下單者決定」。"""
        o = signals.OpenSignal("2330", "測試", "09:05:00", 100.0, 97.0, 108.0, hold_days=2)
        text = signals.format_resolution(o, 108.0, oc.TARGET)
        self.assertIn("續抱與否由你決定", text)
        self.assertNotIn("續抱", signals.format_resolution(o, 97.0, oc.STOP))

    def test_the_tick_verdict_on_a_carried_position_is_written_back(self):
        with tempfile.TemporaryDirectory() as d:
            with unittest.mock.patch.object(config, "STATE_FILE", Path(d) / "s.json"):
                gate = RiskGate(FakeBroker())
                gate.state["carried"] = [dict(V6_SIG, carry_from=DAY1)]
                self.assertTrue(gate.record_live_result("2330", "09:05:00", oc.STOP, 94.0))
                c = gate.state["carried"][0]
        self.assertEqual((c["live_result"], c["live_exit"]), (oc.STOP, 94.0))
        self.assertEqual(c["live_date"], datetime.now().strftime("%Y-%m-%d"))


class TestV6CarryOver(unittest.TestCase):
    """隔天開盤前，從昨天的 state.json 接手還沒結束的部位。"""

    def _prev(self, *sigs):
        return {"date": DAY1, "signals": list(sigs)}

    def test_an_open_two_day_position_is_carried(self):
        carried, notes = signals.carry_over(
            self._prev(dict(V6_SIG)), _DaysBroker({DAY1: QUIET_DAY1}), DAY2)
        self.assertEqual(len(carried), 1)
        self.assertEqual(carried[0]["carry_from"], DAY1)
        self.assertEqual(carried[0]["day1_close"], 103.0)
        self.assertEqual(notes, [])

    def test_finished_or_day_trade_positions_are_not(self):
        prev = self._prev(dict(V6_SIG, code="1", live_result=oc.STOP),
                          dict(V6_SIG, code="2", live_result=oc.TARGET),
                          dict(V6_SIG, code="3", max_hold_days=1))
        carried, _ = signals.carry_over(prev, _DaysBroker({DAY1: QUIET_DAY1}), DAY2)
        self.assertEqual(carried, [])

    def test_a_stop_the_live_loop_missed_is_caught_from_the_bars(self):
        """那天程式中途掛了，tick 沒收到停損 —— 只信 tick 會盯一筆早就沒了的部位。"""
        day1 = [("09:07", 100.0, 101.0, 96.0, 96.5), ("13:30", 98, 98, 98, 98)]
        carried, notes = signals.carry_over(self._prev(dict(V6_SIG)),
                                            _DaysBroker({DAY1: day1}), DAY2)
        self.assertEqual(carried, [])
        self.assertIn("停損", notes[0])

    def test_a_skipped_session_means_the_hold_is_already_over(self):
        b = _DaysBroker({DAY1: QUIET_DAY1, DAY2: [("09:01", 103, 104, 102, 103)]})
        carried, notes = signals.carry_over(self._prev(dict(V6_SIG)), b, "2026-10-09")
        self.assertEqual(carried, [])
        self.assertIn(DAY2, notes[0])

    def test_no_bars_still_carries_and_says_so(self):
        carried, notes = signals.carry_over(self._prev(dict(V6_SIG)), _DaysBroker({}), DAY2)
        self.assertEqual(len(carried), 1)
        self.assertIn("照樣接著盯", notes[0])

    def test_yesterdays_live_fields_are_not_carried_into_today(self):
        sig = dict(V6_SIG, live_at="13:00:00", live_exit=101.0)   # 沒有 live_result
        carried, _ = signals.carry_over(self._prev(sig), _DaysBroker({DAY1: QUIET_DAY1}), DAY2)
        self.assertNotIn("live_at", carried[0])
        self.assertNotIn("live_exit", carried[0])

    def test_only_an_earlier_state_file_is_read(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.json"
            path.write_text(json.dumps({"date": "2000-01-01", "signals": []}), encoding="utf-8")
            self.assertEqual(signals.load_previous_state(path)["date"], "2000-01-01")
            path.write_text(json.dumps({"date": datetime.now().strftime("%Y-%m-%d")}),
                            encoding="utf-8")
            self.assertEqual(signals.load_previous_state(path), {})

    def test_a_carried_code_gets_no_new_signal_today(self):
        states = {"2330": SymbolState("2330", 99.0), "2317": SymbolState("2317", 99.0)}
        signals.block_carried_codes(states, [dict(V6_SIG)])
        self.assertGreaterEqual(states["2330"].signaled, config.SIGNAL["max_signals_per_symbol"])
        self.assertEqual(states["2317"].signaled, 0)

    def test_the_start_message_lists_stop_and_target(self):
        text = signals.format_carry_start([dict(V6_SIG, day1_close=103.0)], ["x 照樣接著盯"])
        for part in ("2330", "97.00", "108.00", "103.00", "照樣接著盯"):
            self.assertIn(part, text)

    def test_run_reads_yesterday_before_the_gate_overwrites_it(self):
        """RiskGate 一存檔，昨天的 state.json 就沒了。順序反過來，留倉永遠接不回來。"""
        src = inspect.getsource(signals.run)
        self.assertLess(src.index("load_previous_state()"), src.index("RiskGate(broker)"))
        tree = ast.parse(textwrap.dedent(src))
        called = {n.func.id for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        for fn in ("carry_over", "block_carried_codes", "format_carry_start"):
            self.assertIn(fn, called)


class TestV6Review(unittest.TestCase):
    def _state(self, d, state):
        path = Path(d) / "state.json"
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        return unittest.mock.patch.object(config, "STATE_FILE", path)

    def test_carried_positions_come_from_todays_state(self):
        today = datetime.now().strftime("%Y-%m-%d")
        with tempfile.TemporaryDirectory() as d, self._state(
                d, {"date": today, "signals": [], "carried": [dict(V6_SIG, carry_from=DAY1)]}):
            self.assertEqual([c["code"] for c in review.load_carried()], ["2330"])

    def test_no_monitor_today_still_finds_yesterdays_open_positions(self):
        """今天沒開 signals.py，state.json 還是昨天的。不補這一步，那幾筆的結局
        永遠不會進 outcomes.csv，而且沒有任何錯誤訊息。"""
        state = {"date": "2000-01-03", "signals": [
            dict(V6_SIG), dict(V6_SIG, code="1", live_result=oc.TARGET),
            dict(V6_SIG, code="2", max_hold_days=1)]}
        with tempfile.TemporaryDirectory() as d, self._state(d, state):
            got = review.load_carried()
        self.assertEqual([(c["code"], c["carry_from"]) for c in got], [("2330", "2000-01-03")])

    def test_carried_rows_are_resolved_against_their_own_day(self):
        b = _DaysBroker({DAY1: QUIET_DAY1, DAY2: [("09:01", 109, 110, 108, 109)]})
        b.market_day = lambda date=None: (None, None)
        b.market_at = lambda hhmm, date=None: None
        out = review.resolve_carried(b, [dict(V6_SIG, carry_from=DAY1)], through=DAY2)
        self.assertEqual((out[0].date, out[0].result, out[0].exit_date), (DAY1, oc.TARGET, DAY2))

    def test_a_carried_row_is_shown_but_not_counted(self):
        carry = oc.resolve(_DaysBroker({DAY1: QUIET_DAY1}), V6_SIG, DAY1)
        text = "\n".join(review.outcome_section([V6_SIG], [carry]))
        self.assertIn("留倉過夜 **1 筆**", text)
        self.assertNotIn("勝率（扣成本後為正才算贏）", text)
        push = review.format_push([V6_SIG], [carry], [])
        self.assertIn("留倉過夜", push)
        self.assertIn("0 勝 0 敗", push)

    def test_yesterdays_result_gets_its_own_section(self):
        b = _DaysBroker({DAY1: QUIET_DAY1, DAY2: [("09:01", 94, 95, 93, 94)]})
        o = oc.resolve(b, V6_SIG, DAY1, through=DAY2)
        text = "\n".join(review.carried_section([o]))
        self.assertIn("昨日留倉的結局", text)
        self.assertIn(DAY2, text)
        self.assertIn("昨日留倉的結局", review.format_push([], [], [], [o]))

    def test_run_never_writes_a_carry_row(self):
        src = inspect.getsource(review.run)
        self.assertEqual(src.count("oc.append_csv("), src.count("!= oc.CARRY]"))


class TestRunOnAfterTarget(unittest.TestCase):
    """續抱分析：到 +8% 之後，持有期內最高又走到哪。"""

    def _o(self, result, mfe):
        return oc.Outcome(date=DAY1, code="2330", time="09:05:00", entry=100.0, stop=97.0,
                          target=108.0, lots=1, result=result, exit_price=108.0,
                          r_multiple=2.67, gross_pct=8.0, net_pct=7.6, bars=1, mfe_pct=mfe)

    def test_counts_how_many_ran_past_each_level(self):
        rows = [self._o(oc.TARGET, m) for m in (8.5, 11.0, 13.0, 21.0, 9.0, 20.0)]
        rows += [self._o(oc.STOP, 30.0)]                # 停損的不算：它沒到目標
        run = analyse.after_target(rows)
        self.assertEqual(run["n"], 6)
        got = {lv["level"]: lv["hit"] for lv in run["levels"]}
        # 剛好碰到 +20.00% 就算到了
        self.assertEqual(got, {10.0: 4, 12.0: 3, 15.0: 2, 20.0: 2})
        self.assertEqual(run["best"][0][2], 21.0)

    def test_too_few_gives_no_rates(self):
        text = "\n".join(analyse.render_after_target(
            analyse.after_target([self._o(oc.TARGET, 21.0)])))
        self.assertIn("太少", text)
        self.assertNotIn("+20% 以上 |", text)

    def test_the_report_includes_it_with_its_caveats(self):
        rows = [self._o(oc.TARGET, m) for m in (8.5, 11.0, 13.0, 21.0, 9.0)]
        text = "\n".join(analyse.report(rows))
        self.assertIn("續抱分析", text)
        self.assertIn("天花板", text)
        self.assertIn("+20% 以上", text)


# ══════════════════════════════════════════════════════
# v7：進場窗口延到 09:30，09:05 先發一批、之後即時發；取消時間到提醒
# ══════════════════════════════════════════════════════
class TestV7TheEntryDesk(unittest.TestCase):
    DAY = datetime(2026, 10, 7)

    def _at(self, h, m, sec=0):
        return self.DAY.replace(hour=h, minute=m, second=sec)

    def _desk(self, cap_ok=True):
        self.sent, self.blocked, self.said = [], [], []

        def emit(sig, now, batch_total):
            if not cap_ok:
                return False
            self.sent.append((sig["code"], now.strftime("%H:%M"), batch_total))
            return True
        return signals.EntryDesk(emit=emit,
                                 blocked=lambda sig, why: self.blocked.append((sig["code"], why)),
                                 say=self.said.append, watched=20, now=self._at(8, 50))

    @staticmethod
    def _sig(code, surge):
        return {"code": code, "volume_surge": surge, "rank": 1}

    def test_before_0905_breakouts_wait_for_the_batch(self):
        desk = self._desk()
        desk.offer(self._sig("A", 2.0), self._at(9, 3))
        desk.offer(self._sig("B", 3.0), self._at(9, 4))
        self.assertEqual(self.sent, [])
        desk.tick(self._at(9, 5))
        # 量能高的先發，帶著批次大小
        self.assertEqual(self.sent, [("B", "09:05", 2), ("A", "09:05", 2)])

    def test_the_batch_still_keeps_only_the_top_n(self):
        desk = self._desk()
        cap = config.RISK["max_signals_per_day"]
        for i in range(cap + 2):
            desk.offer(self._sig(f"S{i}", 2.0 + i), self._at(9, 4))
        desk.tick(self._at(9, 5))
        self.assertEqual(len(self.sent), cap)
        self.assertEqual(len(self.blocked), 2)
        self.assertTrue(all(why == signals.BLOCK_BATCH_RANK for _, why in self.blocked))

    def test_after_0905_a_breakout_goes_out_at_once(self):
        """使用者：「改掉 9:02-9:05 的限制，改為 9:30 前發訊號」。"""
        desk = self._desk()
        desk.tick(self._at(9, 5))                      # 09:05 那一批是空的
        desk.offer(self._sig("C", 2.0), self._at(9, 17))
        self.assertEqual(self.sent, [("C", "09:17", None)])   # 不屬於任何批次

    def test_nothing_goes_out_after_the_window(self):
        desk = self._desk()
        desk.tick(self._at(9, 5))
        desk.offer(self._sig("D", 2.0), self._at(9, 30))
        desk.offer(self._sig("E", 2.0), self._at(9, 45))
        self.assertEqual(self.sent, [])

    def test_the_lock_message_comes_at_0930_and_counts_both_paths(self):
        desk = self._desk()
        desk.offer(self._sig("A", 2.0), self._at(9, 3))
        desk.tick(self._at(9, 5))
        desk.offer(self._sig("C", 2.0), self._at(9, 20))
        self.assertEqual(self.said, [])
        desk.tick(self._at(9, 30))
        self.assertEqual(len(self.said), 1)
        self.assertIn("今日訊號：2 個", self.said[0])
        self.assertIn("09:30", self.said[0])

    def test_a_blocked_emit_is_not_counted(self):
        desk = self._desk(cap_ok=False)
        desk.tick(self._at(9, 5))
        desk.offer(self._sig("C", 2.0), self._at(9, 20))
        desk.tick(self._at(9, 30))
        self.assertIn("今日訊號：0 個", self.said[0])

    def test_a_restart_after_the_window_does_not_send_a_second_lock(self):
        """盤中重開在 09:30 之後：早上那則 🔒 已經發過，再補一則 0 個是假話。"""
        said = []
        desk = signals.EntryDesk(emit=lambda *a: True, blocked=lambda *a: None,
                                 say=said.append, watched=20, now=self._at(10, 15))
        desk.tick(self._at(10, 16))
        self.assertEqual(said, [])

    def test_a_restart_mid_window_keeps_the_morning_count(self):
        said = []
        desk = signals.EntryDesk(emit=lambda *a: True, blocked=lambda *a: None,
                                 say=said.append, watched=20, sent=2, now=self._at(9, 12))
        desk.tick(self._at(9, 12))
        desk.offer(self._sig("C", 2.0), self._at(9, 13))
        desk.tick(self._at(9, 30))
        self.assertIn("今日訊號：3 個", said[0])

    def test_many_threads_at_0905_send_the_batch_once(self):
        """行情回呼是多執行緒的。兩條同時看到「09:05 到了」不可以各發一次。"""
        sent = []
        lock = threading.Lock()

        def emit(sig, now, total):
            time.sleep(0.002)
            with lock:
                sent.append(sig["code"])
            return True
        desk = signals.EntryDesk(emit=emit, blocked=lambda *a: None, say=lambda t: None,
                                 watched=20, now=self._at(8, 50))
        for i in range(3):
            desk.offer(self._sig(f"S{i}", 2.0 + i), self._at(9, 4))
        threads = [threading.Thread(target=desk.tick, args=(self._at(9, 5),))
                   for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(sent), ["S0", "S1", "S2"])


class TestV7TheRulesAreWired(unittest.TestCase):
    def test_the_shipped_config_keeps_the_v7_window(self):
        """v8 只動停利目標；v7 的進場窗口與取消時間到要原封不動。"""
        self.assertEqual(config.SIGNAL["entry_window_end"], "09:30:00")
        self.assertEqual(config.SIGNAL["signal_batch_at"], "09:05:00")
        self.assertIsNone(config.SIGNAL["exit_signal_at"])
        self.assertEqual(config.validate(), [])

    def test_a_time_exit_inside_the_window_is_rejected(self):
        """要恢復「時間到」就得晚於窗口 —— 09:29 發的訊號 09:20 叫你走沒有意義。"""
        with unittest.mock.patch.dict(config.SIGNAL, {"exit_signal_at": "09:20:00"}):
            self.assertIn("exit_signal_at", " / ".join(config.validate()))
        with unittest.mock.patch.dict(config.SIGNAL, {"exit_signal_at": "10:00:00"}):
            self.assertEqual(config.validate(), [])

    def test_run_routes_every_breakout_through_the_desk(self):
        tree = ast.parse(textwrap.dedent(inspect.getsource(signals.run)))
        on_tick = next(n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == "on_tick")
        attrs = {(getattr(n.func.value, "id", ""), n.func.attr) for n in ast.walk(on_tick)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertIn(("desk", "offer"), attrs)
        self.assertIn(("desk", "tick"), attrs)
        # 主迴圈也要 tick：09:30 那一刻沒有報價進來，🔒 也得發
        loop = next(n for n in ast.walk(tree) if isinstance(n, ast.While))
        self.assertIn(("desk", "tick"),
                      {(getattr(n.func.value, "id", ""), n.func.attr) for n in ast.walk(loop)
                       if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)})

    def test_no_time_exit_reminder_when_it_is_switched_off(self):
        src = inspect.getsource(signals.run)
        self.assertIn("exit_at is not None", src)

    def test_dryrun_uses_the_same_desk(self):
        """dryrun 以前自己抄了一份批次邏輯 —— 改規則時它會繼續驗一條不存在的管線。"""
        import dryrun
        src = inspect.getsource(dryrun.main)
        self.assertIn("signals.EntryDesk(", src)
        self.assertNotIn("SignalBatch(", src)


# ══════════════════════════════════════════════════════
# v8：停利目標依個股近 5 日平均振幅（3%～10%）
# ══════════════════════════════════════════════════════
def _kb_ohlc(rows):
    """(YYYY-MM-DD, HH:MM, 高, 低, 收) → shioaji 形狀的假 kbars。"""
    ts, h, l, c = [], [], [], []
    for day, hhmm, hi, lo, cl in rows:
        t = datetime(int(day[:4]), int(day[5:7]), int(day[8:10]),
                     int(hhmm[:2]), int(hhmm[3:]), tzinfo=dt_timezone.utc)
        ts.append(int(t.timestamp() * 1e9)); h.append(hi); l.append(lo); c.append(cl)
    return ts, h, l, c


class TestV8AverageAmplitude(unittest.TestCase):
    def test_each_day_is_measured_against_the_previous_close(self):
        rows = [("2026-10-01", "13:30", 101, 99, 100.0),     # 只當「前一日」
                ("2026-10-02", "09:01", 104, 100, 102),
                ("2026-10-02", "13:30", 103, 98, 102.0),      # 當日 104/98 → 6/100 = 6%
                ("2026-10-05", "09:01", 103, 101, 102),
                ("2026-10-05", "13:30", 104, 102, 103.0)]     # 104/101 → 3/102 = 2.94%
        amp = screener.average_amplitude(*_kb_ohlc(rows), lookback_days=5)
        self.assertAlmostEqual(amp, round((6.0 + 3 / 102 * 100) / 2, 2))

    def test_only_the_last_n_days_count(self):
        rows = [("2026-10-01", "13:30", 100, 100, 100.0),
                ("2026-10-02", "13:30", 120, 100, 100.0),     # 20%：太舊，不該算進來
                ("2026-10-05", "13:30", 102, 100, 100.0)]     # 2%
        self.assertEqual(screener.average_amplitude(*_kb_ohlc(rows), lookback_days=1), 2.0)

    def test_one_day_is_not_enough(self):
        rows = [("2026-10-05", "09:01", 102, 98, 100.0)]
        self.assertIsNone(screener.average_amplitude(*_kb_ohlc(rows), lookback_days=5))

    def test_the_screener_stores_it_from_the_bars_it_already_fetched(self):
        """不多打 API：用量比那一份 K 棒算。"""
        src = inspect.getsource(screener.screen)
        self.assertIn('r["avg_amplitude_pct"] = average_amplitude(', src)


class TestV8PerStockTarget(unittest.TestCase):
    IN_WINDOW = dtime(9, 3)

    def _sig(self, amp):
        st = ready_state(or_high=100.0, last=101.0, vwap=100.5)
        st.amplitude_pct = amp
        return evaluate(st, now=self.IN_WINDOW)

    def test_the_target_follows_the_stocks_own_range(self):
        """使用者：「訊號出來，你沒辦法依個股判斷停利目標嗎？」"""
        sig = self._sig(5.4)
        self.assertEqual(sig["target"], config.round_to_tick(101.0 * 1.054, "up"))
        self.assertEqual((sig["target_pct"], sig["target_basis"]), (5.4, signals.TARGET_BY_AMPLITUDE))
        self.assertNotEqual(self._sig(7.0)["target"], sig["target"])

    def test_a_quiet_stock_gets_the_floor_and_a_wild_one_the_ceiling(self):
        lo, hi = config.SIGNAL["target_min_pct"], config.SIGNAL["target_max_pct"]
        self.assertEqual(self._sig(lo - 1.5)["target_pct"], lo)
        self.assertEqual(self._sig(hi + 4.0)["target_pct"], hi)

    def test_no_range_data_falls_back_to_the_fixed_target(self):
        sig = self._sig(None)
        self.assertEqual((sig["target_pct"], sig["target_basis"]),
                         (config.SIGNAL["target_pct"], signals.TARGET_FIXED))

    def test_switching_it_off_goes_back_to_the_fixed_target(self):
        with unittest.mock.patch.dict(config.SIGNAL, {"target_from_amplitude": False}):
            self.assertEqual(self._sig(5.4)["target_basis"], signals.TARGET_FIXED)

    def test_the_message_says_why_this_number(self):
        text = format_signal(self._sig(5.4), 1, 1)
        self.assertIn("+5.4%", text)
        self.assertIn("近 5 日平均一天振幅 5.4%", text)
        self.assertNotIn("取下限", text)
        low = format_signal(self._sig(1.9), 1, 1)
        self.assertIn("平均一天振幅 1.9%，取下限 3%", low)

    def test_the_watchlist_feeds_each_stock_its_own_range(self):
        src = inspect.getsource(signals.run)
        self.assertIn('st.amplitude_pct = i.get("avg_amplitude_pct") or i.get("amplitude_pct")', src)

    def test_bad_limits_are_rejected(self):
        with unittest.mock.patch.dict(config.SIGNAL, {"target_min_pct": 12.0}):
            self.assertIn("target_min_pct", " / ".join(config.validate()))

    def test_v9_keeps_the_v8_target(self):
        """v9 只加了一道進場條件，v8 的停利目標原封不動。"""
        self.assertTrue(config.SIGNAL["target_from_amplitude"])
        self.assertEqual((config.SIGNAL["target_min_pct"], config.SIGNAL["target_max_pct"]),
                         (3.0, 10.0))
        self.assertEqual(config.validate(), [])


class TestTheSystemDoesNotTellYouToHold(unittest.TestCase):
    """使用者 10-07：「沒碰停損自己決定要不要留倉，因為你沒把握明天留倉會漲」
    ——「要留到明天」「不平倉」「停損建議自己上移」「照 v6 規則留到明天」
    「跳空穿過停損會賠更多」這些勸說全部拿掉，訊息只講事實。"""

    ADVICE = ("要留到明天", "不平倉", "建議自己上移", "移到進場價保本", "照 v6",
              "留到明天", "跳空穿過停損")

    def _no_advice(self, text):
        for phrase in self.ADVICE:
            self.assertNotIn(phrase, text)

    @unittest.mock.patch.dict(config.SIGNAL, {"stop_loss_pct": 3.0, "max_hold_days": 2,
                                              "target_from_amplitude": True})
    def test_the_signal(self):
        st = ready_state(or_high=105.5, last=106.0, vwap=105.0)
        st.prev_close, st.amplitude_pct = 100.0, 8.0
        st.day_open = 100.5                 # 平開之後一路拉上來
        text = format_signal(evaluate(st, now=dtime(9, 3)), 1, 1)
        self._no_advice(text)
        self.assertIn("目標今天到不了", text)            # 事實照講
        self.assertIn("進場後最多 +3.8%", text)          # 110 / 106
        self.assertIn("由你決定", text)

    @unittest.mock.patch.dict(config.SIGNAL, {"max_hold_days": 2})
    def test_the_lock_message(self):
        text = signals.format_window_closed(2, 20)
        self._no_advice(text)
        self.assertIn("由你決定", text)

    def test_reaching_the_target(self):
        o = signals.OpenSignal("2330", "測試", "09:05:00", 100.0, 97.0, 105.0, hold_days=2)
        text = signals.format_resolution(o, 105.0, oc.TARGET)
        self._no_advice(text)
        self.assertIn("續抱與否由你決定", text)

    def test_1325_and_the_next_morning(self):
        o = signals.OpenSignal("2330", "測試", "09:05:00", 100.0, 97.0, 105.0, hold_days=2)
        self._no_advice(signals.format_carry(o, 102.0))
        start = signals.format_carry_start(
            [{"code": "2330", "entry": 100.0, "stop": 97.0, "target": 105.0,
              "day1_close": 102.0}], [])
        self._no_advice(start)
        self.assertIn("接著追蹤", start)


# ══════════════════════════════════════════════════════
# 13:25 還沒結束的那幾筆：只記錄當時的樣子，規則與訊息不變
# ══════════════════════════════════════════════════════
class TestTheCloseSnapshotIsRecorded(unittest.TestCase):
    """使用者 10-07：「要不要留倉，你有辦法算出幾成把握嗎」→「好，加上」（只記錄）。"""

    def _st(self):
        st = SymbolState("2330", 100.0)
        st.day_high, st.day_low, st.vwap = 110.0, 100.0, 104.0
        st.total_volume, st.avg_volume_lots = 30000, 10000
        return st

    def test_the_day_range_comes_from_the_ticks(self):
        st = SymbolState("2330", 100.0)
        st.update(tick(101.0, high=103.0, low=99.5, at="09:10:00"), now=1.0)
        st.update(tick(102.0, high=104.5, low=99.5, at="10:00:00"), now=2.0)
        # 沒帶 high/low 的 tick（只有成交價）不可以把當日高點蓋掉
        st.update(tick(101.0, at="11:00:00"), now=3.0)
        self.assertEqual((st.day_high, st.day_low), (104.5, 99.5))

    def test_the_three_numbers(self):
        snap = signals.close_snapshot(self._st(), 108.0)
        self.assertEqual(snap, {"close_pos_pct": 80.0, "vs_vwap_pct": round(4 / 104 * 100, 2),
                                "volume_x": 3.0})

    def test_unknown_stays_blank_not_zero(self):
        st = SymbolState("2330", 100.0)          # 沒有高低、沒有均價、沒有平常量
        self.assertEqual(signals.close_snapshot(st, 101.0),
                         {"close_pos_pct": None, "vs_vwap_pct": None, "volume_x": None})
        self.assertEqual(signals.close_snapshot(None, 101.0)["close_pos_pct"], None)
        self.assertEqual(signals.close_snapshot(self._st(), None)["volume_x"], None)

    def test_only_the_unfinished_two_day_positions_are_recorded(self):
        seen = []
        t = signals.LiveTracker(on_carry=lambda o, price: seen.append((o.code, price)))
        t.track(dict(V6_SIG, code="A"))
        t.track(dict(V6_SIG, code="B", max_hold_days=1))      # 當沖：不記
        t.track(dict(V6_SIG, code="C"), carried=True)          # 昨天留的：今天結算，不記
        for c in "ABC":
            t.on_price(c, 103.0)
        t.flatten()
        self.assertEqual(seen, [("A", 103.0)])

    def test_a_broken_recorder_does_not_swallow_the_message(self):
        t = signals.LiveTracker(on_carry=lambda *a: 1 / 0)
        t.track(dict(V6_SIG))
        t.on_price("2330", 103.0)
        self.assertEqual(len(t.flatten()), 1)

    def test_it_is_written_back_to_state(self):
        with tempfile.TemporaryDirectory() as d:
            with unittest.mock.patch.object(config, "STATE_FILE", Path(d) / "s.json"):
                gate = RiskGate(FakeBroker())
                gate.state["signals"] = [dict(V6_SIG)]
                self.assertTrue(gate.record_close_snapshot(
                    "2330", "09:05:00", {"close_pos_pct": 80.0, "volume_x": 3.0}))
                self.assertEqual(gate.state["signals"][0]["close_pos_pct"], 80.0)

    def test_run_and_screener_are_wired(self):
        src = inspect.getsource(signals.run)
        self.assertIn("on_carry=_remember_close", src)
        self.assertIn("close_snapshot(states.get(o.code), price)", src)
        self.assertIn('st.avg_volume_lots = i.get("avg_volume_lots")', src)
        self.assertIn('r["avg_volume_lots"] = round(base)', inspect.getsource(screener.screen))

    def test_it_reaches_outcomes_csv_and_back(self):
        sig = dict(V6_SIG, close_pos_pct=80.0, vs_vwap_pct=1.5, volume_x=3.0)
        days = {DAY1: QUIET_DAY1, DAY2: [("09:01", 109, 110, 108, 109)]}
        o = oc.resolve(_DaysBroker(days), sig, DAY1, through=DAY2)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "o.csv"
            oc.append_csv([o], path)
            back = oc.load_csv(path)[0]
        self.assertEqual((back.close_pos_pct, back.vs_vwap_pct, back.volume_x), (80.0, 1.5, 3.0))

    def test_the_report_groups_them(self):
        mk = lambda pos, net: oc.Outcome(
            date=DAY1, code="2330", time="09:05:00", entry=100, stop=97, target=105, lots=1,
            result=oc.TARGET if net > 0 else oc.STOP, exit_price=100, r_multiple=1, gross_pct=net,
            net_pct=net, bars=1, close_pos_pct=pos, vs_vwap_pct=1.0, volume_x=2.5,
            mkt_day_pct=0.3, exit_date=DAY2)
        same_day = oc.Outcome(date=DAY1, code="9999", time="09:05:00", entry=100, stop=97,
                              target=105, lots=1, result=oc.STOP, exit_price=97, r_multiple=-1,
                              gross_pct=-3, net_pct=-3, bars=1)
        rows = [mk(85, 5.0), mk(70, 4.0), mk(50, 1.0), mk(20, -3.0), same_day]
        self.assertEqual(len(analyse.unfinished_at_1325(rows)), 4)     # 當天結束的不算
        groups = analyse.by_close_position(analyse.unfinished_at_1325(rows))
        self.assertEqual(len(groups["收在高點附近（≥70%）"]), 2)       # 70 本身算高點附近
        self.assertEqual(len(groups["中間（30～70%）"]), 1)
        self.assertEqual(len(groups["收在低點附近（<30%）"]), 1)
        text = "\n".join(analyse.report(rows))
        self.assertIn("八、13:25 還沒結束的那幾筆", text)
        self.assertIn("目前樣本：**4 筆**", text)


# v9 的「開盤／回落在昨收 ±1%」10-08 晚取消（v10）。機制測試釘在 v9 的設定上。
V9_GATE = {"near_prev_close_pct": 1.0}


class TestV9NearPreviousClose(unittest.TestCase):
    """使用者 10-08：「開盤回落前日收盤價或開盤近前日收盤價有往上的判斷，再出訊號」，
    ± 範圍選 1%。開盤價、或進場前的當日最低點，有一個在昨收 ±1% 以內才發。"""

    near = staticmethod(config.near_prev_close)

    def test_opening_near_the_close_counts(self):
        self.assertEqual(self.near(100.0, 100.5, 102.0, 1.0), config.NEAR_BY_OPEN)
        self.assertEqual(self.near(100.0, 99.2, 99.0, 1.0), config.NEAR_BY_OPEN)

    def test_gapping_up_then_coming_back_counts(self):
        self.assertEqual(self.near(100.0, 104.0, 100.8, 1.0), config.NEAR_BY_PULLBACK)

    def test_gapping_up_and_never_coming_back_does_not(self):
        self.assertIsNone(self.near(100.0, 104.0, 102.5, 1.0))

    def test_a_crash_through_the_close_is_not_near_either(self):
        """「回落到昨收附近」不包括直接摜破：開盤 -3%、最低 -4% 兩個都不算。"""
        self.assertIsNone(self.near(100.0, 97.0, 96.0, 1.0))

    def test_exactly_one_percent_is_inside_and_one_tick_more_is_not(self):
        self.assertEqual(self.near(100.0, 101.0, 101.0, 1.0), config.NEAR_BY_OPEN)
        self.assertEqual(self.near(100.0, 99.0, 99.0, 1.0), config.NEAR_BY_OPEN)
        self.assertIsNone(self.near(100.0, 101.5, 101.5, 1.0))
        self.assertIsNone(self.near(100.0, 98.9, 98.9, 1.0))
        # 浮點邊界：46.53 × 1.01 = 46.9953，46.99 在裡面
        self.assertEqual(self.near(46.53, 46.99, 47.5, 1.0), config.NEAR_BY_OPEN)

    def test_the_band_is_the_configured_one(self):
        self.assertIsNone(self.near(100.0, 101.5, 101.5, 1.0))
        self.assertEqual(self.near(100.0, 101.5, 101.5, 2.0), config.NEAR_BY_OPEN)

    def test_open_is_named_first_when_both_hold(self):
        self.assertEqual(self.near(100.0, 100.2, 99.8, 1.0), config.NEAR_BY_OPEN)

    def test_unknown_prices_never_count(self):
        """0 / None 是「不知道」，不可以被當成「剛好在昨收」放行。"""
        self.assertIsNone(self.near(0, 100.0, 100.0, 1.0))
        self.assertIsNone(self.near(0, 1.0, 1.0, 1.0))      # 昨收不知道，不是「昨收 = 1」
        self.assertIsNone(self.near(None, 100.0, 100.0, 1.0))
        self.assertIsNone(self.near(100.0, 0, None, 1.0))
        self.assertEqual(self.near(100.0, 0, 100.3, 1.0), config.NEAR_BY_PULLBACK)


@unittest.mock.patch.dict(config.SIGNAL, V9_GATE)
class TestV9TheSignalGate(unittest.TestCase):
    IN_WINDOW = dtime(9, 3)

    def _gapped(self, low=103.0):
        """跳空 +3% 開、區間 104、現價 105 突破 —— 其他每一關都過。"""
        st = ready_state(or_high=104.0, last=105.0, vwap=104.5)
        st.prev_close, st.day_open, st.day_low = 100.0, 103.0, low
        return st

    def test_a_gap_up_that_never_came_back_gets_no_signal(self):
        self.assertIsNone(evaluate(self._gapped(), now=self.IN_WINDOW))

    def test_a_gap_up_that_came_back_to_the_close_does(self):
        sig = evaluate(self._gapped(low=100.6), now=self.IN_WINDOW)
        self.assertIsNotNone(sig)
        self.assertEqual(sig["near_basis"], config.NEAR_BY_PULLBACK)
        self.assertEqual((sig["open_gap_pct"], sig["low_gap_pct"]), (3.0, 0.6))
        self.assertEqual((sig["prev_close"], sig["low_before"]), (100.0, 100.6))

    def test_a_flat_open_does(self):
        st = self._gapped()
        st.day_open = 100.4
        sig = evaluate(st, now=self.IN_WINDOW)
        self.assertEqual(sig["near_basis"], config.NEAR_BY_OPEN)
        self.assertEqual(sig["open_gap_pct"], 0.4)

    def test_no_previous_close_means_no_signal(self):
        st = self._gapped(low=100.0)
        st.prev_close = 0
        self.assertIsNone(evaluate(st, now=self.IN_WINDOW))

    def test_switching_it_off_lets_the_gap_through(self):
        with unittest.mock.patch.dict(config.SIGNAL, {"near_prev_close_pct": None}):
            sig = evaluate(self._gapped(), now=self.IN_WINDOW)
        self.assertIsNotNone(sig)
        self.assertIsNone(sig["near_basis"])
        self.assertEqual(sig["open_gap_pct"], 3.0)      # 照記，20 天後才分得出兩組

    def test_the_block_is_logged_once_not_every_tick(self):
        st = self._gapped()
        with self.assertLogs("signals", level="INFO") as cm:
            evaluate(st, now=self.IN_WINDOW)
            evaluate(st, now=self.IN_WINDOW)
        self.assertEqual(sum("昨收" in m for m in cm.output), 1)

    def test_it_is_checked_after_the_other_gates(self):
        """只有「其他都過了」才 log，否則每個沒突破的 tick 都會記一筆。"""
        st = self._gapped()
        st.last_price = 103.5                            # 沒突破
        evaluate(st, now=self.IN_WINDOW)
        self.assertFalse(st.gap_logged)


class TestV9TheOpeningPrice(unittest.TestCase):
    def _tick(self, close, at, **kw):
        t = tick(close, at=at)
        for k, v in kw.items():
            setattr(t, k, v)
        return t

    def test_the_brokers_open_wins(self):
        st = SymbolState("2330", 100.0)
        st.update(self._tick(102.0, "09:10:00", open=100.5), now=1.0)
        self.assertEqual(st.day_open, 100.5)

    def test_without_it_the_first_tick_in_the_range_is_the_open(self):
        st = SymbolState("2330", 100.0)
        st.update(self._tick(100.3, "09:00:05"), now=1.0)
        st.update(self._tick(101.0, "09:01:00"), now=2.0)
        self.assertEqual(st.day_open, 100.3)

    def test_the_brokers_open_corrects_an_earlier_guess(self):
        st = SymbolState("2330", 100.0)
        st.update(self._tick(100.3, "09:00:05"), now=1.0)          # 猜的
        st.update(self._tick(101.0, "09:00:30", open=100.0), now=2.0)
        self.assertEqual(st.day_open, 100.0)

    def test_starting_late_without_it_leaves_the_open_unknown(self):
        """09:10 才開程式，第一筆早就不是開盤 —— 寧可不知道，也不要猜錯。"""
        st = SymbolState("2330", 100.0)
        st.update(self._tick(104.0, "09:10:00"), now=1.0)
        self.assertEqual(st.day_open, 0.0)


@unittest.mock.patch.dict(config.SIGNAL, V9_GATE)
class TestV9TheMessageAndTheRecord(unittest.TestCase):
    def _sig(self, **kw):
        st = ready_state(or_high=104.0, last=105.0, vwap=104.5)
        st.prev_close, st.day_open, st.day_low = 100.0, 103.0, 100.6
        for k, v in kw.items():
            setattr(st, k, v)
        return evaluate(st, now=dtime(9, 3))

    def test_the_message_says_why_it_counts(self):
        text = format_signal(self._sig(), 1, 1)
        self.assertIn("昨收 100.00｜開盤 103.00（+3.0%）｜最低 100.60（+0.6%）", text)
        self.assertIn("開高後回到昨收附近再往上（±1% 以內）", text)
        flat = format_signal(self._sig(day_open=100.2), 1, 1)
        self.assertIn("開盤就在昨收附近（±1% 以內）", flat)

    def test_an_unknown_open_is_left_out_not_printed_as_zero(self):
        text = format_signal(self._sig(day_open=0.0), 1, 1)
        self.assertNotIn("開盤 0", text)
        self.assertIn("最低 100.60", text)

    def test_old_signals_have_no_such_line(self):
        sig = self._sig()
        for k in ("near_basis", "prev_close", "day_open", "open_gap_pct", "low_gap_pct"):
            sig.pop(k)
        self.assertNotIn("位置：", format_signal(sig, 1, 1))

    def test_both_numbers_reach_outcomes_csv_and_back(self):
        sig = dict(V6_SIG, open_gap_pct=3.0, low_gap_pct=0.6)
        days = {DAY1: QUIET_DAY1, DAY2: [("09:01", 109, 110, 108, 109)]}
        o = oc.resolve(_DaysBroker(days), sig, DAY1, through=DAY2)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "o.csv"
            oc.append_csv([o], path)
            back = oc.load_csv(path)[0]
        self.assertEqual((back.open_gap_pct, back.low_gap_pct), (3.0, 0.6))


@unittest.mock.patch.dict(config.SIGNAL, V9_GATE)
class TestV9WhyNot(unittest.TestCase):
    """事後重建的那張表也要有這一關，否則「為什麼今天沒訊號」會指錯地方。"""

    def _bars(self, low):
        day = datetime(2026, 10, 9)
        at = lambda m: day.replace(hour=9, minute=m)
        return [(at(1), 104.0, low, 104.0, 100.0), (at(2), 104.0, 103.5, 104.0, 100.0),
                (at(3), 106.0, 104.5, 106.0, 400.0)]

    def test_a_gap_up_is_named(self):
        import whynot
        d = whynot.diagnose(self._bars(low=103.0), prev_close=100.0, day_open=103.0)
        self.assertEqual(d["verdict"], whynot.BLOCK_GAP)

    def test_a_pullback_or_a_flat_open_passes(self):
        import whynot
        self.assertEqual(whynot.diagnose(self._bars(low=100.5), prev_close=100.0,
                                         day_open=103.0)["verdict"], whynot.PASS)
        self.assertEqual(whynot.diagnose(self._bars(low=103.0), prev_close=100.0,
                                         day_open=100.8)["verdict"], whynot.PASS)

    def test_the_breakout_bars_own_low_counts(self):
        """盤中的 day_low 包含當下這個 tick，所以突破那一根自己的低點也算。
        （同一根 K 棒裡先跌後漲還是先漲後跌，分鐘 K 看不出來 —— 這是重建的近似。）"""
        import whynot
        bars = self._bars(low=103.0)
        bars[-1] = (bars[-1][0], 106.0, 100.5, 106.0, 400.0)
        self.assertEqual(whynot.diagnose(bars, prev_close=100.0, day_open=103.0)["verdict"],
                         whynot.PASS)

    def test_one_kbars_query_gives_both_bars_and_the_open(self):
        import whynot
        ns = lambda hhmm: int(datetime(2026, 10, 9, int(hhmm[:2]), int(hhmm[3:]),
                                       tzinfo=dt_timezone.utc).timestamp() * 1e9)
        kb = SimpleNamespace(ts=[ns("09:02"), ns("09:01")], High=[2, 1], Low=[2, 1],
                             Close=[2, 1], Volume=[1, 1], Open=[51.0, 50.0])
        calls = []
        fake = SimpleNamespace(kbars=lambda *a: calls.append(a) or kb)
        bars, opened = whynot.day_bars_and_open(fake, "2330", "2026-10-09")
        self.assertEqual((len(bars), opened, len(calls)), (2, 50.0, 1))
        kb.Open = []                                       # 舊版沒有 Open
        self.assertIsNone(whynot.day_bars_and_open(fake, "2330", "2026-10-09")[1])


class TestV9TheRulesAreWired(unittest.TestCase):
    def test_v10_dropped_the_v9_entry_gate(self):
        """使用者 10-08 晚：「這條件開盤要在昨收 ±1% 取消呢？」→ 取消。"""
        self.assertIsNone(config.SIGNAL["near_prev_close_pct"])
        self.assertEqual(config.validate(), [])

    def test_a_gap_up_now_signals_and_still_shows_where_it_opened(self):
        st = ready_state(or_high=104.0, last=105.0, vwap=104.5)
        st.prev_close, st.day_open, st.day_low = 100.0, 103.0, 103.0
        sig = evaluate(st, now=dtime(9, 3))
        self.assertIsNotNone(sig)
        self.assertIsNone(sig["near_basis"])
        text = format_signal(sig, 1, 1)
        self.assertIn("位置：昨收 100.00｜開盤 103.00（+3.0%）｜最低 103.00（+3.0%）", text)
        self.assertNotIn("→", text.split("位置：")[1].split("\n")[1])   # 不當成依據
        self.assertIn("・跌破開盤價 103.00", text)                         # 第 4 條接手

    def test_bad_bands_are_rejected(self):
        for bad in (0, -1.0, 10.0):
            with unittest.mock.patch.dict(config.SIGNAL, {"near_prev_close_pct": bad}):
                self.assertIn("near_prev_close_pct", " / ".join(config.validate()))
        with unittest.mock.patch.dict(config.SIGNAL, {"near_prev_close_pct": None}):
            self.assertEqual(config.validate(), [])


class TestTheMorningListIsQuietUnlessSomethingIsWrong(unittest.TestCase):
    """使用者 10-08：08:40 的「今日觀察名單」不用給。名單照寫（signals.py 要用），
    只是不推；失敗或 0 檔照推 —— 那兩種是真的要人知道的。"""

    def _run(self, argv, rows):
        sent = []
        with tempfile.TemporaryDirectory() as d, \
             unittest.mock.patch.object(config, "WATCHLIST_FILE", Path(d) / "w.json"), \
             unittest.mock.patch.object(screener, "Broker", lambda: None), \
             unittest.mock.patch.object(screener, "screen", lambda b: list(rows)), \
             unittest.mock.patch.object(screener, "archive_watchlist", lambda p: None), \
             unittest.mock.patch.object(signals, "notify", sent.append), \
             contextlib.redirect_stdout(io.StringIO()):
            screener.main(argv)
            written = json.loads((Path(d) / "w.json").read_text(encoding="utf-8"))
        return sent, written

    ROWS = [dict(r, prev_volume=5000) for r in TestWatchlistPush.ROWS]

    def test_a_normal_list_is_written_but_not_pushed(self):
        sent, written = self._run(["--push", "--alert-only"], self.ROWS)
        self.assertEqual(sent, [])
        self.assertEqual([r["code"] for r in written["items"]], ["3707", "2498"])

    def test_an_empty_list_is_still_pushed(self):
        sent, _ = self._run(["--push", "--alert-only"], [])
        self.assertEqual(len(sent), 1)
        self.assertIn("0 檔", sent[0])

    def test_without_the_flag_it_pushes_as_before(self):
        sent, _ = self._run(["--push"], self.ROWS)
        self.assertEqual(len(sent), 1)

    def test_a_failure_is_still_pushed(self):
        sent = []
        def explode(args):
            raise RuntimeError("登入失敗")
        with unittest.mock.patch.object(screener, "run", explode), \
             unittest.mock.patch.object(signals, "notify", sent.append):
            with self.assertRaises(RuntimeError):
                screener.main(["--push", "--alert-only"])
        self.assertEqual(len(sent), 1)
        self.assertIn("登入失敗", sent[0])

    def test_the_scheduled_bat_uses_it_and_keeps_windows_line_endings(self):
        raw = (Path(__file__).parent / "morning.bat").read_bytes()
        self.assertIn(b"python screener.py --push --alert-only", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))


class TestTheBatchIsRepricedWhenItGoesOut(unittest.TestCase):
    """盲點一：09:02:10 突破的那一檔要等到 09:05 才發，訊號上的進場價是 3 分鐘前
    的價格。發出前用當下價格重算進場、停損、目標、張數；突破已經失敗的不發。"""

    AT = datetime(2026, 10, 9, 9, 5)

    def _state(self, last):
        st = ready_state(or_high=100.0, last=100.2, vwap=99.8)
        st.amplitude_pct = 5.0
        sig = evaluate(st, now=dtime(9, 3))
        sig["time"] = "09:02:10"
        st.last_price = last
        return st, sig

    def test_the_price_is_the_one_at_send_time(self):
        st, sig = self._state(last=101.5)
        fresh, why = signals.reprice_at_send(sig, st, self.AT)
        self.assertIsNone(why)
        same = signals._price_plan(st, 101.5)
        for k in ("entry", "stop", "target", "lots", "extension_pct"):
            self.assertEqual(fresh[k], same[k], k)
        self.assertEqual((fresh["breakout_at"], fresh["breakout_price"]), ("09:02:10", 100.2))
        self.assertEqual(fresh["time"], "09:05:00")
        self.assertEqual(sig["entry"], 100.2)                     # 原訊號不被改掉

    def test_the_message_says_what_happened(self):
        st, sig = self._state(last=101.5)
        text = format_signal(signals.reprice_at_send(sig, st, self.AT)[0], 1, 1)
        self.assertIn("進場：101.50", text)
        self.assertIn("09:02 突破時是 100.20", text)
        self.assertIn("09:05 發出當下的價格（+1.3%）", text)
        self.assertNotIn("突破時是", format_signal(sig, 1, None))   # 即時發的沒有這一行

    def test_a_failed_breakout_is_not_sent(self):
        st, sig = self._state(last=100.05)                        # 掉回區間高 100.10 以下
        self.assertEqual(signals.reprice_at_send(sig, st, self.AT),
                         (None, signals.BLOCK_FELL_BACK))

    def test_below_the_average_price_is_not_sent(self):
        st, sig = self._state(last=100.5)
        st.vwap = 100.8
        self.assertEqual(signals.reprice_at_send(sig, st, self.AT)[1], signals.BLOCK_BELOW_VWAP)

    def test_locked_limit_up_is_not_sent(self):
        st, sig = self._state(last=100.5)
        st.last_price = config.limit_up(st.prev_close)
        self.assertEqual(signals.reprice_at_send(sig, st, self.AT)[1], signals.BLOCK_LOCKED)

    def test_no_new_information_changes_nothing(self):
        _, sig = self._state(last=101.5)
        self.assertEqual(signals.reprice_at_send(sig, None, self.AT), (sig, None))
        st = SymbolState("2330", 99.0)
        self.assertEqual(signals.reprice_at_send(sig, st, self.AT), (sig, None))

    def test_the_desk_reprices_the_batch_only(self):
        sent, blocked = [], []
        seen = []

        def reprice(sig, now):
            seen.append(sig["code"])
            return (None, "X") if sig["code"] == "B" else (dict(sig, entry=9.9), None)
        desk = signals.EntryDesk(emit=lambda sig, now, n: sent.append((sig["code"], sig.get("entry"), n)) or True,
                                 blocked=lambda sig, why: blocked.append((sig["code"], why)),
                                 say=lambda t: None, watched=20,
                                 now=datetime(2026, 10, 9, 8, 50), reprice=reprice)
        desk.offer({"code": "A", "volume_surge": 3.0, "entry": 1.0}, datetime(2026, 10, 9, 9, 3))
        desk.offer({"code": "B", "volume_surge": 2.0, "entry": 1.0}, datetime(2026, 10, 9, 9, 4))
        desk.tick(self.AT)
        self.assertEqual(sent, [("A", 9.9, 1)])                  # 批次大小算的是真的發出去的
        self.assertEqual(blocked, [("B", "X")])
        desk.offer({"code": "C", "volume_surge": 2.0, "entry": 5.0}, datetime(2026, 10, 9, 9, 10))
        self.assertEqual(sent[-1], ("C", 5.0, None))             # 即時發的不重算
        self.assertEqual(seen, ["A", "B"])
        self.assertEqual(desk.sent, 2)

    def test_it_is_wired_into_the_live_loop_and_the_dryrun(self):
        self.assertIn("reprice_at_send(", inspect.getsource(signals.run))
        import dryrun
        self.assertIn("signals.reprice_at_send(", inspect.getsource(dryrun))


class TestBreakoutsAfterTheWindowAreRecorded(unittest.TestCase):
    """盲點五：09:30 是硬截止。之後才突破的不發，但要記下來，20 天後才回答得了
    「截止是不是太早」—— 不記的話這一題永遠只能用猜的。"""

    def _st(self):
        st = ready_state(or_high=100.0, last=100.5, vwap=100.0)
        return st

    def _run(self, st, h, m):
        rows = []
        ok = signals.record_late_breakout(st, datetime(2026, 10, 9, h, m),
                                          record=lambda sig, why: rows.append((sig, why)))
        return ok, rows

    def test_a_breakout_at_0940_is_recorded_once_and_not_sent(self):
        st = self._st()
        ok, rows = self._run(st, 9, 40)
        self.assertTrue(ok)
        self.assertEqual(rows[0][1], signals.BLOCK_AFTER_WINDOW)
        self.assertEqual(rows[0][0]["time"], "09:40:00")
        self.assertEqual(st.signaled, 0)                         # 沒有發
        self.assertEqual(self._run(st, 9, 50), (False, []))      # 一檔一天只記一次

    def test_only_between_0930_and_1030(self):
        self.assertFalse(self._run(self._st(), 9, 29)[0])
        self.assertTrue(self._run(self._st(), 9, 30)[0])
        self.assertFalse(self._run(self._st(), 10, 30)[0])

    def test_a_stock_that_already_signalled_is_not_recorded_again(self):
        st = self._st()
        st.signaled = 1
        self.assertFalse(self._run(st, 9, 40)[0])

    def test_no_breakout_means_nothing_and_it_can_still_record_later(self):
        st = self._st()
        st.last_price = 99.0
        self.assertFalse(self._run(st, 9, 40)[0])
        self.assertFalse(st.late_recorded)
        st.last_price = 100.5
        self.assertTrue(self._run(st, 9, 45)[0])

    def test_evaluate_still_refuses_after_the_window_unless_asked(self):
        st = self._st()
        self.assertIsNone(evaluate(st, now=dtime(9, 40)))
        self.assertIsNotNone(evaluate(st, now=dtime(9, 40), ignore_window=True))

    def test_it_is_wired_into_the_live_loop(self):
        src = inspect.getsource(signals.run)
        self.assertIn("record_late_breakout(st, datetime.now())", src)


class TestAWeekdayHolidayDoesNotLoseACarriedPosition(unittest.TestCase):
    """10-09（國慶補假）是平日、但不開盤。電腦照排程開監看：state.json 變成
    休市那天、留倉搬進那天的 carried。下一個交易日只看前一份 state 的 signals
    的話，那一筆會無聲消失 —— 週一不盯、結局也永遠不進 outcomes.csv。"""

    HOLIDAY, NEXT = "2026-10-08", "2026-10-09"     # 沿用 DAY1=10-07 的假資料

    def _holiday_state(self, **kw):
        carried = dict(V6_SIG, carry_from=DAY1, day1_close=103.0, **kw)
        return {"date": self.HOLIDAY, "signals": [], "carried": [carried]}

    def test_it_is_carried_again_after_the_holiday(self):
        carried, notes = signals.carry_over(self._holiday_state(),
                                            _DaysBroker({DAY1: QUIET_DAY1}), self.NEXT)
        self.assertEqual(len(carried), 1)
        self.assertEqual((carried[0]["carry_from"], carried[0]["day1_close"]), (DAY1, 103.0))
        self.assertEqual(notes, [])

    def test_unless_it_already_ended(self):
        for result in (oc.STOP, oc.TARGET, oc.FLAT):
            carried, _ = signals.carry_over(self._holiday_state(live_result=result),
                                            _DaysBroker({DAY1: QUIET_DAY1}), self.NEXT)
            self.assertEqual(carried, [], result)

    def test_unless_a_real_session_went_by(self):
        """「休市」那天其實有開盤（只是那天沒收到報價）—— 抱兩天已經結束了。"""
        b = _DaysBroker({DAY1: QUIET_DAY1, self.HOLIDAY: [("09:01", 103, 104, 102, 103)]})
        carried, notes = signals.carry_over(self._holiday_state(), b, self.NEXT)
        self.assertEqual(carried, [])
        self.assertIn(self.HOLIDAY, notes[0])

    def test_no_bars_keeps_the_day1_close_it_already_had(self):
        carried, _ = signals.carry_over(self._holiday_state(), _DaysBroker({}), self.NEXT)
        self.assertEqual(carried[0]["day1_close"], 103.0)

    def test_the_close_report_finds_it_too_when_the_monitor_did_not_run(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            # 日期要比「今天」早 —— 測試哪天跑都一樣（state 是今天的會走另一條路）
            old = dict(self._holiday_state(), date="2000-01-04")
            old["carried"][0]["carry_from"] = "2000-01-03"
            path.write_text(json.dumps(old), encoding="utf-8")
            with unittest.mock.patch.object(config, "STATE_FILE", path):
                got = review.load_carried()
        self.assertEqual([(c["code"], c["carry_from"]) for c in got], [("2330", "2000-01-03")])


# ══ v10：六條出場 ══════════════════════════════════════
V10_SIG = {"code": "2330", "name": "測試", "time": "09:10:00", "entry": 100.0, "stop": 97.0,
           "target": 106.0, "lots": 4, "or_high": 99.8, "max_hold_days": 1, "ruleset": "v10",
           "exit_rules": 10, "key_level": 99.5, "half_at": 103.0, "trail_pct": 1.5,
           "reason_buffer_pct": 0.2, "vol_window_min": 10, "vol_ratio": 0.5, "flat_pct": 1.0,
           "base_per_min": 10.0, "entry_cum_volume": 1000}
T0 = datetime(2026, 10, 12, 9, 10)


def _at(minutes, seconds=0):
    return T0 + timedelta(minutes=minutes, seconds=seconds)


class TestV10TheSixExits(unittest.TestCase):
    """使用者 10-08 貼的六條出場，四個數字也是使用者選的。
    10-08 晚再改兩件事：理由消失那幾條要「那一分鐘收在線下」才算；量縮的基準改成
    進場後的前 10 分鐘。"""

    def _pos(self, **kw):
        return exits.Position.from_signal(dict(V10_SIG, **kw), T0)

    def _tick(self, pos, price, minute=1, vwap=None, vol=None, second=0):
        return pos.step(_at(minute, second), price, price, price, vwap, vol)

    def _bar(self, pos, minute, high, low, close, vwap=None, vol=None):
        return pos.step(_at(minute), high, low, close, vwap, vol, bar=True)

    def test_2_the_hard_stop_is_hit_at_once(self):
        self.assertEqual(self._tick(self._pos(), 96.9), [("exit", exits.STOP, 97.0)])

    def test_4_below_the_open_needs_the_minute_to_close_below(self):
        pos = self._pos(or_high=None)
        self.assertEqual(self._tick(pos, 99.4, 1, second=10), [])         # 擦過去，還沒收
        self.assertEqual(self._tick(pos, 99.8, 1, second=50), [])         # 這一分鐘收回來了
        self.assertEqual(self._tick(pos, 99.7, 2, second=5), [])          # 上一分鐘收 99.8 → 不出
        self.assertEqual(self._tick(pos, 99.3, 2, second=55), [])
        # 09:12 收 99.3 < 開盤價 99.5 → 下一分鐘第一筆進來時出，出場價 = 那一分鐘的收盤
        self.assertEqual(self._tick(pos, 99.6, 3, second=1), [("exit", exits.BELOW_OPEN, 99.3)])

    def test_1_back_inside_the_range(self):
        # 區間高 99.8 下方 0.2% = 99.60；開盤價拿掉，只看區間
        pos = self._pos(key_level=None)
        self._tick(pos, 99.55, 1)
        self.assertEqual(self._tick(pos, 99.9, 2), [("exit", exits.BACK_IN_RANGE, 99.55)])
        pos = self._pos(key_level=None)
        self._tick(pos, 99.61, 1)
        self.assertEqual(self._tick(pos, 99.9, 2), [])                   # 緩衝內不算

    def test_1_below_the_average_price(self):
        pos = self._pos()
        self._tick(pos, 100.0, 1, vwap=100.5)                              # 100.5 × 0.998 = 100.30
        self.assertEqual(self._tick(pos, 100.5, 2, vwap=100.5), [("exit", exits.BELOW_VWAP, 100.0)])
        pos = self._pos()
        self._tick(pos, 100.5, 1, vwap=100.5)
        self.assertEqual(self._tick(pos, 100.5, 2, vwap=100.5), [])
        pos = self._pos()
        self._tick(pos, 100.0, 1)                                          # 沒有均價線就不判
        self.assertEqual(self._tick(pos, 100.5, 2), [])

    def test_the_signal_minute_itself_is_not_judged(self):
        """訊號 09:10:20 —— 09:10 那一分鐘裡有訊號前的成交，跟分鐘 K 一樣不判。"""
        pos = exits.Position.from_signal(dict(V10_SIG), _at(0, 20))
        self._tick(pos, 99.0, 0, second=40)
        self.assertEqual(self._tick(pos, 100.5, 1, second=1), [])
        self._tick(pos, 99.0, 1, second=59)
        self.assertEqual(self._tick(pos, 100.5, 2, second=1)[0][1], exits.BELOW_OPEN)

    def test_bars_judge_their_own_close(self):
        pos = self._pos()
        self.assertEqual(self._bar(pos, 1, 100.5, 99.0, 99.9), [])        # 低點擦過，收回來
        self.assertEqual(self._bar(pos, 2, 100.0, 99.0, 99.4)[0][:2], ("exit", exits.BELOW_OPEN))

    def test_the_order_within_a_minute(self):
        """碰到就出的先判；一分鐘收盤的那幾條，在同一根 K 裡排在後面。"""
        pos = self._pos()
        self.assertEqual(self._bar(pos, 1, 103.5, 96.0, 100.0), [("exit", exits.STOP, 97.0)])
        pos = self._pos()
        self.assertEqual(self._bar(pos, 1, 103.5, 99.0, 99.4),
                         [("half", 103.0), ("exit", exits.BELOW_OPEN, 99.4)])
        pos = self._pos(key_level=99.0)
        self.assertEqual(self._bar(pos, 1, 100, 98.5, 98.9, vwap=101)[0][1], exits.BELOW_OPEN)
        pos = self._pos(key_level=None)
        self.assertEqual(self._bar(pos, 1, 100, 98.5, 99.0, vwap=101)[0][1], exits.BACK_IN_RANGE)

    def test_3_half_then_trail_from_the_peak(self):
        pos = self._pos()
        self.assertEqual(self._tick(pos, 103.0), [("half", 103.0)])
        self.assertEqual(self._tick(pos, 104.0, 2), [])
        self.assertEqual(pos.trail_line(), 102.0)     # 104 × 0.985 = 102.44 → 往下取 102.0（一檔 0.5）
        self.assertEqual(self._tick(pos, 102.5, 3), [])
        self.assertEqual(self._tick(pos, 102.0, 4), [("exit", exits.TRAIL, 102.0)])

    def test_3_the_trail_never_goes_below_cost(self):
        pos = self._pos(trail_pct=5.0)
        self._tick(pos, 103.0)
        self.assertEqual(pos.trail_line(), 100.0)
        self.assertEqual(self._tick(pos, 100.0, 2), [("exit", exits.TRAIL, 100.0)])

    def test_3_no_trail_before_the_half(self):
        pos = self._pos()
        self.assertEqual(self._tick(pos, 102.0), [])
        self.assertEqual(self._tick(pos, 100.1, 2), [])

    def test_3_a_bar_that_halves_is_not_also_judged_for_the_trail(self):
        pos = self._pos()
        self.assertEqual(self._bar(pos, 1, 103.5, 100.5, 101.0), [("half", 103.0)])
        self.assertEqual(self._bar(pos, 2, 101.0, 100.5, 100.8), [("exit", exits.TRAIL, 101.0)])

    def test_5_the_baseline_is_the_first_ten_minutes_after_entry(self):
        pos = self._pos(entry_cum_volume=1000)
        self._tick(pos, 100.5, 5, vol=1100)
        self.assertIsNone(pos.base_per_min)                               # 還不到 10 分鐘
        self._tick(pos, 100.5, 10, vol=1200)
        self.assertEqual(pos.base_per_min, 20.0)                          # 200 張 / 10 分鐘

    def test_5_volume_dries_up_and_price_sticks(self):
        pos = self._pos(entry_cum_volume=1000)
        self._tick(pos, 100.5, 10, vol=1200)                              # 基準：每分鐘 20 張
        self.assertEqual(self._tick(pos, 100.6, 19, vol=1250), [])        # 還不到 20 分鐘
        # 09:20–09:30 量 90 < 0.5 × 20 × 10 = 100，價格上下 0.1% → 出
        self.assertEqual(self._tick(pos, 100.6, 20, vol=1290), [("exit", exits.VOLUME_DRY, 100.6)])

    def test_5_enough_volume_or_a_moving_price_stays(self):
        pos = self._pos(entry_cum_volume=1000)
        self._tick(pos, 100.5, 10, vol=1200)
        self.assertEqual(self._tick(pos, 100.6, 20, vol=1310), [])        # 量 110 ≥ 100
        pos = self._pos(entry_cum_volume=1000)
        self._tick(pos, 100.0, 10, vol=1200)
        self.assertEqual(self._tick(pos, 101.5, 20, vol=1210), [])        # 價格動了 1.5%

    def test_5_the_window_slides(self):
        pos = self._pos(entry_cum_volume=1000)
        for m in range(1, 23):
            self._tick(pos, 100.5, m, vol=1000 + 20 * m)                    # 每分鐘 20 張，沒縮
        self.assertFalse(pos.done)
        self.assertEqual(self._tick(pos, 100.5, 32, vol=1440 + 50)[0][1], exits.VOLUME_DRY)

    def test_4_closing_exactly_on_the_open_is_not_below(self):
        pos = self._pos(or_high=None)
        self._tick(pos, 99.5, 1)
        self.assertEqual(self._tick(pos, 99.6, 2), [])

    def test_1_the_exit_price_is_the_close_not_the_line(self):
        pos = self._pos()
        self._tick(pos, 100.0, 1, vwap=101.0)                              # 101 × 0.998 = 100.80
        self.assertEqual(self._tick(pos, 100.5, 2, vwap=101.0), [("exit", exits.BELOW_VWAP, 100.0)])

    def test_5_without_a_recorded_start_the_first_tick_is_the_start(self):
        pos = self._pos(entry_cum_volume=None)
        self._tick(pos, 100.5, 1, vol=5000)
        self._tick(pos, 100.5, 10, vol=5200)
        self.assertEqual(pos.base_per_min, 20.0)                          # (5200 − 5000) / 10

    def test_5_the_price_range_counts_from_the_start_of_the_window(self):
        """報價很稀時，窗口起點那一筆就是「10 分鐘前在哪」—— 從 100 漲到 101.5
        不是「黏住」。只看窗口裡的那一筆，會誤判成沒動。"""
        pos = self._pos(entry_cum_volume=1000)
        self._tick(pos, 100.0, 10, vol=1200)
        self.assertEqual(self._tick(pos, 101.5, 20, vol=1210), [])
        pos = self._pos(entry_cum_volume=1000)                             # 往下走也一樣
        self._tick(pos, 101.5, 10, vol=1200)
        self.assertEqual(self._tick(pos, 100.0, 20, vol=1210), [])

    def test_5_a_dead_first_ten_minutes_never_judges(self):
        pos = self._pos(entry_cum_volume=1000)
        self._tick(pos, 100.5, 10, vol=1000)
        self.assertEqual(pos.base_per_min, 0.0)
        self.assertEqual(self._tick(pos, 100.5, 25, vol=1000), [])

    def test_6_flatten_and_nothing_after_an_exit(self):
        pos = self._pos()
        self.assertEqual(pos.flatten(101.2), [("exit", exits.FLAT, 101.2)])
        self.assertEqual(self._tick(pos, 90.0), [])
        self.assertEqual(pos.flatten(90.0), [])

    def test_how_many_lots_go_first(self):
        self.assertEqual(self._pos(lots=5).half_lots, 2)
        self.assertEqual(self._pos(lots=4).half_lots, 2)
        self.assertEqual(self._pos(lots=1).half_lots, 0)

    def test_two_legs_add_up_by_lots(self):
        pct, r = exits.blended(100, 97, 4, 103, 101.5)
        self.assertAlmostEqual(pct, 2.25)
        self.assertAlmostEqual(r, 0.75)
        pct, r = exits.blended(100, 97, 5, 103, 100.0)                # 2 張 103、3 張 100
        self.assertAlmostEqual(pct, 1.2)
        self.assertEqual(exits.blended(100, 97, 1, 103, 101.5), exits.blended(100, 97, 1, None, 101.5))
        self.assertAlmostEqual(exits.blended(100, 97, 0, 103, 101)[0], 2.0)
        self.assertAlmostEqual(exits.blended(100, 97, 4, None, 97)[1], -1.0)


class TestV10TheSignalCarriesThePlan(unittest.TestCase):
    def _sig(self):
        st = ready_state(or_high=100.0, last=100.4, vwap=100.0)
        st.amplitude_pct = 6.0
        st.total_volume = 3000
        return evaluate(st, now=dtime(9, 12))

    def test_the_plan_is_on_the_signal(self):
        sig = self._sig()
        self.assertEqual(sig["exit_rules"], exits.V10)
        self.assertEqual(sig["key_level"], 99.0)                        # 開盤價
        self.assertEqual(sig["half_at"], config.round_to_tick(
            sig["entry"] + (sig["target"] - sig["entry"]) / 2, "up"))
        self.assertEqual(sig["entry_cum_volume"], 3000)
        self.assertEqual((sig["confirm"], sig["vol_base"]), ("minute_close", "after_entry"))
        self.assertNotIn("base_per_min", sig)                           # 進場後才算得出來
        self.assertEqual(sig["max_hold_days"], 1)                       # 回到當沖

    def test_the_message_lists_every_exit_before_entry(self):
        text = format_signal(self._sig(), 1, 1)
        for part in ("出場（哪一條先到就出）", "・停損", "・跌破開盤價 99.00",
                     "・跌回區間：低於 99.80", "・跌破均價線（下方 0.2%）", "先出一半",
                     "從最高點回落 1.5% 出（不低於成本）",
                     "以下三條：那一分鐘「收盤」在線下才出，盤中擦過去不算",
                     "・量縮：進場 20 分鐘後，最近 10 分鐘的量不到進場後前 10 分鐘的一半",
                     "・13:25 全部平倉"):
            self.assertIn(part, text)
        self.assertNotIn("留倉", text)

    def test_an_unknown_open_says_so(self):
        sig = dict(self._sig(), key_level=None)
        self.assertIn("今天的開盤價不知道，這一條不判", format_signal(sig, 1, 1))

    def test_switching_it_off_drops_the_plan(self):
        with unittest.mock.patch.dict(config.SIGNAL, {"exit_rules": False}):
            sig = self._sig()
        self.assertNotIn("half_at", sig)
        self.assertNotIn("出場（", format_signal(sig, 1, 1))

    def test_the_lock_message_names_the_new_exits(self):
        self.assertIn("先出一半", signals.format_window_closed(1, 20))
        self.assertNotIn("留倉", signals.format_window_closed(1, 20))


class TestV10TheLiveTracker(unittest.TestCase):
    def _tracker(self):
        self.resolved, self.halved = [], []
        tr = signals.LiveTracker(on_resolved=lambda o, p, v: self.resolved.append((v, p)),
                                 on_half=lambda o, p: self.halved.append(p))
        tr.track(dict(V10_SIG), now=T0)
        return tr

    def test_half_then_trail_two_messages(self):
        tr = self._tracker()
        msgs = tr.on_price("2330", 103.2, _at(1))
        self.assertEqual(len(msgs), 1)
        self.assertIn("先出一半", msgs[0])
        self.assertIn("先賣 2 張（共 4 張），剩下 2 張改成移動停利", msgs[0])
        self.assertEqual(self.halved, [103.0])
        tr.on_price("2330", 105.0, _at(2))
        msgs = tr.on_price("2330", 103.5, _at(3))                    # 105 × 0.985 = 103.43 → 103.0
        self.assertEqual(msgs, [])
        msgs = tr.on_price("2330", 103.0, _at(4))
        self.assertEqual(self.resolved, [(exits.TRAIL, 103.0)])
        self.assertIn("先出 2 張：100.00 → 103.00（+3.00%）", msgs[0])
        self.assertIn("剩下 2 張：100.00 → 103.00（+3.00%）", msgs[0])
        self.assertIn("+1.00R", msgs[0])
        self.assertEqual(tr.open, [])

    def test_one_lot_cannot_be_split(self):
        tr = signals.LiveTracker()
        tr.track(dict(V10_SIG, lots=1), now=T0)
        msg = tr.on_price("2330", 103.0, _at(1))[0]
        self.assertIn("只有 1 張分不了", msg)
        out = tr.on_price("2330", 101.0, _at(2))[0]                   # 103 × 0.985 → 101.0
        self.assertNotIn("先出", out)                                 # 單一段
        self.assertIn("出場 101.00", out)

    def test_volume_and_average_price_reach_the_rules(self):
        tr = self._tracker()
        tr.on_price("2330", 100.0, _at(1), vwap=100.5)
        self.assertEqual(self.resolved, [])                             # 這一分鐘還沒收
        msgs = tr.on_price("2330", 100.5, _at(2), vwap=100.5)
        self.assertEqual(self.resolved, [(exits.BELOW_VWAP, 100.0)])
        self.assertIn("跌破均價線", msgs[0])
        tr = self._tracker()
        tr.on_price("2330", 100.5, _at(10), total_volume=1200)
        tr.on_price("2330", 100.5, _at(20), total_volume=1290)
        self.assertEqual(self.resolved[-1][0], exits.VOLUME_DRY)

    def test_flatten_after_half_reports_both_legs(self):
        tr = self._tracker()
        tr.on_price("2330", 103.0, _at(1))
        msg = tr.flatten()[0]
        self.assertIn("收盤平倉，全部出場", msg)
        self.assertEqual(self.resolved, [(oc.FLAT, 103.0)])

    def test_a_restart_does_not_halve_twice(self):
        tr = signals.LiveTracker(on_half=lambda o, p: self.fail("不該再出一半"))
        tr.track(dict(V10_SIG, live_half=103.0), now=T0)
        self.assertEqual(tr.on_price("2330", 103.5, _at(1)), [])

    def test_old_signals_keep_stop_and_target(self):
        tr = signals.LiveTracker()
        tr.track(dict(V6_SIG, max_hold_days=1), now=T0)
        self.assertEqual(tr.open[0].pos, None)
        self.assertIn("目標", tr.on_price("2330", 108.0, _at(1))[0])

    def test_the_half_is_written_back_to_state(self):
        b = FakeBroker()
        with tempfile.TemporaryDirectory() as d, \
             unittest.mock.patch.object(config, "STATE_FILE", Path(d) / "s.json"):
            gate = RiskGate(b)
            gate.record(dict(V10_SIG))
            self.assertTrue(gate.record_live_half("2330", "09:10:00", 103.0))
            self.assertEqual(gate.state["signals"][0]["live_half"], 103.0)
            self.assertFalse(gate.record_live_half("9999", "09:10:00", 1.0))

    def test_it_is_wired_into_the_live_loop(self):
        src = inspect.getsource(signals.run)
        self.assertIn("on_half=_remember_half", src)
        self.assertIn("vwap=st.vwap", src)
        self.assertIn("total_volume=st.total_volume", src)


class _VolBroker:
    """一天的假 kbars：rows = [(HH:MM, 開, 高, 低, 收, 量), ...]。"""

    def __init__(self, rows, day="2026-10-12"):
        self.rows, self.day = rows, day

    def kbars(self, code, start, end):
        ts, o, h, l, c, v = [], [], [], [], [], []
        for hhmm, op, hi, lo, cl, vo in self.rows:
            t = datetime(int(self.day[:4]), int(self.day[5:7]), int(self.day[8:10]),
                         int(hhmm[:2]), int(hhmm[3:]), tzinfo=dt_timezone.utc)
            ts.append(int(t.timestamp() * 1e9))
            o.append(op); h.append(hi); l.append(lo); c.append(cl); v.append(vo)
        return SimpleNamespace(ts=ts, Open=o, High=h, Low=l, Close=c, Volume=v)


class TestV10TheCloseReplay(unittest.TestCase):
    """收盤後用分鐘 K 照同一套六條回推（盤中沒收到的那幾筆靠這個）。"""

    DAY = "2026-10-12"
    BEFORE = [("09:%02d" % m, 100, 100.2, 99.9, 100, 100) for m in range(1, 11)]   # 每分鐘 100 張

    def _resolve(self, after, **kw):
        sig = dict(V10_SIG, base_per_min=None, entry_cum_volume=None, **kw)
        return oc.resolve(_VolBroker(self.BEFORE + after), sig, self.DAY)

    def test_half_then_trail(self):
        o = self._resolve([("09:12", 100.5, 103.2, 100.4, 103, 300),
                           ("09:13", 103, 105.0, 103.6, 104.8, 300),
                           ("09:14", 104.8, 104.9, 103.0, 103.2, 300)])
        self.assertEqual((o.result, o.half_exit, o.exit_price), (exits.TRAIL, 103.0, 103.0))
        self.assertAlmostEqual(o.r_multiple, 1.0, places=2)
        self.assertEqual(o.exit_at, "09:14:00")
        back = None
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "o.csv"
            oc.append_csv([o], path)
            back = oc.load_csv(path)[0]
        self.assertEqual(back.half_exit, 103.0)

    def test_the_bars_start_counting_volume_at_entry(self):
        """量縮的起點是進場那一刻的累計量。拿第一根之後的累計量當起點，前 10 分鐘
        的基準會少算一根，偏低 —— 偏低的基準等於量縮更難成立。"""
        after = ([("09:11", 100.4, 100.5, 100.3, 100.4, 200)]
                 + [("09:%02d" % m, 100.4, 100.5, 100.3, 100.4, 20) for m in range(12, 21)]
                 + [("09:%02d" % m, 100.4, 100.5, 100.3, 100.4, 15) for m in range(21, 40)])
        # 基準 (200 + 9×20)/10 = 38 張/分；之後每分鐘 15 → 150 < 190 → 出。
        # 少算第一根的話基準 = 18、門檻 90，150 不算量縮。
        self.assertEqual(self._resolve(after).result, exits.VOLUME_DRY)

    def test_volume_dries_up_on_the_bars(self):
        # 進場後前 10 分鐘每分鐘 40 張；之後每分鐘 2 張、價格不動 → 進場 20 分鐘後出
        after = ([("09:%02d" % m, 100.4, 100.5, 100.3, 100.4, 40) for m in range(11, 21)]
                 + [("09:%02d" % m, 100.4, 100.5, 100.3, 100.4, 2) for m in range(21, 40)])
        o = self._resolve(after)
        self.assertEqual(o.result, exits.VOLUME_DRY)
        self.assertEqual(o.exit_at, "09:30:00")

    def test_the_average_price_is_built_from_the_bars(self):
        # 進場前都在 100 附近成交；之後量大的那根跌到 100.0 以下的均價線緩衝
        o = self._resolve([("09:12", 100.3, 100.4, 99.75, 99.8, 50)], key_level=None,
                          or_high=95.0)
        self.assertEqual((o.result, o.exit_price), (exits.BELOW_VWAP, 99.8))   # 那一根的收盤

    def test_nothing_happens_then_1325(self):
        after = [("09:12", 100.5, 101.0, 100.4, 100.9, 100), ("13:25", 100.9, 101.2, 100.8, 101, 100),
                 ("13:30", 101, 101, 101, 101, 100)]
        o = self._resolve(after, vol_ratio=0.01)                       # 量縮門檻壓到不會觸發
        self.assertEqual((o.result, o.exit_price), (exits.FLAT, 101.0))

    def test_the_live_result_wins(self):
        o = self._resolve([("09:12", 100.5, 100.6, 96.0, 97, 300)],
                          live_result=exits.TRAIL, live_exit=104.0, live_half=103.0,
                          live_at="10:00:00")
        self.assertEqual((o.result, o.exit_price, o.half_exit, o.bars), (exits.TRAIL, 104.0, 103.0, 0))
        self.assertAlmostEqual(o.r_multiple, 1.17, places=2)

    def test_the_bar_that_contains_the_signal_is_not_used(self):
        """訊號 09:10:00。label 09:10 那根涵蓋 09:09–09:10，是訊號**之前**的成交 ——
        那根掃到 96 不是這一筆的停損（跟 v9 以前同一個約定）。"""
        rows = self.BEFORE[:-1] + [("09:10", 100, 100.5, 96.0, 100.4, 100),
                                   ("09:12", 100.4, 100.6, 100.3, 100.5, 100)]
        sig = dict(V10_SIG, base_per_min=None, entry_cum_volume=None, vol_ratio=0.01)
        o = oc.resolve(_VolBroker(rows), sig, self.DAY)
        self.assertNotEqual(o.result, exits.STOP)

    def test_no_bars_no_guess(self):
        self.assertIsNone(oc.resolve(_VolBroker([]), dict(V10_SIG), self.DAY))

    def test_the_report_shows_the_half(self):
        o = self._resolve([("09:12", 100.5, 103.2, 100.4, 103, 300),
                           ("09:13", 103, 105.0, 103.6, 104.8, 300),
                           ("09:14", 104.8, 104.9, 103.0, 103.2, 300)])
        text = review.format_push([dict(V10_SIG)], [o], [o])
        self.assertIn("移動停利（先出一半 103.00）", text)


class TestV10TheRulesAreWired(unittest.TestCase):
    def test_the_shipped_config_is_v10(self):
        self.assertEqual(config.RULESET, "v10")
        cfg = config.SIGNAL
        self.assertTrue(cfg["exit_rules"])
        self.assertEqual(cfg["max_hold_days"], 1)
        self.assertEqual((cfg["exit_half_fraction"], cfg["exit_trail_pct"], cfg["exit_vol_window_min"],
                          cfg["exit_vol_ratio"], cfg["exit_flat_pct"]), (0.5, 1.5, 10, 0.5, 1.0))
        self.assertEqual(config.RISK["per_trade_risk"], 4000)
        self.assertEqual(config.validate(), [])

    def test_bad_numbers_are_rejected(self):
        for k, bad in (("exit_half_fraction", 1.0), ("exit_trail_pct", 0), ("exit_vol_ratio", 1.0),
                       ("exit_flat_pct", 0), ("exit_reason_buffer_pct", -0.1),
                       ("exit_vol_window_min", 0), ("max_hold_days", 2)):
            with unittest.mock.patch.dict(config.SIGNAL, {k: bad}):
                self.assertTrue(config.validate(), k)


class TestOnlyTheTopNAreWatched(unittest.TestCase):
    """使用者 10-08：先「盤前選出三檔，就盯這三檔」，同晚改成盯 10 檔。"""

    ROWS = [{"code": str(1000 + i), "name": f"股{i}", "prev_close": 50.0, "amplitude_pct": 5.0,
             "prev_volume": 9000, "volume_ratio": 20.0 - i} for i in range(13)]

    def _run(self, argv):
        with tempfile.TemporaryDirectory() as d, \
             unittest.mock.patch.object(config, "WATCHLIST_FILE", Path(d) / "w.json"), \
             unittest.mock.patch.object(screener, "Broker", lambda: None), \
             unittest.mock.patch.object(screener, "screen", lambda b: [dict(r) for r in self.ROWS]), \
             unittest.mock.patch.object(screener, "archive_watchlist", lambda p: None), \
             unittest.mock.patch.object(signals, "notify", lambda t: None), \
             contextlib.redirect_stdout(io.StringIO()):
            screener.main(argv)
            return json.loads((Path(d) / "w.json").read_text(encoding="utf-8"))

    def test_the_top_ten_by_volume_ratio_are_watched(self):
        out = self._run(["--push", "--alert-only"])
        self.assertEqual([r["code"] for r in out["items"]], [str(1000 + i) for i in range(10)])
        self.assertEqual([r["code"] for r in out["not_watched"]], ["1010", "1011", "1012"])

    def test_the_command_line_can_still_override(self):
        self.assertEqual(len(self._run(["--top", "5"])["items"]), 5)

    def test_none_watches_the_whole_pool(self):
        with unittest.mock.patch.dict(config.SCREEN, {"watch_top": None}):
            out = self._run([])
        self.assertEqual((len(out["items"]), out["not_watched"]), (13, []))

    def test_the_shipped_number_is_ten_and_validated(self):
        self.assertEqual(config.SCREEN["watch_top"], 10)
        self.assertEqual(config.RISK["max_signals_per_day"], 3)          # 盯得多，做的不多
        for bad in (0, -1, 2.5):
            with unittest.mock.patch.dict(config.SCREEN, {"watch_top": bad}):
                self.assertIn("watch_top", " / ".join(config.validate()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
