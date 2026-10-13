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
import market_calendar
import outcome as oc
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
    net_pct: float = 0.0
    held_min: int = 0


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


def replay_day(stocks: list[dict], or_minutes: int, optimistic: bool = False,
               limit: int | None = None) -> tuple[list[Trade], int]:
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
        plan = _plan(p["stock"], p["or_high"], p["day_open"], entry, b[0].time())
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
    if walked is None:                                # 之後一根 K 都沒有
        tr.result, tr.exit_price = oc.FLAT, plan["entry"]
        return tr
    result, exit_price, _used, exit_at, half = walked
    pct, r = exits.blended(plan["entry"], plan["stop"], plan["lots"], half, exit_price)
    tr.result, tr.exit_price, tr.exit_at = result, round(exit_price, 2), exit_at
    tr.r_multiple = round(r, 2)
    tr.net_pct = round(pct - config.round_trip_cost_pct(), 3)
    end = datetime.combine(fired.date(), _t(exit_at)) if exit_at else fired
    tr.held_min = max(0, int((end - fired).total_seconds() // 60))
    return tr


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
            "total_r": round(sum(t.r_multiple for t in trades), 2),
            "avg_min": round(sum(t.held_min for t in trades) / len(trades)),
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


def render(results: dict, days: list[str], check: list[str], missing: list) -> list[str]:
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
    out += ["## 出場原因（保守）", "", "| 區間 | 出場原因 |", "|---|---|"]
    for orm in GRID_OR:
        s = summarise(results.get((orm, CAUTIOUS), ([], 0))[0])
        why = "、".join(f"{k} {v}" for k, v in sorted(
            s.get("reasons", {}).items(), key=lambda kv: -kv[1])) or "—"
        out.append(f"| {orm} 分 | {why} |")
    out += ["", "## 每一筆（保守）", "",
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

    days, missing = [], []
    for d, payload in archived:
        stocks, miss = stocks_for(d, payload, fetch)
        days.append((d, stocks))
        missing += miss

    results = run_all(days)
    replayed: dict[str, set] = {}
    for t in results[(CURRENT_OR, CAUTIOUS)][0]:
        replayed.setdefault(t.date, set()).add(t.code)
    check = crosscheck(replayed, actual_signals(args.since, args.until))

    lines = render(results, [d for d, _ in days], check, missing)
    path = config.BASE_DIR / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:40]))
    print(f"\n→ 全文寫在 {path}")


if __name__ == "__main__":
    main()
