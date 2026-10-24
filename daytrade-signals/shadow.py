# -*- coding: utf-8 -*-
"""shadow.py —— 影子首選：B、C 兩個公式每天背後也選一檔，收盤後跟正式首選（A）比（不推播）。

10-23 使用者：「好，加影子首選」。pickcheck.py 29 天裡「昨收位置」方向反了最穩定；但那是看了
同一份資料才想到的，直接換公式等於拿考古題考自己。所以正式首選照舊用 A（6／30 的驗證不中斷），
B、C 從今天起每天記一筆 —— 這些日子是改之前沒看過的，11-09 拿來比才算數。

三個公式都用**同一個算法**回推（分鐘 K、09:00 開盤價、同一套出場），A 也是 —— 正式首選盤中的
即時判定（picks.csv）會有一點點不同，拿來跟 B、C 比不公平。結果寫 shadow.csv。
"""
import csv
import json
import logging

import config
import premarket

log = logging.getLogger("shadow")

FILE = config.BASE_DIR / "shadow.csv"
FIELDS = ("date", "formula", "code", "name", "same_as_a", "result", "entry", "exit_price",
          "r_multiple", "net_r", "net_pct", "net_amount")
LOCKED = "漲停買不到"
NO_BARS = "沒有分鐘 K"


def picks_for(wl: dict) -> dict:
    """{"A": 首選, "B": …, "C": …}。存檔裡沒有 shadow（舊的名單）就用同一個候選池重算。"""
    items = wl.get("items") or []
    pool = items + (wl.get("not_watched") or [])
    shadow = wl.get("shadow") or premarket.shadow_picks(pool, watched=[i["code"] for i in items])
    return {"A": wl.get("pick"), **{k: shadow.get(k) for k in premarket.SHADOWS}}


def row_for(date: str, code: str, pick: dict | None, bars, a_code) -> dict | None:
    import whatif
    if not pick:
        return None
    row = {"date": date, "formula": code, "code": str(pick["code"]), "name": pick.get("name", ""),
           "same_as_a": int(str(pick["code"]) == str(a_code))}
    if not bars:
        return dict(row, result=NO_BARS)
    tr = whatif.pick_trade(date, pick, bars)
    if tr is None:
        locked = premarket.plan(pick, bars[0][1]) is None       # 開盤就漲停
        return dict(row, result=LOCKED if locked else NO_BARS)
    return dict(row, result=tr.result, entry=tr.entry, exit_price=tr.exit_price,
                r_multiple=tr.r_multiple, net_r=tr.net_r, net_pct=round(tr.net_pct, 3),
                net_amount=round(tr.net_pct / 100 * tr.entry * 1000 * tr.lots))


def resolve(wl: dict, date: str, bars_of) -> list[dict]:
    """今天三個公式各一筆。bars_of(代號) → 今天的 1 分 K。"""
    picks = picks_for(wl)
    a_code = (picks.get("A") or {}).get("code")
    rows = []
    for code, _name, _f in premarket.FORMULAS:
        pick = picks.get(code)
        row = row_for(date, code, pick, bars_of(str(pick["code"])) if pick else None, a_code)
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
    keep.sort(key=lambda r: (r["date"], r["formula"]))
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in keep:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in FIELDS})


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def report_lines(today: list[dict], history: list[dict]) -> list[str]:
    """日報那一段。單筆一行不超過 20 字。"""
    if not today and not history:
        return []
    lines = ["────────────────", "🌑 影子首選（不推播，只比較）"]
    for r in today:
        label = f"{r['formula']} {r['code']} {str(r.get('name', ''))[:3]}"
        r_val = _num(r.get("net_r"))
        lines.append(f"{label}　{r_val:+.2f}R" if r_val is not None else f"{label}　{r['result']}")
    if history:
        lines.append("累計（同一個算法）：")
        for code, _name, _f in premarket.FORMULAS:
            done = [r for r in history if r.get("formula") == code and _num(r.get("net_r")) is not None]
            if done:
                avg = sum(float(r["net_r"]) for r in done) / len(done)
                lines.append(f"{code} {len(done)} 筆　平均 {avg:+.2f}R")
    return lines


def section(broker, date: str) -> list[str]:
    """review.py 收盤後叫。壞掉不可以讓日報產不出來（呼叫端包 try）。"""
    import outcome as oc
    try:
        wl = json.loads(config.WATCHLIST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if wl.get("date") != date:
        return []
    rows = []
    if broker is not None:
        rows = resolve(wl, date, lambda code: oc.day_bars_ohlcv(broker, code, date))
        append(rows)
    return report_lines(rows, load())
