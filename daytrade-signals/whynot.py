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
BLOCK_GAP = "離昨收太遠"          # v9：開盤和回落低點都不在昨收附近
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


def volume_ratio(bars, hit_time, or_start: dtime) -> float | None:
    """這一分鐘的量 ÷ 開盤後到前一分鐘為止的每分鐘平均量。

    盤中的 volume_surge() 比的是「最近 60 秒的每秒成交率」vs「更早那一段
    的每秒成交率」，而更早那一段會一路往後長 —— 09:04 判的時候，基準包含
    09:01–09:03 全部。所以這裡的基準也是「這一根之前、開盤之後的全部」，
    不是固定只看開盤區間那兩根。

    09:00 那一根（label 09:00 = 08:59–09:00，含開盤集合競價那一筆）不算：
    盤中是用累計量相減，第一筆的累計值本身就被減掉了。
    """
    base = [b[4] for b in bars if or_start < b[0].time() < hit_time.time()]
    hit = next((b[4] for b in bars if b[0] == hit_time), None)
    if not base or hit is None:
        return None
    avg = sum(base) / len(base)
    return (hit / avg) if avg else None


def diagnose(bars, prev_close: float | None = None,
             day_open: float | None = None) -> dict:
    """重建那幾道閘，回傳卡在哪一關。bars = [(dt, high, low, close, volume), ...]

    day_open = 當日開盤價（分鐘 K 的第一根 Open）；不知道就只用回落低點判 v9 那一關。
    """
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

    crossings = [b for b in window if b[1] >= trigger]
    if not crossings:
        return out                      # 連突破都沒有，後面幾關不必判

    # 盤中的 evaluate() **每個 tick 都重判一次**：09:03 被量能擋下，09:04
    # 量能衝上來就過了。第一版只判第一根越過觸發價的 K 棒、被擋就結案 ——
    # 2026-10-05 的加高就這樣被誤判成「量能 0.23x 擋掉」，而它盤中明明在
    # 09:04:38 以 1.94x 發出了訊號。所以：窗口裡每一根越過的都要判，
    # 任何一根全過就算通過；都沒過，報「走得最遠」的那一次卡在哪。
    cap = config.limit_up(prev_close) if prev_close else None
    band = cfg.get("near_prev_close_pct")
    best, best_key = None, None
    for b in crossings:
        vw = vwap_upto(bars, b[0]) if cfg["require_above_vwap"] else None
        vr = volume_ratio(bars, b[0], or_start)
        # 盤中的 day_low 是「到這一刻為止」的當日最低，包含當下這一根。
        low = min((x[2] for x in bars if or_start < x[0].time() <= b[0].time()),
                  default=None)
        if cfg["require_above_vwap"] and (vw is None or b[1] < vw):
            verdict, rank = BLOCK_VWAP, 0
        elif vr is None or vr < cfg["volume_surge_ratio"]:
            verdict, rank = BLOCK_VOLUME, 1
        elif band is not None and not config.near_prev_close(prev_close, day_open, low, band):
            verdict, rank = BLOCK_GAP, 2
        elif cap and b[1] >= cap:
            verdict, rank = BLOCK_LIMIT_UP, 3
        else:
            verdict, rank = PASS, 4
        # 走得越遠越好；同樣卡在量能的，量能比較高的那次比較接近過關
        key = (rank, vr or 0.0)
        if best_key is None or key > best_key:
            best, best_key = (b, vw, vr, verdict), key
        if verdict == PASS:
            break                       # 盤中第一次全過就發了，後面不用看

    b, vw, vr, verdict = best
    out.update(hit_at=b[0], hit_price=b[1], vwap=vw, vol_ratio=vr,
               verdict=verdict, attempts=len(crossings))
    return out


def crosscheck_lines(actual: set | None, rows) -> list[str]:
    """拿 outcomes.csv 裡當天真的發出去的訊號，對重建結果的答案。

    這一段存在的原因：第一版 whynot 把 2026-10-05 的加高判成「量能 0.23x
    擋掉」，而它盤中明明發出了訊號。那是這張表裡**唯一有標準答案的一列**，
    而它答錯了。沒有人去對，這張表就會被當成真的。

    所以每次都對，對不上就放在報表第一段，不是埋在最後。
    """
    if actual is None:
        return ["> ⚠️ **無法對答案**：outcomes.csv 裡沒有這一天的訊號紀錄，"
                "這張表的準確度沒有被驗證過。", ""]
    passed = {code for code, _, d in rows if d["verdict"] == PASS}
    missed = sorted(actual - passed)         # 盤中發了，重建說擋掉
    extra = sorted(passed - actual)          # 重建說會發，盤中沒發
    if not missed and not extra:
        return [f"> ✅ **對過答案了**：盤中當天發出 {len(actual)} 個訊號"
                f"（{'、'.join(sorted(actual)) or '無'}），重建結果完全一致。", ""]
    out = ["> 🛑 **重建跟盤中紀錄對不上 —— 下面這張表不能全信。**"]
    for code in missed:
        d = next((d for c, _, d in rows if c == code), None)
        why = d["verdict"] if d else "不在名單裡"
        out.append(f"> - {code}：盤中**有發**訊號，重建卻判定「{why}」"
                   f" —— 重建比盤中嚴格，被擋的那幾檔可能其實會過")
    for code in extra:
        out.append(f"> - {code}：重建判定**會發**，盤中卻沒發"
                   f" —— 可能是批次只取前 {config.RISK['max_signals_per_day']} 檔，"
                   f"或盤中 tick 層級的細節分鐘 K 看不到")
    return out + [""]


def render(date: str, rows: list, actual: set | None = None,
           check: bool = False) -> list[str]:
    cfg = config.SIGNAL
    out = [
        f"# whynot —— {date} 監看的 {len(rows)} 檔，各自卡在哪一關",
        "",
    ]
    if check:
        out += crosscheck_lines(actual, rows)
    out += [
        "> **這是用分鐘 K 事後重建的，不是盤中那條路徑的紀錄。**",
        "> 量能倍數是分鐘版近似（盤中用 tick 的每秒成交率），均價線也是估的",
        "> （kbars 沒有 Amount，用 (高+低+收)/3 × 量 累加）。",
        f"> 要看的是**分佈**：全場都卡在同一關，跟散在各關，意思完全不同。",
        "",
        f"規則：開盤區間 {cfg['or_start'][:5]}–{cfg['or_end'][:5]}，"
        f"突破緩衝 +{cfg['breakout_buffer_pct']}%，"
        f"進場窗口到 {cfg['entry_window_end'][:5]}，"
        f"量能門檻 {cfg['volume_surge_ratio']}x"
        + (f"，開盤或回落低點在昨收 ±{cfg['near_prev_close_pct']:g}% 以內"
           if cfg.get("near_prev_close_pct") is not None else ""),
        "",
        "| 代號 | 名稱 | 區間高 | 觸發價 | 窗口內最高 | 判定那根 | 均價線 | 量能近似 | 卡在哪一關 |",
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
    for k in (BLOCK_NO_BREAKOUT, BLOCK_VWAP, BLOCK_VOLUME, BLOCK_GAP, BLOCK_LIMIT_UP,
              PASS, "無區間"):
        if k in tally:
            out.append(f"- **{k}**：{tally[k]} 檔")
    out += ["", "怎麼讀："]
    out += ["- 多數卡在「沒突破」→ 瓶頸是窗口／區間長度，不是濾網",
            "- 多數卡在「量能」→ 濾網可能在齊漲日失效（全場都爆量，比值反而接近 1）",
            "- 多數卡在「離昨收太遠」→ 那天的名單大多跳空開高、沒有回到昨收附近（v9 的條件）",
            "- 散在各關 → 沒有單一瓶頸，是機率問題"]
    return out


def day_bars(broker, code: str, date: str):
    """(datetime, high, low, close, volume)，照時間排序。"""
    return day_bars_and_open(broker, code, date)[0]


def day_bars_and_open(broker, code: str, date: str):
    """同一次 kbars 查詢拿兩樣東西：分鐘 K，和當日開盤價（第一根的 Open）。

    開盤價是 v9 那一關要的。分開查等於每檔多打一次 API —— 20 檔就是 20 次，
    券商有流量上限。拿不到 Open（舊版 kbars、欄位長度不對）就回 None，
    v9 那一關改用回落低點判。
    """
    from broker import _bar_time
    try:
        kb = broker.kbars(code, date, date)
    except Exception as e:
        log.warning("%s %s 分鐘 K 取得失敗：%s", date, code, e)
        return [], None
    cols = [list(getattr(kb, n, []) or [])
            for n in ("ts", "High", "Low", "Close", "Volume")]
    if not cols[0] or len({len(c) for c in cols}) != 1:
        log.warning("%s %s 分鐘 K 欄位長度不一致，跳過", date, code)
        return [], None
    rows = []
    for t, hi, lo, cl, vo in zip(*cols):
        bt = _bar_time(t)
        if bt is not None:
            rows.append((bt, float(hi), float(lo), float(cl), float(vo)))
    opens = list(getattr(kb, "Open", []) or [])
    opened = None
    if len(opens) == len(cols[0]):
        firsts = [(_bar_time(t), o) for t, o in zip(cols[0], opens)]
        firsts = sorted((t, float(o)) for t, o in firsts if t is not None and o)
        opened = firsts[0][1] if firsts else None
    return sorted(rows, key=lambda b: b[0]), opened


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
        bars, opened = day_bars_and_open(broker, code, args.date)
        if not bars:
            continue
        rows.append((code, it.get("name", ""),
                     diagnose(bars, it.get("prev_close"), day_open=opened)))

    actual = None
    try:
        import outcome as oc
        today = [r for r in oc.load_csv() if r.date == args.date]
        actual = {str(r.code) for r in today} if today else None
    except Exception as e:
        log.warning("outcomes.csv 讀不到，無法對答案：%s", e)
    text = "\n".join(render(args.date, rows, actual=actual, check=True))
    print()
    print(text)
    out = args.out or (config.JOURNAL_DIR / f"whynot-{args.date.replace('-', '')}.md")
    config.JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(f"\n→ 已寫入 {out}")


if __name__ == "__main__":
    main()
