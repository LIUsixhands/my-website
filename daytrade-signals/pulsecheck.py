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
import csv
import logging
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

# 10-22 使用者：「請想辦法可當預測，上網查或其他方式」。上面五項分數 9 天驗下來沒有預測力；
# 唯一前後一致的是 ④ 量，而且方向相反（漲又爆量之後比較會回落）。文獻裡有證據的幾個方向：
#   - 短線反轉：一檔股票最近半小時的漲跌，跟下一個半小時負相關（Heston, Korajczyk & Sadka 2010）
#   - 量大的漲跌比較會反轉（Campbell, Grossman & Wang 1993）—— 跟 ④ 的結果一致
#   - 同一個半小時時段會延續好幾天：前幾天這個時段漲，今天這個時段也比較會漲（同一篇 HKS 2010）
# 這幾個不是分數，是原始數字，所以用「三等分」比：最低的 1/3 vs 最高的 1/3。
EXTRA = ("ret30", "from_high", "same_slot")
EXTRA_NAMES = {"ret30": "近 30 分鐘漲跌（短線反轉）", "from_high": "離今天最高幾 %",
               "same_slot": "同一時段、過去 5 天的平均漲跌"}
SLOT_DAYS = 5                      # 同一時段看過去幾天
SLOT_MIN_DAYS = 3                  # 至少要有幾天才算

# 10-22 使用者：「邊用邊統計」→「強弱訊息保留，可以加『之後幾分鐘：偏跌』」。9 天裡唯一
# 前後一致的是 ④ 量（反向）：④ 高分之後 30 分鐘平均 −0.36%。盤中每一則強弱訊息加
# 「之後 30 分鐘：偏漲／偏跌／中性」（照目前 ④ 落在哪一組、那一組過去怎麼走），預測變了也推。
# 數字每天收盤後用累積的樣本重算（review.py 14:00 加今天的候選池；whatif.py 跑的時候整段重寫）。
SAMPLES_FILE = config.JOURNAL_DIR / "pulse-samples.csv"
SAMPLE_FIELDS = ("date", "code", "at", *KEYS, *EXTRA, "fwd")
STATS_MIN_N = 100                  # 樣本不到這麼多筆就不顯示

log = logging.getLogger("pulsecheck")


def _price_at(bars, at: datetime):
    seen = [b for b in bars if b[0] <= at]
    return seen[-1][4] if seen else None


def slot_return(bars, clock, horizon: int = HORIZON_MIN):
    """那一天 clock 那一刻到之後 horizon 分鐘（最多到 13:25）的漲跌 %。算不出來 None。"""
    today = [b for b in bars if b[0].time() <= oc.FLATTEN_AT]
    if not today:
        return None
    d = today[0][0].date()
    t0 = datetime.combine(d, clock)
    p0 = _price_at(today, t0)
    p1 = _price_at(today, min(t0 + timedelta(minutes=horizon), datetime.combine(d, oc.FLATTEN_AT)))
    return (p1 - p0) / p0 * 100 if p0 and p1 else None


def same_slot(history, clock, horizon: int = HORIZON_MIN):
    """過去 SLOT_DAYS 天、同一個時段的平均漲跌 %。有資料的天數不到 SLOT_MIN_DAYS → None。"""
    got = [r for r in (slot_return(b, clock, horizon) for b in list(history)[-SLOT_DAYS:] if b)
           if r is not None]
    return sum(got) / len(got) if len(got) >= SLOT_MIN_DAYS else None


def score_day(bars, seed=(), mbars=(), horizon: int = HORIZON_MIN, history=()) -> list[dict]:
    """一檔一天：每根 5 分 K 收完打一次分（照 pickpulse），加上之後 horizon 分鐘的漲跌 %。
    bars / seed / mbars = 今天、前一個交易日、今天 0050 的 1 分 K (t, 開, 高, 低, 收, 量)。
    history = 之前幾個交易日的 1 分 K（舊到新），算「同一時段」用。"""
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
        high = max(b[2] for b in upto)
        out.append({"at": end, "score": score, "fwd": (fut - price) / price * 100,
                    **{k: items[k][1] for k in KEYS if k != "score"},
                    "ret30": move / base[1] * 100 if base[1] else None,
                    "from_high": (price - high) / high * 100 if high else None,
                    "same_slot": same_slot(history, end.time(), horizon)})
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
    for d, stocks, hist in pool_days:
        days.append(d)
        for s in stocks:
            code = str(s["code"])
            for row in score_day(s.get("bars") or [], seeds.get((d, code)) or [],
                                 markets.get(d) or [], history=(hist or {}).get(code) or []):
                samples.append(dict(row, date=d, code=str(s["code"])))
    return {"days": days, "samples": samples}


def save_samples(samples, path=None) -> None:
    """寫進累積檔。同一天重算會蓋掉那一天的舊樣本。"""
    if not samples:
        return
    path = path or SAMPLES_FILE
    days = {r["date"] for r in samples}
    keep = [r for r in load_samples(path) if r["date"] not in days]
    new = [dict(r, at=r["at"].strftime("%H:%M") if isinstance(r["at"], datetime) else r["at"])
           for r in samples]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SAMPLE_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(keep + new, key=lambda r: (r["date"], r["code"], r["at"])):
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in SAMPLE_FIELDS})


def load_samples(path=None) -> list[dict]:
    path = path or SAMPLES_FILE
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            row = {"date": r["date"], "code": r["code"], "at": r["at"]}
            for k in (*KEYS, *EXTRA, "fwd"):
                v = r.get(k)
                row[k] = float(v) if v not in (None, "") else None
            out.append(row)
    return out


COMBO_NAMES = {"high": "稍強以上", "mid": "中性附近", "low": "中性偏弱以下"}


def forecast_stats(samples, path=None) -> dict | None:
    """盤中「之後 30 分鐘：偏漲／偏跌／中性」用的表：④ 分低、中、高三組，各自之後 30 分鐘的
    平均與上漲比例。一組不到 STATS_MIN_N 筆就不放（那一組不預測）。samples=None → 讀累積檔。"""
    rows = load_samples(path) if samples is None else samples
    rows = [r for r in rows if r.get("volume") is not None and r.get("fwd") is not None]
    groups = {}
    for key, test, desc in (("low", lambda v: v <= LOW, f"④ 低（≤{LOW:g}）"),
                            ("mid", lambda v: LOW < v < HIGH, f"④ 中（{LOW:g}～{HIGH:g}）"),
                            ("high", lambda v: v >= HIGH, f"④ 高（≥{HIGH:g}）")):
        g = [r for r in rows if test(r["volume"])]
        if len(g) >= STATS_MIN_N:
            groups[key] = {"desc": desc, "n": len(g), "avg": round(_avg(g), 2),
                           "up": round(sum(1 for r in g if r["fwd"] > 0) / len(g) * 100)}
    if not groups:
        return None
    # 10-24 使用者：「好，改用組合預測」（九格表：稍強以上＋④ 高 −0.43%、中性附近＋④ 高 −0.14%，
    # 兩半都一致；只看 ④ 高是 −0.36%）。只用在 ④ 高那一排；一格不到 STATS_MIN_N 筆就不放（退回只看 ④）。
    combos = {}
    for a, name in COMBO_NAMES.items():
        g = [r for r in rows if band(r["volume"]) == "high" and band(r.get("score")) == a]
        if len(g) >= STATS_MIN_N:
            combos[a] = {"desc": f"「{name}＋④ 高」", "n": len(g), "avg": round(_avg(g), 2),
                         "up": round(sum(1 for r in g if r["fwd"] > 0) / len(g) * 100)}
    return {"days": len({r["date"] for r in rows}), "horizon": HORIZON_MIN, "low": LOW, "high": HIGH,
            "cost": round(config.round_trip_cost_pct(), 2), "groups": groups, "combos": combos}


def daily(broker, date: str | None = None, path=None) -> dict | None:
    """review.py 收盤後叫：今天的候選池回頭打分，加進累積檔。今天沒有名單存檔 → None。"""
    import time
    import whatif
    date = date or datetime.now().strftime("%Y-%m-%d")
    archived = whatif.archived_days(date, date)
    if not archived:
        return None

    def fetch_range(code, start, end):
        time.sleep(config.SCREEN["kbar_sleep_sec"])
        try:
            return whatif.kbars_to_days(broker.kbars(code, start, end))
        except Exception as e:
            log.warning("%s 分鐘 K（%s～%s）取得失敗：%s", code, start, end, e)
            return {}

    pool_days, _missing = whatif.pool_days_for(archived, fetch_range)
    markets = {date: whatif.market_bars(date, lambda c, d: oc.day_bars_ohlcv(broker, c, d))}
    got = run(pool_days, markets, whatif.prev_day_index(pool_days))
    save_samples(got["samples"], path)
    return got


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


def thirds(rows, key) -> tuple[list, list, float | None]:
    """(最低的 1/3, 最高的 1/3, 高的之後平均 − 低的之後平均)。原始數字用這個，不用分數門檻。"""
    have = [r for r in rows if r.get(key) is not None]
    if len(have) < 3:
        return [], [], None
    vals = sorted(r[key] for r in have)
    q1, q2 = vals[len(vals) // 3], vals[len(vals) * 2 // 3]
    lo = [r for r in have if r[key] < q1]
    hi = [r for r in have if r[key] > q2]
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


# 10-23 使用者：強弱名稱那張表「可搭配這個嗎」→「要，表先讓我看一下」→「好」。
# 強弱（平均分）× ④ 量，各分三組、九格，看組合是不是比只看 ④ 更明顯。只是量，盤中還是只看 ④。
SCORE_BANDS = (("high", f"稍強以上（≥{HIGH:g}）"), ("mid", f"中性附近（{LOW:g}～{HIGH:g}）"),
               ("low", f"中性偏弱以下（≤{LOW:g}）"))
VOL_BANDS = (("high", f"高（≥{HIGH:g}）"), ("mid", "中"), ("low", f"低（≤{LOW:g}）"))


def band(v) -> str | None:
    """分數落在哪一組：low（≤3.5）／mid／high（≥6.5）。沒分數 None。"""
    if v is None:
        return None
    return "low" if v <= LOW else "high" if v >= HIGH else "mid"


def combos(samples) -> dict:
    """{(強弱那一組, ④ 那一組): [樣本]}。"""
    out = {(a, b): [] for a, _ in SCORE_BANDS for b, _ in VOL_BANDS}
    for r in samples:
        key = (band(r.get("score")), band(r.get("volume")))
        if key in out and r.get("fwd") is not None:
            out[key].append(r)
    return out


def _half_avg(rows, days) -> str:
    got = [r for r in rows if r["date"] in days]
    return f"{_avg(got):+.2f}%" if got else "—"


def combo_lines(samples, first: set, second: set) -> list[str]:
    import pickpulse
    stats = forecast_stats(samples)
    out = ["", f"強弱名稱 × ④ 量（之後 {HORIZON_MIN} 分鐘；強弱是五項平均）：", "",
           "| 強弱（平均分） | ④ 量 | 預測會顯示 | 筆數 | 之後 30 分鐘 | 前半 | 後半 |",
           "|---|---|---|---|---|---|---|"]
    cells = combos(samples)
    for a, a_name in SCORE_BANDS:
        for b, b_name in VOL_BANDS:
            rows = cells[(a, b)]
            vol = {"high": HIGH, "mid": (LOW + HIGH) / 2, "low": LOW}[b]
            fc = pickpulse.forecast(stats, vol, {"high": HIGH, "mid": (LOW + HIGH) / 2, "low": LOW}[a])
            n = f"{len(rows)}" + ("（樣本少）" if len(rows) < STATS_MIN_N else "")
            out.append(f"| {a_name} | {b_name} | {fc[0] if fc else '—'} | {n} | {_cell(rows)} | "
                       f"{_half_avg(rows, first)} | {_half_avg(rows, second)} |")
    hi = [r for r in samples if band(r.get("volume")) == "high" and r.get("fwd") is not None]
    fc = pickpulse.forecast(stats, HIGH)
    out.append(f"| （對照）只看 ④ 高 | — | {fc[0] if fc else '—'} | {len(hi)} | {_cell(hi)} | "
               f"{_half_avg(hi, first)} | {_half_avg(hi, second)} |")
    out += [
        "",
        "- **「預測會顯示」**：照現在盤中的規則（10-24 起 ④ 高那一排用組合，其他只看 ④），這一格會顯示什麼。",
        "- **跟最後一列比**：某一格比「只看 ④ 高」明顯更好或更差、而且**前半、後半同方向**，"
        "那個組合才有額外的用處；差不多的話，強弱名稱沒有幫上忙，維持只看 ④。",
        f"- 一格不到 {STATS_MIN_N} 筆標「樣本少」，不能信。",
        "- 這裡的強弱是五項平均（分鐘 K 沒有內外盤，少了 ⑤），盤中是六項，會有一點出入。",
    ]
    return out


def lines(result: dict) -> list[str]:
    samples, days = result.get("samples") or [], result.get("days") or []
    # 沒有之後 30 分鐘結果的不算（累積檔讀回來可能有空格）。
    samples = [r for r in samples if r.get("fwd") is not None]
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
    out += ["", "其他候選指標（文獻上有證據的方向；原始數字三等分，最低 1/3 vs 最高 1/3）：", "",
            "| 指標 | 低的 1/3 筆數 | 低的之後 | 高的 1/3 筆數 | 高的之後 | 高減低 | 前半：高減低 | 後半：高減低 |",
            "|---|---|---|---|---|---|---|---|"]
    for key in EXTRA:
        lo, hi, gap = thirds(samples, key)
        g1 = thirds([r for r in samples if r["date"] in first], key)[2]
        g2 = thirds([r for r in samples if r["date"] in second], key)[2]
        out.append(f"| {EXTRA_NAMES[key]} | {len(lo)} | {_cell(lo)} | {len(hi)} | {_cell(hi)} | "
                   f"{_fmt_gap(gap)} | {_fmt_gap(g1)} | {_fmt_gap(g2)} |")
    ch = changes(samples)
    out += ["", "| 名稱跟上一根比 | 筆數 | 之後 30 分鐘 |", "|---|---|---|"]
    for k in (UP, DOWN, SAME):
        out.append(f"| {k} | {len(ch[k])} | {_cell(ch[k])} |")
    out += combo_lines(samples, first, second)
    out += [
        "",
        "- **怎麼看**：「高減低」是正的，代表分數高的那些之後比較會漲 —— 有一點預測力。"
        "要**前半、後半都是正的**才算數；一正一負就是運氣。",
        "- **前半、後半都是負的也有用**：方向相反（高的之後比較會跌），把那一項反過來用就好。"
        "例如「近 30 分鐘漲跌」如果是負的，就是短線反轉：剛漲完的接下來比較會回。",
        f"- 「同一時段」要前面至少 {SLOT_MIN_DAYS} 天有分鐘 K 才算。",
        f"- 「高減低」要大於來回成本（約 {config.round_trip_cost_pct():.2f}%）才有實際用處；小於成本的話，"
        "就算有關係也賺不到。",
        "- ⑤ 外盤比算不出來（分鐘 K 沒有內外盤），平均是其他五項。均價線用分鐘 K 估。",
        f"- 每 5 分鐘一筆、看之後 {HORIZON_MIN} 分鐘，前後幾筆會重疊；同一檔同一天的分數彼此很像。"
        "真正獨立的樣本比較接近「檔×天」的數字，不是分數的筆數。",
        "- 每一檔都當作 09:00 開盤價買進來算（跟首選一樣）。只是量，不改任何規則。",
        "",
    ]
    return out

