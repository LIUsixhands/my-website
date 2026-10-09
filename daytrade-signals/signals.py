"""
signals.py — 盤中訊號引擎。09:00 啟動，13:30 自動收工。

規則是寫死的，盤中不接受任何參數修改。它只做三件事：
  1. 算開盤區間（09:00–09:15 的高低點）
  2. 突破 + 量增 + 站上均價線 → 推播一個「決策錨點」給你
  3. 風控閘門關閉時，不管盤面多漂亮，一律不發

它不會幫你下單。下單是你的手，責任也是你的。
"""
import csv
import json
import logging
import pathlib
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta

import config
import exits
import market_calendar
import outcome
from broker import Broker

# requests 只有推播用得到。缺席時仍要能跑（訊號照樣印在 stdout），
# 但如果你已經設好 Telegram 金鑰卻沒有 requests，那是「訊號發不出去」——
# 必須吵，不能安靜地吞掉。
try:
    import requests
except ImportError:                  # pragma: no cover - 取決於環境
    requests = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("signals")

# 帳務查詢回「未知」時再確認幾次，才肯關閘停手（只有真錢模式會用到）
UNKNOWN_RETRIES = 2
UNKNOWN_RETRY_WAIT = 1.5      # 秒；在鎖內等待，所以不能太久

# 取樣視窗搬到 config.SIGNAL —— 它們不是實作細節，是會讓整條規則失效的參數。
# 寫死在這裡的時候，把進場窗口從三小時改成三分鐘就會無聲地關掉量能過濾。
VOL_MARK_KEEP_SEC = 900      # tick 量能足跡保留長度


def _t(s: str) -> dtime:
    return datetime.strptime(s, "%H:%M:%S").time()


# ══════════════════════════════════════════════════════
# 風控閘門
# ══════════════════════════════════════════════════════
class RiskGate:
    """任何一條紅線踩到，當日直接關閘。關了就不再開，除非隔天。"""

    def __init__(self, broker: Broker):
        self.broker = broker
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.state = self._load()

    def _load(self) -> dict:
        if config.STATE_FILE.exists():
            s = json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
            if s.get("date") == self.today:
                s.setdefault("signals", [])
                s.setdefault("signals_sent", 0)
                s.setdefault("closed", False)
                s.setdefault("closed_reason", "")
                return s
        return {"date": self.today, "signals_sent": 0, "closed": False,
                "closed_reason": "", "signals": []}

    def save(self):
        config.STATE_FILE.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _close(self, reason: str):
        if not self.state["closed"]:
            self.state["closed"] = True
            self.state["closed_reason"] = reason
            self.save()
            log.warning("🚨 風控閘門關閉：%s", reason)
            notify(f"🚨 今日停手\n原因：{reason}\n\n收工。明天再來，市場不會跑掉。")

    @staticmethod
    def _trailing_losses(rows: list[float]) -> int:
        """從最後一筆往前數，連續幾筆是虧的。

        依 list_profit_loss 的回傳順序判斷（同一天內視為時間序）。
        實作放在 outcome.py，因為盤後覆盤的 replay_rules() 要算同一件事 ——
        兩邊各寫一份的話，有一天會走偏，而覆盤算出的「照規則會做幾筆」
        就不再是閘門真正會做的事。
        """
        return outcome.trailing_losses(rows)

    def _requery(self, fn, label):
        """帳務查詢回 None 時再確認幾次，才決定要不要關閘。

        實機遇過：連線 keep-alive 斷掉重連之後，第一次 list_trades 直接 timeout。
        那一瞬間的 None，跟「金鑰沒有帳務權限」在程式眼裡長得一模一樣，
        但意義完全相反 —— 把前者當後者，一個網路抖動就報銷一整天
        （閘門關了當天不會再開，重啟程式也會被擋下來）。
        權限問題每次都失敗，暫時性失敗重試就過，試幾次就分得出來。

        只在真錢模式重試：模擬模式的 None 本來就放行，多等那幾秒沒有意義，
        而且這是在鎖內執行的，會卡住其他檔的行情處理。
        """
        result = fn()
        if result is not None or config.SIMULATION:
            return result
        for i in range(UNKNOWN_RETRIES):
            time.sleep(UNKNOWN_RETRY_WAIT)
            log.warning("%s查不到，重試 %d/%d（暫時性失敗會過，權限問題不會）",
                        label, i + 1, UNKNOWN_RETRIES)
            result = fn()
            if result is not None:
                log.warning("%s重試後查到了，判定為連線暫時失常，不關閘。", label)
                return result
        return result

    def check(self) -> bool:
        """回傳 True 表示可以發訊號。"""
        if self.state["closed"]:
            return False

        r = config.RISK
        if self.state["signals_sent"] >= r["max_signals_per_day"]:
            self._close(f"已達當日訊號上限 {r['max_signals_per_day']} 個")
            return False

        trades = self._requery(self.broker.trades_today, "成交紀錄")
        if trades is None:
            # 查不到成交 = 交易筆數上限這條線失效。與損益同一套處理：
            # 真錢模式停手，模擬模式放行並警告。
            if r["halt_when_pnl_unknown"] and not config.SIMULATION:
                self._close("查不到當日成交紀錄，交易筆數上限失效 —— "
                            "沒有煞車就不上路。請確認金鑰的帳務查詢權限。")
                return False
            log.warning("成交紀錄未知（simulation=%s），本次以 0 筆計算", config.SIMULATION)
            trades = []
        if len(trades) >= r["max_trades_per_day"] * 2:  # 一筆當沖 = 兩次成交
            self._close(f"已達當日交易筆數上限 {r['max_trades_per_day']} 筆")
            return False

        rows = self._requery(self.broker.realized_pnl_rows_today, "已實現損益")
        if rows is None:
            # 查不到損益 = 沒有煞車。真錢模式下寧可停手；
            # 模擬模式本來就沒有損益可查，硬要停手會讓第一個月完全跑不出訊號品質數據。
            if r["halt_when_pnl_unknown"] and not config.SIMULATION:
                self._close("查不到當日已實現損益，日虧上限與連敗停手兩條線都失效 —— "
                            "沒有煞車就不上路。請檢查電子憑證與帳號權限。")
                return False
            log.warning("損益未知（simulation=%s），本次以 0 元計算", config.SIMULATION)
            rows = []

        pnl = sum(rows)
        if pnl <= -abs(r["max_daily_loss"]):
            self._close(f"當日實現虧損 {pnl:,.0f} 元，觸及上限 {r['max_daily_loss']:,} 元")
            return False

        streak = self._trailing_losses(rows)
        if streak >= r["max_consecutive_losses"]:
            self._close(f"連續 {streak} 筆虧損，觸及上限 {r['max_consecutive_losses']} 筆")
            return False

        return True

    def record(self, sig: dict) -> int:
        """記錄訊號，回傳它是今日第幾個（1 起算）。"""
        self.state["signals_sent"] += 1
        self.state["signals"].append(sig)
        self.save()
        return self.state["signals_sent"]

    def record_live_result(self, code: str, time_str: str, result: str,
                           exit_price: float) -> bool:
        """把盤中 tick 看到的結局寫回 state.json 的那一筆訊號。

        沒有這一步，即時判定只存在於那則 Telegram 訊息裡，收盤後就沒人知道了 ——
        而 outcome.py 的分鐘 K 看不到訊號後的頭 60 秒。2026-09-29 允強 09:32:13
        發訊號、09:32:25 就到目標（12 秒），收盤回推完全看不到那一段，只看到後來
        跌回去碰停損，於是同一筆交易被判成 -1.00R，而當下推給使用者的是 +1.57R。

        tick 是實際成交，分鐘 K 是事後的摘要 —— 兩邊衝突時以 tick 為準。
        """
        for sig in self._all_signals():
            if str(sig.get("code")) == str(code) and str(sig.get("time")) == str(time_str):
                sig["live_result"] = result
                sig["live_exit"] = round(float(exit_price), 2)
                sig["live_at"] = datetime.now().strftime("%H:%M:%S")
                # 哪一天判定的。昨天留倉的那一筆今天才結束，outcome.py 要靠這一欄
                # 知道它是隔天出場（成本用留倉稅率、exit_at 是今天的時間）。
                sig["live_date"] = datetime.now().strftime("%Y-%m-%d")
                self.save()
                return True
        log.warning("即時判定找不到對應訊號（%s %s），沒寫回 state.json", code, time_str)
        return False

    def record_live_half(self, code: str, time_str: str, price: float) -> bool:
        """v10「先出一半」那一刻寫回 state.json。收盤回推要靠它算兩段合起來的報酬。"""
        for sig in self._all_signals():
            if str(sig.get("code")) == str(code) and str(sig.get("time")) == str(time_str):
                sig["live_half"] = round(float(price), 2)
                sig["live_half_at"] = datetime.now().strftime("%H:%M:%S")
                self.save()
                return True
        log.warning("先出一半找不到對應訊號（%s %s），沒寫回 state.json", code, time_str)
        return False

    def _all_signals(self) -> list[dict]:
        """今天發的 + 昨天留倉過來的。兩邊都可能被盤中 tick 判定。

        同一檔可能昨天留倉、今天又在名單裡 —— 但今天不會再對它發訊號
        （見 block_carried_codes），所以 (代號, 訊號時間) 仍然唯一。
        """
        return list(self.state.get("signals", [])) + list(self.state.get("carried", []))

    def record_close_snapshot(self, code: str, time_str: str, snap: dict) -> bool:
        """把 13:25 還沒結束的那一筆當時的三個數字寫回 state.json（見 close_snapshot）。"""
        for sig in self._all_signals():
            if str(sig.get("code")) == str(code) and str(sig.get("time")) == str(time_str):
                sig.update(snap)
                self.save()
                return True
        log.warning("13:25 紀錄找不到對應訊號（%s %s），沒寫回 state.json", code, time_str)
        return False

    def record_time_exit(self, code: str, time_str: str, price: float,
                         at: str) -> bool:
        """把 09:30「時間到」那一刻的價位寫回 state.json。

        這一筆**不會因此結束追蹤** —— 使用者定的規則是「未達停損的由下單者
        自己決定」，所以系統只記價、不替人平倉，而且繼續追到 13:25。
        收盤後 outcome.py 會同時產出 exit_0930（照新規則）與 exit_day（續抱）。
        只留一欄的話，「09:30 就走是不是比較好」這一題就永遠沒有對照組。
        """
        for sig in self.state.get("signals", []):
            if str(sig.get("code")) == str(code) and str(sig.get("time")) == str(time_str):
                sig["exit_0930_price"] = round(float(price), 2)
                sig["exit_0930_at"] = at
                self.save()
                return True
        log.warning("時間出場找不到對應訊號（%s %s），沒寫回 state.json", code, time_str)
        return False

    def record_fill(self, code: str, time_str: str, low: float | None) -> bool:
        """把訊號後 5 分鐘內的最低成交價寫回 state.json 的那一筆訊號。

        回答的是使用者問了一整輪的那一題：「買不到就是空談」。
        low 比進場價低（或相等）＝ 限價單掛在進場價會成交；
        low 比進場價高＝ 那段時間根本沒有人在進場價以下賣，這筆買不到，
        除非追價 —— 而追價就不是這套系統算出來的風報比了。

        low 是 None 代表那 5 分鐘內一筆成交都沒收到，不是「買不到」。
        空白要留空白。
        """
        for sig in self.state.get("signals", []):
            if str(sig.get("code")) == str(code) and str(sig.get("time")) == str(time_str):
                sig["fill_low"] = None if low is None else round(float(low), 2)
                self.save()
                return True
        log.warning("成交窗口找不到對應訊號（%s %s），沒寫回 state.json", code, time_str)
        return False


# ══════════════════════════════════════════════════════
# 個股盤中狀態
# ══════════════════════════════════════════════════════
@dataclass
class SymbolState:
    code: str
    prev_close: float
    name: str = ""
    or_high: float = 0.0
    or_low: float = 0.0
    or_locked: bool = False
    last_price: float = 0.0
    vwap: float = 0.0
    total_volume: int = 0
    vol_marks: list = field(default_factory=list)   # (ts, total_volume) 用來算量能速率
    signaled: int = 0
    vwap_warned: bool = False
    rank: int = 0                             # 盤前選股名次（1 = 量比最高），0 = 未知
    category: str = ""                        # 產業類別代碼（輪動題材的客觀代理）
    candidates: int = 0                       # 今日已記錄幾個「被擋掉的候選」
    last_candidate_at: datetime | None = None # 候選之間的冷卻，避免每個 tick 記一筆
    # 內外盤：成交是打在賣價（買方主動 = 外盤）還是打在買價（賣方主動 = 內盤）。
    # 量能倍數只數「量有多大」，分不出方向 —— 量放大但內盤居多，是有人在出貨給你。
    # tick_type：1 = 外盤、2 = 內盤、0 或缺 = 判不出來（不可以當成任何一邊）。
    # 這一檔近 5 日平均日振幅 %（screener.py 算好放在 watchlist.json）。v8 的停利
    # 目標用它。None = 不知道（舊名單、測試），那時退回固定 % 目標。
    amplitude_pct: float | None = None
    # 13:25 還沒結束的那幾筆要記「當時的樣子」（使用者 10-07 同意只記錄、不改規則）：
    # 當日高低（tick 的 high/low 是當日累計）與平常一天的量（screener 算好的）。
    day_high: float = 0.0
    day_low: float = 0.0
    # v9：當日開盤價。0 = 不知道（tick 沒帶 open，而且程式是開盤區間之後才開的）。
    day_open: float = 0.0
    gap_logged: bool = False                  # 「離昨收太遠」一天只記一次 log
    late_recorded: bool = False               # 09:30 之後的突破已經記過一筆了
    weak_recorded: bool = False               # 「量不夠」的突破已經記過一筆了
    avg_volume_lots: float | None = None
    aggressive_buy: int = 0                   # 外盤成交張數
    aggressive_sell: int = 0                  # 內盤成交張數
    unclassified: int = 0                     # 判不出方向的張數 —— 要知道有多少沒算到
    # 開盤前的試撮（模擬撮合）價格往哪裡走。使用者 10-08 貼了一篇「試撮價持續
    # 上移代表買方力道在開盤前就傾斜」，選「只記錄、不當條件」—— 20 天後拿數字
    # 看試撮往上的那幾筆是不是真的比較好。程式 08:50 才開，看到的是最後那十分鐘
    # （文章說的「最後幾秒抽單」也在裡面）。
    sim_first: float = 0.0                    # 收到的第一筆試撮價
    sim_last: float = 0.0                     # 最後一筆（09:00 前）
    sim_ups: int = 0                          # 試撮價往上跳了幾次
    sim_downs: int = 0                        # 往下跳了幾次
    sim_from: str = ""                        # 第一筆試撮的時間（從幾點開始看得到）

    def record_simtrade(self, tick) -> bool:
        """記一筆試撮報價。只收 09:00 以前的 —— 13:25 之後的收盤集合競價也是
        試撮，那跟開盤前的方向無關。**不碰任何進場用的欄位**（區間、均價、量）。"""
        ts = tick.datetime.time() if hasattr(tick.datetime, "time") else datetime.now().time()
        if ts >= _t(config.SIGNAL["or_start"]):
            return False
        price = float(getattr(tick, "close", 0) or 0)
        if price <= 0:
            return False
        if not self.sim_first:
            self.sim_first, self.sim_from = price, ts.strftime("%H:%M:%S")
        elif price > self.sim_last:
            self.sim_ups += 1
        elif price < self.sim_last:
            self.sim_downs += 1
        self.sim_last = price
        return True

    def sim_move_pct(self) -> float | None:
        """試撮從第一筆到最後一筆走了幾 %。沒收到試撮 = None（不知道，不是 0）。"""
        if not self.sim_first:
            return None
        return round((self.sim_last - self.sim_first) / self.sim_first * 100, 2)

    def bid_ask_ratio(self) -> float | None:
        """外盤 ÷ 內盤。判不出方向的那些**不計入任何一邊**。

        回傳 None 而不是 0 或 1：這一檔的 tick 根本沒帶 tick_type（舊版 shioaji、
        或某些商品）時，「不知道」和「內外盤剛好打平」是兩件完全不同的事。
        這個專案已經為了 `0` 當成 `None` 吃過兩次虧（損益查不到、成交窗口沒報價）。
        """
        if self.aggressive_buy <= 0 and self.aggressive_sell <= 0:
            return None
        if self.aggressive_sell <= 0:
            # 全部都是外盤。給一個有上限的數字，不要回傳 inf —— inf 寫進 CSV
            # 讀回來是字串，整列會被跳過。
            return 99.0
        return round(self.aggressive_buy / self.aggressive_sell, 2)

    def should_record_candidate(self, now: datetime) -> bool:
        """候選要記，但不能每個 tick 都記 —— 冷卻與上限都在這裡。"""
        if self.candidates >= MAX_CANDIDATES_PER_SYMBOL:
            return False
        if self.last_candidate_at and now - self.last_candidate_at < CANDIDATE_COOLDOWN:
            return False
        return True

    def lock_opening_range(self, high: float, low: float, source: str = "tick"):
        self.or_high, self.or_low = high, low
        self.or_locked = True
        log.info("%s 開盤區間鎖定（%s）：%.2f / %.2f", self.code, source, high, low)

    def update(self, tick, now: float | None = None):
        """now 可注入，讓離線回放（dryrun.py、測試）能自己控制量能時間軸。"""
        self.last_price = float(tick.close)
        self.vwap = float(getattr(tick, "avg_price", 0) or self.vwap)
        self.total_volume = int(getattr(tick, "total_volume", 0) or 0)
        hi = float(getattr(tick, "high", 0) or tick.close)
        lo = float(getattr(tick, "low", 0) or tick.close)
        self.day_high = max(self.day_high, hi)
        self.day_low = min(self.day_low, lo) if self.day_low else lo
        ts = tick.datetime.time() if hasattr(tick.datetime, "time") else datetime.now().time()
        # 開盤價：shioaji 的 tick 帶 open（當日開盤價）。沒帶的話，只有在開盤區間
        # 結束前收到的第一筆才拿來當開盤價 —— 更晚才開程式時，第一筆早就不是開盤了，
        # 寧可留 0（不知道），讓 v9 只用回落那一條判。
        op = float(getattr(tick, "open", 0) or 0)
        if op > 0:
            self.day_open = op
        elif not self.day_open and _t(config.SIGNAL["or_start"]) <= ts < _t(config.SIGNAL["or_end"]):
            self.day_open = float(tick.close)
        # 內外盤只在開盤區間內累計 —— 訊號要用的是「發訊號之前買盤有多強」，
        # 把整天的成交混進來，那一欄在 09:05 當下根本還不存在。
        if not self.or_locked:
            lots = int(getattr(tick, "volume", 0) or 0)
            kind = int(getattr(tick, "tick_type", 0) or 0)
            if lots > 0:
                if kind == 1:
                    self.aggressive_buy += lots
                elif kind == 2:
                    self.aggressive_sell += lots
                else:
                    self.unclassified += lots
        now = time.time() if now is None else now
        self.vol_marks.append((now, self.total_volume))
        self.vol_marks = [(t, v) for t, v in self.vol_marks
                          if now - t <= VOL_MARK_KEEP_SEC]

        if self.or_locked:
            return
        if _t(config.SIGNAL["or_start"]) <= ts < _t(config.SIGNAL["or_end"]):
            # tick 的 high/low 是當日累計高低；09:00 起算，在開盤區間內等於區間高低。
            self.or_high = max(self.or_high, float(tick.high or tick.close))
            self.or_low = min(self.or_low or 1e9, float(tick.low or tick.close))
        elif ts >= _t(config.SIGNAL["or_end"]) and self.or_high:
            self.lock_opening_range(self.or_high, self.or_low)

    def volume_surge(self) -> float:
        """近 5 分鐘的量能「速率」/ 前一段的量能速率。

        比的是每秒成交量，不是硬把前段除以 2：樣本還不到 10 分鐘時，
        除以 2 會把基準低估成一半，於是開盤後前幾分鐘每一檔都像爆量。
        樣本長度不足時回傳 0.0，讓訊號直接不成立。
        """
        if len(self.vol_marks) < 4:
            return 0.0
        now = self.vol_marks[-1][0]
        window = config.SIGNAL["volume_recent_sec"]
        recent = [(t, v) for t, v in self.vol_marks if now - t <= window]
        older = [(t, v) for t, v in self.vol_marks if now - t > window]
        if len(recent) < 2 or len(older) < 2:
            return 0.0

        recent_span = recent[-1][0] - recent[0][0]
        older_span = older[-1][0] - older[0][0]
        if (recent_span < config.SIGNAL["volume_min_recent_span_sec"]
                or older_span < config.SIGNAL["volume_min_base_span_sec"]):
            return 0.0

        recent_rate = (recent[-1][1] - recent[0][1]) / recent_span
        older_rate = (older[-1][1] - older[0][1]) / older_span
        if older_rate <= 0:
            return 0.0
        return recent_rate / older_rate


# ══════════════════════════════════════════════════════
# 訊號判斷
# ══════════════════════════════════════════════════════
def holds_overnight() -> bool:
    """這一版規則允許留倉過夜嗎（v6 起最多抱到隔天）。"""
    return config.SIGNAL.get("max_hold_days", 1) >= 2


def target_plan(amplitude_pct: float | None) -> tuple[float | None, str]:
    """這一檔的停利目標要往上幾 %，以及依據。回傳 (%, 依據)；% 是 None 表示用 R 倍數。

    依據：AMPLITUDE（v8，依個股平均振幅，夾在上下限之間）／FIXED（固定 %）／R。
    """
    cfg = config.SIGNAL
    if cfg.get("target_from_amplitude") and amplitude_pct and amplitude_pct > 0:
        lo, hi = cfg["target_min_pct"], cfg["target_max_pct"]
        return min(max(float(amplitude_pct), lo), hi), TARGET_BY_AMPLITUDE
    if cfg.get("target_pct") is not None:
        return float(cfg["target_pct"]), TARGET_FIXED
    return None, TARGET_BY_R


TARGET_BY_AMPLITUDE = "振幅"
TARGET_FIXED = "固定"
TARGET_BY_R = "R"


def target_price(entry: float, stop: float, amplitude_pct: float | None = None) -> float:
    """目標價。往上進位到合法檔位 —— 真的到價時，報酬不會低於設定值。"""
    pct, _ = target_plan(amplitude_pct)
    if pct is not None:
        return config.round_to_tick(entry * (1 + pct / 100), "up")
    return config.round_to_tick(entry + (entry - stop) * config.SIGNAL["reward_risk"], "up")


def _minutes_since_open(now: dtime | None) -> float | None:
    if now is None:
        return None
    start = datetime.combine(datetime(2000, 1, 1), _t(config.SIGNAL["or_start"]))
    mins = (datetime.combine(datetime(2000, 1, 1), now) - start).total_seconds() / 60
    return mins if mins > 0 else None


def _price_plan(st: SymbolState, entry: float, now: dtime | None = None) -> dict | None:
    """以 entry 為進場價，算出停損、目標、張數。進場價不可執行（已漲停、停損
    進位後等於進場價）就回 None。

    從 evaluate() 拆出來，是因為 09:05 那一批要用**發出當下**的價格重算一次
    （reprice_at_send）—— 兩邊必須是同一套算法，不然重算出來的停損目標會跟
    即時發的那些對不起來。
    """
    cfg = config.SIGNAL
    # 已經漲停鎖死就不要發了 —— 那個價位你買不到，就算買到也沒有上檔空間。
    cap = config.limit_up(st.prev_close)
    if cap and entry >= cap:
        log.warning("%s 現價 %.2f 已達漲停 %.2f，不發訊號", st.code, entry, cap)
        return None
    # 停損有兩條線，取**較寬**的那一條（較低的停損價）。
    #
    # 1. 固定 %：進場價往下 stop_loss_pct。往上進位（較緊的那一邊），
    #    實際風險不會超過設定的上限。
    # 2. 結構線：區間高點往下 stop_below_or_high_pct。
    #
    # 為什麼需要第二條：第一條和開盤區間完全無關，所以訊號發得越晚、進場價
    # 飄得越高，停損就跟著往上飄 —— 會飄到突破點**之上**。2026-10-02 美亞：
    # 區間高 26.70、進場 27.25、停損 26.85。那檔只要回測一下突破點就被掃，
    # 而突破根本還沒失敗。「跌回區間 = 突破失敗」才是這套策略自己的前提。
    #
    # 進場貼近突破點時第一條本來就比較低，第二條不會生效；只有追高之後才
    # 接手，而且接手的方式是自動加大風險、減少張數 —— 系統自己踩煞車。
    pct_stop = config.round_to_tick(entry * (1 - cfg["stop_loss_pct"] / 100), "up")
    structural_stop = None
    if st.or_high:
        structural_stop = config.round_to_tick(
            st.or_high * (1 - cfg["stop_below_or_high_pct"] / 100), "down")
    stop = min(pct_stop, structural_stop) if structural_stop else pct_stop
    # 哪一條生效，要記下來也要講出來 —— 不然使用者看到一個比平常寬的停損，
    # 會以為程式算錯了。
    stop_rule = "結構線（區間高下方）" if stop != pct_stop else "固定 %"
    if stop >= entry:
        # 低價股在極小的 stop_loss_pct 下會進位到進場價，這種訊號沒有可執行的停損。
        log.warning("%s 停損進位後等於進場價（%.2f），不發訊號", st.code, entry)
        return None
    # 目標同樣往上進位：真的到價時，報酬不會低於設定值。
    target_pct, target_basis = target_plan(st.amplitude_pct)
    target = target_price(entry, stop, st.amplitude_pct)
    # 但目標不可以超過漲停價。2026-09-24 的嘉晶就是這樣：昨收 145.5、漲停 160.0，
    # 而我們發了一個 161.00 的目標 —— 那一筆被判成「收盤平倉」，不是因為它沒走到，
    # 是因為那個價位當天不存在。貼齊漲停，並在訊號上講明賺賠比因此縮水。
    #
    # v6 抱兩天時例外：今天的漲停到不了，明天的漲停線是從今天收盤重算的。
    # 這時不貼齊，改成在訊號上講明「今天到不了，要靠明天」。
    beyond_today = bool(cap and target > cap)
    target_capped = beyond_today and not holds_overnight()
    if target_capped:
        target = cap

    # 四捨五入到分：進場價與停損價都已經進位到合法檔位，一張的風險本來就是整數分。
    # 不 round 的話 (20.2-19.9)*1000 會是 300.0000000000007，3000 // 它 = 9 而不是 10
    # —— 浮點雜訊直接吃掉你一整張。
    risk_per_lot = round((entry - stop) * 1000, 2)   # 一張 1000 股
    lots = int(config.RISK["per_trade_risk"] // risk_per_lot) if risk_per_lot > 0 else 0
    # 連一張都超過單筆風險上限時，張數不能報 0（那不是可執行的指示），
    # 但必須標記出來，否則你會照著它做一筆風險超標的交易而不知道。
    oversized = lots < 1
    lots = max(1, lots)


    return {
        "entry": entry,
        "stop": stop,
        "target": target,
        "lots": lots,
        "risk_per_lot": round(risk_per_lot),
        "oversized": oversized,
        "target_capped": target_capped,
        # 目標高過今天的漲停 —— 今天物理上到不了。只在抱兩天時會是 True 而
        # 目標沒被貼齊；記下漲停價，訊息上才講得出「今天最多到哪」。
        "beyond_today_limit": beyond_today and not target_capped,
        # v8：目標往上幾 %、依據什麼。訊息要講得出「為什麼是這個數字」。
        "target_pct": target_pct,
        "target_basis": target_basis,
        "limit_up": cap,
        # 進場價比突破點高出幾 % —— 追高的程度。以前只進 outcomes.csv，
        # 但看訊號的那一刻才是需要它的時候。
        "extension_pct": (round((entry - st.or_high) / st.or_high * 100, 2)
                          if st.or_high else None),
        "stop_rule": stop_rule,
        # v10：六條出場的計畫（關鍵價、先出一半的價位、移動停利、量縮的基準）。
        **(exits.plan_fields(entry, stop, target, day_open=st.day_open,
                             total_volume=st.total_volume,
                             minutes_since_open=_minutes_since_open(now))
           if cfg.get("exit_rules") else {}),
    }


def evaluate(st: SymbolState, now: dtime | None = None, *,
             ignore_symbol_cap: bool = False,
             ignore_window: bool = False,
             min_surge: float | None = None) -> dict | None:
    """ignore_symbol_cap=True 時照樣算出訊號內容，不管「一檔一天只發一次」。

    這是給候選紀錄用的：被上限擋掉的那些訊號本身是合格的，只是不推播。
    不把它們算出來，20 天後就回答不了「上限該不該放寬」。

    ignore_window=True 同理，給「09:30 之後才突破」的那些用 —— 只記錄、不發。

    min_surge：量能門檻換成這個數字（給「量不夠」的紀錄用，見 record_weak_volume）。
    沒給就是 config 的 volume_surge_ratio。量能算不出來（0）的一律不算。
    """
    cfg = config.SIGNAL
    now = now or datetime.now().time()

    if not st.or_locked:
        return None
    if not ignore_symbol_cap and st.signaled >= cfg["max_signals_per_symbol"]:
        return None
    if not ignore_window and now >= _t(cfg["entry_window_end"]):
        return None

    trigger = st.or_high * (1 + cfg["breakout_buffer_pct"] / 100)
    if st.last_price < trigger:
        return None
    if cfg["require_above_vwap"]:
        # 均價線拿不到時直接不發。原本寫成 `cfg[...] and st.vwap and ...`，
        # vwap 為 0 會讓整個條件短路成 False —— 規則你以為開著，其實整天沒作用。
        if not st.vwap:
            if not st.vwap_warned:
                log.warning("%s 沒有均價線（avg_price=0），require_above_vwap 無從判斷，"
                            "本檔今日不發訊號", st.code)
                st.vwap_warned = True
            return None
        if st.last_price < st.vwap:
            return None
    surge = st.volume_surge()
    need = cfg["volume_surge_ratio"] if min_surge is None else min_surge
    if surge <= 0 or surge < need:
        return None
    # v9：開盤或回落低點要在昨收附近。放在突破／均價線／量能之後判，是為了
    # 只有「其他都過了、只差這一關」的那一刻才留 log —— 每個 tick 都記會淹掉檔案。
    band = cfg.get("near_prev_close_pct")
    near_basis = None
    if band is not None:
        near_basis = config.near_prev_close(st.prev_close, st.day_open, st.day_low, band)
        if near_basis is None:
            if not st.gap_logged:
                log.info("%s 突破、均價線、量能都過了，但開盤 %s／最低 %s 都不在昨收 %s ±%g%% "
                         "以內，不發訊號", st.code, st.day_open or "?", st.day_low or "?",
                         st.prev_close or "?", band)
                st.gap_logged = True
            return None

    plan = _price_plan(st, st.last_price, now)
    if plan is None:
        return None
    return {
        "time": datetime.now().strftime("%H:%M:%S"),
        "code": st.code,
        "name": st.name,
        "direction": "做多",
        **plan,
        "amplitude_pct": st.amplitude_pct,
        "or_high": st.or_high,
        "vwap": round(st.vwap, 2),
        "volume_surge": round(surge, 2),
        # 內外盤比：量能倍數說「量有多大」，這一欄說「那些量是誰主動的」。
        # 先記不排序 —— 它還沒有任何資料支持，20 天後用算的決定要不要變成條件。
        "bid_ask_ratio": st.bid_ask_ratio(),
        "unclassified_lots": st.unclassified,
        # 試撮方向：只記錄（使用者 10-08），不影響發不發。
        "sim_from": st.sim_from,
        "sim_first": st.sim_first or None,
        "sim_last": st.sim_last or None,
        "sim_move_pct": st.sim_move_pct(),
        "sim_ups": st.sim_ups if st.sim_first else None,
        "sim_downs": st.sim_downs if st.sim_first else None,
        "rank": st.rank,
        "category": st.category,
        "ruleset": config.RULESET,
        # 這一筆照規則可以抱幾天。記在訊號上，不是收盤時再去看 config ——
        # 隔天程式重開、或拿新版程式回推舊訊號，都要照**當時**的規則走。
        "max_hold_days": config.SIGNAL.get("max_hold_days", 1),
        # v9：開盤、進場前最低點離昨收幾 %，以及是哪一個讓這一筆過關。
        # v8 以前的訊號也照記（near_basis 是 None）—— 20 天後要比「近昨收」
        # 跟「跳空」兩組，舊資料也能分得出來。
        "prev_close": st.prev_close or None,
        "day_open": st.day_open or None,
        "low_before": st.day_low or None,       # 發訊號這一刻為止的當日最低
        "open_gap_pct": _pct_from(st.day_open, st.prev_close),
        "low_gap_pct": _pct_from(st.day_low, st.prev_close),
        "near_basis": near_basis,
    }


def _pct_from(price: float | None, base: float | None) -> float | None:
    """price 比 base 高幾 %；任一個不知道就是 None（不是 0）。"""
    if not price or not base:
        return None
    return round((price - base) / base * 100, 2)


def _near_line(sig: dict) -> str | None:
    """v9 訊號上講清楚「為什麼這一檔算在昨收附近」。v8 以前的訊號沒有這一行。"""
    basis = sig.get("near_basis")
    if not sig.get("prev_close"):
        return None
    band = config.SIGNAL.get("near_prev_close_pct")
    if not basis and band is not None:
        return None      # 條件開著卻沒有依據 —— 不會發生（沒過就不會有訊號），不印
    parts = [f"昨收 {sig['prev_close']:.2f}"]
    if sig.get("day_open"):
        parts.append(f"開盤 {sig['day_open']:.2f}（{sig['open_gap_pct']:+.1f}%）")
    if sig.get("low_before") and sig.get("low_gap_pct") is not None:
        parts.append(f"最低 {sig['low_before']:.2f}（{sig['low_gap_pct']:+.1f}%）")
    if not basis:
        # 條件關掉了（v10 晚起）：只講事實，不當成進場依據
        return "位置：" + "｜".join(parts)
    why = ("開盤就在昨收附近" if basis == config.NEAR_BY_OPEN
           else "開高後回到昨收附近再往上")
    return "位置：" + "｜".join(parts) + f"\n　→ {why}（±{band:g}% 以內）"


def _format_signal_v10(sig: dict, ordinal: int) -> str:
    """v10 的買入訊號，精簡版（使用者 10-08：「後面的括號說明需要嗎？」→ 選精簡）。

    解釋規則的括號拿掉 —— 規則使用者已經知道了，每次都寫只會讓訊息變長。「目標」
    那一行也拿掉：v10 不會在目標價賣（到一半先出一半，剩下移動停利），留著會讓人
    以為要等它到。10-08 晚再拿掉三個括號（使用者：「這些不用」）：追高幾 %、開盤
    離昨收幾 %、停損最多賠多少 —— 價位都在訊息上，要算自己看得出來；數字照樣記在
    訊號與 outcomes.csv 裡。
    """
    r = config.RISK
    name = f" {sig['name']}" if sig.get("name") else ""
    lines = [
        f"📌 {sig['code']}{name}｜{sig['time']}",
        f"{sig['direction']}（開盤區間突破）",
        f"進場：{sig['entry']:.2f}",
        f"張數：{sig['lots']} 張　量能：{sig['volume_surge']:.2f}x",
    ]
    if sig.get("near_basis"):
        lines.append(_near_line(sig))          # v9 的昨收條件開著時，依據要講
    elif sig.get("prev_close") and sig.get("day_open"):
        lines.append(f"位置：昨收 {sig['prev_close']:.2f}｜開盤 {sig['day_open']:.2f}")
    if sig.get("breakout_at") and sig.get("breakout_price"):
        lines.append(f"ℹ️ {sig['breakout_at'][:5]} 突破時是 {sig['breakout_price']:.2f}，"
                     f"進場價已換成 {sig['time'][:5]} 發出當下的價格")
    if sig.get("oversized"):
        lines.append(f"⚠️ 一張的停損風險 {sig['risk_per_lot']:,} 元，"
                     f"超過上限 {r['per_trade_risk']:,} 元")
    lines.append("────────────────")
    lines += _exit_plan_lines(sig)
    cap = r["max_signals_per_day"]
    tail = ("今天的額度用完了" if ordinal >= cap
            else f"{config.SIGNAL['entry_window_end'][:5]} 前還可能有新的")
    lines += ["────────────────", f"今日第 {ordinal} 個（上限 {cap}）｜{tail}"]
    return "\n".join(lines)


def _exit_plan_lines(sig: dict) -> list[str]:
    """v10：進場前就把六條出場條件的價位寫在訊號上 —— 「進場前先畫好，不是進場後才找」。

    「收盤才算」的三條放在最後、自己一個小標題（10-08 晚：原本「以下三條」底下接了
    五行，看起來不只三條）。小標題之後到分隔線為止，全部都是收盤才算的。
    """
    if not exits.uses_v10(sig):
        return []
    buf = float(sig.get("reason_buffer_pct") or 0)
    win = float(sig["vol_window_min"])
    wait = 2 * win if sig.get("vol_base") == "after_entry" else win
    lines = ["出場（哪一條先到就出）：",
             f"・停損 {sig['stop']:.2f}",
             f"・漲到 {float(sig['half_at']):.2f} 先出一半，剩下從最高點回落 "
             f"{float(sig['trail_pct']):g}% 出",
             f"・量縮（進場 {wait:g} 分鐘後才判）",
             f"・{outcome.FLATTEN_AT:%H:%M} 全部平倉"]
    if sig.get("confirm") == "minute_close":
        lines.append("那一分鐘收盤在線下才出：")
    lines.append(f"・跌破開盤價 {float(sig['key_level']):.2f}" if sig.get("key_level")
                 else "・跌破開盤價（今天開盤價不知道，不判）")
    if sig.get("or_high"):
        lines.append(f"・跌回區間 {float(sig['or_high']) * (1 - buf / 100):.2f}")
    lines.append("・跌破均價線")
    return lines


def _ordinal_line(ordinal: int, batch_total: int | None) -> str:
    cap = config.RISK["max_signals_per_day"]
    head = f"今日第 {ordinal} 個訊號（上限 {cap}）"
    if batch_total:
        head += f"｜{config.SIGNAL['signal_batch_at'][:5]} 這一批共 {batch_total} 個"
    if ordinal >= cap:
        return head + "\n今天的額度用完了，不會再有新的買入訊號。"
    return head + f"\n{config.SIGNAL['entry_window_end'][:5]} 前還可能有新的訊號。"


def _target_line(sig: dict) -> str:
    risk = sig["entry"] - sig["stop"]
    r_mult = (sig["target"] - sig["entry"]) / risk if risk > 0 else 0.0
    if sig.get("target_capped"):
        return f"目標：{sig['target']:.2f}（貼齊漲停，實際 {r_mult:.2f}R）"
    pct = sig.get("target_pct")
    basis = sig.get("target_basis")
    if basis is None and pct is None:      # v8 以前的訊號沒有這兩欄
        pct = config.SIGNAL.get("target_pct")
        basis = TARGET_FIXED if pct is not None else TARGET_BY_R
    if basis == TARGET_BY_AMPLITUDE and sig.get("amplitude_pct"):
        amp = float(sig["amplitude_pct"])
        why = f"這檔近 5 日平均一天振幅 {amp:.1f}%"
        if abs(amp - pct) > 0.05:          # 被上下限夾住，要講出來，不然數字對不起來
            edge = "下限" if pct > amp else "上限"
            why += f"，取{edge} {pct:g}%"
        return f"目標：{sig['target']:.2f}（+{pct:.1f}%，{why}）"
    if pct is not None:
        return f"目標：{sig['target']:.2f}（+{pct:g}%，約 {r_mult:.2f}R）"
    return f"目標：{sig['target']:.2f}（{config.SIGNAL['reward_risk']}R）"


def format_signal(sig: dict, ordinal: int, batch_total: int | None) -> str:
    """ordinal = 這是今日第幾個訊號（1 起算）。batch_total = 09:05 那一批共幾個；
    09:05 之後即時發的那些是 None。

    batch_total 是必填，不給預設值。2026-10-05 只發了一個訊號，訊息卻寫
    「今日第 1/3 個訊號」，看起來像「還有兩個額度，等等可能再來」—— 那時訊號
    是 09:05 一次發完的，那兩個額度**不可能**被用到。

    v7 起進場窗口到 09:30，額度沒用完的話**真的**還可能有。所以這一行要講的是
    實話：額度用完了就說用完了，沒用完就說「窗口結束前還可能有」。
    """
    if exits.uses_v10(sig):
        return _format_signal_v10(sig, ordinal)
    r = config.RISK
    lines = [
        f"📌 {sig['code']}{(' ' + sig['name']) if sig.get('name') else ''}"
        f" 決策錨點｜{sig['time']}",
        "────────────────",
        f"方向：{sig['direction']}（開盤區間突破）",
        # 追高幅度印在進場價旁邊。這個數字以前只進 outcomes.csv，20 天後才看得到
        # —— 但真正需要它的時候，是訊號跳出來、你在決定要不要下單的那 10 秒。
        (f"進場：{sig['entry']:.2f}（區間高 {sig['or_high']:.2f} → "
         f"已追高 +{sig['extension_pct']:.2f}%，均價 {sig['vwap']:.2f}）"
         if sig.get("extension_pct") is not None else
         f"進場：{sig['entry']:.2f}（區間高 {sig['or_high']:.2f}，均價 {sig['vwap']:.2f}）"),
        f"停損：{sig['stop']:.2f}  ← 跌破就走，不准往下修",
        _target_line(sig),
        f"建議張數：{sig['lots']} 張（單筆風險 {r['per_trade_risk']:,} 元）",
        f"量能倍數：{sig['volume_surge']:.2f}x",
    ]
    if sig.get("breakout_at") and sig.get("breakout_price"):
        # 09:05 那一批：進場價已經換成發出當下的價格，講清楚突破時是多少。
        moved = (sig["entry"] - sig["breakout_price"]) / sig["breakout_price"] * 100
        lines.append(f"ℹ️ {sig['breakout_at'][:5]} 突破時是 {sig['breakout_price']:.2f}，"
                     f"上面的進場價是 {sig['time'][:5]} 發出當下的價格（{moved:+.1f}%），"
                     f"停損、目標、張數都照這個價重算過。")
    near = _near_line(sig)
    if near:
        lines.append(near)
    lines += _exit_plan_lines(sig)
    # 下面兩行只講事實，不替使用者做「要不要留倉」的決定 —— 使用者 10-07：
    # 「沒碰停損自己決定要不要留倉，因為你沒把握明天留倉會漲」。
    if sig.get("beyond_today_limit") and sig.get("limit_up"):
        room = (sig["limit_up"] - sig["entry"]) / sig["entry"] * 100
        lines.append(
            f"ℹ️ 今天漲停是 {sig['limit_up']:.2f}（進場後最多 +{room:.1f}%），目標今天到不了。")
    if holds_overnight():
        lines.append(
            f"⏳ {outcome.FLATTEN_AT:%H:%M} 還沒碰停損也沒到目標的話，要不要留倉由你決定。")
    if sig.get("stop_rule", "").startswith("結構"):
        # 停損比平常寬的時候要講原因，否則看起來像算錯了。
        lines.append(
            f"ℹ️ 停損用的是區間高 {sig['or_high']:.2f} 下方的結構線，不是進場價的固定 %"
            f" —— 因為這一筆已經追高 +{sig['extension_pct']:.2f}%，"
            f"固定 % 會把停損放到突破點之上，回測一下就被掃。")
    if sig.get("oversized"):
        lines.append(
            f"⚠️ 這檔一張的停損風險就是 {sig['risk_per_lot']:,} 元，"
            f"已超過單筆上限 {r['per_trade_risk']:,} 元。要做就自己認這個超額，或直接跳過。")
    lines += [
        "────────────────",
        _ordinal_line(ordinal, batch_total),
        "⚠️ 這是規則觸發，不是預測。你有權不做；但做了就照停損走。",
    ]
    return "\n".join(lines)


def format_window_closed(sent: int, watched: int) -> str:
    """進場窗口關掉時**一定**要發的一則 —— 包括一個訊號都沒有的時候。
    v7 起是 09:30（entry_window_end），不再是 09:05 批次那一刻。

    2026-10-05 之前，chosen 是空的時候 flush_batch 什麼都不發。於是手機上
    「今天沒有一檔通過閘門」和「程式當掉了」長得一模一樣：08:50 的開工確認
    之後一路安靜到 13:30。沉默不是一種回報。

    sent 是真的推出去的檔數，由呼叫端在發完之後算 —— 訊號那一則印的分母是
    批次挑中的檔數，萬一其中有人被風控擋掉，以這一則的數字為準。
    """
    cfg, r = config.SIGNAL, config.RISK
    at = cfg["entry_window_end"][:5]
    lines = [f"🔒 {at} 進場窗口已關閉", "────────────────"]
    if sent:
        after = ("出場通知（🛑 停損 ／ 🚪 理由消失 ／ 🟡 先出一半 ／ 💰 移動停利 ／ 💤 量縮"
                 f" ／ ⏹ {outcome.FLATTEN_AT:%H:%M} 全部平倉）"
                 if cfg.get("exit_rules") else "🛑 停損 ／ ✅ 目標")
        if cfg.get("exit_signal_at"):
            after += f" ／ ⏰ {cfg['exit_signal_at'][:5]} 時間到"
        lines += [
            f"今日訊號：{sent} 個（上限 {r['max_signals_per_day']}）",
            "不會再有新的買入訊號。",
            f"接下來只剩 {after}。",
        ]
        if holds_overnight():
            lines.append(f"{outcome.FLATTEN_AT:%H:%M} 還沒結束的會再通知你，要不要留倉由你決定。")
    else:
        lines += [
            f"今日訊號：0 個",
            f"監看的 {watched} 檔，沒有一檔在 {cfg['or_end'][:5]}–{at} 之間"
            "同時通過突破、均價線、量能"
            + ("、開盤在昨收附近" if cfg.get("near_prev_close_pct") is not None else "")
            + "這幾道閘。",
            "",
            "不會再有新的買入訊號。",
            "⚠️ 這不是當掉。程式還在跑，會執行到 13:30 —— 只是今天不出手。",
        ]
    return "\n".join(lines)


_push_warned = False

# ── 被擋掉的候選 ───────────────────────────────────────
# 訊號上限與「一檔一天一次」擋掉的訊號，以前是 return None 直接丟掉。
# 那兩條規則到底訂得對不對，20 天後只能靠這份紀錄回答 —— 沒有紀錄就只能再測一次。
# 這裡只寫檔，不推播、不計入風控、不進 outcomes.csv，策略行為完全沒變。
CANDIDATE_FILE = config.BASE_DIR / "candidates.csv"
CANDIDATE_FIELDS = ("date", "code", "name", "time", "entry", "stop", "target",
                    "lots", "reason", "or_high", "vwap", "volume_surge", "rank",
                    "sim_from", "sim_move_pct", "sim_ups", "sim_downs",
                    # 收盤回推要照**跟訊號一樣**的出場規則走，計畫就得跟著寫下來。
                    # 10-08 晚以前少了這幾欄：v10 的候選會被當成舊的「停損／目標」
                    # 回推，跟真的訊號用的是兩把尺（v10 還沒上線，沒有資料受影響）。
                    "ruleset", "max_hold_days", "exit_rules", "key_level", "half_at",
                    "trail_pct", "reason_buffer_pct", "vol_window_min", "vol_ratio",
                    "flat_pct", "confirm", "vol_base", "entry_cum_volume",
                    "category", "bid_ask_ratio", "open_gap_pct", "low_gap_pct")
# 同一檔的候選之間至少隔這麼久。不設的話突破後每個 tick 都會記一筆，
# 記到的是同一次突破的雜訊，不是「另一次進場機會」。
CANDIDATE_COOLDOWN = timedelta(minutes=5)
MAX_CANDIDATES_PER_SYMBOL = 3

BLOCK_DAILY_CAP = "daily_cap"        # 今日訊號額度用完
BLOCK_SYMBOL_CAP = "symbol_cap"      # 這檔今天已經發過了


def _upgrade_header(path, fields) -> None:
    """舊檔的表頭少了新欄位時，先照新表頭整份重寫一次，再往後附加。

    直接附加的話，新的那幾欄會寫在舊表頭沒有的位置 —— 讀回來整列錯位，
    而且不會報錯。舊列的新欄位留空（那時候還沒記）。
    """
    if not path.exists():
        return
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) == tuple(fields):
            return
        rows = list(reader)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) or "" for k in fields})


def record_candidate(sig: dict, reason: str, path=None) -> None:
    """把被擋掉的候選附加到 candidates.csv。寫檔失敗不可以影響盤中監看。"""
    path = pathlib.Path(path) if path else CANDIDATE_FILE
    row = {k: sig.get(k, "") for k in CANDIDATE_FIELDS}
    row["date"] = datetime.now().strftime("%Y-%m-%d")
    row["reason"] = reason
    try:
        _upgrade_header(path, CANDIDATE_FIELDS)
        new_file = not path.exists()
        with open(path, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=CANDIDATE_FIELDS)
            if new_file:
                w.writeheader()
            w.writerow(row)
    except Exception as e:
        log.warning("候選寫檔失敗（不影響監看）：%s", e)


BLOCK_BATCH_RANK = "批次排序未入選"
BLOCK_FELL_BACK = "發出時已跌回區間"      # 09:05 批次：突破後又掉回區間高以下
BLOCK_BELOW_VWAP = "發出時已跌破均價線"
BLOCK_LOCKED = "發出時已漲停"            # 買不到
BLOCK_AFTER_WINDOW = "09:30 之後才突破"   # 只記錄，不發
BLOCK_WEAK_VOLUME = "量能未達門檻"        # 其他都過了、只差量能（只記錄，不發）


def reprice_at_send(sig: dict, st: "SymbolState | None",
                    now: datetime) -> tuple[dict | None, str | None]:
    """09:05 那一批發出前，用**當下**的價格重算進場、停損、目標、張數。

    09:02:10 突破的那一檔要等到 09:05 才發，原本訊號上的進場價是 3 分鐘前
    的價格 —— 那時你已經買不到了，停損距離與賺賠比也都不是訊息上寫的那樣。
    這一步把它換成你收到訊息那一刻真的能買的價格。

    已經跌回區間（突破失敗）、跌破均價線、或漲停鎖死買不到的，不發，
    回傳 (None, 原因) 讓呼叫端記進 candidates.csv。
    st 不知道或還沒有報價時原樣放行 —— 沒有新資訊就不要亂改。
    """
    if st is None or not st.last_price:
        return sig, None
    cfg = config.SIGNAL
    price = st.last_price
    if price < st.or_high * (1 + cfg["breakout_buffer_pct"] / 100):
        return None, BLOCK_FELL_BACK
    if cfg["require_above_vwap"] and st.vwap and price < st.vwap:
        return None, BLOCK_BELOW_VWAP
    plan = _price_plan(st, price, now.time())
    if plan is None:
        return None, BLOCK_LOCKED
    fresh = dict(sig, **plan)
    fresh.update(
        time=now.strftime("%H:%M:%S"),
        vwap=round(st.vwap, 2),
        breakout_at=sig.get("time"),
        breakout_price=sig.get("entry"),
    )
    return fresh, None


# 09:30 之後的突破記到幾點。只是為了回答「09:30 截止是不是太早」，
# 不必記一整天 —— 10:30 之後的突破跟開盤動能已經是兩回事。
LATE_RECORD_UNTIL = dtime(10, 30)


def record_late_breakout(st: "SymbolState", now: datetime, record=None) -> bool:
    """09:30 之後才突破、今天又還沒發過訊號的那一檔：算出訊號內容、記一筆候選，
    **不發**。一檔一天只記一次。回傳有沒有記。"""
    if st.late_recorded or st.signaled:
        return False
    t = now.time()
    if not (_t(config.SIGNAL["entry_window_end"]) <= t < LATE_RECORD_UNTIL):
        return False
    sig = evaluate(st, t, ignore_window=True)
    if not sig:
        return False
    sig["time"] = now.strftime("%H:%M:%S")
    st.late_recorded = True
    (record or record_candidate)(sig, BLOCK_AFTER_WINDOW)
    return True


def record_weak_volume(st: "SymbolState", now: datetime, record=None) -> bool:
    """進場窗口內，突破、均價線都過了、只差量能不到門檻的那一檔：照樣算出訊號
    內容（量能倍數照實記）、記一筆候選，**不發**。一檔一天只記第一次。

    使用者 10-08 問「為什麼定 1.8 倍」—— 那是第一版的經驗值，從沒驗證過，而
    v4 把量能的比法改了之後它的意思也變了。只看發出去的訊號回答不了「門檻放寬
    到 1.5 會多哪些、結果如何」，因為量不夠的根本沒有紀錄。這就是那份紀錄。

    已經發過訊號的那一檔不記（它的量後來夠了，答案在 outcomes.csv）。之後才
    發訊號的也照樣留著這一筆 —— 「門檻低一點，會早幾分鐘進場」也是答案的一部分。
    """
    if st.weak_recorded or st.signaled:
        return False
    t = now.time()
    if t >= _t(config.SIGNAL["entry_window_end"]):
        return False
    sig = evaluate(st, t, min_surge=0.0)
    if not sig or sig["volume_surge"] >= config.SIGNAL["volume_surge_ratio"]:
        return False
    sig["time"] = now.strftime("%H:%M:%S")
    st.weak_recorded = True
    (record or record_candidate)(sig, BLOCK_WEAK_VOLUME)
    return True


class SignalBatch:
    """09:02–09:05 收集突破，09:05:00 一次發出，按當下量能倍數排序取前 N 檔。

    v3 以前是「誰先突破誰先發」。在三小時長的進場窗口裡那還說得過去 ——
    先突破的確實是先動的那一檔。壓縮到三分鐘之後，先後差距只剩「哪一檔的
    報價封包先到」，那是網路抖動不是市場資訊。排序用的量能倍數是今天
    09:00–09:02 量出來的，比盤前量比（看的是昨天）新鮮。
    """

    def __init__(self, at, limit: int):
        self.at = at
        self.limit = limit
        self.pending: dict[str, dict] = {}
        self.flushed = False

    def add(self, sig: dict) -> None:
        # 同一檔只留第一次突破：那一筆的進場價才是「剛越過區間高」的價格，
        # 之後再觸發只會更高，而追高正是 v4 要離開的那個毛病。
        self.pending.setdefault(str(sig["code"]), sig)

    def due(self, now: datetime) -> bool:
        return not self.flushed and now.time() >= self.at

    def take(self) -> tuple[list[dict], list[dict]]:
        """回傳 (入選的, 落選的)。落選的照樣要進 candidates.csv —— 砍掉樣本
        就等於把「只做前 3 名對不對」這一題變成無法回答。"""
        self.flushed = True
        ranked = sorted(
            self.pending.values(),
            # 量能高的優先；平手時用盤前名次，再平手用代號 —— 任何時候都要
            # 有一個固定的順序，否則同一份資料重跑會得到不同的三檔。
            key=lambda x: (-(x.get("volume_surge") or 0),
                           x.get("rank") or 9999, str(x.get("code"))))
        self.pending = {}
        return ranked[:self.limit], ranked[self.limit:]


class EntryDesk:
    """進場窗口的整條流程（v7）：

      09:02–09:05  突破的先收集（SignalBatch），09:05 按量能排序發出前 N 個
      09:05–09:30  突破的一出現就發，直到湊滿當日上限
      09:30        窗口關閉，**一定**推一則 🔒（包括一個都沒有的時候）

    抽成獨立的東西，是因為 run() 與 dryrun.py 都要走這條路。之前 dryrun 自己
    抄了一份批次邏輯 —— 改規則的時候只改 run() 的話，dryrun 會繼續驗一條
    已經不存在的管線，而且一片綠。

    emit(sig, now, batch_total) 真的去發（過閘、記錄、推播），發出去回 True；
    blocked(sig, reason) 記下被擋掉的；say(text) 推播。
    """

    def __init__(self, emit, blocked, say, watched: int, sent: int = 0,
                 now: datetime | None = None, reprice=None):
        cfg = config.SIGNAL
        # reprice(sig, now) -> (sig | None, 原因)：09:05 那一批發出前用當下價格重算。
        # None = 不重算（測試、舊呼叫端）。
        self.reprice = reprice
        self.batch = SignalBatch(_t(cfg["signal_batch_at"]),
                                 config.RISK["max_signals_per_day"])
        self.window_end = _t(cfg["entry_window_end"])
        self.emit, self.blocked, self.say = emit, blocked, say
        self.watched = watched
        self.sent = sent
        now = now or datetime.now()
        # 窗口結束之後才啟動（盤中重開）：warn_if_too_late 已經講過了，
        # 不要再補一則 🔒 —— 那一則的訊號數會是 0，跟早上實際發的對不起來。
        self.closed = now.time() >= self.window_end
        # 行情回呼跑在多條執行緒上。兩條同時看到「09:05 到了」就會把同一批
        # 各發一次 —— 判斷要在鎖裡做完。發送（含網路推播）放在鎖外，
        # 不要讓一則卡住的推播擋住其他檔的行情。
        self._lock = threading.Lock()

    def offer(self, sig: dict, now: datetime | None = None) -> None:
        """evaluate() 算出一個合格的突破。09:05 前收集，之後直接發。"""
        now = now or datetime.now()
        with self._lock:
            if self.closed or now.time() >= self.window_end:
                return
            if not self.batch.flushed:
                self.batch.add(sig)
                return
        self._send([sig], now, None)

    def tick(self, now: datetime | None = None) -> None:
        """到點就送批次；過了窗口就收尾。行情回呼與主迴圈都會呼叫，重複呼叫無害。"""
        now = now or datetime.now()
        chosen = rest = None
        closing = False
        with self._lock:
            if self.batch.due(now):
                chosen, rest = self.batch.take()
            if not self.closed and now.time() >= self.window_end:
                self.closed = closing = True
        if chosen is not None:
            for sig in rest:
                self.blocked(sig, BLOCK_BATCH_RANK)
            if self.reprice:
                fresh = []
                for sig in chosen:
                    new, why = self.reprice(sig, now)
                    if new is None:
                        self.blocked(sig, why)
                    else:
                        fresh.append(new)
                chosen = fresh
            self._send(chosen, now, len(chosen))
        if closing:
            self.say(format_window_closed(self.sent, self.watched))

    def _send(self, sigs: list[dict], now: datetime, batch_total: int | None) -> None:
        for sig in sigs:
            if self.emit(sig, now, batch_total):
                with self._lock:
                    self.sent += 1


def format_market_closed(reason: str, today: str | None = None) -> str:
    """休市日早上推的那一行。下一個開盤日一起講，免得以為程式壞了。"""
    today = today or datetime.now().strftime("%Y-%m-%d")
    nxt = market_calendar.next_open_day(today)
    return (f"📅 今天 {market_calendar.label(today)} 休市（{reason}），不監看、不出日報。\n"
            f"下一個開盤日：{market_calendar.label(nxt)}")


# 表上沒有的休市日（颱風假、臨時公告）：開盤後這個時間還沒有任何一筆成交，
# 就去看 0050 今天有沒有任何一根分鐘 K。
MARKET_CHECK_AT = dtime(9, 3)


def check_market_open(broker, today: str | None = None) -> bool | None:
    """0050 今天有沒有任何一根分鐘 K。True = 有開盤；False = 沒有（休市）；
    None = 查不到（查詢失敗）—— 那不是休市，不可以當休市處理。"""
    today = today or datetime.now().strftime("%Y-%m-%d")
    try:
        kb = broker.kbars(broker.MARKET_PROXY, today, today)
    except Exception as e:
        log.warning("開盤確認（0050 分鐘 K）失敗：%s", e)
        return None
    return bool(list(getattr(kb, "ts", []) or []))


def format_no_quotes() -> str:
    return ("⚠️ 09:03 還沒收到任何一筆成交，但今天有開盤 —— 監看可能收不到行情。\n"
            "到電腦上看監看視窗；或把 logs\\monitor.log 最後幾行貼出來。")


def format_too_late(now: datetime) -> str:
    """啟動太晚 —— 今天不會有訊號，而且畫面上看不出來。

    v3 的進場窗口有三小時十五分，晚開只是少幾個訊號，補算完開盤區間還能繼續。
    v4 的窗口只有三分鐘（09:02–09:05），**過了就整天掛零**，而「整天掛零」和
    「今天沒有股票突破」在畫面上一模一樣 —— 那正是這個專案一路在修的那種事：
    失敗要出聲，不然你會把故障當成行情。
    """
    cfg = config.SIGNAL
    return "\n".join([
        f"\u26a0\ufe0f {now.strftime('%H:%M:%S')} 盤中監看啟動太晚",
        "────────────────",
        f"發訊號的窗口是 {cfg['or_end']}–{cfg['entry_window_end']}，現在已經過了。",
        "**今天不會有任何買進訊號** —— 這不是今天沒行情，是程式沒趕上。",
        "────────────────",
        "手上如果有部位（含昨日留倉），停損與目標照舊有人盯。",
        f"明天請確認 monitor.bat 在 {cfg['or_end']} 之前就跑起來。",
    ])


def warn_if_too_late(now: datetime | None = None) -> bool:
    """批次窗口已經過了就推一則警告，回傳有沒有推。

    拆成獨立函式而不是寫在 run() 裡，是為了測得到。寫在 run() 裡的話，
    把那個判斷改成 `if False:` 不會有任何測試失敗 —— 而那正是這個專案
    一路在修的毛病：規則看起來在那裡，實際上沒有作用。
    """
    now = now or datetime.now()
    if now.time() < _t(config.SIGNAL["entry_window_end"]):
        return False
    notify(format_too_late(now))
    return True


def format_time_exit(o: "OpenSignal", price: float, at: str) -> str:
    gross = (price - o.entry) / o.entry * 100
    net = gross - config.round_trip_cost_pct()
    risk = o.entry - o.stop
    r = (price - o.entry) / risk if risk > 0 else 0.0
    label = f"{o.code} {o.name}".strip()
    return "\n".join([
        f"⏰ {label} 時間到｜{at}",
        "────────────────",
        f"進場 {o.entry:.2f} → 現價 {price:.2f}",
        f"{gross:+.2f}%（扣掉來回成本 {net:+.2f}%）　{r:+.2f}R",
        f"停損 {o.stop:.2f} 還沒碰到。",
        "────────────────",
        "**走不走由你決定。** 系統只負責在這個時間提醒你，"
        "不替你做這個決定；停損照舊有效，沒走的話它還在。",
    ])


def try_emit(st: SymbolState, gate: RiskGate, lock, sig: dict,
             now: datetime | None = None,
             batch_total: int = 1) -> tuple[str | None, str | None]:
    """在鎖內完成「再確認 → 過閘 → 記錄」。

    回傳 (要推播的訊息, 被擋掉的原因)，兩者恰有一個是 None。被擋的原因要回傳，
    因為候選紀錄的判斷必須跟閘門在同一把鎖裡做完，否則兩條執行緒會各自記一筆。

    行情回呼跑在背景執行緒上，多檔可能同時觸發。這幾步不是原子的話，
    兩檔會雙雙通過 check() 再各自寫進 state.json —— 當日訊號上限就被繞過去了。
    推播與寫檔留在鎖外：網路與磁碟不該卡住其他檔的行情處理。
    """
    now = now or datetime.now()
    with lock:
        # 鎖內再確認一次：可能有另一條執行緒剛剛替這檔發過。
        if st.signaled >= config.SIGNAL["max_signals_per_symbol"]:
            blocked = BLOCK_SYMBOL_CAP
        elif not gate.check():
            blocked = BLOCK_DAILY_CAP
        else:
            blocked = None
        if blocked:
            if not st.should_record_candidate(now):
                return None, None       # 冷卻中或已達上限 —— 擋掉，但也不記
            st.candidates += 1
            st.last_candidate_at = now
            return None, blocked
        st.signaled += 1
        ordinal = gate.record(sig)
    return format_signal(sig, ordinal, batch_total), None


# ══════════════════════════════════════════════════════
# 訊號發出之後 —— 盯到結局為止
# ══════════════════════════════════════════════════════
# v10 一分鐘收盤確認的出場原因
MINUTE_CLOSE_EXITS = (exits.BELOW_OPEN, exits.BACK_IN_RANGE, exits.BELOW_VWAP)

RESOLUTION_MARK = {
    outcome.TARGET: "\u2705",        # ✅
    outcome.STOP: "\U0001f6d1",      # 🛑
    outcome.FLAT: "\u23f9",          # ⏹
    # v10 的出場原因
    exits.BELOW_OPEN: "\U0001f6aa",     # 🚪
    exits.BACK_IN_RANGE: "\U0001f6aa",
    exits.BELOW_VWAP: "\U0001f6aa",
    exits.VOLUME_DRY: "\U0001f4a4",     # 💤
    exits.TRAIL: "\U0001f4b0",          # 💰
}


# 訊號發出後，限價單掛在進場價買不買得到 —— 看這段時間內最低成交到哪裡。
# 和 outcome.FILL_WINDOW_BARS（5 根分鐘 K）是同一個窗口，刻意對齊，兩邊才能互驗。
FILL_WINDOW = timedelta(minutes=5)


@dataclass
class FillProbe:
    """訊號後 5 分鐘內的最低成交價 —— 也就是「這一筆到底買不買得到」。

    這一題只有 tick 答得出來。outcome.py 的 low_5m_pct 是用分鐘 K 算的，
    而分鐘 K 刻意丟掉訊號後的頭 60 秒（見 outcome.bars_after 的說明），
    急拉型的突破訊號正好都在那 60 秒內就離開進場價 —— 於是最需要知道答案的
    那幾筆，欄位反而答不出來，還會答得偏悲觀（說「從來沒回到進場價」）。

    刻意和 OpenSignal 分開成兩個東西，理由有兩個：
      1. 買不買得到和這筆賺賠無關。就算 12 秒就到目標（2026-09-29 允強），
         5 分鐘內買不買得到仍然要記。
      2. 所以這支探針在訊號判定結束之後還要繼續收報價，不能跟著 OpenSignal
         一起被移出追蹤清單。
    """
    code: str
    time: str
    entry: float
    fired: datetime
    low: float | None = None

    def saw(self, price: float) -> None:
        if self.low is None or price < self.low:
            self.low = price

    def closed(self, now: datetime) -> bool:
        return now - self.fired >= FILL_WINDOW


def parse_fired_at(time_str: str, now: datetime) -> datetime | None:
    """把訊號上的 "HH:MM:SS" 還原成今天的 datetime。解析不出來就回 None。"""
    try:
        t = datetime.strptime(str(time_str), "%H:%M:%S").time()
    except (ValueError, TypeError):
        return None
    return datetime.combine(now.date(), t)


@dataclass
class OpenSignal:
    code: str
    name: str
    time: str
    entry: float
    stop: float
    target: float
    # 照規則可以抱幾天（訊號上記的）。>= 2 的，13:25 還沒結束就留倉，不平倉。
    hold_days: int = 1
    # 昨天留倉過來的。今天 13:25 一律平倉，不會再留；成本用留倉稅率。
    carried: bool = False
    lots: int = 0
    # v10：六條出場的狀態（exits.Position）。None = 舊規則（停損／目標／13:25）。
    pos: "exits.Position | None" = None

    def verdict(self, price: float) -> str:
        """這個價位讓這筆結束了嗎。停損先判：往壞處算。"""
        if price <= self.stop:
            return outcome.STOP
        if price >= self.target:
            return outcome.TARGET
        return ""


def format_resolution(o: OpenSignal, price: float, verdict: str,
                      exit_price: float | None = None) -> str:
    """出場價一律取停損／目標那個價位，不取觸發當下的報價。

    理由是要和 outcome.py 的收盤回推對得起來 —— 兩邊算出不同的數字，就沒辦法
    拿其中一邊去驗另一邊。跳空穿過去的部分另外寫在訊息裡，不混進報酬率。
    """
    if exit_price is None:
        exit_price = {outcome.TARGET: o.target, outcome.STOP: o.stop}.get(verdict, price)
    half = o.pos.half_price if o.pos is not None and o.lots != 1 else None
    if half is not None:
        return _format_two_legs(o, price, verdict, half, exit_price)
    # 留倉過夜的那一筆，隔天一開盤就跳過停損 —— 你賣到的是那個價，不是停損價。
    # 當沖時那一點穿價是滑價，可以另外寫；跳空可以是好幾 %，不計入就是假帳。
    if o.carried and verdict == outcome.STOP:
        exit_price = min(price, o.stop)
    elif o.carried and verdict == outcome.TARGET:
        exit_price = max(price, o.target)
    gross = (exit_price - o.entry) / o.entry * 100
    net = gross - config.round_trip_cost_pct(overnight=o.carried)
    risk = o.entry - o.stop
    r = (exit_price - o.entry) / risk if risk > 0 else 0.0
    label = f"{o.code} {o.name}".strip()
    lines = [
        f"{RESOLUTION_MARK.get(verdict, '')} {label} {verdict}"
        f"｜{datetime.now().strftime('%H:%M:%S')}",
        "────────────────",
        f"進場 {o.entry:.2f} → 出場 {exit_price:.2f}",
        f"{gross:+.2f}%（扣掉來回成本 {net:+.2f}%）　{r:+.2f}R",
    ]
    if verdict in MINUTE_CLOSE_EXITS:
        # 一分鐘收盤確認的那幾條：出場價是上一分鐘的收盤，現在的報價是下一分鐘的
        # 第一筆 —— 不是「穿過去」，寫成穿價會讓人以為算錯了。
        lines.append(f"上一分鐘收在 {exit_price:.2f}，在線下；現在的報價 {price:.2f}")
    elif abs(price - exit_price) >= 0.01:
        lines.append(f"觸發時報價 {price:.2f}（穿過去的部分不計入上面的報酬率）")
    if o.carried:
        lines.append("（昨天留倉過來的，成本以留倉稅率 0.3% 計）")
    if verdict == outcome.TARGET:
        # 使用者原話：「有的選對股，甚至再留達 20% 都有可能，交由自己下單者決定」。
        # 系統不替人決定續不續抱；紀錄照規則記在目標價，續抱走多遠由
        # outcomes.csv 的 mfe_pct 回答（analyse.py「續抱分析」那一節）。
        lines.append("🎯 目標到了。**續抱與否由你決定。** 系統的紀錄照規則記在目標價，"
                     "達標後還走了多遠另外記，20 天後看「續抱分析」。")
    lines += [
        f"訊號發出於 {o.time}",
        "────────────────",
        "驗證期不下單。這是照規則做會有的結果，不是你的實際損益。",
    ]
    return "\n".join(lines)


def _format_two_legs(o: OpenSignal, price: float, verdict: str,
                     half: float, exit_price: float) -> str:
    """v10：先出過一半的那一筆，剩下的也出場了。兩段分開寫，再寫合起來的。"""
    half_lots = o.pos.half_lots if o.pos is not None else 0
    pct, r = exits.blended(o.entry, o.stop, o.lots, half, exit_price, half_lots or None)
    net = pct - config.round_trip_cost_pct()
    leg = lambda p: (p - o.entry) / o.entry * 100
    label = f"{o.code} {o.name}".strip()
    first = f"先出 {half_lots} 張" if half_lots else "先出一半"
    rest = f"剩下 {o.lots - half_lots} 張" if half_lots else "剩下一半"
    lines = [
        f"{RESOLUTION_MARK.get(verdict, '')} {label} {verdict}，全部出場"
        f"｜{datetime.now().strftime('%H:%M:%S')}",
        "────────────────",
        f"{first}：{o.entry:.2f} → {half:.2f}（{leg(half):+.2f}%）",
        f"{rest}：{o.entry:.2f} → {exit_price:.2f}（{leg(exit_price):+.2f}%）",
        f"合計 {pct:+.2f}%（扣掉來回成本 {net:+.2f}%）　{r:+.2f}R",
    ]
    if verdict in MINUTE_CLOSE_EXITS:
        lines.append(f"上一分鐘收在 {exit_price:.2f}，在線下；現在的報價 {price:.2f}")
    elif abs(price - exit_price) >= 0.01:
        lines.append(f"觸發時報價 {price:.2f}（穿過去的部分不計入上面的報酬率）")
    lines += [
        f"訊號發出於 {o.time}",
        "────────────────",
        "驗證期不下單。這是照規則做會有的結果，不是你的實際損益。",
    ]
    return "\n".join(lines)


def format_half(o: OpenSignal, price: float, half: float) -> str:
    """v10 條件三：漲到目標的一半，先出一半。剩下的改移動停利。"""
    label = f"{o.code} {o.name}".strip()
    trail = o.pos.trail_pct if o.pos is not None else config.SIGNAL["exit_trail_pct"]
    gain = (half - o.entry) / o.entry * 100
    lines = [f"🟡 {label} 先出一半｜{datetime.now().strftime('%H:%M:%S')}",
             "────────────────",
             f"進場 {o.entry:.2f} → {half:.2f}（{gain:+.2f}%，目標 {o.target:.2f} 的一半）"]
    if o.lots == 1:
        lines.append("只有 1 張分不了 —— 整張改成移動停利：")
    elif o.lots >= 2:
        n = o.lots // 2
        lines.append(f"先賣 {n} 張（共 {o.lots} 張），剩下 {o.lots - n} 張改成移動停利：")
    else:
        lines.append("先賣一半，剩下的改成移動停利：")
    lines += [
        f"從最高點回落 {trail:g}% 就出，最低不低於成本 {o.entry:.2f}。",
        "其他出場條件照舊（停損、跌破開盤價、跌回區間、跌破均價線、量縮、13:25）。",
    ]
    if abs(price - half) >= 0.01:
        lines.append(f"觸發時報價 {price:.2f}")
    lines += ["────────────────",
              "驗證期不下單。這是照規則做會有的結果，不是你的實際損益。"]
    return "\n".join(lines)


def close_snapshot(st: "SymbolState | None", price: float | None) -> dict:
    """13:25 還沒結束的那一筆，當下的三個數字（第四個「大盤」收盤後由 outcome.py 補）。

    使用者 10-07 問「要不要留倉，能算出幾成把握嗎」——現在算不出來，一筆資料都
    沒有。所以先**只記錄**：累積 15～20 筆後拿隔天的結果對，看哪個分得出好壞，
    分得出來的才變成訊息上的一句事實。訊號、訊息、規則都不因為這個改變。

      close_pos_pct  收在今天最低～最高之間的哪裡（0 = 最低，100 = 最高）
      vs_vwap_pct    現價比今天均價線高（+）或低（−）幾 %
      volume_x       今天的量是平常一天的幾倍

    算不出來的留 None（例如沒收到報價、名單裡沒有平常量）—— 空白不是 0。
    """
    out = {"close_pos_pct": None, "vs_vwap_pct": None, "volume_x": None}
    if st is None or not price:
        return out
    if st.day_high > st.day_low > 0:
        out["close_pos_pct"] = round((price - st.day_low) / (st.day_high - st.day_low) * 100, 1)
    if st.vwap:
        out["vs_vwap_pct"] = round((price - st.vwap) / st.vwap * 100, 2)
    if st.avg_volume_lots:
        out["volume_x"] = round(st.total_volume / float(st.avg_volume_lots), 2)
    return out


def format_carry(o: OpenSignal, price: float | None) -> str:
    """第一天 13:25 還沒結束。只講事實，**留不留倉由使用者決定**。

    使用者 10-07 把這一則原本的勸說全刪了：「沒碰停損自己決定要不要留倉，
    因為你沒把握明天留倉會漲」。系統仍然追蹤到隔天 13:25 —— 那是為了 20 天後
    回答得了「留倉到底划不划算」，不是建議你留。
    """
    label = f"{o.code} {o.name}".strip()
    lines = [f"📦 {label} 13:25 還沒結束｜{datetime.now().strftime('%H:%M:%S')}",
             "────────────────"]
    if price is not None:
        gross = (price - o.entry) / o.entry * 100
        risk = o.entry - o.stop
        r = (price - o.entry) / risk if risk > 0 else 0.0
        lines.append(f"進場 {o.entry:.2f} → 現價 {price:.2f}　{gross:+.2f}%（未實現）　{r:+.2f}R")
    else:
        lines.append(f"進場 {o.entry:.2f}（今天沒收到報價，現價不明）")
    lines += [
        f"今天沒碰停損 {o.stop:.2f}、也沒到目標 {o.target:.2f}。",
        "要不要留倉由你決定。",
        "────────────────",
        f"系統會繼續追蹤到明天 {outcome.FLATTEN_AT:%H:%M}，結果另外記"
        f"（明天照常在 {config.SIGNAL['or_start'][:5]} 前開監看才接得到）。",
    ]
    return "\n".join(lines)


class LiveTracker:
    """訊號發出後追到停損或目標為止，當場推播。

    outcome.py 收盤後用分鐘 K 回推同一件事。兩條路完全獨立 —— 一邊看即時 tick、
    一邊看收盤後的分鐘 K —— 所以兩邊對不起來就表示其中一邊錯了。驗證期兩份都留著，
    互為對照。

    tick 回呼跑在背景執行緒，同一檔會連續進來很多筆，所以「判定結束並移出清單」
    必須在鎖內一次做完，否則同一筆會推播好幾次。推播本身留在鎖外，不卡行情。
    """

    def __init__(self, on_resolved=None, on_fill=None, on_time_exit=None, on_carry=None,
                 on_half=None):
        self.open: list[OpenSignal] = []
        self.fills: list[FillProbe] = []
        self.last_price: dict[str, float] = {}
        self._lock = threading.Lock()
        self.time_exited = False
        # 09:30「時間到」的價位交給誰記下來。同理：不寫回去就只活在推播裡。
        self.on_time_exit = on_time_exit
        # 判定完要交給誰記下來。沒有它的話，即時結果只活在那則推播裡。
        self.on_resolved = on_resolved
        # 成交窗口收完要交給誰記下來。同理：不寫回去就只活在記憶體裡。
        self.on_fill = on_fill
        # 13:25 還沒結束（可能留倉）的那一筆，當下的樣子交給誰記下來。
        self.on_carry = on_carry
        # v10「先出一半」那一刻交給誰記下來。
        self.on_half = on_half

    def _handed_off(self, o: "OpenSignal", price: float, verdict: str) -> None:
        if not self.on_resolved:
            return
        try:
            self.on_resolved(o, price, verdict)
        except Exception as e:      # 記錄失敗不可以讓推播跟著沒了
            log.warning("即時判定寫回失敗（%s）：%s", o.code, e)

    def _fill_handed_off(self, p: "FillProbe") -> None:
        if not self.on_fill:
            return
        try:
            self.on_fill(p)
        except Exception as e:      # 同理：記錄失敗不可以影響盤中
            log.warning("成交窗口寫回失敗（%s）：%s", p.code, e)

    def track(self, sig: dict, now: datetime | None = None,
              carried: bool = False) -> None:
        now = now or datetime.now()
        probe = None
        fired = parse_fired_at(sig.get("time", ""), now)
        # 盤中重開時還原舊訊號：窗口早就過了，這時候收到的報價和「當時買不買得到」
        # 無關，記下去會是個假數字。寧可空白 —— 空白代表不知道，0 代表買得到。
        # 昨天留倉的那一筆，「今天的 09:05」跟它的成交窗口毫無關係。
        if not carried and fired is not None and now - fired < FILL_WINDOW:
            probe = FillProbe(code=str(sig["code"]), time=str(sig.get("time", "")),
                              entry=float(sig["entry"]), fired=fired)
        pos = None
        if exits.uses_v10(sig) and not carried and sig.get("half_at"):
            pos = exits.Position.from_signal(sig, fired or now)
            # 盤中重開：已經先出過一半的，照記錄還原（不然會再推一次「先出一半」）
            if sig.get("live_half") is not None:
                pos.half_done, pos.half_price = True, float(sig["live_half"])
                pos.peak = max(pos.peak, pos.half_price)
        with self._lock:
            self.open.append(OpenSignal(
                code=str(sig["code"]), name=str(sig.get("name", "")),
                time=str(sig.get("time", "")), entry=float(sig["entry"]),
                stop=float(sig["stop"]), target=float(sig["target"]),
                hold_days=int(sig.get("max_hold_days") or 1), carried=carried,
                lots=int(sig.get("lots") or 0), pos=pos))
            if probe is not None:
                self.fills.append(probe)

    def on_price(self, code: str, price: float, now: datetime | None = None,
                 vwap: float | None = None, total_volume: float | None = None) -> list[str]:
        """回傳這個報價造成的推播訊息。絕大多數時候是空的。

        vwap / total_volume 是 v10 出場要的（跌破均價線、量縮）；沒給就不判那兩條。
        """
        if not price:
            return []
        now = now or datetime.now()
        done, halves = [], []
        with self._lock:
            self.last_price[code] = price
            still_open = []
            for o in self.open:
                if o.code != code:
                    still_open.append(o)
                    continue
                if o.pos is not None:
                    ended = None
                    for ev in o.pos.step(now, price, price, price, vwap, total_volume):
                        if ev[0] == "half":
                            halves.append((o, ev[1]))
                        else:
                            ended = (o, ev[1], ev[2])
                    if ended:
                        done.append(ended)
                    else:
                        still_open.append(o)
                    continue
                verdict = o.verdict(price)
                if verdict:
                    done.append((o, verdict, None))
                else:
                    still_open.append(o)
            self.open = still_open
            # 成交窗口：這一檔的報價先記進去，再看有沒有哪一檔的窗口滿了。
            # 收窗要檢查**全部**探針、不只這一檔 —— 否則某檔突然沒成交，
            # 它的窗口就要等到 13:25 flatten 才寫得出去，中間程式掛掉就沒了。
            closed, waiting = [], []
            for p in self.fills:
                if p.code == code:
                    p.saw(price)
                (closed if p.closed(now) else waiting).append(p)
            self.fills = waiting
        msgs = []
        for o, half in halves:
            if self.on_half:
                try:
                    self.on_half(o, half)
                except Exception as e:      # 記錄失敗不可以讓推播跟著沒了
                    log.warning("先出一半寫回失敗（%s）：%s", o.code, e)
            msgs.append(format_half(o, price, half))
        for o, v, exit_price in done:
            self._handed_off(o, price if exit_price is None else exit_price, v)
            msgs.append(format_resolution(o, price, v, exit_price))
        for p in closed:
            self._fill_handed_off(p)
        return msgs

    def time_exit(self, now: datetime | None = None) -> list[str]:
        """09:30 的「時間到」訊號：報價、記下來，但**不結束追蹤**。

        使用者定的規則是「未達停損訊號，由下單者自由決定」—— 所以系統不替人
        平倉。同時這一刻的價位要存成 exit_0930，而這一筆繼續追到 13:25 存成
        exit_day。兩欄並存，20 天後才答得出「09:30 就走是不是比較好」；
        現在就把後半天砍掉，那個問題永遠沒有對照組。

        已經碰到停損或目標的不會在這裡出現 —— 它們早就離開 self.open 了。
        """
        now = now or datetime.now()
        at = now.strftime("%H:%M:%S")
        with self._lock:
            if self.time_exited:
                return []
            self.time_exited = True
            # 昨天留倉的不在這裡：09:30「時間到」是第一天的規則，
            # 留倉那一筆今天只看停損、目標、13:25。
            marks = [(o, self.last_price.get(o.code)) for o in self.open if not o.carried]
        msgs = []
        for o, price in marks:
            if price is None:
                # 整天沒收到報價 —— 空白代表不知道，不可以用 0 或進場價頂替。
                log.warning("%s 沒有報價，09:30 的時間出場價記不下來", o.code)
                continue
            if self.on_time_exit:
                try:
                    self.on_time_exit(o, price, at)
                except Exception as e:   # 記錄失敗不可以讓提醒跟著沒了
                    log.warning("時間出場寫回失敗（%s）：%s", o.code, e)
            msgs.append(format_time_exit(o, price, at))
        return msgs

    def flatten(self) -> list[str]:
        """13:25 還沒結束的：當沖的平倉；可以抱到隔天的（v6）留倉。

        昨天留倉過來的那一筆今天一律平倉 —— 規則是最多兩天，不會再留。
        留倉的那一筆**不寫**任何判定回 state.json：它還沒結束。隔天程式啟動時
        從昨天的 state.json 接手，收盤後 outcome.py 拿兩天的 K 棒回推。
        """
        with self._lock:
            rest, self.open = self.open, []
            probes, self.fills = self.fills, []
        # 窗口沒收完就收盤的（那一檔後來完全沒成交），有多少記多少。
        for p in probes:
            self._fill_handed_off(p)
        msgs = []
        for o in rest:
            price = self.last_price.get(o.code)
            if o.hold_days >= 2 and not o.carried:
                if self.on_carry:
                    try:
                        self.on_carry(o, price)
                    except Exception as e:      # 記錄失敗不可以讓通知跟著沒了
                        log.warning("13:25 紀錄寫回失敗（%s）：%s", o.code, e)
                msgs.append(format_carry(o, price))
                continue
            if price is None:
                log.warning("%s 整天沒收到報價，無法即時平倉（收盤後仍會由 "
                            "outcome.py 用分鐘 K 回推）", o.code)
                continue
            self._handed_off(o, price, outcome.FLAT)
            msgs.append(format_resolution(o, price, outcome.FLAT))
        return msgs


def notify(text: str):
    global _push_warned
    # 印出來的是終端機印得出的版本，送出去的是原文
    print("\n" + config.console_text(text) + "\n")
    if not config.push_enabled():
        return
    if requests is None:
        if not _push_warned:
            log.error("已設定 Telegram 金鑰但沒有安裝 requests，訊號只會印在畫面上、"
                      "不會推到手機。請執行 pip install -r requirements.txt。")
            _push_warned = True
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text}, timeout=5)
    except Exception as e:
        log.warning("推播失敗：%s", e)


# ══════════════════════════════════════════════════════
# 主程式
# ══════════════════════════════════════════════════════
def restore_signaled(states: dict, gate: RiskGate) -> int:
    """從 state.json 把「今天已經發過訊號」的檔數補回個股狀態。

    程式盤中重開時，gate 的 signals_sent 會從檔案讀回來，但每檔的 signaled
    是新物件、一律歸零 —— 於是已經發過的那檔可以再發一次，
    max_signals_per_symbol 這條「杜絕凹單」的規則就在重開的那一刻失效了。
    """
    restored = 0
    for sig in gate.state.get("signals", []):
        st = states.get(sig.get("code"))
        if st:
            st.signaled += 1
            restored += 1
    if restored:
        log.warning("自 state.json 還原今日已發訊號 %d 個：%s",
                    restored,
                    "、".join(f"{c}×{s.signaled}" for c, s in states.items() if s.signaled))
    return restored


# ── 留倉（v6）──────────────────────────────────────────
# 昨天的 state.json 在今天 RiskGate 第一次存檔時就會被今天的蓋掉。
# 所以要在建 RiskGate 之前先讀出來，把還沒結束的那幾筆搬進今天的
# state["carried"] —— 從那一刻起它們就跟著今天的 state.json 走，
# 盤中重開不會重搬，收盤後 review.py 也從同一個地方讀。
_LIVE_KEYS = ("live_result", "live_exit", "live_at", "live_date")


def load_previous_state(path=None) -> dict:
    """state.json 如果是**今天以前**的，原樣讀出來；否則回空 dict。"""
    path = pathlib.Path(path) if path else config.STATE_FILE
    if not path.exists():
        return {}
    try:
        s = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("讀不到之前的 state.json（留倉部位接不回來）：%s", e)
        return {}
    return s if str(s.get("date", "")) < datetime.now().strftime("%Y-%m-%d") else {}


def carry_over(prev: dict, broker, today: str) -> tuple[list[dict], list[str]]:
    """從前一個交易日的 state 找出今天要接著盯的部位。回傳 (留倉清單, 說明)。

    留倉的條件：
      1. 那一筆照當時的規則可以抱兩天（訊號上的 max_hold_days）。
      2. 盤中 tick 沒有判定它停損或到目標。
      3. 拿那一天的分鐘 K 再確認一次也沒結束 —— tick 可能沒收到（程式那天中途
         掛掉），只信 tick 的話，一筆早就停損的部位今天會被當成還在、還推播。
      4. 中間沒有隔著別的交易日。昨天沒開程式、今天才開 —— 那一筆的「隔天」
         已經過去了，今天盯它沒有意義（結局由 review.py 用 K 棒回推）。

    分鐘 K 拿不到時**照樣接**：寧可多盯一筆（多一則推播），不要漏掉一筆真的
    還在的部位。說明裡會講。
    """
    notes: list[str] = []
    if not prev or str(prev.get("date", "")) >= today:
        return [], notes
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    # 要看的有兩種：
    #   - 前一份 state 那天發的訊號（day1 = 那一天）
    #   - 前一份 state 裡**接手中、還沒結束**的留倉（day1 = 它真正發訊號那天）
    # 第二種是平日休市造成的：10-09（國慶補假）電腦照排程開了監看，state.json
    # 變成 10-09、10-08 的留倉搬進了 10-09 的 carried，但那天根本沒開盤。只看
    # signals 的話，週一就找不到它 —— 那一筆會無聲消失，結局永遠不進 outcomes.csv。
    pending = [(sig, str(prev["date"])) for sig in prev.get("signals", [])
               if int(sig.get("max_hold_days") or 1) >= 2
               and sig.get("live_result") not in (outcome.STOP, outcome.TARGET)]
    pending += [(c, str(c["carry_from"])) for c in prev.get("carried", [])
                if c.get("carry_from") and not c.get("live_result")]
    out = []
    for sig, day1 in pending:
        code = str(sig.get("code"))
        try:
            o = outcome.resolve(broker, sig, day1)
        except Exception as e:
            log.warning("%s 留倉確認失敗：%s", code, e)
            o = None
        if o is not None and o.result != outcome.CARRY:
            when = f" {o.exit_at[:5]}" if o.exit_at else ""
            notes.append(f"{code} {day1}{when} 就{o.result}了，今天不接")
            continue
        missed, _ = outcome.next_session_bars(broker, code, day1, yesterday)
        if missed:
            notes.append(f"{code} 是 {day1} 的訊號，{missed} 就該結束了（那天沒開監看），"
                         "今天不接；結局由 review.py 回推")
            continue
        if o is None:
            notes.append(f"{code} 拿不到 {day1} 的分鐘 K 確認，照樣接著盯")
        c = {k: v for k, v in sig.items() if k not in _LIVE_KEYS}
        c["carry_from"] = day1
        c["day1_close"] = (o.exit_price if o is not None
                           else sig.get("day1_close"))
        out.append(c)
    return out, notes


def format_carry_start(carried: list[dict], notes: list[str]) -> str:
    """開盤前告訴使用者：昨天留下來的，今天繼續盯。

    一檔都沒接（只有說明）時不要印「還沒結束的 0 檔，今天接著追蹤」跟停損／目標
    的說明 —— 10-08 界霖 13:25 推了「還沒結束」，收盤集合競價就碰停損了，隔個
    交易日早上只該講「那一筆已經結束、不接」。
    """
    if not carried:
        return "\n".join(["📦 昨日 13:25 還沒結束的部位：今天沒有要接的", "────────────────"]
                         + [f"ℹ️ {n}" for n in notes])
    lines = [f"📦 昨日 13:25 還沒結束的 {len(carried)} 檔，今天接著追蹤", "────────────────"]
    for c in carried:
        label = f"{c['code']} {c.get('name') or ''}".strip()
        mark = (f"，昨收 {float(c['day1_close']):.2f}"
                if c.get("day1_close") is not None else "")
        lines.append(f"{label}：進場 {float(c['entry']):.2f}{mark}")
        lines.append(f"　停損 {float(c['stop']):.2f}／目標 {float(c['target']):.2f}")
    lines += ["────────────────",
              f"今天碰到停損或目標會通知你；{outcome.FLATTEN_AT:%H:%M} 還沒碰到就以那時的價格結算。",
              "這幾檔今天不會再發新的買入訊號（不加碼）。"]
    lines += [f"ℹ️ {n}" for n in notes]
    return "\n".join(lines)


def block_carried_codes(states: dict, carried: list[dict]) -> int:
    """留倉中的那幾檔，今天不再發新訊號 —— 手上已經有了，再發一次等於加碼。"""
    n = 0
    for c in carried:
        st = states.get(str(c.get("code")))
        if st is not None:
            st.signaled = max(st.signaled, config.SIGNAL["max_signals_per_symbol"])
            n += 1
    return n


def backfill_opening_ranges(broker: Broker, states: dict):
    """啟動時間已過 09:15 → 用分鐘 K 補算區間，否則今天一個訊號都不會發。"""
    cfg = config.SIGNAL
    ok, failed = 0, []
    for code, st in states.items():
        rng = broker.opening_range(code, cfg["or_start"], cfg["or_end"])
        if rng:
            st.lock_opening_range(rng[0], rng[1], source="分鐘K補算")
            ok += 1
        else:
            failed.append(code)
    msg = (f"⏰ 啟動時間已過 {cfg['or_end']}，以分鐘 K 補算開盤區間："
           f"成功 {ok} 檔")
    if failed:
        msg += f"／失敗 {len(failed)} 檔（{'、'.join(failed)}）：這幾檔今天不會發訊號"
    log.warning(msg)
    notify(msg)


FAILURE_DETAIL_CHARS = 400


def format_failure(exc: BaseException) -> str:
    """盤中監看掛掉，一定要出聲。

    這是三支程式裡最不能靜默的一支。screener 掛了你只是沒名單；review 掛了資料
    晚一天補。但 signals.py 在 10:30 死掉的話：**已經發出的訊號沒有人在追蹤**
    （到目標或到停損都不會再通知你），而且後面的訊號不會出現 —— 而畫面上看起來
    就只是「今天比較少訊號」。自動排程之後更嚴重，因為視窗可能是縮著的。
    """
    detail = f"{type(exc).__name__}: {exc}".strip()
    if len(detail) > FAILURE_DETAIL_CHARS:
        detail = detail[:FAILURE_DETAIL_CHARS] + "…（完整訊息在電腦上）"
    return "\n".join([
        f"\U0001f6a8 {datetime.now().strftime('%H:%M')} 盤中監看中斷",
        "────────────────",
        detail,
        "────────────────",
        "**已發出的訊號現在沒有人在追蹤了** —— 到目標或到停損都不會再通知你。",
        "手上有部位的話，改用看盤軟體自己盯著停損。",
        "到電腦上重新執行 signals.py 可以接回今天已發出的訊號。",
    ])


def push_failure(exc: BaseException) -> None:
    """推失敗通知。推播自己壞掉也不能蓋掉原始錯誤，所以整段包起來。"""
    try:
        notify(format_failure(exc))
    except Exception as e:
        log.error("連失敗通知都送不出去：%s", e)


def run():
    errs = config.validate()
    if errs:
        raise SystemExit("config.py 參數有問題，盤中不要硬上：\n" +
                         "\n".join(f"  - {e}" for e in errs))
    for w in config.warnings():
        log.warning("設定提醒：%s", w)

    # 休市日：推一行就結束，不碰 state.json（10-09 國慶補假照樣「✅ 今日監看
    # 10 檔」、09:30「今日訊號 0 個」—— 看起來像開盤了只是沒訊號）。
    closed = market_calendar.closed_today()
    if closed:
        log.info("今天休市（%s），不監看。", closed)
        notify(format_market_closed(closed))
        return

    if not config.WATCHLIST_FILE.exists():
        raise SystemExit(f"找不到 {config.WATCHLIST_FILE.name}，請先跑 screener.py")
    wl = json.loads(config.WATCHLIST_FILE.read_text(encoding="utf-8"))
    if wl["date"] != datetime.now().strftime("%Y-%m-%d"):
        raise SystemExit(f"watchlist 是 {wl['date']} 的，不是今天的，請先跑 screener.py")
    if not wl.get("items"):
        raise SystemExit("watchlist 是空的，今天沒有標的可監看。")

    broker = Broker()
    # 一定要在 RiskGate 之前：它一存檔，昨天的 state.json 就沒了。
    previous = load_previous_state()
    gate = RiskGate(broker)
    if gate.state["closed"]:
        raise SystemExit(f"今日風控閘門已關閉（{gate.state['closed_reason']}），不再啟動。")

    # watchlist 已依（量比, 振幅）排好序，名次就是它在清單裡的位置。
    # 記下來，20 天後才答得出「只做前 N 名會不會比較好」—— 不然那一題要重測。
    states = {}
    for n, i in enumerate(wl["items"], 1):
        st = SymbolState(i["code"], i["prev_close"], i.get("name", ""))
        st.rank = n
        # 近 5 日平均振幅；算不出來（量比沒查到的那幾檔）就用昨天一天的振幅。
        st.amplitude_pct = i.get("avg_amplitude_pct") or i.get("amplitude_pct")
        st.avg_volume_lots = i.get("avg_volume_lots")
        st.category = str(i.get("category", "") or "")
        states[i["code"]] = st
    restore_signaled(states, gate)

    # 留倉：今天第一次啟動才從昨天的 state 搬過來；盤中重開時 state 裡已經有了。
    carry_notes: list[str] = []
    if "carried" not in gate.state:
        gate.state["carried"], carry_notes = carry_over(
            previous, broker, datetime.now().strftime("%Y-%m-%d"))
        gate.save()
    carried = gate.state["carried"]
    block_carried_codes(states, carried)

    signal_lock = threading.Lock()
    def _remember(o, price, verdict):
        # 在同一把鎖裡寫 state.json：行情回呼是多執行緒的，
        # 跟 gate.record() 共用一把鎖才不會互相蓋掉。
        with signal_lock:
            gate.record_live_result(o.code, o.time, verdict, price)

    def _remember_fill(p: FillProbe):
        gate.record_fill(p.code, p.time, p.low)

    def _remember_time_exit(o, price, at):
        with signal_lock:
            gate.record_time_exit(o.code, o.time, price, at)

    def _remember_close(o, price):
        snap = close_snapshot(states.get(o.code), price)
        with signal_lock:
            gate.record_close_snapshot(o.code, o.time, snap)

    def _remember_half(o, price):
        with signal_lock:
            gate.record_live_half(o.code, o.time, price)

    tracker = LiveTracker(on_resolved=_remember, on_fill=_remember_fill,
                          on_time_exit=_remember_time_exit, on_carry=_remember_close,
                          on_half=_remember_half)
    def _emit(sig: dict, now: datetime, batch_total: int | None) -> bool:
        """過閘 → 記錄 → 開始追蹤 → 推播。被擋掉的進 candidates.csv。

        落選與被擋的照樣要留：被規則擋掉的樣本如果不留，20 天後
        「只發三個夠不夠」「第四名是不是本來會賺」就只能回答「再測一次」。
        """
        st = states.get(str(sig["code"]))
        if st is None:
            return False
        msg, blocked = try_emit(st, gate, signal_lock, sig, now, batch_total=batch_total)
        if blocked:
            record_candidate(sig, blocked)
            return False
        if not msg:
            return False
        tracker.track(sig)
        notify(msg)
        return True

    desk = EntryDesk(emit=_emit, blocked=record_candidate, say=notify,
                     watched=len(states), sent=len(gate.state.get("signals", [])),
                     reprice=lambda sig, now: reprice_at_send(
                         sig, states.get(str(sig["code"])), now))
    # 盤中重開時，今天已經發過的訊號也要繼續盯 —— 否則它們的結局只剩收盤後才知道。
    # 代價是已經結束的那幾筆會被重新追蹤，價格再次碰到時會重複推播一次。
    for past in gate.state.get("signals", []):
        if past.get("live_result"):
            continue        # 盤中已經判定完的，重開後不要再追一次把結果蓋掉
        tracker.track(past)
    for c in carried:
        if not c.get("live_result"):
            tracker.track(c, carried=True)
    if gate.state.get("signals"):
        log.warning("已還原 %d 個今日訊號繼續追蹤結局（重開前已結束的可能會再推一次）",
                    len(gate.state["signals"]))

    quotes = {"n": 0}

    @broker.api.on_tick_stk_v1()
    def on_tick(exchange, tick):
        if getattr(tick, "simtrade", 0):
            # 試撮不是成交：只記方向，不進區間、均價、量能，也不判出場。
            st = states.get(tick.code)
            if st:
                st.record_simtrade(tick)
            return
        quotes["n"] += 1            # 真的成交（不是試撮）—— 09:03 的開盤確認看這個
        st = states.get(tick.code)
        if not st:
            # 不在今天名單裡、但昨天留倉的那幾檔：只看停損目標，不算訊號。
            if tick.code in carried_codes:
                for done in tracker.on_price(tick.code, float(tick.close)):
                    notify(done)
            return
        st.update(tick)
        # 先看已發出的訊號有沒有走完，再看要不要發新的
        for done in tracker.on_price(st.code, st.last_price, vwap=st.vwap,
                                     total_volume=st.total_volume):
            notify(done)
        # ignore_symbol_cap：連「這檔今天發過了」的那種也要算出來並記錄，
        # 否則「被洗掉後能不能重新進場」這一題永遠沒有資料可以回答。
        sig = evaluate(st, ignore_symbol_cap=True)
        if sig:
            desk.offer(sig)         # 09:05 前收集；之後一出現就發
        elif desk.closed:
            # 09:30 之後的突破只記錄、不發 —— 20 天後回答「截止是不是太早」。
            record_late_breakout(st, datetime.now())
        else:
            # 只差量能的突破只記錄、不發 —— 20 天後回答「1.8 倍是不是太嚴」。
            record_weak_volume(st, datetime.now())
        # 到點就送。從回呼觸發是因為 09:05 的報價很密，幾乎必然在一秒內進來；
        # 下面的主迴圈是備援，萬一整批都沒報價也不會卡著不發。
        desk.tick()

    carried_codes = {str(c["code"]) for c in carried} - set(states)
    import shioaji as sj  # 只有真的要訂閱行情時才需要
    for code in list(states) + sorted(carried_codes):
        broker.api.quote.subscribe(
            broker.stock(code),
            quote_type=sj.constant.QuoteType.Tick,
            version=sj.constant.QuoteVersion.v1,
        )
    log.info("已訂閱 %d 檔，開始監看。Ctrl+C 結束。", len(states))
    notify(f"✅ 今日監看 {len(states)} 檔：{'、'.join(states)}\n"
           f"紅線：最多 {config.RISK['max_signals_per_day']} 訊號／"
           f"{config.RISK['max_trades_per_day']} 筆／虧損上限 "
           f"{config.RISK['max_daily_loss']:,} 元")
    if carried or carry_notes:
        notify(format_carry_start(carried, carry_notes))
    nxt_year = str(datetime.now().year + 1)
    if datetime.now().month == 12 and not market_calendar.year_is_known(nxt_year + "-01-01"):
        notify(f"⚠️ {nxt_year} 年的休市表還沒填（market_calendar.py）。"
               "證交所公告後補進去，不然國定假日只能靠 09:03 的保險判斷。")

    if (config.SIGNAL["backfill_opening_range"]
            and datetime.now().time() >= _t(config.SIGNAL["or_end"])):
        backfill_opening_ranges(broker, states)

    # 補算完區間也救不了「批次窗口已經過了」。這一則一定要推，不能只寫進 log：
    # log 在那個被導向檔案的黑視窗裡，沒有人會在早上九點去翻。
    warn_if_too_late()

    close_at = _t(config.SIGNAL["market_close"])
    # None = 不發「時間到」提醒（v7 起）。
    exit_at = (_t(config.SIGNAL["exit_signal_at"])
               if config.SIGNAL.get("exit_signal_at") else None)
    poll_every = config.RISK["poll_interval_sec"]
    last_poll = time.monotonic()
    flattened = False
    market_checked = False
    try:
        while datetime.now().time() < close_at:
            time.sleep(30)
            broker.ensure_session()
            # 表上沒有的休市日：09:03 還沒有任何成交 → 看 0050 今天有沒有 K 棒。
            if not market_checked and datetime.now().time() >= MARKET_CHECK_AT:
                market_checked = True
                if not quotes["n"]:
                    is_open = check_market_open(broker)
                    if is_open is False:
                        reason = "09:03 沒有任何成交，0050 今天也沒有 K 棒"
                        notify(format_market_closed(reason))
                        gate.state["market_closed"] = reason
                        break
                    notify(format_no_quotes())
            # 批次發訊號與 🔒 收窗的備援。正常情況回呼早就做了，這裡是為了
            # 「那一刻剛好沒有報價進來」的日子 —— 不然訊號會卡在記憶體裡，
            # 09:30 的 🔒 也不會發。
            desk.tick()
            # 「時間到」提醒（有設才發）。這裡**不平倉**，只提醒並記下價位。
            if exit_at is not None and datetime.now().time() >= exit_at:
                for msg in tracker.time_exit():
                    notify(msg)
            # 13:25 還沒走完停損或目標的，一律平倉並告知結果。
            # 與 outcome.py 的收盤回推用同一個時間，兩邊才比得起來。
            if not flattened and datetime.now().time() >= outcome.FLATTEN_AT:
                flattened = True
                for msg in tracker.flatten():
                    notify(msg)
            # 主動輪詢風控。只在訊號觸發時才檢查的話，虧損上限的「停手」通知
            # 會等到下一個訊號才發 —— 而那可能是收盤前，早就來不及了。
            # 但每 30 秒查一次帳務會撞到 Shioaji 流量上限，所以自己節流。
            if not gate.state["closed"] and time.monotonic() - last_poll >= poll_every:
                last_poll = time.monotonic()
                # 跟發訊號走同一把鎖：check() 可能會 _close() 改寫 state，
                # 與 try_emit 的「過閘 → 記錄」撞在一起會寫壞同一份 state。
                with signal_lock:
                    gate.check()
    except KeyboardInterrupt:
        pass
    finally:
        gate.save()
        log.info("收盤。請執行 review.py 產出今日覆盤。")


def main():
    try:
        run()
    except SystemExit:
        # 「今天沒名單」「閘門已關」這類是正常的停止，不是故障，不推播。
        raise
    except Exception as exc:
        push_failure(exc)
        raise


if __name__ == "__main__":
    main()
