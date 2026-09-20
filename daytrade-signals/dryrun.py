"""
dryrun.py — 不連券商、不用金鑰，把一整天的 tick 灌進引擎跑一遍。

    python3 dryrun.py

用途是**驗證管線本身**，不是驗證策略賺不賺錢：
訊號條件、風控閘門、覆盤版型有沒有真的串起來。
第一次上線前、以及每次改完 config.py 之後跑一次，
免得在真正的 09:00 才發現整天不會發訊號。

產出寫到 journal/DRYRUN-YYYYMMDD.md，不會覆蓋真實交易日誌。
"""
import argparse
import random
from datetime import datetime, time as dtime
from types import SimpleNamespace

import config
import review
import signals as sig_mod
from signals import RiskGate, SymbolState, evaluate, format_signal


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


def synth_day(code: str, prev_close: float, breakout: bool, rng: random.Random):
    """造一天的 tick。breakout=True 的那檔會在 09:40 帶量突破開盤區間。"""
    ticks = []
    price = config.round_to_tick(prev_close)
    total_volume = 0
    cum_pv = 0.0          # 用來算均價線

    # 09:00–09:15 開盤區間：小幅來回
    for i in range(90):
        price = config.round_to_tick(prev_close * (1 + rng.uniform(-0.004, 0.004)))
        lots = rng.randint(3, 12)
        total_volume += lots
        cum_pv += price * lots
        ticks.append((dtime(9, i // 6, (i % 6) * 10), price, lots, total_volume,
                      round(cum_pv / total_volume, 2)))
    or_high = max(t[1] for t in ticks)

    # 09:15–09:40 盤整，量能平淡（建立量能基準）
    minute = 15
    for i in range(150):
        price = config.round_to_tick(or_high * (1 - rng.uniform(0.001, 0.008)))
        lots = rng.randint(3, 12)
        total_volume += lots
        cum_pv += price * lots
        ticks.append((dtime(9, minute + i // 6, (i % 6) * 10), price, lots, total_volume,
                      round(cum_pv / total_volume, 2)))

    # 09:40 起：突破組帶量向上，其餘繼續盤整
    for i in range(120):
        if breakout:
            price = config.round_to_tick(or_high * (1 + 0.002 + i * 0.0004))
            lots = rng.randint(30, 60)          # 量能明顯放大
        else:
            price = config.round_to_tick(or_high * (1 - rng.uniform(0.001, 0.008)))
            lots = rng.randint(3, 12)
        total_volume += lots
        cum_pv += price * lots
        ticks.append((dtime(9, 40 + i // 6, (i % 6) * 10), price, lots, total_volume,
                      round(cum_pv / total_volume, 2)))

    return ticks


def as_tick(code, t: dtime, price, total_volume, avg, day_high, day_low):
    return SimpleNamespace(
        code=code, close=price, high=day_high, low=day_low,
        avg_price=avg, total_volume=total_volume, simtrade=0,
        datetime=datetime.combine(datetime.now().date(), t))


def main():
    ap = argparse.ArgumentParser(description="離線灌 tick 驗證管線")
    ap.add_argument("--seed", type=int, default=20260101)
    ap.add_argument("--symbols", type=int, default=5, help="模擬幾檔")
    ap.add_argument("--breakouts", type=int, default=2, help="其中幾檔會帶量突破")
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
    print(f"來回成本基準：{config.round_trip_cost_pct():.4f}%\n")

    for idx, (code, prev_close) in enumerate(codes):
        st = SymbolState(code, prev_close)
        ticks = synth_day(code, prev_close, breakout=idx < args.breakouts, rng=rng)
        day_high = day_low = ticks[0][1]
        base = 1_000_000.0                       # 假的 wall clock 起點
        for n, (t, price, _lots, total_volume, avg) in enumerate(ticks):
            day_high, day_low = max(day_high, price), min(day_low, price)
            tk = as_tick(code, t, price, total_volume, avg, day_high, day_low)
            # 每筆 tick 間隔 10 模擬秒。量能速率算的是「每秒成交量」，
            # 不注入模擬時鐘的話所有 tick 都落在同一瞬間，速率永遠算不出來。
            st.update(tk, now=base + n * 10)
            s = evaluate(st, now=t)
            if s and gate.check():
                st.signaled += 1
                s["time"] = t.strftime("%H:%M:%S")
                ordinal = gate.record(s)
                fired.append(s)
                print(format_signal(s, ordinal))
                print()

        status = (config.symbol("✔ 已鎖定", "[鎖定]") if st.or_locked
                  else config.symbol("✘ 未鎖定", "[未鎖]"))
        print(f"[{code}] 開盤區間 {status} {st.or_high:.2f}/{st.or_low:.2f}"
              f"  收 {st.last_price:.2f}  量能倍數 {st.volume_surge():.2f}x"
              f"  訊號 {st.signaled}")

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
