"""
dryrun.py — 不連券商、不用金鑰，把一整天的 tick 灌進引擎跑一遍。

    python3 dryrun.py        （Windows 是 python dryrun.py）

用途是**驗證管線本身**，不是驗證策略賺不賺錢：
訊號條件、風控閘門、覆盤版型有沒有真的串起來。
第一次上線前、以及每次改完 config.py 之後跑一次，
免得在真正的 09:00 才發現整天不會發訊號。

產出寫到 journal/DRYRUN-YYYYMMDD.md，不會覆蓋真實交易日誌。
"""
import os
os.environ.setdefault("DAYTRADE_NO_PUSH", "1")  # 假 tick 不可以推到手機
import argparse
import random
from datetime import datetime, time as dtime
from types import SimpleNamespace

import config
import review
import signals
from signals import RiskGate, SymbolState, evaluate, format_signal, _t


class FakeBroker:
    """只實作風控閘門會用到的三個方法。"""

    def __init__(self, pnl_rows=None, trades=None):
        self._pnl_rows = pnl_rows if pnl_rows is not None else []
        self._trades = trades or []

    def trades_today(self):
        return self._trades

    def realized_pnl_rows_today(self):
        return self._pnl_rows

    def realized_pnl_today(self):
        return None if self._pnl_rows is None else float(sum(self._pnl_rows))


def synth_day(code: str, prev_close: float, breakout: bool, rng: random.Random,
              flat_after: bool = False):
    """造一天的 tick，照 v4 的時間軸。

    09:00:00–09:02:00  開盤區間，量能平淡（這一段同時是量能基準）
    09:02:00–09:03:30  盤整
    09:03:30–09:05:00  breakout=True 的那檔帶量向上突破
    09:05:00–09:35:00  收盤前的走勢，用來走到 09:30 的「時間到」提醒

    每 10 秒一筆。進場窗口只有三分鐘，所以取樣密度必須比 v3 高 ——
    一分鐘一筆的話整個突破窗口只有三個點，量能速率算不出來。
    """
    ticks = []
    total_volume = 0
    cum_pv = 0.0
    SURGE_FROM = 210            # 09:03:30，距離 09:00 的秒數

    def push(sec: int, price: float, lots: int):
        nonlocal total_volume, cum_pv
        total_volume += lots
        cum_pv += price * lots
        ticks.append((dtime(9, sec // 60, sec % 60), price, lots, total_volume,
                      round(cum_pv / total_volume, 2)))

    for sec in range(0, 120, 10):           # 開盤區間
        push(sec, config.round_to_tick(prev_close * (1 + rng.uniform(-0.004, 0.004))),
             rng.randint(8, 12))
    or_high = max(t[1] for t in ticks)

    for sec in range(120, SURGE_FROM, 10):  # 盤整
        push(sec, config.round_to_tick(or_high * (1 - rng.uniform(0.001, 0.006))),
             rng.randint(8, 12))

    for sec in range(SURGE_FROM, 300, 10):  # 突破窗口
        if breakout:
            step = (sec - SURGE_FROM) / 10
            push(sec, config.round_to_tick(or_high * (1 + 0.003 + step * 0.0012)),
                 rng.randint(55, 70))       # 量能明顯放大
        else:
            push(sec, config.round_to_tick(or_high * (1 - rng.uniform(0.001, 0.006))),
                 rng.randint(8, 12))

    for sec in range(300, 2100, 30):        # 09:05 → 09:35，走到時間出場
        if flat_after:
            # 刻意不動：這一檔既不到目標也不到停損，09:30 的「時間到」提醒
            # 才有東西可以提醒。驗證工具走不到的路徑，等於沒有被驗證。
            push(sec, ticks[-1][1], rng.randint(5, 15))
            continue
        drift = rng.uniform(-0.004, 0.004) + (0.0015 if breakout else -0.0005)
        push(sec, config.round_to_tick(ticks[-1][1] * (1 + drift)), rng.randint(5, 15))

    return ticks


def as_tick(code, t: dtime, price, total_volume, avg, day_high, day_low):
    return SimpleNamespace(
        code=code, close=price, high=day_high, low=day_low,
        avg_price=avg, total_volume=total_volume, simtrade=0,
        datetime=datetime.combine(datetime.now().date(), t))


def main():
    ap = argparse.ArgumentParser(description="離線灌 tick 驗證管線")
    ap.add_argument("--seed", type=int, default=20260101)
    ap.add_argument("--symbols", type=int, default=6, help="模擬幾檔")
    # 突破的檔數刻意多於訊號上限，否則 SignalBatch 的排序與淘汰整段走不到。
    ap.add_argument("--breakouts", type=int, default=4, help="其中幾檔會帶量突破")
    args = ap.parse_args()

    errs = config.validate()
    if errs:
        raise SystemExit("config.py 參數有問題：\n" + "\n".join(f"  - {e}" for e in errs))

    rng = random.Random(args.seed)
    codes = [(f"{2330 + i}", 100.0 + i * 20) for i in range(args.symbols)]

    gate = RiskGate(FakeBroker())
    gate.state = {"date": datetime.now().strftime("%Y-%m-%d"), "signals_sent": 0,
                  "closed": False, "closed_reason": "", "signals": []}
    original_save, gate.save = gate.save, lambda: None    # dry run 不碰 state.json

    fired = []
    print(f"=== DRY RUN（seed={args.seed}）===")
    print(f"來回成本基準：{config.round_trip_cost_pct():.4f}%")
    print(f"規則版本：{config.RULESET}　進場窗口 {config.SIGNAL['or_end']}–"
          f"{config.SIGNAL['signal_batch_at']}　訊號上限 "
          f"{config.RISK['max_signals_per_day']}\n")

    # 所有檔的 tick 併成一條時間序。v4 的訊號是 09:05 一次發出、跨檔排序的，
    # 一檔跑完再跑下一檔的話，SignalBatch 的排序與上限根本沒有被走到 ——
    # 那就等於這支程式在驗一條實際上不存在的管線。
    states, streams = {}, []
    for idx, (code, prev_close) in enumerate(codes):
        states[code] = SymbolState(code, prev_close)
        ticks = synth_day(code, prev_close, breakout=idx < args.breakouts, rng=rng,
                          # 第一檔突破後橫盤到收 —— 專門用來走 09:30 的提醒
                          flat_after=(idx == 0))
        hi = lo = ticks[0][1]
        for n, (t, price, _lots, total_volume, avg) in enumerate(ticks):
            hi, lo = max(hi, price), min(lo, price)
            streams.append((t, n, code, price, total_volume, avg, hi, lo))
    streams.sort(key=lambda r: (r[0], r[1]))

    batch = signals.SignalBatch(_t(config.SIGNAL["signal_batch_at"]),
                                config.RISK["max_signals_per_day"])
    tracker = signals.LiveTracker()
    blocked = []
    today = datetime.now().date()

    def flush(at: dtime):
        if not batch.due(datetime.combine(today, at)):
            return
        chosen, rest = batch.take()
        blocked.extend(rest)
        for sig in chosen:
            st = states[str(sig["code"])]
            if not gate.check():
                blocked.append(sig)
                continue
            st.signaled += 1
            ordinal = gate.record(sig)
            fired.append(sig)
            tracker.track(sig)
            print(format_signal(sig, ordinal))
            print()

    exited = []
    for t, n, code, price, total_volume, avg, hi, lo in streams:
        st = states[code]
        # 每筆 tick 間隔 10 模擬秒。量能速率算的是「每秒成交量」，
        # 不注入模擬時鐘的話所有 tick 都落在同一瞬間，速率永遠算不出來。
        st.update(as_tick(code, t, price, total_volume, avg, hi, lo),
                  now=1_000_000.0 + (t.hour * 3600 + t.minute * 60 + t.second))
        for msg in tracker.on_price(code, price):
            print(msg + "\n")
        sig = evaluate(st, now=t)
        if sig:
            sig["time"] = t.strftime("%H:%M:%S")
            batch.add(sig)
        flush(t)
        if t >= _t(config.SIGNAL["exit_signal_at"]) and not exited:
            exited = tracker.time_exit(datetime.combine(today, t))
            for msg in exited:
                print(msg + "\n")

    flush(dtime(23, 59))        # 整天都沒報價也要把批次送出去
    for code, st in states.items():
        status = (config.symbol("✔ 已鎖定", "[鎖定]") if st.or_locked
                  else config.symbol("✘ 未鎖定", "[未鎖]"))
        print(f"[{code}] 開盤區間 {status} {st.or_high:.2f}/{st.or_low:.2f}"
              f"  收 {st.last_price:.2f}  量能倍數 {st.volume_surge():.2f}x"
              f"  訊號 {st.signaled}")
    print(f"\n批次落選／被閘門擋掉：{len(blocked)} 檔"
          f"　09:30 時間到提醒：{len(exited)} 則")
    # 這支程式的用途是「上線前確認管線是通的」。沒走到的分支就是沒驗過的分支，
    # 要說出來 —— 不然它看起來一片綠，而真正的那天才發現某一段從來沒執行過。
    for cond, what in ((blocked, "批次淘汰（突破檔數沒有超過訊號上限）"),
                       (exited, "09:30 時間到提醒（沒有部位活到那個時間）")):
        if not cond:
            print(config.symbol("⚠️ ", "[WARN] ") + f"這次沒有走到：{what}")

    gate.save = original_save
    print(f"\n訊號數：{len(fired)}／上限 {config.RISK['max_signals_per_day']}"
          f"　閘門：{'已關閉 — ' + gate.state['closed_reason'] if gate.state['closed'] else '開啟'}")

    lines = review.render(fired, [], gate.state, pnl=0.0,
                          note="⚠️ 這是 dryrun.py 的模擬資料，不是真實交易紀錄。")
    path = review.write_journal(lines, date=f"DRYRUN-{datetime.now():%Y%m%d}")
    print(f"→ 覆盤版型已寫入 {path}")

    if not fired:
        print("\n⚠️ 一個訊號都沒發。要嘛條件太嚴，要嘛管線有斷點 —— 上線前先查清楚。")


if __name__ == "__main__":
    main()
