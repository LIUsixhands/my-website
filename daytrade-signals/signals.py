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

RECENT_WINDOW_SEC = 300      # 「近期」量能取樣長度
MIN_RECENT_SPAN_SEC = 60     # 近期樣本至少要橫跨這麼久才算得出速率
MIN_OLDER_SPAN_SEC = 240     # 基準樣本至少要橫跨這麼久，否則基準不可信
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
        for sig in self.state.get("signals", []):
            if str(sig.get("code")) == str(code) and str(sig.get("time")) == str(time_str):
                sig["live_result"] = result
                sig["live_exit"] = round(float(exit_price), 2)
                sig["live_at"] = datetime.now().strftime("%H:%M:%S")
                self.save()
                return True
        log.warning("即時判定找不到對應訊號（%s %s），沒寫回 state.json", code, time_str)
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
        now = time.time() if now is None else now
        self.vol_marks.append((now, self.total_volume))
        self.vol_marks = [(t, v) for t, v in self.vol_marks
                          if now - t <= VOL_MARK_KEEP_SEC]

        ts = tick.datetime.time() if hasattr(tick.datetime, "time") else datetime.now().time()
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
        recent = [(t, v) for t, v in self.vol_marks if now - t <= RECENT_WINDOW_SEC]
        older = [(t, v) for t, v in self.vol_marks if now - t > RECENT_WINDOW_SEC]
        if len(recent) < 2 or len(older) < 2:
            return 0.0

        recent_span = recent[-1][0] - recent[0][0]
        older_span = older[-1][0] - older[0][0]
        if recent_span < MIN_RECENT_SPAN_SEC or older_span < MIN_OLDER_SPAN_SEC:
            return 0.0

        recent_rate = (recent[-1][1] - recent[0][1]) / recent_span
        older_rate = (older[-1][1] - older[0][1]) / older_span
        if older_rate <= 0:
            return 0.0
        return recent_rate / older_rate


# ══════════════════════════════════════════════════════
# 訊號判斷
# ══════════════════════════════════════════════════════
def evaluate(st: SymbolState, now: dtime | None = None, *,
             ignore_symbol_cap: bool = False) -> dict | None:
    """ignore_symbol_cap=True 時照樣算出訊號內容，不管「一檔一天只發一次」。

    這是給候選紀錄用的：被上限擋掉的那些訊號本身是合格的，只是不推播。
    不把它們算出來，20 天後就回答不了「上限該不該放寬」。
    """
    cfg = config.SIGNAL
    now = now or datetime.now().time()

    if not st.or_locked:
        return None
    if not ignore_symbol_cap and st.signaled >= cfg["max_signals_per_symbol"]:
        return None
    if now >= _t(cfg["entry_window_end"]):
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
    if surge < cfg["volume_surge_ratio"]:
        return None

    entry = st.last_price
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
    # 目標同樣往上進位：真的到價時，R 倍數不會低於設定值。
    target = config.round_to_tick(entry + (entry - stop) * cfg["reward_risk"], "up")
    # 但目標不可以超過漲停價。2026-09-24 的嘉晶就是這樣：昨收 145.5、漲停 160.0，
    # 而我們發了一個 161.00 的目標 —— 那一筆被判成「收盤平倉」，不是因為它沒走到，
    # 是因為那個價位當天不存在。貼齊漲停，並在訊號上講明賺賠比因此縮水。
    target_capped = bool(cap and target > cap)
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
        "time": datetime.now().strftime("%H:%M:%S"),
        "code": st.code,
        "name": st.name,
        "direction": "做多",
        "entry": entry,
        "stop": stop,
        "target": target,
        "lots": lots,
        "risk_per_lot": round(risk_per_lot),
        "oversized": oversized,
        "target_capped": target_capped,
        "or_high": st.or_high,
        # 進場價比突破點高出幾 % —— 追高的程度。以前只進 outcomes.csv，
        # 但看訊號的那一刻才是需要它的時候。
        "extension_pct": (round((entry - st.or_high) / st.or_high * 100, 2)
                          if st.or_high else None),
        "stop_rule": stop_rule,
        "vwap": round(st.vwap, 2),
        "volume_surge": round(surge, 2),
        "rank": st.rank,
        "category": st.category,
        "ruleset": config.RULESET,
    }


def format_signal(sig: dict, ordinal: int) -> str:
    """ordinal = 這是今日第幾個訊號（1 起算）。"""
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
        (f"目標：{sig['target']:.2f}（貼齊漲停，"
         f"實際 {(sig['target'] - sig['entry']) / (sig['entry'] - sig['stop']):.2f}R）"
         if sig.get("target_capped") else
         f"目標：{sig['target']:.2f}（{config.SIGNAL['reward_risk']}R）"),
        f"建議張數：{sig['lots']} 張（單筆風險 {r['per_trade_risk']:,} 元）",
        f"量能倍數：{sig['volume_surge']:.2f}x",
    ]
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
        f"今日第 {ordinal}/{r['max_signals_per_day']} 個訊號",
        "⚠️ 這是規則觸發，不是預測。你有權不做；但做了就照停損走。",
    ]
    return "\n".join(lines)


_push_warned = False

# ── 被擋掉的候選 ───────────────────────────────────────
# 訊號上限與「一檔一天一次」擋掉的訊號，以前是 return None 直接丟掉。
# 那兩條規則到底訂得對不對，20 天後只能靠這份紀錄回答 —— 沒有紀錄就只能再測一次。
# 這裡只寫檔，不推播、不計入風控、不進 outcomes.csv，策略行為完全沒變。
CANDIDATE_FILE = config.BASE_DIR / "candidates.csv"
CANDIDATE_FIELDS = ("date", "code", "name", "time", "entry", "stop", "target",
                    "lots", "reason", "or_high", "vwap", "volume_surge", "rank")
# 同一檔的候選之間至少隔這麼久。不設的話突破後每個 tick 都會記一筆，
# 記到的是同一次突破的雜訊，不是「另一次進場機會」。
CANDIDATE_COOLDOWN = timedelta(minutes=5)
MAX_CANDIDATES_PER_SYMBOL = 3

BLOCK_DAILY_CAP = "daily_cap"        # 今日訊號額度用完
BLOCK_SYMBOL_CAP = "symbol_cap"      # 這檔今天已經發過了


def record_candidate(sig: dict, reason: str, path=None) -> None:
    """把被擋掉的候選附加到 candidates.csv。寫檔失敗不可以影響盤中監看。"""
    path = pathlib.Path(path) if path else CANDIDATE_FILE
    row = {k: sig.get(k, "") for k in CANDIDATE_FIELDS}
    row["date"] = datetime.now().strftime("%Y-%m-%d")
    row["reason"] = reason
    try:
        new_file = not path.exists()
        with open(path, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=CANDIDATE_FIELDS)
            if new_file:
                w.writeheader()
            w.writerow(row)
    except Exception as e:
        log.warning("候選寫檔失敗（不影響監看）：%s", e)


BLOCK_BATCH_RANK = "批次排序未入選"


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
             now: datetime | None = None) -> tuple[str | None, str | None]:
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
    return format_signal(sig, ordinal), None


# ══════════════════════════════════════════════════════
# 訊號發出之後 —— 盯到結局為止
# ══════════════════════════════════════════════════════
RESOLUTION_MARK = {
    outcome.TARGET: "\u2705",        # ✅
    outcome.STOP: "\U0001f6d1",      # 🛑
    outcome.FLAT: "\u23f9",          # ⏹
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

    def verdict(self, price: float) -> str:
        """這個價位讓這筆結束了嗎。停損先判：往壞處算。"""
        if price <= self.stop:
            return outcome.STOP
        if price >= self.target:
            return outcome.TARGET
        return ""


def format_resolution(o: OpenSignal, price: float, verdict: str) -> str:
    """出場價一律取停損／目標那個價位，不取觸發當下的報價。

    理由是要和 outcome.py 的收盤回推對得起來 —— 兩邊算出不同的數字，就沒辦法
    拿其中一邊去驗另一邊。跳空穿過去的部分另外寫在訊息裡，不混進報酬率。
    """
    exit_price = {outcome.TARGET: o.target, outcome.STOP: o.stop}.get(verdict, price)
    gross = (exit_price - o.entry) / o.entry * 100
    net = gross - config.round_trip_cost_pct()
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
    if abs(price - exit_price) >= 0.01:
        lines.append(f"觸發時報價 {price:.2f}（穿過去的部分不計入上面的報酬率）")
    lines += [
        f"訊號發出於 {o.time}",
        "────────────────",
        "驗證期不下單。這是照規則做會有的結果，不是你的實際損益。",
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

    def __init__(self, on_resolved=None, on_fill=None, on_time_exit=None):
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

    def track(self, sig: dict, now: datetime | None = None) -> None:
        now = now or datetime.now()
        probe = None
        fired = parse_fired_at(sig.get("time", ""), now)
        # 盤中重開時還原舊訊號：窗口早就過了，這時候收到的報價和「當時買不買得到」
        # 無關，記下去會是個假數字。寧可空白 —— 空白代表不知道，0 代表買得到。
        if fired is not None and now - fired < FILL_WINDOW:
            probe = FillProbe(code=str(sig["code"]), time=str(sig.get("time", "")),
                              entry=float(sig["entry"]), fired=fired)
        with self._lock:
            self.open.append(OpenSignal(
                code=str(sig["code"]), name=str(sig.get("name", "")),
                time=str(sig.get("time", "")), entry=float(sig["entry"]),
                stop=float(sig["stop"]), target=float(sig["target"])))
            if probe is not None:
                self.fills.append(probe)

    def on_price(self, code: str, price: float, now: datetime | None = None) -> list[str]:
        """回傳這個報價造成的推播訊息。絕大多數時候是空的。"""
        if not price:
            return []
        now = now or datetime.now()
        done = []
        with self._lock:
            self.last_price[code] = price
            still_open = []
            for o in self.open:
                verdict = o.verdict(price) if o.code == code else ""
                if verdict:
                    done.append((o, verdict))
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
        for o, v in done:
            self._handed_off(o, price, v)
        for p in closed:
            self._fill_handed_off(p)
        return [format_resolution(o, price, v) for o, v in done]

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
            marks = [(o, self.last_price.get(o.code)) for o in self.open]
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
        """13:25 還沒結束的，一律以最後看到的報價平倉。"""
        with self._lock:
            rest, self.open = self.open, []
            probes, self.fills = self.fills, []
        # 窗口沒收完就收盤的（那一檔後來完全沒成交），有多少記多少。
        for p in probes:
            self._fill_handed_off(p)
        msgs = []
        for o in rest:
            price = self.last_price.get(o.code)
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

    if not config.WATCHLIST_FILE.exists():
        raise SystemExit(f"找不到 {config.WATCHLIST_FILE.name}，請先跑 screener.py")
    wl = json.loads(config.WATCHLIST_FILE.read_text(encoding="utf-8"))
    if wl["date"] != datetime.now().strftime("%Y-%m-%d"):
        raise SystemExit(f"watchlist 是 {wl['date']} 的，不是今天的，請先跑 screener.py")
    if not wl.get("items"):
        raise SystemExit("watchlist 是空的，今天沒有標的可監看。")

    broker = Broker()
    gate = RiskGate(broker)
    if gate.state["closed"]:
        raise SystemExit(f"今日風控閘門已關閉（{gate.state['closed_reason']}），不再啟動。")

    # watchlist 已依（量比, 振幅）排好序，名次就是它在清單裡的位置。
    # 記下來，20 天後才答得出「只做前 N 名會不會比較好」—— 不然那一題要重測。
    states = {}
    for n, i in enumerate(wl["items"], 1):
        st = SymbolState(i["code"], i["prev_close"], i.get("name", ""))
        st.rank = n
        st.category = str(i.get("category", "") or "")
        states[i["code"]] = st
    restore_signaled(states, gate)

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

    tracker = LiveTracker(on_resolved=_remember, on_fill=_remember_fill,
                          on_time_exit=_remember_time_exit)
    batch = SignalBatch(_t(config.SIGNAL["signal_batch_at"]),
                        config.RISK["max_signals_per_day"])

    def flush_batch(now: datetime | None = None) -> None:
        """09:05:00 到了就把收集到的突破排序、取前 N 檔發出去。

        落選的照樣寫進 candidates.csv：被規則擋掉的樣本如果不留，20 天後
        「只發三個夠不夠」「第四名是不是本來會賺」就只能回答「再測一次」。
        """
        now = now or datetime.now()
        if not batch.due(now):
            return
        chosen, rest = batch.take()
        for sig in rest:
            record_candidate(sig, BLOCK_BATCH_RANK)
        for sig in chosen:
            st = states.get(str(sig["code"]))
            if st is None:
                continue
            msg, blocked = try_emit(st, gate, signal_lock, sig, now)
            if blocked:
                record_candidate(sig, blocked)
                continue
            if msg:
                tracker.track(sig)
                notify(msg)
    # 盤中重開時，今天已經發過的訊號也要繼續盯 —— 否則它們的結局只剩收盤後才知道。
    # 代價是已經結束的那幾筆會被重新追蹤，價格再次碰到時會重複推播一次。
    for past in gate.state.get("signals", []):
        if past.get("live_result"):
            continue        # 盤中已經判定完的，重開後不要再追一次把結果蓋掉
        tracker.track(past)
    if gate.state.get("signals"):
        log.warning("已還原 %d 個今日訊號繼續追蹤結局（重開前已結束的可能會再推一次）",
                    len(gate.state["signals"]))

    @broker.api.on_tick_stk_v1()
    def on_tick(exchange, tick):
        st = states.get(tick.code)
        if not st or getattr(tick, "simtrade", 0):
            return
        st.update(tick)
        # 先看已發出的訊號有沒有走完，再看要不要發新的
        for done in tracker.on_price(st.code, st.last_price):
            notify(done)
        # ignore_symbol_cap：連「這檔今天發過了」的那種也要算出來並記錄，
        # 否則「被洗掉後能不能重新進場」這一題永遠沒有資料可以回答。
        sig = evaluate(st, ignore_symbol_cap=True)
        if sig:
            batch.add(sig)          # 先收集，不發 —— 09:05 排序完才一次送出
        # 到點就送。從回呼觸發是因為 09:05 的報價很密，幾乎必然在一秒內進來；
        # 下面的主迴圈是備援，萬一整批都沒報價也不會卡著不發。
        flush_batch()

    import shioaji as sj  # 只有真的要訂閱行情時才需要
    for code in states:
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

    if (config.SIGNAL["backfill_opening_range"]
            and datetime.now().time() >= _t(config.SIGNAL["or_end"])):
        backfill_opening_ranges(broker, states)

    close_at = _t(config.SIGNAL["market_close"])
    exit_at = _t(config.SIGNAL["exit_signal_at"])
    poll_every = config.RISK["poll_interval_sec"]
    last_poll = time.monotonic()
    flattened = False
    try:
        while datetime.now().time() < close_at:
            time.sleep(30)
            broker.ensure_session()
            # 批次發訊號的備援。正常情況回呼早就送出去了，這裡是為了
            # 「整批都沒有報價進來」那種日子 —— 不然訊號會卡在記憶體裡。
            flush_batch()
            # 09:30「時間到」。這裡**不平倉**，只提醒並記下價位，
            # 部位繼續追到 13:25（exit_day），走不走由使用者決定。
            if datetime.now().time() >= exit_at:
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
