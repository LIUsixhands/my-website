# -*- coding: utf-8 -*-
"""whatif.py —— 用已經累積的分鐘 K 重跑不同的進場／出場規則。

v4 的四條原則是使用者定的，這支程式**不會去推翻它們**。它只回答那幾個
使用者沒指定、而我是用猜的填進去的格子：

  - 開盤區間要幾分鐘？（我填 2 分鐘，沒有任何數據支持）
  - 09:30 出場比抱到停損或目標好嗎？
  - 目標 1.5R 是不是真的比 2.5R 好？

為什麼值得先算：這些參數如果等 20 個交易日跑完才回答，就是再花一個月；
而同一份分鐘 K 現在就在券商那裡，一個晚上算得完。

**這份回測對自己有利，要記得。** 它只重跑 outcomes.csv 裡有的那些股票 ——
也就是當天「後來真的突破了」的那幾檔。碰到區間高就掛掉的那些從來沒進過
紀錄，但縮短區間之後它們會被買進來。所以任何「縮短區間比較好」的結論
都偏樂觀，報表第一行會寫這件事。要修掉這個偏誤，需要每天完整的
watchlist.json 存檔（從 10-02 起才開始留）。
"""
import argparse
import csv
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta

import config
import outcome as oc

log = logging.getLogger("whatif")

BAR_SPAN = timedelta(minutes=1)
FLATTEN_AT = dtime(13, 25)


@dataclass
class Replay:
    code: str
    date: str
    or_high: float
    entry: float
    stop: float
    target: float
    result: str
    exit_price: float
    r_multiple: float
    net_pct: float
    held_min: int


def _t(hhmm: str) -> dtime:
    h, m = (int(x) for x in hhmm.split(":")[:2])
    return dtime(h, m)


def opening_range(bars, or_minutes: int, start=dtime(9, 0)):
    """回傳 (高, 低)。K 棒 label 是該分鐘的結束時間，所以 label 為 T 的那根
    涵蓋 (T-1分, T] —— 區間要收的是 label 在 (start, start+N] 之間的那些。"""
    begin = datetime.combine(datetime(2000, 1, 1), start)
    end = begin + timedelta(minutes=or_minutes)
    inside = [b for b in bars
              if begin < datetime.combine(datetime(2000, 1, 1), b[0].time()) <= end]
    if not inside:
        return None
    return max(b[1] for b in inside), min(b[2] for b in inside)


def replay(bars, or_minutes: int, window_minutes: int, reward_risk: float,
           exit_at: dtime | None, optimistic: bool = True) -> Replay | None:
    """重跑一檔一天。bars = [(datetime, high, low, close), ...]，已照時間排序。

    optimistic=True  → 進場價取突破點（限價掛在那裡剛好成交）
    optimistic=False → 進場價取那一分鐘的收盤價（市價追進去）
    真實情況落在兩者之間。只報一個數字會讓人把其中一端當成事實。
    """
    cfg = config.SIGNAL
    rng = opening_range(bars, or_minutes)
    if not rng:
        return None
    or_high, _or_low = rng

    or_end = (datetime.combine(datetime(2000, 1, 1), dtime(9, 0))
              + timedelta(minutes=or_minutes)).time()
    win_end = (datetime.combine(datetime(2000, 1, 1), or_end)
               + timedelta(minutes=window_minutes)).time()
    trigger = or_high * (1 + cfg["breakout_buffer_pct"] / 100)

    hit = next((b for b in bars if or_end < b[0].time() <= win_end and b[1] >= trigger),
               None)
    if hit is None:
        return None
    # 一律往上進位到合法檔位。往下取的話會假設成交在一個「突破根本不需要
    # 走到」的價位，整份回測會無聲地偏向好看。
    entry = config.round_to_tick(trigger if optimistic else hit[3], "up")
    stop = min(config.round_to_tick(entry * (1 - cfg["stop_loss_pct"] / 100), "up"),
               config.round_to_tick(or_high * (1 - cfg["stop_below_or_high_pct"] / 100),
                                    "down"))
    risk = entry - stop
    if risk <= 0:
        return None
    target = config.round_to_tick(entry + risk * reward_risk, "up")

    # 整根都在進場之後的 K 棒才算 —— 和 outcome.py 同一個約定。包著進場那一刻的
    # 那根裡面有一段是進場前的價格，算進去會製造假停損（09-24 五筆誤判了四筆）。
    after = hit[0] + BAR_SPAN
    result, exit_price, last_t = oc.FLAT, bars[-1][3], bars[-1][0]
    for t, hi, lo, close in bars:
        if t < after or t.time() > FLATTEN_AT:
            continue
        last_t = t
        if lo <= stop:                      # 停損先判：往壞處算
            result, exit_price = oc.STOP, stop
            break
        if hi >= target:
            result, exit_price = oc.TARGET, target
            break
        if exit_at and t.time() >= exit_at:
            result, exit_price = "時間到", close
            break
    else:
        exit_price = bars[-1][3]

    gross = (exit_price - entry) / entry * 100
    return Replay(
        code="", date="", or_high=or_high, entry=entry, stop=stop, target=target,
        result=result, exit_price=round(exit_price, 2),
        r_multiple=round((exit_price - entry) / risk, 2),
        net_pct=round(gross - config.round_trip_cost_pct(), 3),
        held_min=max(0, int((last_t - hit[0]).total_seconds() // 60)),
    )


def summarise(rows: list[Replay]) -> dict:
    if not rows:
        return {"n": 0}
    wins = [r for r in rows if r.net_pct > 0]
    return {"n": len(rows), "wins": len(wins),
            "rate": round(len(wins) / len(rows) * 100, 1),
            "avg_r": round(sum(r.r_multiple for r in rows) / len(rows), 2),
            "total_r": round(sum(r.r_multiple for r in rows), 2),
            "avg_min": round(sum(r.held_min for r in rows) / len(rows))}


def day_bars(broker, code: str, date: str):
    """當天全部分鐘 K，(datetime, high, low, close)。"""
    from broker import _bar_time
    try:
        kb = broker.kbars(code, date, date)
    except Exception as e:
        log.warning("%s %s 分鐘 K 取得失敗：%s", date, code, e)
        return []
    ts = list(getattr(kb, "ts", []) or [])
    his = list(getattr(kb, "High", []) or [])
    los = list(getattr(kb, "Low", []) or [])
    cls = list(getattr(kb, "Close", []) or [])
    if not (len(ts) == len(his) == len(los) == len(cls)):
        log.warning("%s %s 分鐘 K 欄位長度不一致，跳過", date, code)
        return []
    return sorted(((_bar_time(t), float(h), float(l), float(c))
                   for t, h, l, c in zip(ts, his, los, cls)), key=lambda b: b[0])


GRID_OR = (1, 2, 3, 5, 15)
GRID_RR = (1.0, 1.5, 2.0, 2.5)
GRID_EXIT = (("09:30", dtime(9, 30)), ("10:00", dtime(10, 0)), ("抱到底", None))


def render(results: dict, pairs: int, optimistic: bool) -> list[str]:
    head = "樂觀（限價掛在突破點）" if optimistic else "悲觀（該分鐘收盤價追進去）"
    out = [
        "# whatif —— 不同進場／出場規則的重跑",
        "",
        "> **這份回測對自己有利。** 它只重跑 `outcomes.csv` 裡有的股票，也就是當天",
        "> 後來真的突破了的那幾檔。碰到區間高就掛掉的那些從來沒進過紀錄，但縮短",
        "> 區間之後它們會被買進來。所以「縮短區間比較好」這個方向的結論偏樂觀。",
        "> 要修掉這個偏誤，需要每天完整的 watchlist.json 存檔。",
        "",
        f"進場價取法：**{head}**。真實情況落在兩種之間。",
        f"樣本：{pairs} 個（日期 × 股票）。漲停夾擠未計入。",
        "",
        "| 區間 | 目標 | 出場 | 筆數 | 勝率 | 平均R | 合計R | 平均持有 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key in sorted(results):
        s = results[key]
        if not s["n"]:
            continue
        orm, rr, ex = key
        out.append(f"| {orm} 分 | {rr}R | {ex} | {s['n']} | {s['rate']}% | "
                   f"{s['avg_r']:+.2f} | {s['total_r']:+.2f} | {s['avg_min']} 分 |")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="重跑不同的進場／出場規則")
    ap.add_argument("--window", type=int, default=3,
                    help="區間鎖定後，幾分鐘內的突破算數（預設 3，對應 09:02–09:05）")
    ap.add_argument("--pessimistic", action="store_true",
                    help="進場價改用該分鐘的收盤價（市價追進去）")
    ap.add_argument("--out", default="journal/whatif.md")
    args = ap.parse_args(argv)

    rows = oc.load_csv()
    if not rows:
        raise SystemExit("outcomes.csv 是空的或讀不到 —— 先累積幾天再跑。")
    pairs = sorted({(r.date, r.code) for r in rows})
    print(f"要重跑 {len(pairs)} 個（日期 × 股票），每個都要跟券商要一次分鐘 K。")

    from broker import Broker
    broker = Broker()
    broker.login()

    cache = {}
    for date, code in pairs:
        cache[(date, code)] = day_bars(broker, code, date)
    missing = [k for k, v in cache.items() if not v]
    if missing:
        print(f"⚠️ {len(missing)} 個取不到分鐘 K，已排除：{missing[:5]}")

    results = {}
    for orm in GRID_OR:
        for rr in GRID_RR:
            for label, ex in GRID_EXIT:
                got = []
                for key, bars in cache.items():
                    if not bars:
                        continue
                    r = replay(bars, orm, args.window, rr, ex,
                               optimistic=not args.pessimistic)
                    if r:
                        got.append(r)
                results[(orm, rr, label)] = summarise(got)

    lines = render(results, len(pairs) - len(missing), not args.pessimistic)
    path = config.BASE_DIR / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ 已寫入 {path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
