#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小簿 — 台灣稅務／勞健保申報行事曆提醒（零依賴）
用法：
  python3 tax_calendar.py                 # 未來 45 天內的期限
  python3 tax_calendar.py --days 90
  python3 tax_calendar.py --today 2026-09-01 --days 30
  python3 tax_calendar.py --all           # 全年度總表

⚠️ 期限遇例假日順延，實際依財政部／勞保局／健保署公告為準。稅率與門檻會修法，本表只寫「時點」不寫死金額。
"""
import argparse
from datetime import date, timedelta

# (月, 日, 事項, 說明)  月=0 代表每月
ITEMS = [
    (0, 10, "代扣稅款繳納", "繳納上月各類所得扣繳稅款（薪資、租金、執行業務所得等）"),
    (0, 31, "勞健保費／勞退提繳", "繳納上月單位負擔＋員工自付之勞保、健保、勞退（月底前）"),
    (0, 31, "二代健保補充保費", "繳納上月扣取之補充保費（月底前）"),
    (1, 15, "營業稅 401／403 申報", "申報前一年 11-12 月銷售額及稅額"),
    (1, 31, "各類所得扣繳憑單申報", "申報並填發前一年度扣繳暨免扣繳憑單、股利憑單"),
    (3, 15, "營業稅 401／403 申報", "申報 1-2 月"),
    (4, 30, "使用牌照稅", "公司名下車輛，4 月開徵"),
    (5, 15, "營業稅 401／403 申報", "申報 3-4 月"),
    (5, 31, "營利事業所得稅結算申報", "前一年度營所稅結算＋未分配盈餘申報（5/1–5/31）"),
    (5, 31, "綜合所得稅結算申報", "負責人／個人綜所稅（5/1–5/31）"),
    (5, 31, "房屋稅", "5 月開徵（房屋稅 2.0 起全年一次徵收）"),
    (7, 15, "營業稅 401／403 申報", "申報 5-6 月"),
    (7, 31, "汽車燃料使用費", "7 月開徵"),
    (9, 15, "營業稅 401／403 申報", "申報 7-8 月"),
    (9, 30, "營利事業所得稅暫繳", "9/1–9/30 辦理暫繳申報"),
    (11, 15, "營業稅 401／403 申報", "申報 9-10 月"),
    (11, 30, "地價稅", "11 月開徵"),
]


def occurrences(start, end):
    out = []
    y = start.year
    for yy in (y, y + 1):
        for m, d, name, note in ITEMS:
            months = range(1, 13) if m == 0 else [m]
            for mm in months:
                dd = d
                while dd > 28:  # 月底型項目自動退到當月最後一天
                    try:
                        dt = date(yy, mm, dd)
                        break
                    except ValueError:
                        dd -= 1
                else:
                    dt = date(yy, mm, dd)
                if start <= dt <= end:
                    out.append((dt, name, note))
    return sorted(set(out))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--today", default=None)
    p.add_argument("--days", type=int, default=45)
    p.add_argument("--all", action="store_true", help="列出全年度總表")
    a = p.parse_args()
    today = date.fromisoformat(a.today) if a.today else date.today()
    end = date(today.year, 12, 31) if a.all else today + timedelta(days=a.days)
    start = date(today.year, 1, 1) if a.all else today

    rows = occurrences(start, end)
    title = f"{today.year} 年度稅務行事曆總表" if a.all else f"未來 {a.days} 天申報期限（基準日 {today}）"
    print(f"# 🗓 {title}\n")
    print("| 期限 | 剩餘 | 事項 | 說明 |")
    print("|:---|---:|:---|:---|")
    for dt, name, note in rows:
        left = (dt - today).days
        flag = "🔴" if left <= 7 else ("🟡" if left <= 21 else "")
        print(f"| {dt} | {left} 天 {flag} | {name} | {note} |")
    if not rows:
        print("| — | — | 這段期間沒有固定申報期限 | — |")
    print("\n> ⚠️ 期限遇例假日順延；實際以財政部／各地區國稅局／勞保局／健保署公告為準。")
    print("> 對外申報作業請交由委任之記帳士或會計師辦理，小簿只做「不漏日期」的提醒與資料備齊。")


if __name__ == "__main__":
    main()
