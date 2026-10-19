# -*- coding: utf-8 -*-
"""followup.py —— 盤前首選之後 5 個交易日怎麼走（只記錄，不影響任何規則）。

10-19 律勝連三天開盤鎖漲停（10-15 首選、買不到）。使用者：「起漲前線型真的很漂亮」。
事後看當然漂亮 —— 要知道「首選買不到的，後面是不是常常續漲」，得每一筆都記，
不能只記得漲上去的那幾檔。11-09 拿這份決定要不要另外做一套波段規則。

每一天的首選（買得到、買不到都算），記：
- 當天開盤價（盤前首選的買進價；開盤就漲停的，就是排隊買到的價格）
- 之後第 1～5 個交易日的收盤價，比開盤價漲跌幾 %
- 這 5 天裡最高漲到幾 %、最低跌到幾 %

review.py 每天 14:00 收盤後自動更新；手動看：python followup.py
"""
import csv
import logging
from datetime import date as ddate, datetime, time as dtime, timedelta

import config
import market_calendar

log = logging.getLogger("followup")

FOLLOW_DAYS = 5
FILE = config.BASE_DIR / "pick_followup.csv"
DAY_DONE_AT = dtime(13, 35)        # 收盤後才把今天算成「走完的一天」
FIELDS = ("date", "code", "name", "prev_close", "open0", "close0", "locked",
          *[f"d{i}_pct" for i in range(1, FOLLOW_DAYS + 1)], "high_pct", "low_pct", "days")


def trading_days_after(day: str, n: int) -> list[str]:
    """day 之後的 n 個交易日（舊到新）。週末和休市表上的日子跳過。"""
    out, d = [], ddate.fromisoformat(day)
    while len(out) < n:
        d += timedelta(days=1)
        if not market_calendar.closed_reason(d.isoformat()):
            out.append(d.isoformat())
    return out


def last_done_day(now: datetime | None = None) -> str:
    """走完的最後一天：收盤後是今天，盤中（或開盤前）是昨天。"""
    now = now or datetime.now()
    d = now.date() if now.time() >= DAY_DONE_AT else now.date() - timedelta(days=1)
    return d.isoformat()


def daily(bars) -> tuple | None:
    """一天的分鐘 K → (開, 高, 低, 收)。沒有 K 棒就 None。"""
    if not bars:
        return None
    return bars[0][1], max(b[2] for b in bars), min(b[3] for b in bars), bars[-1][4]


def _pct(price: float, base: float) -> float:
    return round((price - base) / base * 100, 2)


def build_row(day: str, pick: dict, by_day: dict, done: str) -> dict | None:
    """一筆首選。by_day = {日期: 分鐘 K}；done = 走完的最後一天。當天沒有 K 棒就 None。"""
    d0 = daily(by_day.get(day))
    if d0 is None:
        return None
    open0, prev = d0[0], float(pick["prev_close"])
    lu = config.limit_up(prev)
    row = {"date": day, "code": str(pick["code"]), "name": pick.get("name", ""),
           "prev_close": prev, "open0": open0, "close0": d0[3],
           "locked": int(lu is not None and open0 >= lu)}
    highs, lows, n = [], [], 0
    for i, d in enumerate(trading_days_after(day, FOLLOW_DAYS), 1):
        bar = daily(by_day.get(d)) if d <= done else None
        if bar is None:
            break                                 # 還沒走到，或那天沒資料：後面都先空著
        n = i
        row[f"d{i}_pct"] = _pct(bar[3], open0)
        highs.append(bar[1])
        lows.append(bar[2])
    row["high_pct"] = _pct(max(highs), open0) if highs else None
    row["low_pct"] = _pct(min(lows), open0) if lows else None
    row["days"] = n
    return row


def picks_from_journal() -> list[tuple[str, dict]]:
    """journal/ 裡每一天存的盤前首選（10-14 起才有）。"""
    import json
    out = []
    for path in sorted(config.JOURNAL_DIR.glob("watchlist-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("%s 讀不到：%s", path.name, e)
            continue
        d, pick = str(payload.get("date") or ""), payload.get("pick")
        if d and pick and not market_calendar.closed_reason(d):
            out.append((d, pick))
    return out


def load(path=None) -> list[dict]:
    path = path or FILE
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def save(rows: list[dict], path=None) -> None:
    path = path or FILE
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["date"]):
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in FIELDS})


def update(fetch_days, picks: list[tuple[str, dict]], done: str, path=None) -> list[dict]:
    """還沒走完 5 天的首選重抓一次。fetch_days(代號, 起, 迄) → {日期: 分鐘 K}。
    已經走完的不再抓。抓壞了的那一筆保留舊的，不影響其他筆。"""
    old = {r["date"]: r for r in load(path)}
    rows = dict(old)
    for day, pick in picks:
        if day > done:
            continue
        prev = old.get(day)
        if prev and prev.get("code") == str(pick["code"]) and int(prev.get("days") or 0) >= FOLLOW_DAYS:
            continue
        end = min(done, trading_days_after(day, FOLLOW_DAYS)[-1])
        try:
            row = build_row(day, pick, fetch_days(str(pick["code"]), day, end) or {}, done)
        except Exception as e:
            log.warning("%s %s 後續走勢抓不到：%s", day, pick.get("code"), e)
            continue
        if row is not None:
            rows[day] = row
    save(list(rows.values()), path)
    return sorted(rows.values(), key=lambda r: r["date"])


def broker_fetch(broker):
    """用券商的分鐘 K 抓一段日子，切成一天一天。"""
    import time
    from whatif import kbars_to_days

    def fetch(code, start, end):
        time.sleep(config.SCREEN["kbar_sleep_sec"])
        return kbars_to_days(broker.kbars(code, start, end))
    return fetch


def run(broker, now: datetime | None = None, path=None) -> list[dict]:
    """review.py 收盤後叫這一個。"""
    return update(broker_fetch(broker), picks_from_journal(), last_done_day(now), path)


def _cell(v) -> str:
    if v in (None, ""):
        return "　—"
    return f"{float(v):+.1f}%"


def table(rows: list[dict]) -> list[str]:
    """python followup.py 印出來的表。漲跌都是比當天開盤價。"""
    if not rows:
        return ["還沒有首選的紀錄（journal/ 裡沒有 10-14 以後的 watchlist 存檔）。"]
    head = "日期   首選          開盤  " + "  ".join(f"第{i}天" for i in range(1, FOLLOW_DAYS + 1)) \
        + "   最高    最低"
    out = ["盤前首選之後 5 個交易日（比當天開盤價；🔒＝開盤就漲停，買不到）", "", head]
    for r in rows:
        mark = "🔒" if str(r.get("locked")) == "1" else "　"
        days = "  ".join(_cell(r.get(f"d{i}_pct")) for i in range(1, FOLLOW_DAYS + 1))
        out.append(f"{r['date'][5:]}  {mark}{r['code']} {r['name'][:4]:<4}  "
                   f"{float(r['open0']):>6.2f}  {days}  {_cell(r.get('high_pct'))}  "
                   f"{_cell(r.get('low_pct'))}")
    out += ["", "只是記錄，不是買賣建議，也不改 v10。筆數少的時候不要下結論。"]
    return out


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from broker import Broker
    broker = Broker()                     # 建構時就登入了
    print("\n".join(table(run(broker))))
    print(f"\n→ 寫在 {FILE}")


if __name__ == "__main__":
    main()
