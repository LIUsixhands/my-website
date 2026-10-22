# -*- coding: utf-8 -*-
"""pulsecheck.py —— 首選強弱分數能不能預測（whatif 的一張表）。

10-22 使用者：「中性 → 中性偏弱，這訊號是如何產生的，可以拿來預測嗎」→「怎麼改公式，
改了可以預測嗎」→ 選了先驗證。首選一天只有一檔，要等很久；所以拿候選池每一檔、每一根
5 分 K，照 pickpulse 同一套公式回頭打分，看「分數高低」跟「之後 30 分鐘漲跌」有沒有關係。

跟盤中的差別：
- ⑤ 外盤比算不出來（分鐘 K 沒有內外盤），平均是其他五項。
- 均價線用分鐘 K 的典型價估（跟 whynot 一樣），盤中是逐筆成交算的。
- 每一檔都當作 09:00 開盤價買進（跟首選一樣），從那一刻開始算量的 30 分鐘。

不改任何規則，只是量。
"""
from datetime import datetime, timedelta

import config
import outcome as oc
import pickpulse
import premarket
import whynot

HORIZON_MIN = 30                   # 看之後幾分鐘
LOW, HIGH = 3.5, 6.5               # 中性偏弱以下 ／ 稍強以上
KEYS = ("score", "vwap", "ma20", "ma_gap", "volume", "market")
NAMES = {"score": "平均（五項）", "vwap": "① 均價線", "ma20": "② 20MA",
         "ma_gap": "③ 5MA 比 20MA", "volume": "④ 量", "market": "⑥ 大盤"}
UP, DOWN, SAME = "轉強（名稱升一級以上）", "轉弱（名稱降一級以上）", "名稱沒變"


def _price_at(bars, at: datetime):
    seen = [b for b in bars if b[0] <= at]
    return seen[-1][4] if seen else None


def score_day(bars, seed=(), mbars=(), horizon: int = HORIZON_MIN) -> list[dict]:
    """一檔一天：每根 5 分 K 收完打一次分（照 pickpulse），加上之後 horizon 分鐘的漲跌 %。
    bars / seed / mbars = 今天、前一個交易日、今天 0050 的 1 分 K (t, 開, 高, 低, 收, 量)。"""
    today = [b for b in bars if b[0].time() <= oc.FLATTEN_AT]
    if not today:
        return []
    day = today[0][0].date()
    start = datetime.combine(day, premarket.ENTRY_AT)
    flat = datetime.combine(day, oc.FLATTEN_AT)
    closes = [c for _t, c in premarket_closes(seed)]
    samples = [(start, today[0][1], 0.0)]           # (時間, 價格, 累計量)：09:00 開盤價買進
    m_open = mbars[0][1] if mbars else None
    wn = whynot_bars(today)
    out = []
    for end, close in premarket_closes(today):
        closes.append(close)
        if end.time() >= pickpulse.END_AT:
            break
        upto = [b for b in today if b[0] <= end]
        price = upto[-1][4]
        vol = float(sum(b[5] for b in upto))
        ago = end - timedelta(minutes=pickpulse.WINDOW_MIN)
        base = next((s for s in reversed(samples) if s[0] <= ago), samples[0])
        minutes = max(1.0, (end - base[0]).total_seconds() / 60)
        since_open = max(1.0, (end - start).total_seconds() / 60)
        avg = vol / since_open * minutes if vol else 0
        ratio = round((vol - base[2]) / avg, 2) if avg else None
        move = price - base[1]
        m_now = _price_at(mbars, end) if m_open else None
        market = (m_now - m_open) / m_open * 100 if m_now else None
        items = pickpulse.score_items(price, whynot.vwap_upto(wn, end),
                                      premarket._ma(closes, premarket.MA_FAST),
                                      premarket._ma(closes, premarket.MA_SLOW),
                                      ratio, (move > 0) - (move < 0), None, market)
        samples.append((end, price, vol))
        score = pickpulse.average(items)
        fut = _price_at(today, min(end + timedelta(minutes=horizon), flat))
        if score is None or fut is None or not price:
            continue
        out.append({"at": end, "score": score, "fwd": (fut - price) / price * 100,
                    **{k: items[k][1] for k in KEYS if k != "score"}})
    return out


def premarket_closes(bars):
    """1 分 K → 5 分 K 的 (收完的時間, 收盤)，跟盤中均線版同一個切法。"""
    got: dict = {}
    for b in bars:
        got[premarket.five_min_end(b[0])] = b[4]
    return sorted(got.items())


def whynot_bars(bars):
    return [(t, h, l, c, v) for t, _o, h, l, c, v in bars]


def run(pool_days, markets: dict, seeds: dict) -> dict:
    """{"days": [日期...], "samples": [{date, code, at, score, 各項, fwd}...]}。
    pool_days = whatif.pool_days_for 的結果；seeds = {(日期, 代號): 前一天的 1 分 K}。"""
    days, samples = [], []
    for d, stocks, _hist in pool_days:
        days.append(d)
        for s in stocks:
            for row in score_day(s.get("bars") or [], seeds.get((d, str(s["code"]))) or [],
                                 markets.get(d) or []):
                samples.append(dict(row, date=d, code=str(s["code"])))
    return {"days": days, "samples": samples}


def _avg(rows):
    return sum(r["fwd"] for r in rows) / len(rows) if rows else None


def _cell(rows) -> str:
    if not rows:
        return "—"
    up = sum(1 for r in rows if r["fwd"] > 0) / len(rows) * 100
    return f"{_avg(rows):+.2f}%（{up:.0f}% 漲）"


def spread(rows, key) -> tuple[list, list, float | None]:
    """(低分那一組, 高分那一組, 高分組之後平均 − 低分組之後平均)。"""
    lo = [r for r in rows if r.get(key) is not None and r[key] <= LOW]
    hi = [r for r in rows if r.get(key) is not None and r[key] >= HIGH]
    gap = _avg(hi) - _avg(lo) if lo and hi else None
    return lo, hi, gap


def changes(samples) -> dict:
    """同一檔同一天，名稱跟上一根比升了、降了、沒變 → 之後 30 分鐘。"""
    out = {UP: [], DOWN: [], SAME: []}
    prev = None
    for r in sorted(samples, key=lambda r: (r["date"], r["code"], r["at"])):
        key = (r["date"], r["code"])
        lv = pickpulse.level(r["score"])[0]
        if prev and prev[0] == key:
            out[UP if lv > prev[1] else DOWN if lv < prev[1] else SAME].append(r)
        prev = (key, lv)
    return out


def _fmt_gap(gap) -> str:
    return "—" if gap is None else f"{gap:+.2f}%"


def lines(result: dict) -> list[str]:
    samples, days = result.get("samples") or [], result.get("days") or []
    out = [f"## 強弱分數能不能預測（候選池每一檔、每根 5 分 K 重算，看之後 {HORIZON_MIN} 分鐘）", ""]
    if not samples:
        return out + ["沒有資料（候選池沒有分鐘 K）。", ""]
    half = len(days) // 2
    first, second = set(days[:half]), set(days[half:])
    stock_days = len({(r["date"], r["code"]) for r in samples})
    out += [f"{len(days)} 天、{stock_days} 個「檔×天」、{len(samples)} 個分數。"
            f"前半 {days[0][5:]}～{days[max(half - 1, 0)][5:]}，後半 {days[half][5:]}～{days[-1][5:]}。", "",
            f"| 項目 | 低分（≤{LOW:g}）筆數 | 低分之後 | 高分（≥{HIGH:g}）筆數 | 高分之後 | "
            "高減低 | 前半：高減低 | 後半：高減低 |",
            "|---|---|---|---|---|---|---|---|"]
    for key in KEYS:
        lo, hi, gap = spread(samples, key)
        g1 = spread([r for r in samples if r["date"] in first], key)[2]
        g2 = spread([r for r in samples if r["date"] in second], key)[2]
        out.append(f"| {NAMES[key]} | {len(lo)} | {_cell(lo)} | {len(hi)} | {_cell(hi)} | "
                   f"{_fmt_gap(gap)} | {_fmt_gap(g1)} | {_fmt_gap(g2)} |")
    ch = changes(samples)
    out += ["", "| 名稱跟上一根比 | 筆數 | 之後 30 分鐘 |", "|---|---|---|"]
    for k in (UP, DOWN, SAME):
        out.append(f"| {k} | {len(ch[k])} | {_cell(ch[k])} |")
    out += [
        "",
        "- **怎麼看**：「高減低」是正的，代表分數高的那些之後比較會漲 —— 有一點預測力。"
        "要**前半、後半都是正的**才算數；一正一負就是運氣。",
        f"- 「高減低」要大於來回成本（約 {config.round_trip_cost_pct():.2f}%）才有實際用處；小於成本的話，"
        "就算有關係也賺不到。",
        "- ⑤ 外盤比算不出來（分鐘 K 沒有內外盤），平均是其他五項。均價線用分鐘 K 估。",
        f"- 每 5 分鐘一筆、看之後 {HORIZON_MIN} 分鐘，前後幾筆會重疊；同一檔同一天的分數彼此很像。"
        "真正獨立的樣本比較接近「檔×天」的數字，不是分數的筆數。",
        "- 每一檔都當作 09:00 開盤價買進來算（跟首選一樣）。只是量，不改任何規則。",
        "",
    ]
    return out

