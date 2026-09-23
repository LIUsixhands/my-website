#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股資料抓取工具 — 小析（Sixhands Studio台股分析師）專用
只用 Python 標準庫（urllib），零依賴，資料來源全部是官方公開 API：
  - 台灣證交所 OpenAPI（openapi.twse.com.tw）— 上市股票日成交、本益比/殖利率/淨值比、大盤成交統計、三大法人
  - 證交所 MIS 即時行情（mis.twse.com.tw）— 盤中/最近成交價
  - 櫃買中心 OpenAPI（www.tpex.org.tw）— 上櫃股票（fallback）

用法：
  python3 twstock_fetch.py quote 2330          # 個股報價＋估值（本益比/殖利率/淨值比）
  python3 twstock_fetch.py index               # 大盤（加權指數）近 N 日成交統計
  python3 twstock_fetch.py institutional 2330  # 個股最近一個交易日三大法人買賣超
  python3 twstock_fetch.py market              # 三大法人全市場買賣金額統計
所有輸出為 JSON（stdout），方便上層直接解析。
"""
import json
import ssl
import sys
import urllib.request

# Windows 主控台預設 cp950，繁中/JSON 輸出會炸 UnicodeEncodeError → 強制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TIMEOUT = 20
CTX = ssl.create_default_context()
HEADERS = {"User-Agent": "Mozilla/5.0 (lobster-academy-analyst)", "Accept": "application/json"}


def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def quote(code):
    """個股：日成交 + 估值。先掃證交所全市場檔，找不到再試櫃買。"""
    out = {"code": code}
    # 上市日成交（前一交易日收盤）
    try:
        rows = fetch_json("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
        hit = next((r for r in rows if r.get("Code") == code), None)
        if hit:
            out["market"] = "上市(TWSE)"
            out["daily"] = hit
    except Exception as e:
        out["daily_error"] = str(e)
    # 估值：本益比 / 殖利率 / 股價淨值比
    try:
        rows = fetch_json("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL")
        hit = next((r for r in rows if r.get("Code") == code), None)
        if hit:
            out["valuation"] = hit
    except Exception as e:
        out["valuation_error"] = str(e)
    # 即時（盤中）報價
    try:
        data = fetch_json(
            f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{code}.tw|otc_{code}.tw&json=1&delay=0"
        )
        arr = data.get("msgArray") or []
        if arr:
            m = arr[0]
            out["realtime"] = {k: m.get(k) for k in ("c", "n", "z", "y", "o", "h", "l", "v", "tlong") if k in m}
    except Exception as e:
        out["realtime_error"] = str(e)
    # 櫃買 fallback（上櫃股票日成交）
    if "daily" not in out:
        try:
            rows = fetch_json("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")
            hit = next((r for r in rows if r.get("SecuritiesCompanyCode") == code), None)
            if hit:
                out["market"] = "上櫃(TPEx)"
                out["daily"] = hit
        except Exception as e:
            out["tpex_error"] = str(e)
    return out


def index():
    """大盤：加權指數近月每日成交統計（日期/成交量值/指數/漲跌點數）。"""
    rows = fetch_json("https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK")
    return {"index": "發行量加權股價指數", "recent": rows[-10:]}


def _recent_trading_data(url_tpl, days=10):
    """從今天往回找最近一個有資料的交易日（假日/未收盤時 stat 不是 OK）。"""
    import datetime
    d = datetime.date.today()
    for _ in range(days):
        ds = d.strftime("%Y%m%d")
        try:
            data = fetch_json(url_tpl.format(date=ds))
            if data.get("stat") == "OK" and data.get("data"):
                return ds, data
        except Exception:
            pass
        d -= datetime.timedelta(days=1)
    return None, None


def institutional(code):
    """個股最近一個交易日三大法人買賣超（T86 全市場檔過濾）。"""
    ds, data = _recent_trading_data(
        "https://www.twse.com.tw/rwd/zh/fund/T86?date={date}&selectType=ALL&response=json"
    )
    if not data:
        return {"code": code, "error": "近 10 日抓不到 T86 資料"}
    fields = data["fields"]
    hit = next((row for row in data["data"] if row[0] == code), None)
    return {
        "code": code,
        "date": ds,
        "t86": dict(zip(fields, hit)) if hit else None,
        "note": "單位：股；正=買超 負=賣超",
    }


def market():
    """三大法人全市場買賣金額統計（BFI82U）。"""
    ds, data = _recent_trading_data(
        "https://www.twse.com.tw/rwd/zh/fund/BFI82U?dayDate={date}&type=day&response=json"
    )
    if not data:
        return {"error": "近 10 日抓不到 BFI82U 資料"}
    fields = data["fields"]
    return {
        "date": ds,
        "rows": [dict(zip(fields, row)) for row in data["data"]],
        "note": "單位：元",
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "quote" and len(sys.argv) >= 3:
        result = quote(sys.argv[2])
    elif cmd == "index":
        result = index()
    elif cmd == "institutional" and len(sys.argv) >= 3:
        result = institutional(sys.argv[2])
    elif cmd == "market":
        result = market()
    else:
        print(__doc__)
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
