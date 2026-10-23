# -*- coding: utf-8 -*-
"""pickcheck.py —— 挑股驗證：盤前首選的公式到底有沒有用（只是量，不改公式）。

10-23 使用者：「盤前那一檔的驗證…我是說挑股怎麼挑」→「可以再往後幾天會比較準確？」→
「往前 20 天好嗎？」→「都要」。每天的首選結果混了兩件事（挑對股沒有、出場規則好不好），
分不出來。這裡把同一天候選池 20 檔**全部**照首選的規則（09:00 開盤價買、同一套出場）
回推，看：
  1. 首選（第 1 名）有沒有比第 2～3 名、其他候選好
  2. 四項分數（量比、振幅、RSI、昨收位置）各自高的 1/3 vs 低的 1/3，哪一項真的有用
  3. 三項沒用在公式裡的（開盤跳空、昨收比 10 日均線、一張的風險）有沒有用

    python pickcheck.py                 用 journal/ 裡有存的候選池（約 10-12 起）
    python pickcheck.py --rebuild 20    另外重建之前 20 個交易日的候選池再一起算

重建（--rebuild）：前一個交易日的成交量排行（永豐 scanners，200 檔）→ 照 screener 同樣的
門檻篩、振幅前 60 名用分鐘 K 算量比、取前 20 → 同一條公式選首選。只用那天以前的資料。
跟當時真的跑會有出入：可不可以當沖用的是「現在」的名單、處置股不篩、排行只看前 200 名。
重建的存 journal/rebuilt/，不跟真的存檔混在一起；報表分開標。
"""
import argparse
import json
import logging
import time
from datetime import date as ddate, datetime, timedelta
from types import SimpleNamespace

import config
import premarket
import screener
import whatif

log = logging.getLogger("pickcheck")

REBUILT_DIR = config.JOURNAL_DIR / "rebuilt"
REPORT = config.JOURNAL_DIR / "pickcheck.md"
RANK_SIZE = 200                 # 排行一次抓幾檔（永豐 scanners 上限）
FETCH_BACK_DAYS = 70            # 重建時分鐘 K 往前抓幾個日曆天（RSI 要 30 個交易日左右）
TREND_DAYS = 10                 # 「昨收比 N 日均線」
REAL, REBUILT = "存檔", "重建"
RANK_GROUPS = (("首選（第 1 名）", 1, 1), ("第 2～3 名", 2, 3), ("第 4～10 名", 4, 10),
               ("第 11～20 名", 11, 99))
FACTORS = (("volume_ratio", "量比"), ("amplitude", "近 5 日振幅"),
           ("rsi_gap", "RSI 離 60（小＝近 60）"), ("close_pos", "昨收在昨天高低的位置"),
           ("total", "公式總分（小＝排前面）"), ("gap", "開盤跳空 %（公式沒用）"),
           ("trend", f"昨收比 {TREND_DAYS} 日均線 %（公式沒用）"),
           ("risk_lot", "一張的停損風險（公式沒用）"))


# ── 每一天：候選池全部照首選的規則回推 ─────────────────────────────
def daily_ohlcv(bars) -> tuple | None:
    if not bars:
        return None
    return (bars[0][1], max(b[2] for b in bars), min(b[3] for b in bars), bars[-1][4],
            sum(b[5] for b in bars))


def trend_pct(history, prev_close: float) -> float | None:
    """昨收比前 TREND_DAYS 個交易日（含昨天）收盤平均高幾 %。資料不夠 None。"""
    closes = [d[3] for d in (daily_ohlcv(b) for b in history) if d]
    if len(closes) < TREND_DAYS or not prev_close:
        return None
    ma = sum(closes[-TREND_DAYS:]) / TREND_DAYS
    return round((prev_close - ma) / ma * 100, 2)


def day_rows(day: str, payload: dict, bars_of: dict, hist: dict, source: str) -> list[dict]:
    """那一天候選池每一檔一列：名次、分數、照首選規則的結果。買不到（開盤漲停）的 result=None。"""
    pool = whatif.pool_rows(payload)
    out = []
    for n, s in enumerate(premarket.score(pool), 1):
        code, row = s["code"], s["row"]
        bars = bars_of.get(code) or []
        if not bars:
            continue
        prev_close = float(row["prev_close"])
        pick = {"code": code, "name": s["name"], "prev_close": prev_close,
                "amplitude_pct": row.get("avg_amplitude_pct") or row.get("amplitude_pct"),
                "features": s["features"]}
        tr = whatif.pick_trade(day, pick, bars)
        f = s["features"]
        out.append({
            "date": day, "code": code, "name": s["name"], "rank": n, "source": source,
            "volume_ratio": f["volume_ratio"], "amplitude": f["amplitude"], "rsi_gap": f["rsi_gap"],
            "close_pos": f["close_pos"], "total": s["total"],
            "gap": round((bars[0][1] - prev_close) / prev_close * 100, 2) if prev_close else None,
            "trend": trend_pct(hist.get(code) or [], prev_close),
            "risk_lot": round((tr.entry - tr.stop) * 1000) if tr else None,
            "net_r": tr.net_r if tr else None, "net_pct": tr.net_pct if tr else None,
            "result": tr.result if tr else None,
        })
    return out


# ── 重建過去的候選池 ─────────────────────────────────────────────
def _lots(items) -> float:
    """排行的成交量單位：看起來是股（最大的超過 500 萬）就換成張。"""
    vols = [float(getattr(i, "total_volume", 0) or 0) for i in items]
    return 1000.0 if vols and max(vols) > 5_000_000 else 1.0


def describe(item) -> str:
    """排行的一筆印出來看（欄位對不上時才知道永豐給了什麼）。"""
    keys = ("code", "name", "date", "close", "high", "low", "total_volume", "volume")
    got = {k: getattr(item, k, None) for k in keys}
    return "、".join(f"{k}={v}" for k, v in got.items() if v is not None) or repr(item)[:200]


def rebuild_day(day: str, prev: str, items, days_of, tradable) -> dict | None:
    """重建 day 那天早上的候選池（跟 screener 同樣的門檻、排序）。
    items = prev 那天的成交量排行；days_of(代號) → {日期: 1 分 K}；tradable(代號) → 可不可當沖。"""
    cfg = config.SCREEN
    items = list(items or [])
    unit = _lots(items)
    rows, ok_code = [], 0
    for it in items:
        code = str(getattr(it, "code", ""))
        if not code.isdigit() or len(code) != 4 or not tradable(code):
            continue
        ok_code += 1
        snap = SimpleNamespace(code=code, close=getattr(it, "close", 0), high=getattr(it, "high", 0),
                               low=getattr(it, "low", 0),
                               total_volume=int(float(getattr(it, "total_volume", 0) or 0) / unit))
        row = screener.passes_basic(snap, cfg)
        if row:
            row["name"] = str(getattr(it, "name", "") or "")
            rows.append(row)
    if not rows:
        # 10-23 第一次跑 20 天全部重建不出來 —— 說清楚卡在哪一關，不要只說「跳過」。
        log.warning("%s 重建不出候選池：%s 的排行 %d 檔、四碼可當沖 %d 檔、過量價門檻 0 檔%s",
                    day, prev, len(items), ok_code,
                    f"（第一筆：{describe(items[0])}）" if items else "（排行是空的）")
        return None
    rows.sort(key=lambda r: r["amplitude_pct"], reverse=True)
    probe, rest = rows[: cfg["max_kbar_queries"]], rows[cfg["max_kbar_queries"]:]
    for r in probe:
        days = {d: b for d, b in (days_of(r["code"]) or {}).items() if d <= prev}
        daily = {d: daily_ohlcv(b) for d, b in days.items() if b}
        order = sorted(daily)
        r["volume_ratio"] = 1.0
        if prev in daily:
            base_days = [d for d in order if d < prev][-cfg["lookback_days"]:]
            base = sum(daily[d][4] for d in base_days) / len(base_days) if base_days else 0
            if base > 0:
                r["volume_ratio"] = round(daily[prev][4] / base, 2)
                r["avg_volume_lots"] = round(base)
        ranges = [(daily[b][1] - daily[b][2]) / daily[a][3] * 100
                  for a, b in zip(order, order[1:]) if daily[a][3] > 0]
        tail = ranges[-cfg["lookback_days"]:]
        r["avg_amplitude_pct"] = round(sum(tail) / len(tail), 2) if tail else None
        r["daily_rsi"] = screener.wilder_rsi([daily[d][3] for d in order])
    for r in rest:
        r["volume_ratio"] = 1.0
        r["daily_rsi"] = None
    rows.sort(key=lambda r: (r["volume_ratio"], r["amplitude_pct"]), reverse=True)
    pool = rows[: cfg["max_universe"]]
    items_, rest_ = pool[: cfg["watch_top"]], pool[cfg["watch_top"]:]
    return {"date": day, "rebuilt": True, "items": items_, "not_watched": rest_,
            "pick": premarket.choose(pool, watched=[r["code"] for r in items_])}


def rebuilt_path(day: str):
    return REBUILT_DIR / f"watchlist-{day.replace('-', '')}.json"


def load_rebuilt(day: str) -> dict | None:
    path = rebuilt_path(day)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("%s 讀不到，重建：%s", path.name, e)
        return None


def save_rebuilt(payload: dict) -> None:
    path = rebuilt_path(payload["date"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def days_to_rebuild(first_real: str, n: int) -> list[str]:
    """第一天有完整存檔的日子之前 n 個交易日（舊到新）。"""
    return whatif.trading_days_before(first_real, n)


# ── 報表 ─────────────────────────────────────────────────────
def _stats(rows) -> str:
    done = [r for r in rows if r.get("net_r") is not None]
    if not done:
        return "—"
    wins = sum(1 for r in done if r["net_pct"] > 0)
    return (f"{sum(r['net_r'] for r in done) / len(done):+.2f}R"
            f"（{wins / len(done) * 100:.0f}% 勝）")


def _avg_r(rows) -> str:
    done = [r for r in rows if r.get("net_r") is not None]
    return f"{sum(r['net_r'] for r in done) / len(done):+.2f}R" if done else "—"


def thirds(rows, key):
    have = [r for r in rows if r.get(key) is not None and r.get("net_r") is not None]
    if len(have) < 3:
        return [], [], None
    vals = sorted(r[key] for r in have)
    q1, q2 = vals[len(vals) // 3], vals[len(vals) * 2 // 3]
    lo = [r for r in have if r[key] < q1]
    hi = [r for r in have if r[key] > q2]
    if not lo or not hi:
        return lo, hi, None
    gap = sum(r["net_r"] for r in hi) / len(hi) - sum(r["net_r"] for r in lo) / len(lo)
    return lo, hi, gap


def _gap(g) -> str:
    return "—" if g is None else f"{g:+.2f}R"


def lines(rows: list[dict]) -> list[str]:
    out = ["## 挑股驗證：盤前首選的公式有沒有用", ""]
    if not rows:
        return out + ["沒有資料。", ""]
    days = sorted({r["date"] for r in rows})
    half = len(days) // 2
    first, second = set(days[:half]), set(days[half:])
    real = sorted({r["date"] for r in rows if r["source"] == REAL})
    rebuilt = sorted({r["date"] for r in rows if r["source"] == REBUILT})
    out += [f"{len(days)} 天（{REAL} {len(real)} 天、{REBUILT} {len(rebuilt)} 天）、{len(rows)} 檔次。"
            f"前半 {days[0][5:]}～{days[max(half - 1, 0)][5:]}，後半 {days[half][5:]}～{days[-1][5:]}。", "",
            "每一檔都照首選的規則：09:00 開盤價買、停損 -3%、同一套出場、13:25 平倉；R 是扣過成本的。", "",
            "| 名次 | 檔次 | 買不到 | 平均R（勝率） | 前半 | 後半 | 只看存檔日 | 只看重建日 |",
            "|---|---|---|---|---|---|---|---|"]
    for name, lo, hi in RANK_GROUPS:
        g = [r for r in rows if lo <= r["rank"] <= hi]
        locked = sum(1 for r in g if r["net_r"] is None)
        out.append(f"| {name} | {len(g)} | {locked} | {_stats(g)} | "
                   f"{_avg_r([r for r in g if r['date'] in first])} | "
                   f"{_avg_r([r for r in g if r['date'] in second])} | "
                   f"{_avg_r([r for r in g if r['source'] == REAL])} | "
                   f"{_avg_r([r for r in g if r['source'] == REBUILT])} |")
    out.append(f"| 全部 | {len(rows)} | {sum(1 for r in rows if r['net_r'] is None)} | {_stats(rows)} | "
               f"{_avg_r([r for r in rows if r['date'] in first])} | "
               f"{_avg_r([r for r in rows if r['date'] in second])} | "
               f"{_avg_r([r for r in rows if r['source'] == REAL])} | "
               f"{_avg_r([r for r in rows if r['source'] == REBUILT])} |")
    out += ["", "每一項分數：同一天候選池全部放在一起，最低的 1/3 vs 最高的 1/3。", "",
            "| 指標 | 低的 1/3 | 高的 1/3 | 高減低 | 前半：高減低 | 後半：高減低 |",
            "|---|---|---|---|---|---|"]
    for key, name in FACTORS:
        lo, hi, gap = thirds(rows, key)
        g1 = thirds([r for r in rows if r["date"] in first], key)[2]
        g2 = thirds([r for r in rows if r["date"] in second], key)[2]
        out.append(f"| {name} | {_stats(lo)} | {_stats(hi)} | {_gap(gap)} | {_gap(g1)} | {_gap(g2)} |")
    out += [
        "",
        "- **首選有沒有用**：第 1 名要比第 2～3 名、其他候選好，而且**前半、後半都比較好**才算數。"
        "跟「全部」差不多，就是公式沒有比隨便挑一檔好。",
        "- **每一項分數**：量比、振幅、昨收位置是越高越好，「高減低」要是正的；RSI 離 60、公式總分是"
        "越小越好，「高減低」要是負的。前半、後半同方向才算數。",
        "- 「公式沒用」那三項：前後一致而且差得多，才考慮加進公式。",
        "- **買不到**：開盤就漲停，照規則不進場，不算進平均。",
        f"- **{REBUILT}**的日子是用永豐的歷史成交量排行回頭重建的：可不可以當沖用的是現在的名單、"
        "處置股沒篩、只看排行前 200 名，跟當時真的跑會有出入。兩邊分開看一致才算數。",
        "- 每一檔用同一套規則，比較的是「挑哪一檔」；首選本身的成績照舊看日報。只是量，不改公式。",
        "",
    ]
    return out


# ── 主程式 ─────────────────────────────────────────────────────
def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="挑股驗證：盤前首選的公式有沒有用")
    ap.add_argument("--rebuild", type=int, default=0, help="另外重建之前幾個交易日的候選池")
    ap.add_argument("--until", default=(ddate.today() - timedelta(days=1)).isoformat())
    args = ap.parse_args(argv)

    archived = [(d, p) for d, p in whatif.archived_days("2000-01-01", args.until)
                if p.get("not_watched")]
    if not archived and not args.rebuild:
        raise SystemExit("journal/ 裡沒有完整的候選池存檔（10-09 以後才有）。")
    broker = None

    def get_broker():
        nonlocal broker
        if broker is None:
            from broker import Broker
            broker = Broker()
            broker.login()
        return broker

    def fetch_range(code, start, end):
        time.sleep(config.SCREEN["kbar_sleep_sec"])
        try:
            return whatif.kbars_to_days(get_broker().kbars(code, start, end))
        except Exception as e:
            log.warning("%s 分鐘 K（%s～%s）取得失敗：%s", code, start, end, e)
            return {}

    payloads = [(d, p, REAL) for d, p in archived]
    if args.rebuild:
        first_real = archived[0][0] if archived else args.until
        todo = days_to_rebuild(first_real, args.rebuild)
        start = (datetime.strptime(todo[0], "%Y-%m-%d")
                 - timedelta(days=FETCH_BACK_DAYS)).strftime("%Y-%m-%d")
        cache: dict = {}

        def days_of(code):
            if code not in cache:
                cache[code] = fetch_range(code, start, todo[-1])
                for d, b in cache[code].items():
                    whatif.save_cached(d, code, b)
            return cache[code]

        def tradable(code):
            try:
                b = get_broker()
                return b.is_day_tradable(b.stock(code))
            except Exception:
                return False

        print(f"重建 {todo[0]}～{todo[-1]} 共 {len(todo)} 天的候選池（第一次要抓一陣子）……")
        for day in todo:
            payload = load_rebuilt(day)
            if payload is None:
                prev = whatif.trading_days_before(day, 1)[0]
                try:
                    items = get_broker().volume_rank(prev, RANK_SIZE)
                except Exception as e:
                    log.warning("%s 成交量排行抓不到，這一天跳過：%s", prev, e)
                    continue
                payload = rebuild_day(day, prev, items, days_of, tradable)
                if payload is None:
                    continue
                save_rebuilt(payload)
            payloads.append((day, payload, REBUILT))
    payloads.sort(key=lambda x: x[0])

    pool_days, _missing = whatif.pool_days_for([(d, p) for d, p, _s in payloads], fetch_range)
    source = {d: s for d, _p, s in payloads}
    by_day = {d: p for d, p, _s in payloads}
    rows = []
    for d, stocks, hist in pool_days:
        rows += day_rows(d, by_day[d], {s["code"]: s["bars"] for s in stocks}, hist, source[d])
    text = lines(rows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(text), encoding="utf-8")
    print("\n".join(text))
    print(f"\n→ 全文寫在 {REPORT}")


if __name__ == "__main__":
    main()
