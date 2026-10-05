# -*- coding: utf-8 -*-
"""whynot.py —— 那一天監看的每一檔，各自卡在哪一關。

2026-10-05：大盤 +2.30%、開盤就是當日最低一路沒回頭，量比第一名的聯一光
漲停 +9.95% —— 而系統只發了 1 個訊號，那一筆還停損。想知道另外 19 檔是
卡在突破、均價線還是量能，結果發現**查不到**：

    surge = st.volume_surge()
    if surge < cfg["volume_surge_ratio"]:
        return None          # ← 沒有 log，沒有 CSV，什麼都不留

`evaluate()` 的四道閘全部是靜音的 `return None`。candidates.csv 只記
「訊號已經產生、但被額度或批次排序擋掉」的那種，跟這四關無關。

這支程式用分鐘 K 事後重建那四道閘，把「為什麼今天只有 N 個訊號」從用猜的
變成一張表。

**它不是盤中那條路徑的紀錄，是重建。** 兩個已知落差：

1. **量能倍數只能近似。** 盤中的 volume_surge() 用 tick 算「每秒成交率」，
   這裡只有每分鐘總量。足以分辨「全場都在 1.0 附近」和「有人 3x 卻被別的
   關卡擋掉」，不能拿來跟訊息上那個 1.94x 逐位比對。
2. **均價線也是近似。** kbars 沒有 Amount 欄位（preflight 只檢查
   ts/High/Low/Volume），所以用 (高+低+收)/3 × 量 累加去估 VWAP，
   不是券商回報的 avg_price。

所以這張表要看的是**分佈**，不是單一數字。

用法：
    python whynot.py                  # 今天
    python whynot.py --date 2026-10-05
"""
import argparse
import json
import logging
import sys
from datetime import datetime, time as dtime, timedelta

import config

log = logging.getLogger("whynot")

# evaluate() 裡四道閘的順序。重建時必須照同一個順序判，否則「卡在哪一關」
# 會指到錯的地方 —— 一檔可能同時過不了兩關，盤中擋下它的是先遇到的那一關。
BLOCK_NO_BREAKOUT = "沒突破"
BLOCK_VWAP = "均價線"
BLOCK_VOLUME = "量能"
BLOCK_LIMIT_UP = "漲停"
PASS = "通過"


def _t(hhmmss: str) -> dtime:
    h, m, s = (int(x) for x in hhmmss.split(":"))
    return dtime(h, m, s)


def in_range(bar_time: dtime, start: dtime, end: dtime) -> bool:
    """K 棒 label 是該分鐘的**結束**時間，label 為 T 的那根涵蓋 (T-1分, T]。

    所以 09:00–09:02 的開盤區間要收的是 label 09:01 和 09:02 那兩根，
    判斷式是 (start, end]，不是 [start, end)。

    broker.py 第 222 行的註解說 ts 是「該分鐘的起點」，跟同一個檔案第 281
    行和 whatif.py 的說法相反。二比一，而且 v4 之後那條路徑是休眠的
    （09:05 就批次發完，晚啟動本來就不會有訊號），所以沒有動它 —— 但這裡
    用的是結束時間這個版本。
    """
    return start < bar_time <= end


def opening_range(bars, or_start: dtime, or_end: dtime):
    inside = [b for b in bars if in_range(b[0].time(), or_start, or_end)]
    if not inside:
        return None
    return max(b[1] for b in inside), min(b[2] for b in inside)


def vwap_upto(bars, upto) -> float | None:
    """到 upto（含）為止的累計均價估計。沒有 Amount 欄位，用典型價代替。"""
    num = den = 0.0
    for t, hi, lo, cl, vol in bars:
        if t > upto:
            break
        typical = (hi + lo + cl) / 3
        num += typical * vol
        den += vol
    return (num / den) if den else None


def volume_ratio(bars, hit_time, or_start: dtime, or_end: dtime) -> float | None:
    """突破那一分鐘的量 ÷ 開盤區間每分鐘的平均量。

    這是「加速度」的分鐘版近似。盤中那個 volume_surge() 比的是
    最近 60 秒的每秒成交率 vs 更早的基準 —— 同樣的意思，粗很多的尺。
    """
    base = [b[4] for b in bars if in_range(b[0].time(), or_start, or_end)]
    hit = next((b[4] for b in bars if b[0] == hit_time), None)
    if not base or hit is None:
        return None
    avg = sum(base) / len(base)
    return (hit / avg) if avg else None


def diagnose(bars, prev_close: float | None = None) -> dict:
    """重建那四道閘，回傳卡在哪一關。bars = [(dt, high, low, close, volume), ...]"""
    cfg = config.SIGNAL
    or_start, or_end = _t(cfg["or_start"]), _t(cfg["or_end"])
    win_end = _t(cfg["entry_window_end"])

    out = {"or_high": None, "or_low": None, "trigger": None, "hit_at": None,
           "hit_price": None, "window_high": None, "vwap": None,
           "vol_ratio": None, "verdict": BLOCK_NO_BREAKOUT}

    rng = opening_range(bars, or_start, or_end)
    if not rng:
        out["verdict"] = "無區間"
        return out
    out["or_high"], out["or_low"] = rng
    trigger = rng[0] * (1 + cfg["breakout_buffer_pct"] / 100)
    out["trigger"] = trigger

    window = [b for b in bars if in_range(b[0].time(), or_end, win_end)]
    out["window_high"] = max((b[1] for b in window), default=None)

    hit = next((b for b in window if b[1] >= trigger), None)
    if hit is None:
        return out                      # 連突破都沒有，後面幾關不必判
    out["hit_at"], out["hit_price"] = hit[0], hit[1]

    # ① 均價線
    if cfg["require_above_vwap"]:
        vw = vwap_upto(bars, hit[0])
        out["vwap"] = vw
        if vw is None or hit[1] < vw:
            out["verdict"] = BLOCK_VWAP
            return out

    # ② 量能
    vr = volume_ratio(bars, hit[0], or_start, or_end)
    out["vol_ratio"] = vr
    if vr is None or vr < cfg["volume_surge_ratio"]:
        out["verdict"] = BLOCK_VOLUME
        return out

    # ③ 漲停
    cap = config.limit_up(prev_close) if prev_close else None
    if cap and hit[1] >= cap:
        out["verdict"] = BLOCK_LIMIT_UP
        return out

    out["verdict"] = PASS
    return out


def render(date: str, rows: list) -> list[str]:
    cfg = config.SIGNAL
    out = [
        f"# whynot —— {date} 監看的 {len(rows)} 檔，各自卡在哪一關",
        "",
        "> **這是用分鐘 K 事後重建的，不是盤中那條路徑的紀錄。**",
        "> 量能倍數是分鐘版近似（盤中用 tick 的每秒成交率），均價線也是估的",
        "> （kbars 沒有 Amount，用 (高+低+收)/3 × 量 累加）。",
        f"> 要看的是**分佈**：全場都卡在同一關，跟散在各關，意思完全不同。",
        "",
        f"規則：開盤區間 {cfg['or_start'][:5]}–{cfg['or_end'][:5]}，"
        f"突破緩衝 +{cfg['breakout_buffer_pct']}%，"
        f"進場窗口到 {cfg['entry_window_end'][:5]}，"
        f"量能門檻 {cfg['volume_surge_ratio']}x",
        "",
        "| 代號 | 名稱 | 區間高 | 觸發價 | 窗口內最高 | 突破時間 | 均價線 | 量能近似 | 卡在哪一關 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for code, name, d in rows:
        f = lambda v, p=2: f"{v:.{p}f}" if isinstance(v, (int, float)) else "—"
        out.append(
            f"| {code} | {name} | {f(d['or_high'])} | {f(d['trigger'])} | "
            f"{f(d['window_high'])} | "
            f"{d['hit_at'].strftime('%H:%M') if d['hit_at'] else '—'} | "
            f"{f(d['vwap'])} | "
            f"{f(d['vol_ratio']) + 'x' if d['vol_ratio'] is not None else '—'} | "
            f"**{d['verdict']}** |")

    tally = {}
    for _, _, d in rows:
        tally[d["verdict"]] = tally.get(d["verdict"], 0) + 1
    out += ["", "## 卡在哪一關的分佈", ""]
    for k in (BLOCK_NO_BREAKOUT, BLOCK_VWAP, BLOCK_VOLUME, BLOCK_LIMIT_UP,
              PASS, "無區間"):
        if k in tally:
            out.append(f"- **{k}**：{tally[k]} 檔")
    out += ["", "怎麼讀："]
    out += ["- 多數卡在「沒突破」→ 瓶頸是窗口／區間長度，不是濾網",
            "- 多數卡在「量能」→ 濾網可能在齊漲日失效（全場都爆量，比值反而接近 1）",
            "- 散在各關 → 沒有單一瓶頸，是機率問題"]
    return out


def day_bars(broker, code: str, date: str):
    """(datetime, high, low, close, volume)，照時間排序。"""
    from broker import _bar_time
    try:
        kb = broker.kbars(code, date, date)
    except Exception as e:
        log.warning("%s %s 分鐘 K 取得失敗：%s", date, code, e)
        return []
    cols = [list(getattr(kb, n, []) or [])
            for n in ("ts", "High", "Low", "Close", "Volume")]
    if not cols[0] or len({len(c) for c in cols}) != 1:
        log.warning("%s %s 分鐘 K 欄位長度不一致，跳過", date, code)
        return []
    rows = []
    for t, hi, lo, cl, vo in zip(*cols):
        bt = _bar_time(t)
        if bt is not None:
            rows.append((bt, float(hi), float(lo), float(cl), float(vo)))
    return sorted(rows, key=lambda b: b[0])


def main(argv=None):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="那一天每一檔卡在哪一關")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    path = config.JOURNAL_DIR / f"watchlist-{args.date.replace('-', '')}.json"
    if not path.exists():
        raise SystemExit(
            f"找不到 {path.name}。\n"
            "當日候選池存檔是 screener.py 從 2026-10-05 起才開始寫的，"
            "更早的日子沒有 —— 那些日子監看了哪幾檔已經查不回來了。")
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    print(f"{args.date} 監看 {len(items)} 檔，每檔跟券商要一次分鐘 K。")

    from broker import Broker
    broker = Broker()
    broker.login()

    rows = []
    for it in items:
        code = str(it["code"])
        bars = day_bars(broker, code, args.date)
        if not bars:
            continue
        rows.append((code, it.get("name", ""),
                     diagnose(bars, it.get("prev_close"))))

    text = "\n".join(render(args.date, rows))
    print()
    print(text)
    out = args.out or (config.JOURNAL_DIR / f"whynot-{args.date.replace('-', '')}.md")
    config.JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(f"\n→ 已寫入 {out}")


if __name__ == "__main__":
    main()
