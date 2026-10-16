# -*- coding: utf-8 -*-
"""market_calendar.py —— 今天台股有沒有開。

2026-10-09（國慶日補假）三支排程照常跑：08:40 選股、08:50「✅ 今日監看 10 檔」、
09:30「今日訊號 0 個」—— 休市日看起來像是開盤了，只是沒訊號。使用者：「今天
休市，說有監看 10 檔，不是很怪嗎？」

兩道：
  1. 這張表（證交所公告的休市日）。表上有的，三支程式一開始就停：選股不跑、
     監看推一行「今天休市」就結束、日報不發。
  2. 表上漏了的（臨時休市：颱風假、證交所另行公告），監看 09:03 還沒收到任何
     成交、0050 今天也沒有任何一根分鐘 K，就當休市、推一行、結束。
     見 signals.check_market_open()。

週六、週日不在表上 —— 程式自己會判。每年年底證交所公告下一年的休市日，
**要把下一年補進來**（12 月起，表上還沒有下一年時，08:50 的監看會多推一行提醒）。
"""
from datetime import date, datetime, timedelta

# 證交所公告：115 年（2026）集中交易市場休市日（不含週六、週日）。
# 2/12、2/13 不交易但仍辦理結算交割 —— 對我們來說一樣是不開盤。
CLOSED_DAYS = {
    "2026-01-01": "開國紀念日",
    "2026-02-12": "農曆春節前（不交易）",
    "2026-02-13": "農曆春節前（不交易）",
    "2026-02-16": "農曆春節",
    "2026-02-17": "農曆春節",
    "2026-02-18": "農曆春節",
    "2026-02-19": "農曆春節",
    "2026-02-20": "農曆春節補假",
    "2026-02-27": "和平紀念日補假",
    "2026-04-03": "兒童節",
    "2026-04-06": "民族掃墓節補假",
    "2026-05-01": "勞動節",
    "2026-06-19": "端午節",
    "2026-09-25": "中秋節",
    "2026-09-28": "教師節",
    "2026-10-09": "國慶日補假",
    "2026-10-26": "臺灣光復節補假",
    "2026-12-25": "行憲紀念日",
}

KNOWN_YEARS = {d[:4] for d in CLOSED_DAYS}


def _iso(day) -> str:
    if isinstance(day, str):
        return day
    if isinstance(day, datetime):
        day = day.date()
    return day.isoformat()


def closed_reason(day=None) -> str | None:
    """那一天不開盤的原因；有開盤回 None。day 可以是 'YYYY-MM-DD'、date、datetime。"""
    iso = _iso(day or date.today())
    if iso in CLOSED_DAYS:
        return CLOSED_DAYS[iso]
    if datetime.strptime(iso, "%Y-%m-%d").weekday() >= 5:
        return "週末"
    return None


def closed_today() -> str | None:
    """三支排程程式一開始問的那一句。測試會把它換掉（不然週末跑測試會全部提早結束）。"""
    return closed_reason(date.today())


def year_is_known(day=None) -> bool:
    """這一年的休市表填了沒有。沒填的話，國定假日只剩 09:03 那道保險。"""
    return _iso(day or date.today())[:4] in KNOWN_YEARS


def next_open_day(day=None) -> str:
    """day 之後（不含）的下一個開盤日，'YYYY-MM-DD'。"""
    d = datetime.strptime(_iso(day or date.today()), "%Y-%m-%d").date()
    for _ in range(30):
        d += timedelta(days=1)
        if closed_reason(d) is None:
            return d.isoformat()
    return d.isoformat()


WEEKDAYS = "一二三四五六日"


def label(iso: str) -> str:
    """'2026-10-12' → '10-12（一）'"""
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    return f"{iso[5:]}（{WEEKDAYS[d.weekday()]}）"
