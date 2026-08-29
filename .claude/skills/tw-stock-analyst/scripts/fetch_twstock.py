#!/usr/bin/env python3
"""
台股資料抓取工具（加值路線，環境允許對外連線時用）。

直連兩個免金鑰來源：
  - 證交所 TWSE 開放資料（官方，日頻，含個股日成交、三大法人買賣超）
  - FinMind 公開端點（打包股價/籌碼/營收/財報，免登入有基本額度）

用法：
  python fetch_twstock.py price 2330                # 近一個月日 K
  python fetch_twstock.py chips 2330               # 近期三大法人買賣超（FinMind）
  python fetch_twstock.py revenue 2330             # 月營收（FinMind）
  python fetch_twstock.py twse_t86                 # 當日全市場三大法人買賣超（TWSE 官方）

重要：若因網路政策被擋（回 403 / 連線失敗），本工具會印出 BLOCKED 訊息並以非零碼結束。
      這是預期中的情況（手機/web 環境常見）——請不要重試繞道，改用 SKILL.md 的 WebSearch 主力路線。
"""
import sys
import json
import datetime
import urllib.request
import urllib.error

FINMIND = "https://api.finmindtrade.com/api/v4/data"
TWSE = "https://openapi.twse.com.tw/v1"
TIMEOUT = 20


def _get(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tw-stock-analyst/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (403, 407):
            print(f"BLOCKED: 對外連線被網路政策擋下 (HTTP {e.code})。請改用 WebSearch 主力路線。", file=sys.stderr)
            sys.exit(2)
        print(f"ERROR: HTTP {e.code} - {url}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"BLOCKED_OR_ERROR: {e}。若為連線問題請改用 WebSearch 主力路線。", file=sys.stderr)
        sys.exit(2)


def _finmind(dataset, data_id=None, days=40):
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    url = f"{FINMIND}?dataset={dataset}&start_date={start}"
    if data_id:
        url += f"&data_id={data_id}"
    data = _get(url)
    if isinstance(data, dict) and data.get("msg") and not data.get("data"):
        print(f"NOTE: FinMind 回應 - {data.get('msg')}（可能達免費額度上限，改用 WebSearch）", file=sys.stderr)
    return data


def price(ticker):
    return _finmind("TaiwanStockPrice", ticker, days=40)


def chips(ticker):
    return _finmind("TaiwanStockInstitutionalInvestorsBuySell", ticker, days=20)


def revenue(ticker):
    return _finmind("TaiwanStockMonthRevenue", ticker, days=200)


def twse_t86():
    return _get(f"{TWSE}/fund/T86")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    fns = {"price": price, "chips": chips, "revenue": revenue, "twse_t86": lambda a=None: twse_t86()}
    if cmd not in fns:
        print(f"未知指令: {cmd}\n{__doc__}", file=sys.stderr)
        sys.exit(1)
    result = fns[cmd](arg) if cmd != "twse_t86" else twse_t86()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
