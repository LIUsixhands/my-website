"""
signals.py — 盤中訊號引擎。09:00 啟動，13:30 自動收工。

規則是寫死的，盤中不接受任何參數修改。它只做三件事：
  1. 算開盤區間（09:00–09:15 的高低點）
  2. 突破 + 量增 + 站上均價線 → 推播一個「決策錨點」給你
  3. 風控閘門關閉時，不管盤面多漂亮，一律不發

它不會幫你下單。下單是你的手，責任也是你的。
"""
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dtime

import config
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
        """
        n = 0
        for pnl in reversed(rows):
            if pnl < 0:
                n += 1
            else:
                break
        return n

    def check(self) -> bool:
        """回傳 True 表示可以發訊號。"""
        if self.state["closed"]:
            return False

        r = config.RISK
        if self.state["signals_sent"] >= r["max_signals_per_day"]:
            self._close(f"已達當日訊號上限 {r['max_signals_per_day']} 個")
            return False

        trades = self.broker.trades_today()
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

        rows = self.broker.realized_pnl_rows_today()
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


# ══════════════════════════════════════════════════════
# 個股盤中狀態
# ══════════════════════════════════════════════════════
@dataclass
class SymbolState:
    code: str
    prev_close: float
    or_high: float = 0.0
    or_low: float = 0.0
    or_locked: bool = False
    last_price: float = 0.0
    vwap: float = 0.0
    total_volume: int = 0
    vol_marks: list = field(default_factory=list)   # (ts, total_volume) 用來算量能速率
    signaled: int = 0
    vwap_warned: bool = False

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
def evaluate(st: SymbolState, now: dtime | None = None) -> dict | None:
    cfg = config.SIGNAL
    now = now or datetime.now().time()

    if not st.or_locked or st.signaled >= cfg["max_signals_per_symbol"]:
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
    # 停損往上進位（較緊的那一邊）：實際風險不會超過 stop_loss_pct 設定的上限。
    stop = config.round_to_tick(entry * (1 - cfg["stop_loss_pct"] / 100), "up")
    if stop >= entry:
        # 低價股在極小的 stop_loss_pct 下會進位到進場價，這種訊號沒有可執行的停損。
        log.warning("%s 停損進位後等於進場價（%.2f），不發訊號", st.code, entry)
        return None
    # 目標同樣往上進位：真的到價時，R 倍數不會低於設定值。
    target = config.round_to_tick(entry + (entry - stop) * cfg["reward_risk"], "up")

    risk_per_lot = (entry - stop) * 1000          # 一張 1000 股
    lots = int(config.RISK["per_trade_risk"] // risk_per_lot) if risk_per_lot > 0 else 0
    # 連一張都超過單筆風險上限時，張數不能報 0（那不是可執行的指示），
    # 但必須標記出來，否則你會照著它做一筆風險超標的交易而不知道。
    oversized = lots < 1
    lots = max(1, lots)

    return {
        "time": datetime.now().strftime("%H:%M:%S"),
        "code": st.code,
        "direction": "做多",
        "entry": entry,
        "stop": stop,
        "target": target,
        "lots": lots,
        "risk_per_lot": round(risk_per_lot),
        "oversized": oversized,
        "or_high": st.or_high,
        "vwap": round(st.vwap, 2),
        "volume_surge": round(surge, 2),
    }


def format_signal(sig: dict, ordinal: int) -> str:
    """ordinal = 這是今日第幾個訊號（1 起算）。"""
    r = config.RISK
    lines = [
        f"📌 {sig['code']} 決策錨點｜{sig['time']}",
        "────────────────",
        f"方向：{sig['direction']}（開盤區間突破）",
        f"進場：{sig['entry']:.2f}（區間高 {sig['or_high']:.2f}，均價 {sig['vwap']:.2f}）",
        f"停損：{sig['stop']:.2f}  ← 跌破就走，不准往下修",
        f"目標：{sig['target']:.2f}（{config.SIGNAL['reward_risk']}R）",
        f"建議張數：{sig['lots']} 張（單筆風險 {r['per_trade_risk']:,} 元）",
        f"量能倍數：{sig['volume_surge']:.2f}x",
    ]
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


def try_emit(st: SymbolState, gate: RiskGate, lock, sig: dict) -> str | None:
    """在鎖內完成「再確認 → 過閘 → 記錄」，回傳要推播的訊息（或 None）。

    行情回呼跑在背景執行緒上，多檔可能同時觸發。這幾步不是原子的話，
    兩檔會雙雙通過 check() 再各自寫進 state.json —— 當日訊號上限就被繞過去了。
    推播留在鎖外：網路請求不該卡住其他檔的行情處理。
    """
    with lock:
        # 鎖內再確認一次：可能有另一條執行緒剛剛替這檔發過。
        if st.signaled >= config.SIGNAL["max_signals_per_symbol"]:
            return None
        if not gate.check():
            return None
        st.signaled += 1
        ordinal = gate.record(sig)
    return format_signal(sig, ordinal)


def notify(text: str):
    global _push_warned
    # 印出來的是終端機印得出的版本，送出去的是原文
    print("\n" + config.console_text(text) + "\n")
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
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


def main():
    errs = config.validate()
    if errs:
        raise SystemExit("config.py 參數有問題，盤中不要硬上：\n" +
                         "\n".join(f"  - {e}" for e in errs))

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

    states = {i["code"]: SymbolState(i["code"], i["prev_close"]) for i in wl["items"]}
    restore_signaled(states, gate)

    signal_lock = threading.Lock()

    @broker.api.on_tick_stk_v1()
    def on_tick(exchange, tick):
        st = states.get(tick.code)
        if not st or getattr(tick, "simtrade", 0):
            return
        st.update(tick)
        sig = evaluate(st)
        if not sig:
            return
        msg = try_emit(st, gate, signal_lock, sig)
        if msg:
            notify(msg)

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
    poll_every = config.RISK["poll_interval_sec"]
    last_poll = time.monotonic()
    try:
        while datetime.now().time() < close_at:
            time.sleep(30)
            broker.ensure_session()
            # 主動輪詢風控。只在訊號觸發時才檢查的話，虧損上限的「停手」通知
            # 會等到下一個訊號才發 —— 而那可能是收盤前，早就來不及了。
            # 但每 30 秒查一次帳務會撞到 Shioaji 流量上限，所以自己節流。
            if not gate.state["closed"] and time.monotonic() - last_poll >= poll_every:
                last_poll = time.monotonic()
                gate.check()
    except KeyboardInterrupt:
        pass
    finally:
        gate.save()
        log.info("收盤。請執行 review.py 產出今日覆盤。")


if __name__ == "__main__":
    main()
