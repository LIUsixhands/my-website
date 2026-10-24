# -*- coding: utf-8 -*-
"""manual.py —— 手動版：09:05 推「掛單清單」，事先掛好、不跟價格賽跑（分開記錄）。

10-20 台郡 09:05 發訊號、09:07 就鎖漲停。使用者：「還是買不到，其他買到的也會虧」→
「請以手動的方式來設計程式，需要改的是開盤後的」。whatif 7 天：
  - 盯的 10 檔都掛觸價單，先成交先算 → 都是負的（最先碰到的常常是假突破）
  - 只掛盤前排名前 3 名 → +0.18R（15 筆）；總量門檻沒有幫助（越高越差）
所以手動版：盤前排名前 3 名，各一張「快速單：成交價 ≥ 觸價就買」，09:30 還沒成交就刪單。

出場只用永豐 App 設得了的：停損單、移動出場單（漲到「先出一半」的價位才開始、從最高點
回落 1.5%、不低於成本）、13:25 自己平倉。沒有先出一半、跌破均價線那些（App 設不了）。

跟 v10 一起跑、**分開記錄**（manual.csv）：v10 照原計畫跑到 11-09，不受影響。
盤中只推清單；成交和出場收盤後用分鐘 K 回推（跟 whatif 同一個算法）。
"""
import csv
import logging
from datetime import datetime, time as dtime

import config

log = logging.getLogger("manual")

LABEL = "手動版"
TOP_N = 3
PUSH_AT = dtime(9, 5)              # 跟 v10 批次同一個時間
CANCEL_AT = dtime(9, 30)           # 還沒成交就刪單（跟 v10 進場窗口一樣）
TRAIL = "移動出場"
NOT_FILLED = "沒成交"
LOCKED = "漲停買不到"
FILE = config.BASE_DIR / "manual.csv"
FIELDS = ("date", "code", "name", "rank", "trigger", "stop", "half_at", "lots", "source",
          "entry", "filled_at", "result", "exit_price", "exit_at", "r_multiple", "net_r",
          "net_pct", "net_amount")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── 盤中：09:05 的掛單清單 ──────────────────────────────────
def order_for(st, now: datetime) -> dict:
    """一檔的單子。觸價＝開盤區間最高 +0.1%（跟 v10 的突破價一樣），停損、先出一半的價位、
    張數用 v10 同一個函式、照觸價算。開盤區間還沒鎖、或觸價已經在漲停 → 寫原因。"""
    import signals
    base = {"code": st.code, "name": st.name, "rank": st.rank, "prev_close": st.prev_close}
    if not st.or_locked or not st.or_high:
        return dict(base, missing="開盤區間還沒有資料")
    trigger = config.round_to_tick(
        st.or_high * (1 + config.SIGNAL["breakout_buffer_pct"] / 100), "up")
    plan = signals._price_plan(st, trigger, now.time())
    if plan is None:
        return dict(base, missing="觸價已經在漲停，不掛")
    return dict(base, trigger=trigger, stop=plan["stop"], half_at=plan.get("half_at"),
                lots=plan["lots"], oversized=bool(plan.get("oversized")),
                risk_per_lot=plan.get("risk_per_lot"), last=st.last_price or None)


def build_orders(states: dict, now: datetime) -> list[dict]:
    """盤前排名前 3 名（名次 0 = 不知道，排最後）。"""
    top = sorted(states.values(), key=lambda s: (s.rank or 9999, s.code))[:TOP_N]
    return [order_for(st, now) for st in top]


def format_orders(orders: list[dict], now: datetime) -> str:
    lines = [f"🧾 {LABEL}掛單清單｜{now:%H:%M}", "盤前排名前 3 名，事先掛好、不用搶快"]
    for n, o in enumerate(orders, 1):
        label = f"{o['code']} {o.get('name', '')}".strip()
        lines.append("────────────────")
        lines.append(f"{n}. {label}")
        if o.get("missing"):
            lines.append(f"不掛：{o['missing']}")
            continue
        lines.append(f"快速單：成交價 ≥ {o['trigger']:.2f} 買 {o['lots']} 張")
        lines.append(f"停損單：{o['stop']:.2f}")
        if o.get("half_at"):
            lines.append(f"移動出場：漲到 {o['half_at']:.2f} 後，從最高點回落 "
                         f"{config.SIGNAL['exit_trail_pct']:g}% 出")
        if o.get("oversized"):
            lines.append(f"⚠️ 一張風險 {o['risk_per_lot']:,} 元，超過上限 "
                         f"{config.RISK['per_trade_risk']:,} 元")
        if o.get("last") and o["last"] >= o["trigger"]:
            lines.append(f"現價 {o['last']:.2f} 已經在觸價之上，掛上去會馬上成交")
    lines += ["────────────────",
              f"{CANCEL_AT:%H:%M} 還沒成交的刪單；13:25 還沒出的全部賣掉。",
              "跟 v10 分開記錄。驗證期不下單。"]
    return "\n".join(lines)


# ── 收盤後：用分鐘 K 回推 ────────────────────────────────────
def exit_walk(bars, entry: float, stop: float, half_at: float, fired: datetime):
    """(結果, 出場價, 出場時間)。停損單＋移動出場單＋13:25。移動出場在漲到 half_at
    之後才開始：從最高點回落 exit_trail_pct %，不低於成本。同一根先判停損、再判移動
    （用前面幾根的最高點，保守）。成交那一分鐘不判。沒有之後的 K 棒 → None。"""
    import outcome as oc
    trail = config.SIGNAL["exit_trail_pct"] / 100
    peak, armed, last = entry, False, None
    for t, o, h, l, c, _v in bars:
        if t < fired + oc.BAR_SPAN:
            continue
        if t.time() > oc.FLATTEN_AT:
            break
        if l <= stop:
            return oc.STOP, min(o, stop), t.strftime("%H:%M:%S")
        if armed:
            level = max(entry, peak * (1 - trail))
            if l <= level:
                return TRAIL, min(o, level), t.strftime("%H:%M:%S")
        peak = max(peak, h)
        armed = armed or peak >= half_at
        last = c
    if last is None:
        return None
    return oc.FLAT, last, oc.FLATTEN_AT.strftime("%H:%M:%S")


def fill_bar(bars, trigger: float):
    """09:05 之後、09:30 以前，第一根最高價碰到觸價的 1 分 K（label 是結束時間）。"""
    return next((b for b in bars if PUSH_AT < b[0].time() <= CANCEL_AT and b[2] >= trigger),
                None)


def replay_order(o: dict, bars: list, date: str, source: str) -> dict | None:
    """一張單子的結局。沒有 K 棒 → None（不寫，免得把「沒資料」記成「沒成交」）。"""
    import exits
    if o.get("missing"):
        return None
    if not bars:
        return None
    row = {"date": date, "code": str(o["code"]), "name": o.get("name", ""),
           "rank": o.get("rank"), "trigger": o["trigger"], "stop": o["stop"],
           "half_at": o.get("half_at"), "lots": o["lots"], "source": source}
    b = fill_bar(bars, float(o["trigger"]))
    if b is None:
        return dict(row, result=NOT_FILLED)
    entry = config.round_to_tick(max(float(o["trigger"]), b[1]), "up")
    lu = config.limit_up(float(o.get("prev_close") or 0))
    if lu and entry >= lu and b[3] >= lu:
        return dict(row, result=LOCKED, filled_at=b[0].strftime("%H:%M:%S"))
    stop, lots = float(o["stop"]), int(o["lots"])
    got = exit_walk(bars, entry, stop, float(o.get("half_at") or float("inf")), b[0])
    if got is None:
        return dict(row, entry=entry, filled_at=b[0].strftime("%H:%M:%S"), result=NOT_FILLED)
    result, price, at = got
    pct, r = exits.blended(entry, stop, lots, None, price)
    cost = config.round_trip_cost_pct()
    risk = entry - stop
    return dict(row, entry=entry, filled_at=b[0].strftime("%H:%M:%S"), result=result,
                exit_price=round(price, 2), exit_at=at, r_multiple=round(r, 2),
                net_r=round(r - cost / 100 * entry / risk, 2) if risk > 0 else round(r, 2),
                net_pct=round(pct - cost, 3),
                net_amount=round((pct - cost) / 100 * entry * 1000 * lots))


def orders_from_bars(items: list[dict], bars_of: dict) -> list[dict]:
    """盤中沒推到清單（監看沒開、09:30 之後才開）→ 用分鐘 K 照同一個規則重算單子。"""
    import signals
    import whatif
    out = []
    for n, i in enumerate(items[:TOP_N], 1):
        code = str(i["code"])
        bars = bars_of.get(code) or []
        st = signals.SymbolState(code, float(i["prev_close"]), i.get("name", ""))
        st.rank = n
        st.amplitude_pct = i.get("avg_amplitude_pct") or i.get("amplitude_pct")
        rng = whatif.opening_range(bars, whatif.CURRENT_OR)
        if rng:
            st.or_high, st.or_low = rng
            st.or_locked = True
            st.day_open = bars[0][1]
        at = datetime.combine(bars[0][0].date(), PUSH_AT) if bars else datetime.now()
        out.append(order_for(st, at))
    return out


def resolve(broker, saved: dict | None, items: list[dict], date: str) -> list[dict]:
    """今天手動版每一張單子的結局。盤中推過清單的照那一份；沒有就重算。"""
    import outcome as oc
    orders = (saved or {}).get("orders")
    source = "盤中清單"
    codes = [str(o["code"]) for o in orders] if orders else [str(i["code"]) for i in items[:TOP_N]]
    bars_of = {c: oc.day_bars_ohlcv(broker, c, date) for c in codes}
    if not orders:
        orders, source = orders_from_bars(items, bars_of), "分鐘 K 重算"
    rows = []
    for o in orders:
        row = replay_order(o, bars_of.get(str(o["code"])) or [], date, source)
        if row:
            rows.append(row)
    return rows


def load(path=None) -> list[dict]:
    path = path or FILE
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def append(rows: list[dict], path=None) -> None:
    """同一天重跑會蓋掉那一天的舊紀錄。"""
    if not rows:
        return
    path = path or FILE
    days = {r["date"] for r in rows}
    keep = [r for r in load(path) if r.get("date") not in days] + list(rows)
    keep.sort(key=lambda r: (r["date"], int(_num(r.get("rank")) or 9999)))
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in keep:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in FIELDS})


def report_lines(today: list[dict], history: list[dict]) -> list[str]:
    """日報裡手動版那一段。單筆一行不超過 20 字。"""
    if not today and not history:
        return []
    lines = ["────────────────", f"🧾 {LABEL}（分開記錄）"]
    for r in today:
        label = f"{r['code']} {str(r.get('name', ''))[:3]}"
        if _num(r.get("r_multiple")) is None:
            lines.append(f"{label}　{r['result']}")
        else:
            lines.append(f"{label}　{r['result']} {float(r['r_multiple']):+.2f}R")
    done = [r for r in history if _num(r.get("net_pct")) is not None]
    if done:
        n = len(done)
        wins = sum(1 for r in done if float(r["net_pct"]) > 0)
        lines += [f"{LABEL}累計 {n} 筆｜勝率 {wins / n * 100:.1f}%",
                  f"平均 {sum(float(r['r_multiple']) for r in done) / n:+.2f}R"
                  f"（扣成本 {sum(float(r['net_r']) for r in done) / n:+.2f}R）",
                  f"{LABEL}累計損益 {sum(float(r['net_amount']) for r in done):+,.0f} 元"]
    missed = sum(1 for r in history if r.get("result") in (NOT_FILLED, LOCKED))
    if missed:
        lines.append(f"另有 {missed} 張單子沒成交")
    return lines
