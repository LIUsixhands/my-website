"""
screener.py — 盤前選股。每天 08:30 跑一次。

    python3 screener.py              （Windows 是 python screener.py）
    python3 screener.py --top 5      只留量比最高的 5 檔

輸出 watchlist.json：10~20 檔候選 + 每檔的關鍵水位（昨高、昨低、昨均價、量能基準）。
這一層只做「收斂」，不做預測。把 1800 檔縮到你眼睛顧得住的數量，就是它全部的工作。

--top N 存在的理由：驗證期要的是**可重現**。每天用同一條排序規則取前 N 檔，
20 天之後那份數據才回答得了「這套規則有沒有效」。手挑的話，賺賠都不知道
該歸因給規則還是歸因給當天的判斷，等於白跑。
"""
import argparse
import json
import logging
from datetime import datetime, timedelta

import config
from broker import Broker, throttle, _bar_time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("screener")


def passes_basic(snap, cfg: dict) -> dict | None:
    """單檔的量價門檻。通過回傳整理好的列，不通過回傳 None。

    抽成純函式才測得到 —— 這幾行決定了整天看哪幾檔，錯了不會有任何報錯。
    """
    close = float(getattr(snap, "close", 0) or 0)
    high = float(getattr(snap, "high", 0) or 0)
    low = float(getattr(snap, "low", 0) or 0)
    vol = int(getattr(snap, "total_volume", 0) or 0)      # 張

    if close <= 0 or vol <= 0 or high <= 0 or low <= 0:
        return None
    if not (cfg["min_price"] <= close <= cfg["max_price"]):
        return None
    if vol < cfg["min_prev_volume_lots"]:
        return None
    amplitude = (high - low) / close * 100
    if amplitude < cfg["min_amplitude_pct"]:
        return None

    return {
        "code": snap.code,
        "prev_close": close,
        "prev_high": high,
        "prev_low": low,
        "prev_avg": float(getattr(snap, "average_price", 0) or 0),
        "prev_volume": vol,
        "amplitude_pct": round(amplitude, 2),
    }


def daily_volumes(ts_list, volume_list) -> dict:
    """把分鐘 K 的量依日期加總，回傳 {date: 當日總量}。"""
    per_day: dict = {}
    for ts, v in zip(ts_list, volume_list):
        dt = _bar_time(ts)
        if dt is None:
            continue
        per_day[dt.date()] = per_day.get(dt.date(), 0.0) + float(v or 0)
    return per_day


def volume_baseline(ts_list, volume_list, lookback_days: int) -> float:
    """最近 N 個交易日的「日均量」，排除最後一天。

    原本的寫法是 (每分鐘均量 × 270 ÷ 1000)，量綱整個錯掉：kbars 的 Volume
    已經是張，再除 1000 會讓基準小三個數量級，於是量比全部變成四位數，
    排序等於亂排。改成直接按日加總再取平均，單位自然對齊 prev_volume。

    排除最後一天，是因為最後一天就是要被比較的那天（昨日）；
    把它放進基準等於拿自己跟自己比，放大的量會被自己稀釋掉。
    """
    per_day = daily_volumes(ts_list, volume_list)
    if len(per_day) < 2:
        return 0.0
    days = sorted(per_day)[:-1][-lookback_days:]
    if not days:
        return 0.0
    return sum(per_day[d] for d in days) / len(days)


def screen(broker: Broker) -> list[dict]:
    cfg = config.SCREEN
    contracts = broker.all_stocks()
    log.info("全市場商品檔：%d 檔", len(contracts))

    # 第一道：合約層級過濾（不打 API，先砍掉大半）
    stage1 = []
    for c in contracts:
        code = getattr(c, "code", "")
        if not code.isdigit() or len(code) != 4:   # 排除 ETF/權證/特別股等非四碼普通股
            continue
        if cfg["require_day_trade"] and not broker.is_day_tradable(c):
            continue
        stage1.append(c)
    log.info("可當沖 + 四碼普通股：%d 檔", len(stage1))

    # 第二道：昨日量價（snapshots 帶回昨日收盤資訊）
    snaps = broker.snapshots(stage1)
    rows = []
    for s in snaps:
        try:
            row = passes_basic(s, cfg)
            if row:
                rows.append(row)
        except Exception as e:
            log.debug("skip %s: %s", getattr(s, "code", "?"), e)

    log.info("通過量價門檻：%d 檔", len(rows))

    # 第三道：量能是否「異常」放大（今天有人在裡面才會有波動）
    # 只對振幅前段的標的打 kbars —— 每檔一次 API，全打會撞到流量上限被停用一分鐘。
    rows.sort(key=lambda r: r["amplitude_pct"], reverse=True)
    probe, rest = rows[: cfg["max_kbar_queries"]], rows[cfg["max_kbar_queries"]:]
    if rest:
        log.info("量比只計算振幅前 %d 名（API 流量上限），其餘 %d 檔以 1.0 計",
                 len(probe), len(rest))

    start = (datetime.now() - timedelta(days=cfg["lookback_days"] * 3)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    for r in probe:
        try:
            kb = broker.kbars(r["code"], start, end)
            base = volume_baseline(getattr(kb, "ts", []), getattr(kb, "Volume", []),
                                   cfg["lookback_days"])
            r["volume_ratio"] = round(r["prev_volume"] / base, 2) if base > 0 else 1.0
        except Exception as e:
            log.debug("%s 量比計算失敗，以 1.0 計：%s", r["code"], e)
            r["volume_ratio"] = 1.0
        throttle(cfg["kbar_sleep_sec"])
    for r in rest:
        r["volume_ratio"] = 1.0

    rows.sort(key=lambda r: (r["volume_ratio"], r["amplitude_pct"]), reverse=True)
    return rows[: cfg["max_universe"]]


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="盤前選股")
    ap.add_argument("--top", type=int, metavar="N",
                    help="只保留量比最高的 N 檔（不給就全部保留）")
    args = ap.parse_args(argv)
    if args.top is not None and args.top < 1:
        ap.error("--top 至少要 1")
    return args


def main(argv=None):
    args = parse_args(argv)
    errs = config.validate()
    if errs:
        raise SystemExit("config.py 參數有問題：\n" + "\n".join(f"  - {e}" for e in errs))

    broker = Broker()
    watchlist = screen(broker)
    dropped = []
    if args.top is not None and len(watchlist) > args.top:
        # rows 已在 screen() 裡依 (量比, 振幅) 由高到低排好，直接取前 N 檔
        watchlist, dropped = watchlist[:args.top], watchlist[args.top:]

    payload = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "round_trip_cost_pct": round(config.round_trip_cost_pct(), 4),
        "items": watchlist,
    }
    config.WATCHLIST_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n=== {payload['date']} 當沖候選池（{len(watchlist)} 檔）===")
    print(f"來回成本基準：{payload['round_trip_cost_pct']}%（你的停利要遠大於這個數字）\n")
    print(f"{'代號':<8}{'昨收':>9}{'振幅%':>9}{'量(張)':>11}{'量比':>8}")
    for r in watchlist:
        print(f"{r['code']:<8}{r['prev_close']:>9.2f}{r['amplitude_pct']:>9.2f}"
              f"{r['prev_volume']:>11,}{r['volume_ratio']:>8.2f}")
    if dropped:
        print(f"\n--top {args.top}：已捨去量比較低的 {len(dropped)} 檔"
              f"（{'、'.join(r['code'] for r in dropped)}）")
        print(f"下一步：{config.PY_CMD} signals.py")
    else:
        print(f"\n下一步：開盤前自己看一眼題材與昨日型態，刪到剩 5 檔再跑 signals.py。")
        print(f"（或直接跑 {config.PY_CMD} screener.py --top 5 讓程式照量比取前 5 檔）")


if __name__ == "__main__":
    main()
