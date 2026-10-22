# -*- coding: utf-8 -*-
"""whatif.py —— 開盤區間要看幾分鐘？用同一批日子、同一批股票重跑 v10。

10-13 使用者：「還有注意一下要看 9:00～9:02 及還是其他時間」。2 分鐘是我
當初猜的，沒有任何數據支持。這支程式回答它：同樣的 v10（進場三關、09:05
批次、上限 3 檔、六條出場），只把開盤區間換成 1／2／3／5／15 分鐘，各自
會發哪些訊號、結果如何。

**它不改規則、不影響盤中。** 排程不會跑它；要看結果時手動跑（預定 11-09
第 20 個交易日收盤後）。

和第一版的差別（第一版是 v4 時代寫的）：

  1. 股票來源：第一版只重跑 outcomes.csv 裡有的 —— 當天真的突破了的那幾檔。
     區間一改，原本沒突破的會被買進來，原本有突破的會消失，所以結論偏樂觀。
     現在用每天盤前存檔的 journal/watchlist-YYYYMMDD.json，**當天監看的
     每一檔都重跑**。
  2. 出場：第一版只有停損／目標／時間到。現在走 outcome.walk_v10 ——
     跟收盤回推是同一份六條出場（exits.py）。
  3. 進場：三關（突破、均價線、量能）用 whynot.py 那一套分鐘 K 重建；
     09:05 批次照量能排序取前 3、發出那一刻重新定價；停損、目標、張數用
     signals._price_plan —— 跟盤中同一套算法。

每一種區間都給一樣長的時間：區間結束後 3 分鐘批次（2 分鐘版就是 09:05），
進場窗口 28 分鐘（2 分鐘版就是到 09:30）。

**它是重建，不是盤中紀錄。** 量能倍數和均價線都是分鐘 K 的近似（見 whynot.py）。
所以 2 分鐘那一列會拿去跟盤中真的發出的訊號對答案，對不上的寫在報表最前面。

10-15 再加一張「大盤」：加權指數一開盤就是當天最高、收黑 3.41%，v10 三筆全輸。使用者：
「大盤不好，突破就下跌」。把 v10 的每一筆照進場那一分鐘大盤（0050）在不在今天開盤價之上
分組 —— 那一刻就知道，可以變成規則；另外照大盤當天收紅／收黑分組 —— 收盤才知道，只能看。

10-14 再加一張「停損寬度」：1.5％／2％／2.5％／現在，突破訊號和首選各一組。

10-13 再加一張「三種進場方式」：突破即買（v10）、回踩再買（使用者貼的文章）、
08:45 盤前首選（開盤價）。同一批日子、同一套出場，只換進場方式。

用法：
    python whatif.py                      # 10-12（v10 第一天）到昨天
    python whatif.py --since 2026-10-12 --until 2026-11-09
分鐘 K 抓過一次就存在 journal/kbars/，再跑不會重抓。
"""
import argparse
import json
import logging
import time
from dataclasses import dataclass
from datetime import date as ddate, datetime, time as dtime, timedelta

import config
import exits
import manual
import market_calendar
import outcome as oc
import premarket
import pulsecheck
import whynot

log = logging.getLogger("whatif")

V10_START = "2026-10-12"          # v10 第一天；之前的日子規則不一樣
GRID_OR = (1, 2, 3, 5, 15)        # 開盤區間幾分鐘
CURRENT_OR = 2                    # 現在用的（09:00–09:02）
CACHE_DIR = config.JOURNAL_DIR / "kbars"

OPTIMISTIC = "樂觀"
CAUTIOUS = "保守"


def _t(hhmmss: str) -> dtime:
    h, m, s = (int(x) for x in hhmmss.split(":"))
    return dtime(h, m, s)


def _minutes_between(a: str, b: str) -> int:
    d = datetime(2000, 1, 1)
    return int((datetime.combine(d, _t(b)) - datetime.combine(d, _t(a))).total_seconds() // 60)


def schedule(or_minutes: int) -> tuple[dtime, dtime, dtime]:
    """(區間結束, 批次時間, 進場窗口結束)。批次與窗口跟著區間往後移，長度不變。"""
    cfg = config.SIGNAL
    start = datetime.combine(datetime(2000, 1, 1), _t(cfg["or_start"]))
    or_end = start + timedelta(minutes=or_minutes)
    batch = or_end + timedelta(minutes=_minutes_between(cfg["or_end"], cfg["signal_batch_at"]))
    win = or_end + timedelta(minutes=_minutes_between(cfg["or_end"], cfg["entry_window_end"]))
    return or_end.time(), batch.time(), win.time()


def opening_range(bars, or_minutes: int):
    """(高, 低)。bars = [(dt, 開, 高, 低, 收, 量)]；K 棒 label 是那一分鐘的結束時間，
    所以收的是 label 在 (09:00, 09:00+N] 的那幾根 —— label 09:00 那根是盤前。"""
    or_start = _t(config.SIGNAL["or_start"])
    or_end, _, _ = schedule(or_minutes)
    return whynot.opening_range(_wn(bars), or_start, or_end)


def _wn(bars):
    """whynot 的格式：(dt, 高, 低, 收, 量)。"""
    return [(t, h, l, c, v) for t, _o, h, l, c, v in bars]


@dataclass
class Trade:
    date: str
    code: str
    name: str
    fired: datetime
    or_high: float
    entry: float
    stop: float
    lots: int
    vol_ratio: float
    batch: bool                 # 09:05 那一批發的（否則是之後即時發的）
    result: str = ""
    exit_price: float = 0.0
    exit_at: str = ""
    r_multiple: float = 0.0
    net_r: float = 0.0           # 扣掉來回成本之後的 R
    net_pct: float = 0.0
    held_min: int = 0
    chase_pct: float | None = None   # 慢一步用市價追，比進場價多付幾 %（下一根 K 的開盤）
    limit_room_pct: float | None = None  # 進場時離漲停還有幾 %
    oversized: bool = False          # 一張的停損風險就超過單筆上限


def _gates(wbars, b, trigger: float, or_start: dtime) -> float | None:
    """這一根 K 過不過三關（突破、均價線、量能）。過了回量能倍數，沒過回 None。
    判法跟 whynot.diagnose 一樣：最高價碰到觸發價、最高價不低於均價線。"""
    cfg = config.SIGNAL
    if b[1] < trigger:
        return None
    if cfg["require_above_vwap"]:
        vw = whynot.vwap_upto(wbars, b[0])
        if vw is None or b[1] < vw:
            return None
    vr = whynot.volume_ratio(wbars, b[0], or_start)
    if vr is None or vr < cfg["volume_surge_ratio"]:
        return None
    return vr


def _plan(stock: dict, or_high: float, day_open: float | None, entry: float,
          now: dtime) -> dict | None:
    """停損、目標、張數、出場計畫 —— 跟盤中同一個函式。"""
    import signals
    st = signals.SymbolState(stock["code"], stock["prev_close"], stock.get("name", ""))
    st.or_high = or_high
    st.amplitude_pct = stock.get("amplitude_pct")
    st.day_open = day_open
    return signals._price_plan(st, entry, now)


def restop(plan: dict | None, pct: float | None) -> dict | None:
    """停損換成「進場價往下 pct %」（不看結構線），張數照單筆風險上限重算。
    pct = None 就是現在的規則，原樣回傳。先出一半的價位跟目標有關、跟停損無關，不動。

    張數一起重算，是因為停損縮小、單筆風險固定 4,000 元時，實際會多買幾張 ——
    不重算的話，「停損改小」量到的只是一半的效果。"""
    if plan is None or pct is None:
        return plan
    entry = plan["entry"]
    stop = config.round_to_tick(entry * (1 - pct / 100), "up")
    if stop >= entry:
        return None
    risk_per_lot = round((entry - stop) * 1000, 2)
    cap = config.RISK["per_trade_risk"]
    return dict(plan, stop=stop, lots=max(1, int(cap // risk_per_lot)),
                risk_per_lot=round(risk_per_lot), oversized=risk_per_lot > cap)


def replay_day(stocks: list[dict], or_minutes: int, optimistic: bool = False,
               limit: int | None = None, stop_pct: float | None = None
               ) -> tuple[list[Trade], int]:
    """一天、一種區間長度。stocks = [{code, name, rank, prev_close, amplitude_pct,
    bars}]，bars = [(dt, 開, 高, 低, 收, 量)]。回傳 (發出的訊號, 因為額度滿了沒發的檔數)。

    進場價：
      09:05 那一批 → 批次那一根的收盤（盤中就是用發出當下的價格重算）
      之後即時發的 → 保守：那一根的收盤（不低於觸發價）；樂觀：觸發價
    """
    cfg = config.SIGNAL
    limit = config.RISK["max_signals_per_day"] if limit is None else limit
    or_start = _t(cfg["or_start"])
    or_end, batch_at, win_end = schedule(or_minutes)

    prepared = []
    for s in stocks:
        bars = s.get("bars") or []
        rng = opening_range(bars, or_minutes)
        if not rng:
            continue
        or_high = rng[0]
        wbars = _wn(bars)
        trigger = or_high * (1 + cfg["breakout_buffer_pct"] / 100)
        passes = []                                   # (那一根, 量能倍數)
        for b in wbars:
            if not (or_end < b[0].time() <= win_end):
                continue
            vr = _gates(wbars, b, trigger, or_start)
            if vr is not None:
                passes.append((b, vr))
        if passes:
            prepared.append(dict(stock=s, or_high=or_high, trigger=trigger, wbars=wbars,
                                 passes=passes, day_open=bars[0][1] if bars else None))

    sent: list[Trade] = []

    def fire(p, b, vr, entry, batch):
        plan = restop(_plan(p["stock"], p["or_high"], p["day_open"], entry, b[0].time()),
                      stop_pct)
        if plan is None:                              # 漲停買不到、停損進位到進場價
            return False
        sent.append(_walk(p, b, vr, plan, batch))
        return True

    # 09:05 那一批：每檔取第一次過關的那一根，按量能排序取前 N，發出前用當下價格重算
    in_batch = []
    for p in prepared:
        first = next(((b, vr) for b, vr in p["passes"] if b[0].time() <= batch_at), None)
        if first:
            in_batch.append((p, *first))
    in_batch.sort(key=lambda x: (-x[2], x[0]["stock"].get("rank") or 9999,
                                 str(x[0]["stock"]["code"])))
    done = set()
    for p, _b, vr in in_batch[:limit]:
        at = next((b for b in p["wbars"] if b[0].time() == batch_at), None)
        if at is None:
            at = next((b for b in reversed(p["wbars"]) if b[0].time() <= batch_at), None)
        if at is None or at[3] < p["trigger"]:
            continue                                  # 已經跌回區間
        if cfg["require_above_vwap"]:
            vw = whynot.vwap_upto(p["wbars"], at[0])
            if vw is not None and at[3] < vw:
                continue                              # 已經跌破均價線
        if fire(p, at, vr, at[3], True):
            done.add(p["stock"]["code"])

    # 之後：一出現就發，直到額度滿
    later = sorted(((b, vr, p) for p in prepared for b, vr in p["passes"]
                    if b[0].time() > batch_at),
                   key=lambda x: (x[0][0], x[2]["stock"].get("rank") or 9999))
    skipped = set()
    for b, vr, p in later:
        code = p["stock"]["code"]
        if code in done:
            continue
        if len(sent) >= limit:
            skipped.add(code)
            continue
        entry = p["trigger"] if optimistic else max(p["trigger"], b[3])
        entry = config.round_to_tick(entry, "up")
        if fire(p, b, vr, entry, False):
            done.add(code)
    capped = {p["stock"]["code"] for p, _b, _v in in_batch[limit:]} | skipped
    return sent, len(capped - done)


def _walk(p: dict, b, vr: float, plan: dict, batch: bool) -> Trade:
    s = p["stock"]
    fired = b[0]
    sig = dict(plan, or_high=p["or_high"])
    walked = oc.walk_v10(s["bars"], sig, fired)
    tr = Trade(date=fired.strftime("%Y-%m-%d"), code=str(s["code"]), name=s.get("name", ""),
               fired=fired, or_high=p["or_high"], entry=plan["entry"], stop=plan["stop"],
               lots=plan["lots"], vol_ratio=round(vr, 2), batch=batch)
    lu = config.limit_up(s.get("prev_close") or 0)
    if lu:
        tr.limit_room_pct = round((lu - plan["entry"]) / plan["entry"] * 100, 3)
    tr.oversized = bool(plan.get("oversized"))
    chase = oc.chase_price(s["bars"], fired)
    if chase is not None:
        tr.chase_pct = round((chase - plan["entry"]) / plan["entry"] * 100, 3)
    if walked is None:                                # 之後一根 K 都沒有
        tr.result, tr.exit_price = oc.FLAT, plan["entry"]
        return tr
    result, exit_price, _used, exit_at, half = walked
    pct, r = exits.blended(plan["entry"], plan["stop"], plan["lots"], half, exit_price)
    tr.result, tr.exit_price, tr.exit_at = result, round(exit_price, 2), exit_at
    _finish(tr, plan["entry"], plan["stop"], r, pct, exit_at, fired)
    return tr


def _finish(tr: Trade, entry: float, stop: float, r: float, pct: float,
            exit_at: str, fired: datetime) -> None:
    cost = config.round_trip_cost_pct()
    tr.r_multiple = round(r, 2)
    tr.net_r = round(r - cost / 100 * entry / (entry - stop), 2) if entry > stop else tr.r_multiple
    tr.net_pct = round(pct - cost, 3)
    end = datetime.combine(fired.date(), _t(exit_at)) if exit_at else fired
    tr.held_min = max(0, int((end - fired).total_seconds() // 60))


# ── 進場方式的比較組 ──────────────────────────────────────
# 10-13 使用者貼了一篇當沖心得：「前 5 分鐘不追第一根」「等第一次回踩再決定 ——
# 回踩時量縮、守住突破位置，再重新往上才進場」。v10 是突破就買，沒有這一步。
# 使用者選「加進 whatif 當比較組」：同一批日子、同一套出場，只換進場方式。
BREAKOUT = "突破即買（v10 現在）"
PULLBACK = "回踩再買"
PICK = "盤前首選（開盤價）"
PULLBACK_BAND_PCT = 0.5      # 低點回到突破點上方 0.5% 以內，算「回踩到了」


def pullback_entry(wbars, or_high: float, trigger: float, or_start: dtime,
                   or_end: dtime, win_end: dtime):
    """回踩再買。wbars = [(dt, 高, 低, 收, 量)]。回傳 (進場那一根, 突破時的量能倍數,
    前一根的高點) 或 None。

    1. 先要有一次 v10 會買的突破（突破、均價線、量能三關都過）
    2. 之後有一根的低點回到突破點附近（區間高 +0.5% 以內），而且量比突破那一根小
       —— 文章的「回踩時量能縮下來」
    3. 再來有一根收盤高過前一根的高點、收在均價線上 —— 「重新出現往上的力道」
    中途任何一根收回區間（區間高 -0.2% 以下）＝突破失敗，當天不買。
    一直沒回踩就一路漲上去的，買不到 —— 這是這種進場方式的代價，要算進去。
    """
    hold = or_high * (1 - config.SIGNAL["exit_reason_buffer_pct"] / 100)
    near = or_high * (1 + PULLBACK_BAND_PCT / 100)
    stage, brk, prev = 0, None, None
    for b in wbars:
        if not (or_end < b[0].time() <= win_end):
            prev = b
            continue
        if stage == 0:
            vr = _gates(wbars, b, trigger, or_start)
            if vr is not None:
                stage, brk = 1, (b, vr)
        elif b[3] < hold:
            return None
        elif stage == 1:
            if b[2] <= near and b[4] < brk[0][4]:
                stage = 2
        elif stage == 2 and b[3] > prev[1]:
            vw = whynot.vwap_upto(wbars, b[0])
            if vw is None or b[3] >= vw:
                return b, brk[1], prev[1]
        prev = b
    return None


def replay_pullback_day(stocks: list[dict], optimistic: bool = False,
                        limit: int | None = None) -> tuple[list[Trade], int]:
    """一天、回踩再買、開盤區間 2 分鐘。依進場時間先到先買，額度跟 v10 一樣。
    保守：那一根的收盤；樂觀：剛越過前一根高點的價位。"""
    cfg = config.SIGNAL
    limit = config.RISK["max_signals_per_day"] if limit is None else limit
    or_start = _t(cfg["or_start"])
    or_end, _batch, win_end = schedule(CURRENT_OR)
    hits = []
    for s in stocks:
        bars = s.get("bars") or []
        rng = opening_range(bars, CURRENT_OR)
        if not rng:
            continue
        wbars = _wn(bars)
        trigger = rng[0] * (1 + cfg["breakout_buffer_pct"] / 100)
        got = pullback_entry(wbars, rng[0], trigger, or_start, or_end, win_end)
        if got:
            p = dict(stock=s, or_high=rng[0], trigger=trigger, wbars=wbars,
                     day_open=bars[0][1] if bars else None)
            hits.append((got[0], got[1], got[2], p))
    hits.sort(key=lambda x: (x[0][0], x[3]["stock"].get("rank") or 9999))
    sent, capped = [], 0
    for b, vr, prev_high, p in hits:
        if len(sent) >= limit:
            capped += 1
            continue
        entry = min(b[3], prev_high) if optimistic else b[3]
        plan = _plan(p["stock"], p["or_high"], p["day_open"],
                     config.round_to_tick(entry, "up"), b[0].time())
        if plan is not None:
            sent.append(_walk(p, b, vr, plan, False))
    return sent, capped


def pick_of(payload: dict) -> dict | None:
    """那一天的盤前首選。10-14 起存檔裡就有；之前的日子用同一條公式重算
    （候選池 = 盯的 + 沒盯的）。"""
    if payload.get("pick"):
        return payload["pick"]
    items = payload.get("items") or []
    return premarket.choose(items + (payload.get("not_watched") or []),
                            watched=[i["code"] for i in items])


def pick_trade(day: str, pick: dict | None, bars, stop_pct: float | None = None
               ) -> Trade | None:
    """盤前首選那一筆：開盤價買進、照 v10 出場（跟 premarket.resolve 同一個走法）。"""
    if not pick or not bars:
        return None
    sig = restop(premarket.plan(pick, bars[0][1]), stop_pct)
    if sig is None:
        return None
    sig["time"] = premarket.REPLAY_ENTRY_TIME
    replayed = premarket.replay(pick, bars, day, sig)
    if replayed is None:
        return None
    sig, (result, exit_price, _used, exit_at, half) = replayed
    fired = datetime.strptime(f"{day} {sig['time']}", "%Y-%m-%d %H:%M:%S")
    pct, r = exits.blended(sig["entry"], sig["stop"], sig["lots"], half, exit_price)
    tr = Trade(date=day, code=str(pick["code"]), name=pick.get("name", ""), fired=fired,
               or_high=0.0, entry=sig["entry"], stop=sig["stop"], lots=sig["lots"],
               vol_ratio=round(float((pick.get("features") or {}).get("volume_ratio") or 0), 2),
               batch=False, result=result, exit_price=round(float(exit_price), 2),
               exit_at=exit_at)
    _finish(tr, sig["entry"], sig["stop"], r, pct, exit_at, fired)
    return tr


# ── 停損寬度 ──────────────────────────────────────────────
# 10-14 使用者：「回測停損不到 3%」。None = 現在的規則（v10：進場價 -3% 與區間高下方
# 0.2% 取寬的那條；首選：開盤價 -3%）。
STOP_GRID = (1.5, 2.0, 2.5, None)


def run_stops(days: list[tuple[str, list[dict]]], picks: list[tuple[str, dict, list]]) -> dict:
    """{停損 %: (v10 突破即買的訊號, 盤前首選)}。區間 2 分鐘、保守進場價。"""
    out = {}
    for pct in STOP_GRID:
        v10 = [t for _d, stocks in days for t in replay_day(stocks, CURRENT_OR, stop_pct=pct)[0]]
        chosen = [t for t in (pick_trade(d, p, b, stop_pct=pct) for d, p, b in picks) if t]
        out[pct] = (v10, chosen)
    return out


def _stop_lines(stops: dict) -> list[str]:
    def cells(trades):
        s = summarise(trades)
        if not s["n"]:
            return "0 | — | — | — | — | —"
        return (f"{s['n']} | {s['stops']} | {s['rate']}% | {s['avg_r']:+.2f} | "
                f"{s['avg_net_r']:+.2f} | {s['amount']:+,}")
    out = ["## 停損寬度（區間 2 分鐘、保守進場價、其他出場照 v10）", "",
           "| 停損 | 突破：筆數 | 被停損 | 勝率 | 平均R | 扣成本R | 金額 "
           "| 首選：筆數 | 被停損 | 勝率 | 平均R | 扣成本R | 金額 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for pct in STOP_GRID:
        v10, chosen = stops.get(pct, ([], []))
        name = f"{pct:g}%" if pct is not None else "現在"
        out.append(f"| {name} | {cells(v10)} | {cells(chosen)} |")
    out += [
        "",
        "- **現在**：突破訊號是「進場價 -3%」和「區間高下方 0.2%」取比較寬的那條；首選是開盤價 -3%。"
        "其他列是只用「進場價往下 X%」。",
        "- 停損改小，張數會照單筆風險 4,000 元重算（買比較多張）。所以**每一筆冒的錢差不多**，"
        "R 可以直接比；金額欄是照那個張數算的。",
        "- 停損越小，越容易被開盤的上下震盪洗掉（「被停損」那一欄），但每次賠得少、張數多。"
        "哪一邊贏要看數字，不是看感覺。",
        "- 一次比 4 種，一樣會有「剛好」最好看的那一種 —— 只能當下一輪要驗證的新規則。",
        "",
    ]
    return out


# ── 手動下單 ──────────────────────────────────────────
# 10-15 使用者：「訊號到手動下單都過頭了」「手動一定買不到」。恩德 09:06 訊號 25.60，
# 09:07 已經 25.80；沛爾 09:17 訊號 40.05，09:18 已經 40.45。
def _chased_r(t: Trade, net: bool) -> float:
    """出場價不變、進場改成慢一步的市價：R 少「多付的錢 ÷ 每股風險」。"""
    r = t.net_r if net else t.r_multiple
    if t.chase_pct is None or t.entry <= t.stop:
        return r
    return r - t.chase_pct / 100 * t.entry / (t.entry - t.stop)


def _over_breakout(t: Trade, price: float) -> float:
    """price 比這一筆的突破價（區間高 + 緩衝）貴幾 %。"""
    trigger = t.or_high * (1 + config.SIGNAL["breakout_buffer_pct"] / 100)
    return (price - trigger) / trigger * 100


def _chase_lines(ideal: list[Trade], late: list[Trade]) -> list[str]:
    """10-15 使用者要的版本：拿**突破價**當基準，不是拿保守價。

    第一版拿保守價（那一分鐘的收盤）當基準，再晚幾秒當然幾乎沒差 —— 表上寫「只多付
    0.03%」，看起來手動沒成本，其實保守價本身就已經晚了。真正的差距在突破價和手動
    價之間：同一批 4 天，樂觀 +0.49R、保守 -0.12R。"""
    out = [f"## 手動下單：進場價差多少（v10 突破即買、區間 {CURRENT_OR} 分鐘）", ""]
    chased = [t for t in late if t.chase_pct is not None]
    if not ideal and not late:
        return out + ["沒有可以算的訊號。", ""]

    def row(label, trades, price, r):
        if not trades:
            return f"| {label} | 0 | — | — | — |"
        n = len(trades)
        return (f"| {label} | {n} | {sum(_over_breakout(t, price(t)) for t in trades) / n:+.2f}% | "
                f"{sum(r(t, False) for t in trades) / n:+.2f} | "
                f"{sum(r(t, True) for t in trades) / n:+.2f} |")

    plain = lambda t, net: t.net_r if net else t.r_multiple
    out += ["| 進場價 | 筆數 | 比突破價貴 | 平均R | 扣成本R |", "|---|---|---|---|---|",
            row("剛好買在突破價（觸價單的理想情況）", ideal, lambda t: t.entry, plain),
            row("那一分鐘的收盤價（晚幾十秒）", late, lambda t: t.entry, plain),
            row("慢一步市價追（下一分鐘第一筆）", chased,
                lambda t: t.entry * (1 + t.chase_pct / 100), _chased_r),
            "",
            "- **第一列和最後一列的差距，就是手動下單的成本。** 每一列都是同一批訊號、同一套出場，"
            "只換進場價。",
            "- 09:05 那一批三列的進場價差不多（都是發出當下的價格），差距主要來自之後即時發的那幾筆。",
            "- 第一列是最理想的情況：真的用觸價單，成交價也可能比突破價高一兩檔。",
            "- 最後一列是訊號後 0～60 秒的價格，實際手動通常更慢，所以還是**偏樂觀**。",
            ""]
    return out


# ── 觸價單：只看價格 ─────────────────────────────────────
# 10-15：手動下單表的第一列（剛好買在突破價 +0.49R）太樂觀 —— 它假設三關都過的那一刻
# 還能買在突破價，但量能與均價線通常比價格晚過關。券商的觸價單只看價格：一碰到突破價
# 就送單，不管量能、均價線。假突破也會買進去。這一張回答「真的用觸價單會怎樣」。
def replay_trigger_day(stocks: list[dict], or_minutes: int = CURRENT_OR,
                       limit: int | None = None) -> tuple[list[Trade], int]:
    """一天。每檔第一次碰到突破價（區間高 + 緩衝）就買：那一根開盤已經在突破價之上
    （跳上去）就買在開盤價，否則買在突破價。沒有 09:05 批次（單子早就掛在券商那邊），
    照碰到的時間先後，上限 3 檔，09:30 之後碰到的不算。出場照 v10。"""
    cfg = config.SIGNAL
    limit = config.RISK["max_signals_per_day"] if limit is None else limit
    or_end, _batch, win_end = schedule(or_minutes)
    hits = []
    for s in stocks:
        bars = s.get("bars") or []
        rng = opening_range(bars, or_minutes)
        if not rng:
            continue
        trigger = rng[0] * (1 + cfg["breakout_buffer_pct"] / 100)
        b = next((b for b in bars if or_end < b[0].time() <= win_end and b[2] >= trigger), None)
        if b is not None:
            hits.append((b, s, rng[0], trigger))
    hits.sort(key=lambda x: (x[0][0], x[1].get("rank") or 9999, str(x[1]["code"])))
    sent: list[Trade] = []
    capped = 0
    for b, s, or_high, trigger in hits:
        if len(sent) >= limit:
            capped += 1
            continue
        entry = config.round_to_tick(max(trigger, b[1]), "up")
        day_open = s["bars"][0][1] if s.get("bars") else None
        plan = _plan(s, or_high, day_open, entry, b[0].time())
        if plan is None:                              # 漲停買不到
            continue
        p = {"stock": s, "or_high": or_high}
        sent.append(_walk(p, _wn([b])[0], 0.0, plan, False))
    return sent, capped


def run_trigger(days: list[tuple[str, list[dict]]]) -> tuple[list[Trade], int]:
    trades, capped = [], 0
    for _d, stocks in days:
        t, c = replay_trigger_day(stocks)
        trades += t
        capped += c
    return trades, capped


def _trigger_lines(trigger: tuple[list[Trade], int], results: dict) -> list[str]:
    out = [f"## 觸價單：只看價格（區間 {CURRENT_OR} 分鐘、出場照 v10）", "",
           "| 進場方式 | 筆數 | 賺的 | 勝率 | 平均R | 扣成本R | 金額 | 額度滿了沒發 |",
           "|---|---|---|---|---|---|---|---|"]
    rows = (("觸價單：碰到突破價就買（不看量能、均價線）", trigger),
            ("v10 三關都過、剛好買在突破價（樂觀）", results.get((CURRENT_OR, OPTIMISTIC), ([], 0))),
            ("v10 三關都過、那一分鐘收盤價（保守）", results.get((CURRENT_OR, CAUTIOUS), ([], 0))))
    for label, (trades, capped) in rows:
        st = summarise(trades)
        if not st["n"]:
            out.append(f"| {label} | 0 | — | — | — | — | — | {capped} |")
            continue
        out.append(f"| {label} | {st['n']} | {st['wins']} | {st['rate']}% | {st['avg_r']:+.2f} | "
                   f"{st['avg_net_r']:+.2f} | {st['amount']:+,} | {capped} |")
    out += [
        "",
        "- **第一列才是觸價單真正會有的成績**：只看價格，假突破（一碰就掉回來）也會買進去。",
        "- 第二列是「三關都過、還能買在突破價」—— 實際做不到（量能、均價線通常比價格晚過關），"
        "只是上限。",
        "- 第一列的成交價已經算了「那一分鐘一開盤就跳過突破價」的情況（買在開盤價），"
        "但沒算送單那一瞬間再往上跳一兩檔，所以還是**偏樂觀**一點。",
        "- 觸價單沒有 09:05 批次：單子早就掛在券商那邊，誰先碰到誰先成交，滿 3 檔就停。",
        "",
    ]
    return out


# ── 研究版出場：只有停損，其餘抱到 13:25 ─────────────────────
# 10-16 使用者：「往後問題一樣機率很高……上網找找」。查到的開盤突破研究（Zarattini、
# Barbon、Aziz 2024）出場只有一個停損，其他一律抱到收盤；v10 有六條、常常幾秒就出場
# （10-16 亞電 5 秒、廣寰科 22 秒），手動跟不上。這一張只換出場，看差多少。
def simple_exit(bars, entry: float, stop: float, fired: datetime):
    """(結果, 出場價, 出場時間)。只看停損和 13:25。訊號那一分鐘不判（跟 v10 同一個約定）。
    一開盤就跳空在停損下面 → 出在那一根的開盤價。沒有之後的 K 棒 → None。"""
    last = None
    for t, o, h, l, c, _v in bars:
        if t < fired + oc.BAR_SPAN:
            continue
        if t.time() > oc.FLATTEN_AT:
            break
        if l <= stop:
            return oc.STOP, min(o, stop), t.strftime("%H:%M:%S")
        last = c
    if last is None:
        return None
    return oc.FLAT, last, oc.FLATTEN_AT.strftime("%H:%M:%S")


def resimple(trades: list[Trade], bars_of: dict) -> list[Trade]:
    """同一批進場，出場換成「停損＋13:25」。bars_of[(日期, 代號)] = 那天的分鐘 K。"""
    out = []
    for t in trades:
        got = simple_exit(bars_of.get((t.date, t.code)) or [], t.entry, t.stop, t.fired)
        if got is None:
            continue
        result, price, at = got
        n = Trade(date=t.date, code=t.code, name=t.name, fired=t.fired, or_high=t.or_high,
                  entry=t.entry, stop=t.stop, lots=t.lots, vol_ratio=t.vol_ratio,
                  batch=t.batch, result=result, exit_price=round(price, 2), exit_at=at,
                  limit_room_pct=t.limit_room_pct, oversized=t.oversized)
        pct, r = exits.blended(t.entry, t.stop, t.lots, None, price)
        _finish(n, t.entry, t.stop, r, pct, at, t.fired)
        out.append(n)
    return out


def bars_index(days: list[tuple[str, list[dict]]]) -> dict:
    return {(d, str(s["code"])): s.get("bars") or [] for d, stocks in days for s in stocks}


def run_simple(days, results: dict, trigger: tuple) -> dict:
    idx = bars_index(days)
    v10 = results.get((CURRENT_OR, CAUTIOUS), ([], 0))[0]
    trig = trigger[0] if trigger else []
    return {"v10_six": v10, "v10_simple": resimple(v10, idx),
            "trig_six": trig, "trig_simple": resimple(trig, idx)}


def _simple_lines(simple: dict) -> list[str]:
    out = [f"## 研究版出場：只有停損，其餘抱到 13:25（區間 {CURRENT_OR} 分鐘）", "",
           "| 進場 | 出場 | 筆數 | 賺的 | 勝率 | 平均R | 扣成本R | 金額 | 平均持有 |",
           "|---|---|---|---|---|---|---|---|---|"]
    rows = (("v10 三關（保守價）", "v10 六條", "v10_six"),
            ("v10 三關（保守價）", "停損＋13:25", "v10_simple"),
            ("觸價單（只看價格）", "v10 六條", "trig_six"),
            ("觸價單（只看價格）", "停損＋13:25（研究版）", "trig_simple"))
    for entry, exit_, key in rows:
        st = summarise(simple.get(key, []))
        if not st["n"]:
            out.append(f"| {entry} | {exit_} | 0 | — | — | — | — | — | — |")
            continue
        out.append(f"| {entry} | {exit_} | {st['n']} | {st['wins']} | {st['rate']}% | "
                   f"{st['avg_r']:+.2f} | {st['avg_net_r']:+.2f} | {st['amount']:+,} | "
                   f"{st['avg_min']} 分 |")
    out += [
        "",
        "- **停損＋13:25**：停損照原本的價位；碰到就出，沒碰到就抱到 13:25。沒有先出一半、"
        "移動停利、跌破開盤價／區間／均價線、量縮。手動做得到：進場後掛好停損（或母子單），"
        "13:25 前賣掉。",
        "- 研究版跟原論文還有一個差別：論文挑的是「今天開盤前 5 分鐘量最熱」的股票，這裡用的是"
        "盤前名單（昨天的量）。",
        "- 平均持有：v10 常常幾秒到幾分鐘；抱到 13:25 是幾個小時 —— 盤中漲上去再掉回來的，"
        "這裡會全部吐回去，所以兩邊各有輸贏，看數字。",
        "",
    ]
    return out


# ── 過濾條件：離漲停太近、一張就超過風險上限 ─────────────────────
# 10-16 台虹（進場時已漲 6%、目標＝漲停價、一張風險 9,000 元）、亞電（已漲 8%、
# 離漲停 1.7%、先出一半只設在 +0.85%，2 秒碰到、5 秒保本出場）。研究：台股接近漲停會
# 加速（磁吸效應），追進去剩下的空間很小。
LIMIT_ROOM_PCT = 3.0


def run_filters(trades: list[Trade]) -> list[tuple[str, list[Trade]]]:
    is_near = lambda t: t.limit_room_pct is not None and t.limit_room_pct < LIMIT_ROOM_PCT
    near = [t for t in trades if is_near(t)]
    far = [t for t in trades if not is_near(t)]
    big = [t for t in trades if t.oversized]
    ok = [t for t in trades if not t.oversized]
    both = [t for t in far if not t.oversized]
    g = f"{LIMIT_ROOM_PCT:g}%"
    return [("全部（v10 現在）", trades),
            (f"離漲停不到 {g}（會被排除的）", near),
            (f"離漲停 {g} 以上（排除後剩下的）", far),
            ("一張就超過風險上限（會被排除的）", big),
            ("一張沒超過上限（排除後剩下的）", ok),
            ("兩個都排除後剩下的", both)]


def _filter_lines(rows: list[tuple[str, list[Trade]]]) -> list[str]:
    out = [f"## 過濾條件（v10 突破即買、區間 {CURRENT_OR} 分鐘、保守進場價）", "",
           "| 分組 | 筆數 | 賺的 | 勝率 | 平均R | 扣成本R | 金額 |", "|---|---|---|---|---|---|---|"]
    for label, trades in rows:
        st = summarise(trades)
        if not st["n"]:
            out.append(f"| {label} | 0 | — | — | — | — | — |")
            continue
        out.append(f"| {label} | {st['n']} | {st['wins']} | {st['rate']}% | {st['avg_r']:+.2f} | "
                   f"{st['avg_net_r']:+.2f} | {st['amount']:+,} |")
    out += [
        "",
        f"- **離漲停**：進場價到當天漲停價還有幾 %。不到 {LIMIT_ROOM_PCT:g}% 的，目標常被漲停壓住，"
        "能賺的空間很小（10-16 亞電 1.7%）。",
        "- **一張就超過風險上限**：一張的停損風險已經超過單筆 4,000 元（10-16 台虹 9,000 元）。"
        "只有 1 張，也沒辦法先出一半。",
        "- 看「會被排除的」那幾列：如果它們明顯比較差，排除掉就有用；如果差不多，排除只是少做幾筆。",
        "- 排除後筆數會變少；筆數太少的那一列不能信。",
        "",
    ]
    return out


# ── 今天開盤 5 分鐘最熱（研究的 Stocks in Play）─────────────────────
# 10-16 使用者看完研究：「用今天開盤前 5 分鐘的量跟過去 14 天同時段比，挑最熱的 20 檔，
# 這一點感覺不錯」。研究：開盤 5 分鐘的量 ÷ 過去 14 天同時段的平均量，至少 1 倍、取最高的；
# 5 分鐘開盤區間、碰到區間高就買（觸價單）、停損、抱到收盤。我們一天最多 3 筆，所以取 3 檔。
# 排名用 09:00–09:05 的量，進場在 09:05 之後 —— 沒有偷看未來。
IN_PLAY_OR = 5
IN_PLAY_LOOKBACK = 14
IN_PLAY_MIN_HISTORY = 5          # 過去少於 5 天的資料就不算（剛上市、資料缺）
IN_PLAY_MIN_RVOL = 1.0
IN_PLAY_TOP = 3


def trading_days_before(day: str, n: int) -> list[str]:
    """day 之前的 n 個交易日（舊到新）。週末和休市表上的日子跳過。"""
    out, d = [], ddate.fromisoformat(day)
    while len(out) < n:
        d -= timedelta(days=1)
        if d.weekday() >= 5 or market_calendar.closed_reason(d.isoformat()):
            continue
        out.append(d.isoformat())
    return out[::-1]


def first_minutes_volume(bars, minutes: int = IN_PLAY_OR) -> float | None:
    """09:00 之後前 N 分鐘的量（K 棒 label 是結束時間：09:01～09:0N 那幾根）。沒有就 None。"""
    start = _t(config.SIGNAL["or_start"])
    end = (datetime.combine(ddate(2000, 1, 1), start) + timedelta(minutes=minutes)).time()
    vols = [b[5] for b in bars if start < b[0].time() <= end]
    return float(sum(vols)) if vols else None


def relative_volume(today_bars, history: list) -> float | None:
    """今天前 5 分鐘的量 ÷ 過去幾天同時段的平均。歷史不夠就 None（不知道，不是 0）。"""
    today = first_minutes_volume(today_bars)
    past = [v for v in (first_minutes_volume(b) for b in history) if v]
    if today is None or len(past) < IN_PLAY_MIN_HISTORY:
        return None
    return today / (sum(past) / len(past))


def kbars_to_days(kb) -> dict[str, list]:
    """一次抓好幾天的 kbars → {日期: [(時間, 開, 高, 低, 收, 量)]}。"""
    from broker import _bar_time
    cols = [list(getattr(kb, k, []) or []) for k in ("ts", "Open", "High", "Low", "Close", "Volume")]
    out: dict[str, list] = {}
    if not cols[0] or len({len(c) for c in cols}) != 1:
        return out
    for raw, o, h, l, c, v in zip(*cols):
        t = _bar_time(raw)
        if t is not None:
            out.setdefault(t.strftime("%Y-%m-%d"), []).append(
                (t, float(o), float(h), float(l), float(c), float(v)))
    return {d: sorted(rows, key=lambda r: r[0]) for d, rows in out.items()}


def pool_rows(payload: dict) -> list[dict]:
    """整個候選池：盯的 10 檔 + 沒盯的，照盤前名次。"""
    items = list(payload.get("items") or [])
    rest = list(payload.get("not_watched") or [])
    return ([dict(r, watched=True) for r in items] + [dict(r, watched=False) for r in rest])


def in_play_day(stocks: list[dict], histories: dict) -> list[dict]:
    """這一天最熱的 IN_PLAY_TOP 檔：相對量至少 IN_PLAY_MIN_RVOL 倍，由高到低。"""
    scored = []
    for s in stocks:
        rv = relative_volume(s.get("bars") or [], histories.get(str(s["code"])) or [])
        if rv is not None and rv >= IN_PLAY_MIN_RVOL:
            scored.append(dict(s, rvol=round(rv, 2)))
    scored.sort(key=lambda s: (-s["rvol"], s.get("rank") or 9999))
    return scored[:IN_PLAY_TOP]


def run_in_play(pool_days: list[tuple[str, list[dict], dict]]) -> dict:
    """pool_days = [(日期, 整個池子帶分鐘 K, {代號: 過去幾天的分鐘 K})]。"""
    six, capped, chosen, overlap, no_hist = [], 0, 0, 0, 0
    picked_days = []
    for d, stocks, hist in pool_days:
        top = in_play_day(stocks, hist)
        if not top:
            no_hist += 1
            continue
        chosen += len(top)
        overlap += sum(1 for s in top if s.get("watched"))
        t, c = replay_trigger_day(top, IN_PLAY_OR, limit=IN_PLAY_TOP)
        six += t
        capped += c
        picked_days.append((d, top))
    return {"six": six, "simple": resimple(six, bars_index(picked_days)), "capped": capped,
            "chosen": chosen, "overlap": overlap, "days": len(pool_days), "empty_days": no_hist}


def _in_play_lines(ip: dict, results: dict) -> list[str]:
    out = ["## 今天開盤 5 分鐘最熱（研究的選股方式）", "",
           "| 選股 | 進場 | 出場 | 筆數 | 賺的 | 勝率 | 平均R | 扣成本R | 金額 |",
           "|---|---|---|---|---|---|---|---|---|"]
    rows = (("v10 現在（昨天量前 10）", "三關、保守價", "v10 六條",
             results.get((CURRENT_OR, CAUTIOUS), ([], 0))[0]),
            (f"開盤 {IN_PLAY_OR} 分鐘最熱 {IN_PLAY_TOP} 檔", f"觸價單（{IN_PLAY_OR} 分鐘區間）",
             "v10 六條", ip.get("six", [])),
            (f"開盤 {IN_PLAY_OR} 分鐘最熱 {IN_PLAY_TOP} 檔", f"觸價單（{IN_PLAY_OR} 分鐘區間）",
             "停損＋13:25（研究版）", ip.get("simple", [])))
    for pick, entry, exit_, trades in rows:
        st = summarise(trades)
        if not st["n"]:
            out.append(f"| {pick} | {entry} | {exit_} | 0 | — | — | — | — | — |")
            continue
        out.append(f"| {pick} | {entry} | {exit_} | {st['n']} | {st['wins']} | {st['rate']}% | "
                   f"{st['avg_r']:+.2f} | {st['avg_net_r']:+.2f} | {st['amount']:+,} |")
    out += [
        "",
        f"- {ip.get('days', 0)} 天裡挑出 {ip.get('chosen', 0)} 檔，其中 {ip.get('overlap', 0)} 檔"
        "本來就在 v10 盯的 10 檔裡。"
        + (f"{ip['empty_days']} 天沒有挑出任何一檔（過去的資料不夠，或都沒有比平常熱）。"
           if ip.get("empty_days") else ""),
        f"- **最熱**＝今天 09:00–09:{IN_PLAY_OR:02d} 的量 ÷ 過去 {IN_PLAY_LOOKBACK} 個交易日同時段的"
        f"平均量，至少 {IN_PLAY_MIN_RVOL:g} 倍，從整個候選池 20 檔（盯的 + 沒盯的）裡取最高的 "
        f"{IN_PLAY_TOP} 檔。",
        f"- 排名只用 09:{IN_PLAY_OR:02d} 以前的量，進場在那之後 —— 盤中做得到。09:{IN_PLAY_OR:02d} "
        "排出來之後掛觸價單（多條件單）就好，不用搶快。",
        "- 跟研究還有差別：研究從 1,000 檔裡挑，這裡只從盤前的 20 檔裡挑；停損用 v10 的，"
        "不是研究的 ATR。",
        "",
    ]
    return out


# ── 均線出場（5 分 K）────────────────────────────────────
# 10-20 使用者：「盤前那一檔，開盤後能否繼續監看，用 5MA 及 20MA 告知盤中強弱，讓我
# 繼續抱或出場」。不做「你自己判斷」—— 做成明確的規則才驗證得了：停損照舊，其餘換成
# 5 分 K 的均線出場。5 分 K 收完才判、下一分鐘的開盤價出場：收到通知再手動賣得到。
# 均線要接著昨天的 K 棒算（看盤軟體也是這樣），不然 20MA 要到 10:40 才有。
MA_FAST = 5
MA_SLOW = 20
MA_BAR_MIN = 5
MA_BELOW = "停損＋5 分 K 收盤跌破 20MA"
MA_CROSS = "停損＋5MA 往下穿過 20MA"
# 10-20 使用者傳的影片：「不看交叉、不看數值」「跌破 20MA、反彈卻站不回來 → 今天不要再硬做」。
MA_FAIL = "停損＋跌破 20MA、下一根站不回來"
MA_MODES = (MA_BELOW, MA_CROSS, MA_FAIL)
MA_RESULT = premarket.MA_RESULT


def five_minute_closes(bars, minutes: int = MA_BAR_MIN) -> list[tuple[datetime, float]]:
    """1 分 K → 5 分 K 的 (收完的時間, 收盤)。label 是結束時間：09:01～09:05 是一根，
    09:00 那根（開盤集合競價）併進 09:05。盤中均線版用同一個切法（premarket）。"""
    out: dict[datetime, float] = {}
    for b in bars:
        out[premarket.five_min_end(b[0], minutes)] = b[4]
    return sorted(out.items())


_ma = premarket._ma


def ma_exit(bars, entry: float, stop: float, fired: datetime, seed=(), mode: str = MA_BELOW):
    """(結果, 出場價, 出場時間)。停損照舊（盤中碰到就出，券商停損單）；均線條件在
    5 分 K 收完時判，成立就用下一根 1 分 K 的開盤價出（收到通知再賣）。13:25 平倉。
    seed = 前一個交易日的 1 分 K，讓均線一開盤就有值。沒有之後的 K 棒 → None。"""
    prev = [c for _t, c in five_minute_closes(seed or [])]
    today = [b for b in bars if b[0].time() <= oc.FLATTEN_AT]
    buckets = dict(five_minute_closes(today))
    closes = list(prev)
    pending = False
    last = None
    started = False
    prev_fast = prev_slow = None
    broke = False                     # 影片版：上一根 5 分 K 收在 20MA 下面
    for i, (t, o, h, l, c, _v) in enumerate(today):
        if t >= fired + oc.BAR_SPAN:
            started = True
            if pending:
                return MA_RESULT, o, t.strftime("%H:%M:%S")
            if l <= stop:
                return oc.STOP, min(o, stop), t.strftime("%H:%M:%S")
            last = c
        if t in buckets:
            closes.append(buckets[t])
            fast, slow = _ma(closes, MA_FAST), _ma(closes, MA_SLOW)
            if started and t > fired and slow is not None:
                if mode == MA_BELOW:
                    hit = buckets[t] < slow
                elif mode == MA_FAIL:
                    below = buckets[t] < slow
                    hit, broke = below and broke, below
                else:
                    hit = (fast is not None and prev_fast is not None and prev_slow is not None
                           and fast < slow and prev_fast >= prev_slow)
                if hit:
                    if t.time() >= oc.FLATTEN_AT:
                        return MA_RESULT, c, t.strftime("%H:%M:%S")
                    pending = True
            prev_fast, prev_slow = fast, slow
    if last is None:
        return None
    return oc.FLAT, last, oc.FLATTEN_AT.strftime("%H:%M:%S")


def reexit(trades: list[Trade], bars_of: dict, exit_fn) -> list[Trade]:
    """同一批進場，出場換成 exit_fn(那天的分鐘 K, 那一筆) → (結果, 出場價, 出場時間)。"""
    out = []
    for t in trades:
        got = exit_fn(bars_of.get((t.date, t.code)) or [], t)
        if got is None:
            continue
        result, price, at = got
        n = Trade(date=t.date, code=t.code, name=t.name, fired=t.fired, or_high=t.or_high,
                  entry=t.entry, stop=t.stop, lots=t.lots, vol_ratio=t.vol_ratio,
                  batch=t.batch, result=result, exit_price=round(price, 2), exit_at=at,
                  limit_room_pct=t.limit_room_pct, oversized=t.oversized)
        pct, r = exits.blended(t.entry, t.stop, t.lots, None, price)
        _finish(n, t.entry, t.stop, r, pct, at, t.fired)
        out.append(n)
    return out


def prev_day_index(pool_days) -> dict:
    """{(日期, 代號): 前一個交易日的分鐘 K}，從「開盤 5 分鐘最熱」抓過的歷史拿。"""
    return {(d, code): (h[-1] if h else []) for d, _s, hist in pool_days
            for code, h in hist.items()}


def run_ma(days, results: dict, picks, pool_days) -> dict:
    idx = bars_index(days)
    seeds = prev_day_index(pool_days)
    pick_trades = [t for t in (pick_trade(d, p, b) for d, p, b in picks) if t]
    pick_bars = {(d, str(p["code"])): b for d, p, b in picks}
    v10 = results.get((CURRENT_OR, CAUTIOUS), ([], 0))[0]

    def with_mode(mode):
        return lambda bars, t: ma_exit(bars, t.entry, t.stop, t.fired,
                                       seeds.get((t.date, t.code)) or [], mode)
    out = {}
    for label, trades, bars_of in (("v10", v10, idx), ("pick", pick_trades, pick_bars)):
        out[(label, "six")] = trades
        for mode in MA_MODES:
            out[(label, mode)] = reexit(trades, bars_of, with_mode(mode))
    out["seeded"] = sum(1 for t in v10 + pick_trades if seeds.get((t.date, t.code)))
    out["total"] = len(v10) + len(pick_trades)
    return out


def _row(label: str, exit_: str, trades: list[Trade]) -> str:
    st = summarise(trades)
    if not st["n"]:
        return f"| {label} | {exit_} | 0 | — | — | — | — | — | — |"
    return (f"| {label} | {exit_} | {st['n']} | {st['wins']} | {st['rate']}% | "
            f"{st['avg_r']:+.2f} | {st['avg_net_r']:+.2f} | {st['amount']:+,} | {st['avg_min']} 分 |")


def _ma_lines(ma: dict) -> list[str]:
    out = ["## 均線出場（5 分 K、停損照舊）", "",
           "| 進場 | 出場 | 筆數 | 賺的 | 勝率 | 平均R | 扣成本R | 金額 | 平均持有 |",
           "|---|---|---|---|---|---|---|---|---|"]
    for key, label in (("pick", "盤前首選（開盤價）"), ("v10", "v10 三關（保守價）")):
        out.append(_row(label, "v10 六條（現在）", ma.get((key, "six"), [])))
        for mode in MA_MODES:
            out.append(_row(label, mode, ma.get((key, mode), [])))
    out += [
        "",
        "- 5 分 K 收完才判；成立的話用**下一分鐘的開盤價**出 —— 收到通知再手動賣，來得及。",
        "- 停損照舊（券商停損單，碰到就出）；13:25 還沒出就平倉。沒有先出一半、移動停利、"
        "跌破開盤價／區間／均價線、量縮。",
        f"- 均線接著前一個交易日的 K 棒算（{ma.get('seeded', 0)}/{ma.get('total', 0)} 筆有前一天的資料；"
        "沒有的，20MA 要到 10:40 左右才有，之前只看停損）。",
        "- **跌破 20MA、下一根站不回來**（10-20 使用者傳的影片：不看交叉，看跌破後站不站得回來）："
        "一根 5 分 K 收在 20MA 下面，下一根還是收在下面才出；中間站回去就重算。",
        "- **5MA 往下穿過 20MA** 只在「穿過去那一根」出；進場時 5MA 已經在 20MA 下面的，"
        "要等它先站上去再跌破才出。",
        "- 首選筆數很少，主要看 v10 那幾列：同一批進場，只換出場。",
        "",
    ]
    return out


# ── 手動版：多條件單（觸價＋總量）─────────────────────────
# 10-20 使用者：「還是買不到，其他買到的也會虧」→「請以手動的方式來設計程式，需要改的
# 是開盤後的」。手動版：09:05 前把多條件單掛好（成交價 ≥ 突破價 且 今天總量 ≥ N），
# 不跟價格賽跑。出場只用 App 設得了的：停損單、移動出場單（漲到先出一半的價位才開始，
# 從最高點回落 1.5%、不低於成本）、13:25 自己平倉。N 用這一張決定。
VOL_GRID = (0, 5, 10, 15, 20)      # 今天總量 ≥ 昨天全天量的幾 %
MANUAL_ALL = "盯的 10 檔都掛，先成交先算，滿 3 檔取消其他"
MANUAL_TOP = "只掛盤前排名前 3 檔"
MANUAL_ACTIVE_AFTER = dtime(9, 5)  # 09:05 推掛單清單，之後才算掛好
TRAIL = manual.TRAIL


def manual_exit(bars, entry: float, stop: float, half_at: float, fired: datetime):
    """停損單＋移動出場單＋13:25 —— 跟盤中手動版同一個函式（manual.exit_walk）。"""
    return manual.exit_walk(bars, entry, stop, half_at, fired)


def manual_day(stocks: list[dict], prev_volume: dict, vol_pct: float, top_only: bool = False,
               limit: int | None = None) -> tuple[list[Trade], int]:
    """一天。每檔一張多條件單：成交價 ≥ 突破價（區間高 + 緩衝）且今天總量 ≥ 昨天全天量
    × vol_pct %。09:05 之後第一根兩個都成立的 K 成交（開盤已經跳過突破價就是開盤價）。
    先成交先算、滿 3 檔不再算。回傳 (成交的, 因為滿了沒算的)。"""
    cfg = config.SIGNAL
    limit = config.RISK["max_signals_per_day"] if limit is None else limit
    or_end, _batch, win_end = schedule(CURRENT_OR)
    pool = sorted(stocks, key=lambda s: s.get("rank") or 9999)
    if top_only:
        pool = pool[:limit]
    hits = []
    for s in pool:
        bars = s.get("bars") or []
        rng = opening_range(bars, CURRENT_OR)
        need = prev_volume.get(str(s["code"]))
        if not rng or (vol_pct and not need):
            continue
        trigger = rng[0] * (1 + cfg["breakout_buffer_pct"] / 100)
        cum = 0.0
        for b in bars:
            cum += b[5]
            if not (MANUAL_ACTIVE_AFTER < b[0].time() <= win_end):
                continue
            if b[2] >= trigger and cum >= (need or 0) * vol_pct / 100:
                hits.append((b, s, rng[0], trigger))
                break
    hits.sort(key=lambda x: (x[0][0], x[1].get("rank") or 9999, str(x[1]["code"])))
    sent, capped = [], 0
    for b, s, or_high, trigger in hits:
        if len(sent) >= limit:
            capped += 1
            continue
        entry = config.round_to_tick(max(trigger, b[1]), "up")
        plan = _plan(s, or_high, s["bars"][0][1], entry, b[0].time())
        if plan is None:
            continue
        tr = Trade(date=b[0].strftime("%Y-%m-%d"), code=str(s["code"]), name=s.get("name", ""),
                   fired=b[0], or_high=or_high, entry=plan["entry"], stop=plan["stop"],
                   lots=plan["lots"], vol_ratio=0.0, batch=False)
        got = manual_exit(s["bars"], plan["entry"], plan["stop"],
                          plan.get("half_at") or float("inf"), b[0])
        if got is None:
            tr.result, tr.exit_price = oc.FLAT, plan["entry"]
        else:
            tr.result, price, tr.exit_at = got
            tr.exit_price = round(price, 2)
            pct, r = exits.blended(plan["entry"], plan["stop"], plan["lots"], None, price)
            _finish(tr, plan["entry"], plan["stop"], r, pct, tr.exit_at, b[0])
        sent.append(tr)
    return sent, capped


def prev_volumes(pool_days) -> dict:
    """{日期: {代號: 前一個交易日的全天量}}（跟今天的總量同一個單位：分鐘 K 的量）。"""
    out = {}
    for d, _s, hist in pool_days:
        out[d] = {code: sum(b[5] for b in h[-1]) for code, h in hist.items() if h and h[-1]}
    return out


def run_manual(days, pool_days) -> dict:
    vols = prev_volumes(pool_days)
    out = {}
    for top in (False, True):
        for pct in VOL_GRID:
            trades, capped = [], 0
            for d, stocks in days:
                t, c = manual_day(stocks, vols.get(d, {}), pct, top_only=top)
                trades += t
                capped += c
            out[(top, pct)] = (trades, capped)
    return out


def _manual_lines(manual: dict, results: dict) -> list[str]:
    out = ["## 手動版：多條件單（觸價＋總量）、停損＋移動出場＋13:25", "",
           "| 掛哪幾檔 | 總量門檻（昨天全天量的） | 筆數 | 賺的 | 勝率 | 平均R | 扣成本R | 金額 | 滿了沒算 |",
           "|---|---|---|---|---|---|---|---|---|"]
    for top, label in ((False, MANUAL_ALL), (True, MANUAL_TOP)):
        for pct in VOL_GRID:
            trades, capped = manual.get((top, pct), ([], 0))
            st = summarise(trades)
            name = "不設（只看價格）" if pct == 0 else f"{pct}%"
            if not st["n"]:
                out.append(f"| {label} | {name} | 0 | — | — | — | — | — | {capped} |")
                continue
            out.append(f"| {label} | {name} | {st['n']} | {st['wins']} | {st['rate']}% | "
                       f"{st['avg_r']:+.2f} | {st['avg_net_r']:+.2f} | {st['amount']:+,} | {capped} |")
    for mode, label in ((OPTIMISTIC, "（對照）v10 剛好買在突破價"), (CAUTIOUS, "（對照）v10 那一分鐘收盤價")):
        st = summarise(results.get((CURRENT_OR, mode), ([], 0))[0])
        if st["n"]:
            out.append(f"| {label} | — | {st['n']} | {st['wins']} | {st['rate']}% | "
                       f"{st['avg_r']:+.2f} | {st['avg_net_r']:+.2f} | {st['amount']:+,} | — |")
    out += [
        "",
        "- **多條件單**：成交價 ≥ 突破價（09:00–09:02 最高 +0.1%）**而且**今天累計總量 ≥ 昨天全天量的 X %，"
        "兩個都成立才買。09:05 之後才算掛好（推掛單清單、你設好單要時間），09:30 截止。",
        "- 成交價：碰到的那一分鐘開盤已經在突破價之上就是開盤價，不然是突破價。沒算送單後再跳一兩檔，"
        "所以還是**偏樂觀**一點。",
        "- 出場：停損單＋移動出場單（漲到「先出一半」的價位才開始，從最高點回落 1.5%、不低於成本）"
        "＋13:25 自己平倉。沒有先出一半、跌破均價線那些。",
        "- **永豐的移動出場單能不能設「漲到某個價才開始」還沒確認**；不能的話要改成手動在那個價位設。",
        "- 一次比 10 列，總有一列剛好好看 —— 選的是**下一輪要驗證的**門檻，不是直接拿來下單。",
        "",
    ]
    return out


# ── 第一版重跑（同一批日子）──────────────────────────────
# 10-21 使用者：「之前因為設了時間點，感覺失準，感覺第一版比較好」。outcomes.csv：早期（未標版本，
# 主要是第一版）25 筆 +0.37R、v10 21 筆 +0.09R —— 但時期不同（9 月 vs 10 月）。這一張把第一版
# 的規則放到 v10 這幾天重跑，同樣的日子、同樣的名單，分得出是「規則」還是「行情」。
# 第一版（9-20 的 config）：區間 09:00–09:15、突破 +0.1%、站上均價線、量能 1.8 倍，12:30 前
# 突破就發（沒有批次），一天最多 5 個、同一檔一次；停損進場價 -1.5%、目標 1.5R；碰到就出，
# 不然 13:25 平倉。張數照現在的單筆風險 4,000 元算（金額才跟 v10 比得起來）。
V1_OR = 15
V1_WINDOW_END = dtime(12, 30)
V1_STOP_PCT = 1.5
V1_RR = 1.5
V1_LIMIT = 5


def v1_exit(bars, entry: float, stop: float, target: float, fired: datetime):
    """(結果, 出場價, 出場時間)。停損、目標碰到就出（同一根兩個都碰到算停損，保守）；
    一開就跳過去用開盤價。13:25 平倉。訊號那一分鐘不判。沒有之後的 K 棒 → None。"""
    last = None
    for t, o, h, l, c, _v in bars:
        if t < fired + oc.BAR_SPAN:
            continue
        if t.time() > oc.FLATTEN_AT:
            break
        if l <= stop:
            return oc.STOP, min(o, stop), t.strftime("%H:%M:%S")
        if h >= target:
            return oc.TARGET, max(o, target), t.strftime("%H:%M:%S")
        last = c
    if last is None:
        return None
    return oc.FLAT, last, oc.FLATTEN_AT.strftime("%H:%M:%S")


def v1_plan(entry: float) -> dict | None:
    stop = config.round_to_tick(entry * (1 - V1_STOP_PCT / 100), "up")
    if stop >= entry:
        return None
    target = config.round_to_tick(entry + (entry - stop) * V1_RR, "up")
    risk_per_lot = round((entry - stop) * 1000, 2)
    return {"entry": entry, "stop": stop, "target": target,
            "lots": max(1, int(config.RISK["per_trade_risk"] // risk_per_lot))}


def replay_v1_day(stocks: list[dict], optimistic: bool = False) -> tuple[list[Trade], int]:
    """一天。每檔第一次三關都過（09:15 之後、12:30 以前）就發，照時間先後，最多 5 個。"""
    cfg = config.SIGNAL
    or_start = _t(cfg["or_start"])
    or_end, _batch, _win = schedule(V1_OR)
    hits = []
    for s in stocks:
        bars = s.get("bars") or []
        rng = opening_range(bars, V1_OR)
        if not rng:
            continue
        wbars = _wn(bars)
        trigger = rng[0] * (1 + cfg["breakout_buffer_pct"] / 100)
        for b in wbars:
            if not (or_end < b[0].time() <= V1_WINDOW_END):
                continue
            vr = _gates(wbars, b, trigger, or_start)
            if vr is not None:
                hits.append((b, vr, s, rng[0], trigger))
                break
    hits.sort(key=lambda x: (x[0][0], x[2].get("rank") or 9999, str(x[2]["code"])))
    sent, capped = [], 0
    for b, vr, s, or_high, trigger in hits:
        if len(sent) >= V1_LIMIT:
            capped += 1
            continue
        entry = config.round_to_tick(trigger if optimistic else max(trigger, b[3]), "up")
        lu = config.limit_up(s.get("prev_close") or 0)
        plan = v1_plan(entry)
        if plan is None or (lu and entry >= lu):
            continue
        tr = Trade(date=b[0].strftime("%Y-%m-%d"), code=str(s["code"]), name=s.get("name", ""),
                   fired=b[0], or_high=or_high, entry=entry, stop=plan["stop"],
                   lots=plan["lots"], vol_ratio=round(vr, 2), batch=False)
        got = v1_exit(s["bars"], entry, plan["stop"], plan["target"], b[0])
        if got is None:
            tr.result, tr.exit_price = oc.FLAT, entry
        else:
            tr.result, price, tr.exit_at = got
            tr.exit_price = round(price, 2)
            pct, r = exits.blended(entry, plan["stop"], plan["lots"], None, price)
            _finish(tr, entry, plan["stop"], r, pct, tr.exit_at, b[0])
        sent.append(tr)
    return sent, capped


def run_v1(days) -> dict:
    out = {}
    for mode, optimistic in ((CAUTIOUS, False), (OPTIMISTIC, True)):
        trades, capped = [], 0
        for _d, stocks in days:
            t, c = replay_v1_day(stocks, optimistic)
            trades += t
            capped += c
        out[mode] = (trades, capped)
    return out


def _v1_lines(v1: dict, results: dict) -> list[str]:
    out = ["## 第一版重跑（同一批日子）", "",
           "| 規則 | 進場價 | 筆數 | 賺的 | 勝率 | 平均R | 扣成本R | 平均％ | 金額 | 平均持有 |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    rows = (("v10 現在", "那一分鐘收盤價", results.get((CURRENT_OR, CAUTIOUS), ([], 0))[0]),
            ("v10 現在", "剛好買在突破價", results.get((CURRENT_OR, OPTIMISTIC), ([], 0))[0]),
            ("第一版", "那一分鐘收盤價", v1.get(CAUTIOUS, ([], 0))[0]),
            ("第一版", "剛好買在突破價", v1.get(OPTIMISTIC, ([], 0))[0]))
    for rule, entry, trades in rows:
        st = summarise(trades)
        if not st["n"]:
            out.append(f"| {rule} | {entry} | 0 | — | — | — | — | — | — | — |")
            continue
        avg_pct = sum(t.net_pct for t in trades) / len(trades)
        out.append(f"| {rule} | {entry} | {st['n']} | {st['wins']} | {st['rate']}% | "
                   f"{st['avg_r']:+.2f} | {st['avg_net_r']:+.2f} | {avg_pct:+.2f}% | "
                   f"{st['amount']:+,} | {st['avg_min']} 分 |")
    reasons = summarise(v1.get(CAUTIOUS, ([], 0))[0]).get("reasons", {})
    out += [
        "",
        "- **第一版**：區間 09:00–09:15；突破 +0.1%、站上均價線、量能 1.8 倍；09:15 之後突破就發"
        "（沒有 09:05 批次），12:30 截止，一天最多 5 個、同一檔一次。停損進場價 -1.5%、目標 1.5R"
        "（約 +2.25%），碰到就出，不然 13:25 平倉。",
        "- 停損寬度不一樣（第一版 1.5%、v10 約 3%），同樣漲 1.5%，第一版是 +1R、v10 是 +0.5R —— "
        "**看「平均％」比較公平**（扣過來回成本）。",
        "- 張數照現在的單筆風險 4,000 元算，金額跟 v10 比得起來（第一版當時是 2,000 元）。",
        "- 量能倍數用 v10 的算法近似（第一版當時是 5 分鐘速率比），會有一點出入。",
        "- 第一版停損、目標都是固定價位：進場後在 App 掛一張**母子單**就好，手動做得到。",
        "- 第一版出場原因（收盤價進場）："
        + ("、".join(f"{k} {v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])) or "—"),
        "",
    ]
    return out


# ── 大盤 ──────────────────────────────────────────────
# 跟 broker.MARKET_PROXY 同一檔：kbars 拿得到分鐘 K、跟加權指數走勢幾乎一樣。
MARKET_PROXY = "0050"
MKT_UP = "進場時大盤在開盤價之上"
MKT_DOWN = "進場時大盤在開盤價之下"
DAY_RED = "大盤當天收紅（收盤才知道）"
DAY_BLACK = "大盤當天收黑（收盤才知道）"
MKT_UNKNOWN = "大盤資料缺"
MARKET_GROUPS = (MKT_UP, MKT_DOWN, DAY_RED, DAY_BLACK, MKT_UNKNOWN)


def market_state(mbars, at: datetime) -> str | None:
    """at 那一分鐘（含）以前最後一根的收盤，跟大盤今天的開盤價比。平盤算「之上」。
    只用 at 以前的 K 棒 —— 這個分組拿去當規則，盤中做得到。"""
    if not mbars:
        return None
    seen = [b for b in mbars if b[0] <= at]
    if not seen:
        return None
    return MKT_UP if seen[-1][4] >= mbars[0][1] else MKT_DOWN


def day_color(mbars) -> str | None:
    """收盤比開盤高 → 收紅（紅 K）；平或低 → 收黑。事後資訊，只能看、不能當規則。"""
    if not mbars:
        return None
    return DAY_RED if mbars[-1][4] > mbars[0][1] else DAY_BLACK


def run_market(trades: list[Trade], markets: dict) -> dict:
    """{分組: [這一組的訊號]}。同一筆會同時在「進場當下」和「當天收盤」各出現一次。"""
    out = {k: [] for k in MARKET_GROUPS}
    for t in trades:
        mbars = markets.get(t.date)
        now, day = market_state(mbars, t.fired), day_color(mbars)
        if now is None or day is None:
            out[MKT_UNKNOWN].append(t)
            continue
        out[now].append(t)
        out[day].append(t)
    return out


def _market_lines(groups: dict) -> list[str]:
    out = [f"## 大盤（v10 突破即買、區間 {CURRENT_OR} 分鐘、保守進場價）", "",
           "| 分組 | 筆數 | 賺的 | 勝率 | 平均R | 扣成本R | 金額 |", "|---|---|---|---|---|---|---|"]
    for label in MARKET_GROUPS:
        s = summarise(groups.get(label, []))
        if not s["n"]:
            if label != MKT_UNKNOWN:
                out.append(f"| {label} | 0 | — | — | — | — | — |")
            continue
        out.append(f"| {label} | {s['n']} | {s['wins']} | {s['rate']}% | {s['avg_r']:+.2f} | "
                   f"{s['avg_net_r']:+.2f} | {s['amount']:+,} |")
    out += [
        "",
        f"- 大盤用 {MARKET_PROXY}（元大台灣50）的分鐘 K 代表，跟加權指數走勢幾乎一樣。",
        "- **前兩列可以變成規則**：進場那一分鐘就知道大盤在開盤價之上還是之下。"
        "如果「之下」那一列明顯比較差，v11 可以考慮「大盤在開盤價之下就不做多」。",
        "- **後兩列不能變成規則**：收紅收黑要收盤才知道，只能拿來確認「大盤不好的日子，突破比較容易失敗」"
        "這個觀察對不對。",
        "- 前兩列加起來、後兩列加起來，都是同一批訊號。",
        "",
    ]
    return out


def run_entries(days: list[tuple[str, list[dict]]], picks: list[tuple[str, dict, list]],
                results: dict) -> dict:
    """三種進場方式（區間 2 分鐘、保守進場價）。突破即買直接拿主表那一格。"""
    pull, capped = [], 0
    for _d, stocks in days:
        t, c = replay_pullback_day(stocks)
        pull += t
        capped += c
    chosen = [t for t in (pick_trade(d, p, b) for d, p, b in picks) if t]
    return {BREAKOUT: results[(CURRENT_OR, CAUTIOUS)], PULLBACK: (pull, capped),
            PICK: (chosen, 0)}


def summarise(trades: list[Trade]) -> dict:
    if not trades:
        return {"n": 0}
    wins = [t for t in trades if t.net_pct > 0]
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t.result] = reasons.get(t.result, 0) + 1
    return {"n": len(trades), "wins": len(wins),
            "rate": round(len(wins) / len(trades) * 100),
            "avg_r": round(sum(t.r_multiple for t in trades) / len(trades), 2),
            "avg_net_r": round(sum(t.net_r for t in trades) / len(trades), 2),
            "total_r": round(sum(t.r_multiple for t in trades), 2),
            "avg_min": round(sum(t.held_min for t in trades) / len(trades)),
            "stops": sum(1 for t in trades if t.result == oc.STOP),
            "amount": round(sum(t.net_pct / 100 * t.entry * 1000 * t.lots for t in trades)),
            "reasons": reasons}


def crosscheck(replayed: dict[str, set], actual: dict[str, set]) -> list[str]:
    """2 分鐘版重建出來的訊號，跟盤中真的發出的對答案。日期 → 代號集合。"""
    lines, missed, extra = [], [], []
    for d in sorted(set(replayed) | set(actual)):
        r, a = replayed.get(d, set()), actual.get(d, set())
        missed += [f"{d[5:]} {c}" for c in sorted(a - r)]
        extra += [f"{d[5:]} {c}" for c in sorted(r - a)]
    total = sum(len(v) for v in actual.values())
    if not actual:
        return ["> ⚠️ **無法對答案**：outcomes.csv 裡沒有這段期間的訊號紀錄。", ""]
    if not missed and not extra:
        return [f"> ✅ **對過答案了**：2 分鐘版重建出來的訊號，跟盤中真的發出的 "
                f"{total} 個完全一致。", ""]
    lines.append(f"> 🛑 **2 分鐘版重建跟盤中紀錄有出入**（盤中共 {total} 個）。"
                 "下面每一列都是同一套近似算的，彼此可以比；但絕對數字不能全信。")
    if missed:
        lines.append(f"> - 盤中有發、重建沒有：{'、'.join(missed)}")
    if extra:
        lines.append(f"> - 重建會發、盤中沒有：{'、'.join(extra)}")
    return lines + [""]


def render(results: dict, days: list[str], check: list[str], missing: list,
           entries: dict | None = None, recomputed: int = 0,
           stops: dict | None = None, market: dict | None = None,
           trigger: tuple | None = None, simple: dict | None = None,
           filters: list | None = None, in_play: dict | None = None,
           ma: dict | None = None, manual: dict | None = None,
           v1: dict | None = None, pulse: dict | None = None) -> list[str]:
    """results[(區間分鐘, 樂觀/保守)] = (trades, 額度滿了沒發的檔數)。"""
    first, last = (days[0], days[-1]) if days else ("—", "—")
    out = [
        "# whatif —— 開盤區間要看幾分鐘",
        "",
        "> **先讀這三句。**",
        f"> 1. 一次比 {len(GRID_OR)} 種區間，總有一種「剛好」最好看 —— 那可能只是運氣。"
        "比出來的結果只能當**下一輪要驗證的新規則**，不能直接拿來下單。",
        "> 2. 這是用分鐘 K 重建的：量能倍數、均價線都是近似（見 whynot.py）。",
        "> 3. 每一種區間都重跑**當天監看的全部股票**（盤前存檔的名單），不是只重跑有發訊號的。",
        "",
    ]
    out += check
    out += [
        f"期間：{first} ～ {last}，共 {len(days)} 個交易日。",
        "規則：v10 全部照舊（三關進場、批次排序、上限 "
        f"{config.RISK['max_signals_per_day']} 檔、六條出場），只換開盤區間。"
        "批次＝區間結束後 3 分鐘，進場窗口＝區間結束後 28 分鐘。",
        "",
    ]
    if missing:
        out += [f"⚠️ {len(missing)} 檔取不到分鐘 K，已排除：{'、'.join(missing[:8])}"
                + ("…" if len(missing) > 8 else ""), ""]
    for mode, desc in ((CAUTIOUS, "即時發的用那一分鐘的收盤價進場（比較接近實際）"),
                       (OPTIMISTIC, "即時發的用突破價進場（剛好買在突破點）")):
        out += [f"## {mode}：{desc}", "",
                "09:05 那一批兩種算法相同（都用發出當下的價格）。", "",
                "| 區間 | 筆數 | 賺的 | 勝率 | 平均R | 合計R | 平均持有 | 額度滿了沒發 |",
                "|---|---|---|---|---|---|---|---|"]
        for orm in GRID_OR:
            trades, capped = results.get((orm, mode), ([], 0))
            s = summarise(trades)
            name = f"{orm} 分" + ("（現在）" if orm == CURRENT_OR else "")
            if not s["n"]:
                out.append(f"| {name} | 0 | — | — | — | — | — | {capped} |")
                continue
            out.append(f"| {name} | {s['n']} | {s['wins']} | {s['rate']}% | "
                       f"{s['avg_r']:+.2f} | {s['total_r']:+.2f} | {s['avg_min']} 分 | "
                       f"{capped} |")
        out.append("")
    if entries:
        out += _entry_lines(entries, recomputed)
    if stops:
        out += _stop_lines(stops)
    if market:
        out += _market_lines(market)
    if trigger is not None:
        out += _trigger_lines(trigger, results)
    if simple is not None:
        out += _simple_lines(simple)
    if filters is not None:
        out += _filter_lines(filters)
    if in_play is not None:
        out += _in_play_lines(in_play, results)
    if v1 is not None:
        out += _v1_lines(v1, results)
    if manual is not None:
        out += _manual_lines(manual, results)
    if ma is not None:
        out += _ma_lines(ma)
    if pulse is not None:
        out += pulsecheck.lines(pulse)
    if results.get((CURRENT_OR, CAUTIOUS)):
        out += _chase_lines(results.get((CURRENT_OR, OPTIMISTIC), ([], 0))[0],
                            results[(CURRENT_OR, CAUTIOUS)][0])
    out += ["## 出場原因（保守）", "", "| 區間 | 出場原因 |", "|---|---|"]
    for orm in GRID_OR:
        s = summarise(results.get((orm, CAUTIOUS), ([], 0))[0])
        why = "、".join(f"{k} {v}" for k, v in sorted(
            s.get("reasons", {}).items(), key=lambda kv: -kv[1])) or "—"
        out.append(f"| {orm} 分 | {why} |")
    out += ["", "## 每一筆（保守，開盤區間各種長度）", "",
            "| 區間 | 日期 | 代號 | 名稱 | 進場時間 | 進場 | 停損 | 張數 | 量能 | 出場 | 出場價 | R |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for orm in GRID_OR:
        for t in sorted(results.get((orm, CAUTIOUS), ([], 0))[0],
                        key=lambda x: (x.date, x.fired)):
            out.append(f"| {orm} 分 | {t.date[5:]} | {t.code} | {t.name} | "
                       f"{t.fired.strftime('%H:%M')}{'（批次）' if t.batch else ''} | "
                       f"{t.entry:.2f} | {t.stop:.2f} | {t.lots} | {t.vol_ratio:.2f}x | "
                       f"{t.result} {t.exit_at[:5]} | {t.exit_price:.2f} | "
                       f"{t.r_multiple:+.2f} |")
    return out


def _entry_lines(entries: dict, recomputed: int) -> list[str]:
    out = [f"## 三種進場方式（區間 {CURRENT_OR} 分鐘、保守進場價、出場都照 v10）", "",
           "| 進場方式 | 筆數 | 賺的 | 勝率 | 平均R | 扣成本R | 合計R | 平均持有 | 額度滿了沒發 |",
           "|---|---|---|---|---|---|---|---|---|"]
    for label in (BREAKOUT, PULLBACK, PICK):
        trades, capped = entries.get(label, ([], 0))
        s = summarise(trades)
        if not s["n"]:
            out.append(f"| {label} | 0 | — | — | — | — | — | — | {capped} |")
            continue
        out.append(f"| {label} | {s['n']} | {s['wins']} | {s['rate']}% | {s['avg_r']:+.2f} | "
                   f"{s['avg_net_r']:+.2f} | {s['total_r']:+.2f} | {s['avg_min']} 分 | {capped} |")
    out += [
        "",
        f"- **回踩再買**：先有一次 v10 會買的突破；之後低點回到區間高 +{PULLBACK_BAND_PCT:g}% 以內、"
        "量比突破那一根小；再有一根收盤高過前一根高點、站上均價線才買。中途收回區間就不買。"
        "一路漲上去沒回踩的，買不到 —— 那也算在結果裡。",
        "- **盤前首選**：一天最多 1 筆，不受 3 檔額度限制，所以筆數跟另外兩列不能直接比總和，"
        "要看平均。",
    ]
    if recomputed:
        out.append(f"- 其中 {recomputed} 天的首選是**用現在的公式重算的**（10-14 以前還沒有首選）。")
    out += ["- 三列還是同一批日子、同一套近似，比較的是彼此，不是絕對數字。", ""]
    return out


# ── 資料 ──────────────────────────────────────────────
def archived_days(since: str, until: str) -> list[tuple[str, dict]]:
    """journal/ 裡 since～until（含）有存檔、而且有開盤的日子：[(日期, 名單)]。"""
    out = []
    for path in sorted(config.JOURNAL_DIR.glob("watchlist-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("%s 讀不到：%s", path.name, e)
            continue
        d = str(payload.get("date") or "")
        if not (since <= d <= until) or market_calendar.closed_reason(d):
            continue
        out.append((d, payload))
    return out


def _cache_path(date: str, code: str):
    return CACHE_DIR / f"{date.replace('-', '')}-{code}.json"


def load_cached(date: str, code: str):
    path = _cache_path(date, code)
    if not path.exists():
        return None
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return [(datetime.fromisoformat(r[0]), *map(float, r[1:])) for r in rows]
    except (OSError, ValueError, TypeError, IndexError) as e:
        log.warning("%s 快取壞了，重抓：%s", path.name, e)
        return None


def save_cached(date: str, code: str, bars) -> None:
    """只存已經收盤的日子 —— 盤中存下來的是半天的 K 棒，之後會一直被當成整天。"""
    if not bars or date >= ddate.today().isoformat():
        return
    path = _cache_path(date, code)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([[b[0].isoformat(), *b[1:]] for b in bars]),
                        encoding="utf-8")
    except OSError as e:
        log.warning("%s 快取寫不進去：%s", path.name, e)


def stocks_for(day: str, payload: dict, fetch) -> tuple[list[dict], list[str]]:
    """那一天的名單 + 分鐘 K。fetch(code, date) 是去券商抓的那一個（有快取就不叫）。"""
    stocks, missing = [], []
    for n, item in enumerate(payload.get("items") or [], 1):
        code = str(item["code"])
        bars = load_cached(day, code)
        if bars is None:
            bars = fetch(code, day)
            save_cached(day, code, bars)
        if not bars:
            missing.append(f"{day[5:]} {code}")
            continue
        stocks.append({"code": code, "name": item.get("name", ""), "rank": n,
                       "prev_close": float(item["prev_close"]),
                       "amplitude_pct": item.get("avg_amplitude_pct") or item.get("amplitude_pct"),
                       "bars": bars})
    return stocks, missing


def pick_for(day: str, payload: dict, stocks: list[dict], fetch):
    """(日期, 首選, 分鐘 K)。首選不在盯的那 10 檔裡，就另外抓它的分鐘 K（有快取用快取）。"""
    pick = pick_of(payload)
    if not pick:
        return None
    code = str(pick["code"])
    bars = next((x["bars"] for x in stocks if x["code"] == code), None)
    if bars is None:
        bars = load_cached(day, code)
        if bars is None:
            bars = fetch(code, day)
            save_cached(day, code, bars)
    return day, pick, bars


def market_bars(day: str, fetch):
    """那一天大盤（0050）的分鐘 K，有快取用快取。"""
    bars = load_cached(day, MARKET_PROXY)
    if bars is None:
        bars = fetch(MARKET_PROXY, day)
        save_cached(day, MARKET_PROXY, bars)
    return bars


def pool_days_for(archived: list[tuple[str, dict]], fetch_range) -> tuple[list, list[str]]:
    """每一天：整個候選池帶當天分鐘 K，加上每一檔過去 IN_PLAY_LOOKBACK 天的分鐘 K。
    一檔一次抓一整段（不是一天一次）—— kbars 有流量上限。抓過的照樣存進快取。"""
    need: dict[str, set] = {}
    for d, payload in archived:
        for r in pool_rows(payload):
            need.setdefault(str(r["code"]), set()).update(
                [d] + trading_days_before(d, IN_PLAY_LOOKBACK))
    bars: dict[tuple[str, str], list] = {}
    missing = []
    for code, dates in sorted(need.items()):
        got = {d: load_cached(d, code) for d in dates}
        if any(v is None for v in got.values()):
            fetched = fetch_range(code, min(dates), max(dates)) or {}
            for d in dates:
                if got[d] is None:
                    got[d] = fetched.get(d) or []
                    save_cached(d, code, got[d])
        for d, b in got.items():
            bars[(d, code)] = b or []
    out = []
    for d, payload in archived:
        stocks, hist = [], {}
        for n, r in enumerate(pool_rows(payload), 1):
            code = str(r["code"])
            today = bars.get((d, code)) or []
            if not today:
                missing.append(f"{d[5:]} {code}")
                continue
            stocks.append({"code": code, "name": r.get("name", ""), "rank": n,
                           "watched": r.get("watched", False),
                           "prev_close": float(r["prev_close"]),
                           "amplitude_pct": r.get("avg_amplitude_pct") or r.get("amplitude_pct"),
                           "bars": today})
            hist[code] = [bars.get((h, code)) or [] for h in trading_days_before(d, IN_PLAY_LOOKBACK)]
        out.append((d, stocks, hist))
    return out, missing


def actual_signals(since: str, until: str) -> dict[str, set]:
    out: dict[str, set] = {}
    for r in oc.load_csv():
        if since <= r.date <= until:
            out.setdefault(r.date, set()).add(str(r.code))
    return out


def run_all(days: list[tuple[str, list[dict]]]) -> dict:
    results = {}
    for orm in GRID_OR:
        for mode in (CAUTIOUS, OPTIMISTIC):
            trades, capped = [], 0
            for _d, stocks in days:
                t, c = replay_day(stocks, orm, optimistic=(mode == OPTIMISTIC))
                trades += t
                capped += c
            results[(orm, mode)] = (trades, capped)
    return results


def summary_part(lines: list[str]) -> list[str]:
    """印在畫面上的部分：所有比較表，到「出場原因」之前（後面是每一筆的明細，很長）。
    10-15 使用者第一次跑，只印前 40 行，第三張表起全被切掉。"""
    cut = next((i for i, l in enumerate(lines) if l.startswith("## 出場原因")), len(lines))
    return lines[:cut]


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    yesterday = (ddate.today() - timedelta(days=1)).isoformat()
    ap = argparse.ArgumentParser(description="開盤區間要看幾分鐘：同一批日子重跑 v10")
    ap.add_argument("--since", default=V10_START, help=f"從哪一天（預設 {V10_START}，v10 第一天）")
    ap.add_argument("--until", default=yesterday, help="到哪一天（預設昨天）")
    ap.add_argument("--out", default="journal/whatif.md")
    args = ap.parse_args(argv)

    archived = archived_days(args.since, args.until)
    if not archived:
        raise SystemExit(f"journal/ 裡沒有 {args.since}～{args.until} 的 watchlist 存檔。")
    print(f"{len(archived)} 個交易日。分鐘 K 有快取的不重抓；第一次跑要一點時間。")

    broker = None

    def fetch(code, day):
        nonlocal broker
        if broker is None:
            from broker import Broker
            broker = Broker()
            broker.login()
        time.sleep(config.SCREEN["kbar_sleep_sec"])
        return oc.day_bars_ohlcv(broker, code, day)

    days, missing, picks, recomputed, markets = [], [], [], 0, {}
    for d, payload in archived:
        stocks, miss = stocks_for(d, payload, fetch)
        days.append((d, stocks))
        markets[d] = market_bars(d, fetch)
        missing += miss
        got = pick_for(d, payload, stocks, fetch)
        if got:
            picks.append(got)
            recomputed += 0 if payload.get("pick") else 1

    results = run_all(days)
    entries = run_entries(days, picks, results)
    stops = run_stops(days, picks)
    market = run_market(results[(CURRENT_OR, CAUTIOUS)][0], markets)
    trigger = run_trigger(days)
    simple = run_simple(days, results, trigger)
    filters = run_filters(results[(CURRENT_OR, CAUTIOUS)][0])
    v1 = run_v1(days)

    def fetch_range(code, start, end):
        nonlocal broker
        if broker is None:
            from broker import Broker
            broker = Broker()
            broker.login()
        time.sleep(config.SCREEN["kbar_sleep_sec"])
        try:
            return kbars_to_days(broker.kbars(code, start, end))
        except Exception as e:
            log.warning("%s 分鐘 K（%s～%s）取得失敗：%s", code, start, end, e)
            return {}

    print("開盤 5 分鐘最熱：整個候選池 + 過去 14 天的分鐘 K，第一次要抓一陣子……")
    pool_days, _pool_missing = pool_days_for(archived, fetch_range)
    in_play = run_in_play(pool_days)
    manual = run_manual(days, pool_days)
    ma = run_ma(days, results, picks, pool_days)
    pulse = pulsecheck.run(pool_days, markets, prev_day_index(pool_days))
    try:
        pulsecheck.save_samples(pulse["samples"])          # 盤中 ④ 那一行的統計用
    except Exception as e:
        log.warning("強弱樣本寫不進去（不影響報表）：%s", e)
    replayed: dict[str, set] = {}
    for t in results[(CURRENT_OR, CAUTIOUS)][0]:
        replayed.setdefault(t.date, set()).add(t.code)
    check = crosscheck(replayed, actual_signals(args.since, args.until))

    lines = render(results, [d for d, _ in days], check, missing, entries, recomputed, stops,
                   market=market, trigger=trigger, simple=simple, filters=filters,
                   in_play=in_play, manual=manual, ma=ma, v1=v1, pulse=pulse)
    path = config.BASE_DIR / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(summary_part(lines)))
    print(f"\n→ 全文寫在 {path}")


if __name__ == "__main__":
    main()
