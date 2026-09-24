"""
outcome.py — 用分鐘 K 回推每個訊號的結局。

訊號發出後程式就不再追蹤那檔（一檔一天只發一次），所以「後來到底怎麼了」
從來沒有被記下來。驗證期跑 20 天、每天只存下「發了什麼訊號」，
最後會拿到一疊沒有結果的紀錄 —— 勝率、賺賠比、扣完成本的淨值，一個都算不出來。

這支程式補上那一段：收盤後回頭看分鐘 K，從發訊號的下一根開始往後走，
看停損與目標哪一個先被碰到。都沒碰到就以收盤平倉計（當沖不留倉）。

三個刻意選擇的保守假設，每一個都寧可低估這套系統：

1. **同一根 K 同時觸及停損與目標 → 判停損。** 分鐘 K 只有開高低收，
   看不出那一分鐘內哪個先到。往壞處算。
2. **成交價就是訊號上的進場價與出場價。** 真實交易有滑價，實際成績
   只會比這裡差，不會更好。
3. **平倉時間卡在 13:25**，不是 13:30 —— 尾盤集合競價那五分鐘不保證出得掉。
"""
import csv
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, time as dtime, timedelta

import config

log = logging.getLogger("outcome")

STOP = "停損"
TARGET = "目標"
FLAT = "收盤平倉"

# 當沖平倉的最後時點。13:25 之後進尾盤集合競價，不保證出得掉。
FLATTEN_AT = dtime(13, 25)

OUTCOME_FILE = config.BASE_DIR / "outcomes.csv"

# 一根分鐘 K 涵蓋的時間長度。用來排掉「包著訊號那一刻」的那一根。
BAR_SPAN = timedelta(minutes=1)
FIELDS = ("date", "code", "time", "entry", "stop", "target", "lots",
          "result", "exit_price", "r_multiple", "gross_pct", "net_pct", "bars",
          "or_high", "vwap", "volume_surge", "extension_pct", "vwap_gap_pct")


@dataclass
class Outcome:
    date: str
    code: str
    time: str
    entry: float
    stop: float
    target: float
    lots: int
    result: str
    exit_price: float
    r_multiple: float     # 以「進場到停損」為 1R
    gross_pct: float      # 未扣成本的報酬率
    net_pct: float        # 扣掉來回成本後
    bars: int             # 從進場到出場經過幾根分鐘 K
    # 以下是發訊號當下的現場條件。它們不影響任何判定，純粹是為了讓 20 天之後
    # 回答得了「什麼樣的訊號比較會成功」—— 沒留下來的話，那些問題就永遠問不了。
    or_high: float | None = None        # 開盤區間高點
    vwap: float | None = None           # 當時的均價線
    volume_surge: float | None = None   # 當時的量能倍數
    extension_pct: float | None = None  # 進場價比區間高點高出幾 %（追高的程度）
    vwap_gap_pct: float | None = None   # 進場價比均價線高出幾 %

    @property
    def is_win(self) -> bool:
        return self.net_pct > 0


def _num(value) -> float | None:
    """舊的訊號紀錄沒有這些欄位，缺了就留空，不要塞 0 冒充真實數字。"""
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _pct_above(price: float, base: float | None) -> float | None:
    """price 比 base 高出幾 %。base 缺或為 0 就沒有意義，回 None。"""
    if not base:
        return None
    return round((price - base) / base * 100, 3)


def _parse_signal_time(sig: dict, date: str) -> datetime | None:
    raw = str(sig.get("time", "")).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(raw, fmt).time()
            return datetime.combine(datetime.strptime(date, "%Y-%m-%d").date(), t)
        except ValueError:
            continue
    log.warning("訊號時間格式看不懂：%r", raw)
    return None


def bars_after(broker, code: str, date: str, after: datetime) -> list[tuple]:
    """回傳 (時間, 高, 低, 收) 的清單，只留**完全在訊號之後**、13:25 之前的 K 棒。

    K 棒的時間戳是該分鐘的**結束**時間（實機驗證過：09:00~09:01 那根標 09:01）。
    所以「label > 訊號時間」的第一根，涵蓋的是訊號發出**前**的那幾十秒。
    以前的版本留著那一根，還以為只是「略偏保守」——

    那是錯的，而且錯得剛好會毀掉這個策略的統計。突破訊號依定義發在股價剛越過
    開盤區間高點的那一刻，而停損就設在區間高點下方一點。那一根 K 棒裡，訊號
    發出前的每一筆成交都還在區間高點之下 —— 低點幾乎必然掃到停損。
    2026-09-24 五個訊號有四個被判成「第一根就停損」，實際上合晶當天從 119 一路
    走到目標 121.50 還收在 120.50。不是市場的事，是尺量錯了。

    所以只收「起點不早於訊號時間」的 K 棒，也就是 label >= 訊號時間 + 1 分鐘。
    代價是訊號後最多 60 秒內的價格看不到 —— 那段空白對停損和目標一視同仁，
    不偏向任何一邊；而且盤中的即時追蹤（signals.py 的 LiveTracker）看的是 tick，
    正好補上這一段。
    """
    from broker import _bar_time
    try:
        kb = broker.kbars(code, date, date)
    except Exception as e:
        log.warning("%s 分鐘 K 取得失敗：%s", code, e)
        return []
    ts = list(getattr(kb, "ts", []) or [])
    highs = list(getattr(kb, "High", []) or [])
    lows = list(getattr(kb, "Low", []) or [])
    closes = list(getattr(kb, "Close", []) or [])
    if not (len(ts) == len(highs) == len(lows) == len(closes)):
        log.warning("%s 分鐘 K 欄位長度不一致，跳過", code)
        return []

    # K 棒 label 是該分鐘的結束時間，所以 label 為 T 的那根涵蓋 (T-1分, T]。
    # 要「整根都在訊號之後」，就是 T - 1分 >= 訊號時間。
    first_ok = after + BAR_SPAN
    out = []
    for raw, h, l, c in zip(ts, highs, lows, closes):
        t = _bar_time(raw)
        if t is None or t < first_ok or t.time() > FLATTEN_AT:
            continue
        out.append((t, float(h), float(l), float(c)))
    out.sort(key=lambda r: r[0])
    return out


def resolve(broker, sig: dict, date: str | None = None) -> Outcome | None:
    """回推單一訊號的結局。拿不到 K 棒就回 None（不要猜）。"""
    date = date or datetime.now().strftime("%Y-%m-%d")
    fired = _parse_signal_time(sig, date)
    if fired is None:
        return None
    entry, stop, target = float(sig["entry"]), float(sig["stop"]), float(sig["target"])
    risk = entry - stop
    if risk <= 0:
        log.warning("%s 停損不在進場價之下，無法計算 R", sig.get("code"))
        return None

    bars = bars_after(broker, str(sig["code"]), date, fired)
    if not bars:
        return None

    result, exit_price, used = FLAT, bars[-1][3], len(bars)
    for i, (_, high, low, _close) in enumerate(bars, 1):
        hit_stop, hit_target = low <= stop, high >= target
        if hit_stop:                      # 同時觸及也判停損：分鐘 K 看不出先後
            result, exit_price, used = STOP, stop, i
            break
        if hit_target:
            result, exit_price, used = TARGET, target, i
            break

    gross = (exit_price - entry) / entry * 100
    or_high, vwap = _num(sig.get("or_high")), _num(sig.get("vwap"))
    return Outcome(
        date=date, code=str(sig["code"]), time=str(sig.get("time", "")),
        entry=entry, stop=stop, target=target, lots=int(sig.get("lots", 0) or 0),
        result=result, exit_price=round(exit_price, 2),
        r_multiple=round((exit_price - entry) / risk, 2),
        gross_pct=round(gross, 3),
        net_pct=round(gross - config.round_trip_cost_pct(), 3),
        bars=used,
        or_high=or_high, vwap=vwap,
        volume_surge=_num(sig.get("volume_surge")),
        extension_pct=_pct_above(entry, or_high),
        vwap_gap_pct=_pct_above(entry, vwap),
    )


def resolve_all(broker, sigs: list[dict], date: str | None = None) -> list[Outcome]:
    out = []
    for s in sigs:
        try:
            o = resolve(broker, s, date)
        except Exception as e:                       # 一檔壞掉不該讓整份覆盤產不出來
            log.warning("%s 回推失敗：%s", s.get("code"), e)
            o = None
        if o:
            out.append(o)
    return out


def append_csv(outcomes: list[Outcome], path=None) -> None:
    """累積到 outcomes.csv —— 20 天之後的統計靠這一份，不靠解析 Markdown。

    同一天重跑會先把當天的舊列刪掉，避免 review.py 跑兩次就重複計算。
    """
    if not outcomes:
        return
    path = path or OUTCOME_FILE
    dates = {o.date for o in outcomes}
    kept = []
    if path.exists():
        # utf-8-sig 讀得了有 BOM 與沒有 BOM 的檔，所以舊檔照樣接得下去
        with open(path, newline="", encoding="utf-8-sig") as f:
            kept = [r for r in csv.DictReader(f) if r.get("date") not in dates]
    # 寫成帶 BOM 的 UTF-8：台灣的 Excel 預設用 cp950 開 csv，沒有 BOM 的話
    # 「停損」「目標」會變成一串亂碼。這份檔是要給人看的，不是只給程式讀的。
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in kept:
            w.writerow({k: r.get(k, "") for k in FIELDS})
        for o in outcomes:
            w.writerow(asdict(o))


def summarise(outcomes: list[Outcome]) -> dict:
    """勝率與賺賠比。淨值一律以扣掉來回成本後計算。"""
    n = len(outcomes)
    if not n:
        return {"n": 0}
    wins = [o for o in outcomes if o.is_win]
    losses = [o for o in outcomes if not o.is_win]
    avg = lambda xs: sum(xs) / len(xs) if xs else 0.0
    avg_win = avg([o.net_pct for o in wins])
    avg_loss = avg([o.net_pct for o in losses])
    return {
        "n": n,
        "wins": len(wins),
        "win_rate": round(len(wins) / n * 100, 1),
        "avg_win_pct": round(avg_win, 3),
        "avg_loss_pct": round(avg_loss, 3),
        "payoff": round(avg_win / abs(avg_loss), 2) if avg_loss else None,
        "total_net_pct": round(sum(o.net_pct for o in outcomes), 3),
        "avg_r": round(avg([o.r_multiple for o in outcomes]), 2),
        "by_result": {r: sum(1 for o in outcomes if o.result == r)
                      for r in (TARGET, STOP, FLAT)},
    }
