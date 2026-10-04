# 台股資料源速查（小析專用）

`scripts/twstock_fetch.py` 已包好以下端點，全部免金鑰、官方公開。此文件記錄端點細節，
腳本壞掉或要加功能時看這裡。

## 已驗證可用的端點（2026-07-15 實測）

### 1. 證交所 OpenAPI（openapi.twse.com.tw）— 回 JSON 陣列，無需參數
| 端點 | 內容 | 用在 |
|:---|:---|:---|
| `/v1/exchangeReport/STOCK_DAY_ALL` | 全部上市股票**前一交易日**日成交（OHLC/量/漲跌） | `quote` |
| `/v1/exchangeReport/BWIBBU_ALL` | 全部上市股票本益比/殖利率/股價淨值比 | `quote` |
| `/v1/exchangeReport/FMTQIK` | 加權指數近月每日成交統計（TAIEX/量/值/漲跌） | `index` |

⚠️ **OpenAPI 沒有三大法人端點**（`/v1/fund/T86` 會 302），法人資料走 rwd API。

### 2. 證交所 rwd API（www.twse.com.tw/rwd/zh/...）— 需帶日期參數，回 `{stat,fields,data}`
| 端點 | 內容 | 用在 |
|:---|:---|:---|
| `/fund/T86?date=YYYYMMDD&selectType=ALL&response=json` | 個股三大法人買賣超日報 | `institutional` |
| `/fund/BFI82U?dayDate=YYYYMMDD&type=day&response=json` | 三大法人全市場買賣金額 | `market` |

- 日期是**西元** YYYYMMDD；假日/未收盤日 `stat` 不是 OK → 腳本會自動往回找 10 天。
- 盤中打當天日期就有當日盤中統計（實測 15:00 前也回得出來）。

### 3. 證交所 MIS 即時行情（mis.twse.com.tw）
`/stock/api/getStockInfo.jsp?ex_ch=tse_2330.tw|otc_2330.tw&json=1&delay=0`
- 欄位：`z`=最近成交價、`y`=昨收、`o`/`h`/`l`=開高低、`v`=累積量（張）、`n`=名稱、`tlong`=毫秒時間戳
- 上市用 `tse_`、上櫃用 `otc_` 前綴，可用 `|` 一次查多檔。

### 4. 櫃買中心 OpenAPI（www.tpex.org.tw）
`/openapi/v1/tpex_mainboard_daily_close_quotes` — 上櫃股票日收盤，`quote` 的 fallback。

## 欄位陷阱

1. **民國年**：OpenAPI 的 `Date` 是民國年（`1150714` = 2026-07-14）。報告中一律換算成西元。
2. **數字帶千分位逗號**：rwd API 的股數/金額是字串 `"15,647,223"`，運算前要去逗號。
3. **T86 證券名稱帶尾隨空白**：比對用代號欄不要用名稱欄。
4. **quote 的 daily 是前一交易日、realtime 是盤中**：報告要分清楚「昨收」與「現價」。
5. **法人單位**：T86 是**股**、BFI82U 是**元**，別混用；換算億元 = 金額 / 1e8。

## 想加功能時的候選端點（未實測，用前先驗）

- 月營收：`https://openapi.twse.com.tw/v1/opendata/t187ap05_L`（上市公司每月營業收入）
- 財報 EPS：`/v1/opendata/t187ap14_L`（綜合損益表）
- 融資融券：rwd `/marginTrading/MI_MARGN?date=...&selectType=ALL&response=json`
- 歷史個股日K（單月）：rwd `/afterTrading/STOCK_DAY?date=YYYYMMDD&stockNo=2330&response=json`
- 更長歷史／技術指標：可用 `pip install yfinance`（代號 `2330.TW`、大盤 `^TWII`），但屬第三方非官方。
