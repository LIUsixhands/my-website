#!/usr/bin/env python3
"""screener.py 的離線測試：用合成資料驗證解析與評分，不需要網路。

執行：python3 test_screener.py
"""

import datetime as dt
import sys

import screener as S

FAILURES = []


def check(cond, label):
    if cond:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label}")
        FAILURES.append(label)


def make_bars(closes, vols=None, market="上市", name="測試", start="2026-07-01"):
    """由收盤價序列造出 Bar 序列，高低點以收盤價 ±1.5% 模擬。"""
    vols = vols or [5000.0] * len(closes)
    d = dt.date.fromisoformat(start)
    bars = []
    for i, (c, v) in enumerate(zip(closes, vols)):
        bars.append(
            S.Bar(
                date=(d + dt.timedelta(days=i)).isoformat(),
                open=round(c * 0.995, 2),
                high=round(c * 1.015, 2),
                low=round(c * 0.985, 2),
                close=round(c, 2),
                volume=v,
                market=market,
                name=name,
            )
        )
    return bars


# --------------------------------------------------------------------------
print("解析工具")
check(S.to_float("1,234.50") == 1234.5, "to_float 處理千分位")
check(S.to_float("+0.50") == 0.5, "to_float 處理正號")
check(S.to_float("--") is None, "to_float 處理空值符號")
check(S.to_float("＋1.20") == 1.2, "to_float 處理全形正號")
check(S.to_float("X") is None, "to_float 處理 X 註記")
check(S.roc_date(dt.date(2026, 8, 17)) == "115/08/17", "民國日期轉換")
check(S.is_common_stock("2409"), "四位數普通股通過")
check(not S.is_common_stock("0050"), "ETF 被排除")
check(not S.is_common_stock("2887A"), "特別股被排除")
check(not S.is_common_stock("031234"), "權證被排除")

print("\n檔位進位")
check(S.round_tick(33.33) == 33.35, "50 元以下取 0.05 檔位")
check(S.round_tick(56.77) == 56.8, "50 元以上取 0.1 檔位")

print("\n技術指標")
check(S.sma([1, 2, 3, 4, 5], 5) == 3.0, "SMA 計算")
check(S.sma([1, 2], 5) is None, "資料不足時 SMA 回 None")
flat = make_bars([100.0] * 20)
a = S.atr(flat, 14)
check(a is not None and abs(a - 3.0) < 0.2, f"ATR 對 ±1.5% 區間約 3.0（得到 {a:.2f}）")

# --------------------------------------------------------------------------
print("\n證交所 MI_INDEX 解析")
twse_payload = {
    "tables": [
        {"fields": ["指數", "收盤指數"], "data": [["發行量加權股價指數", "45,877.39"]]},
        {
            "fields": [
                "證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額",
                "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差",
            ],
            "data": [
                ["2409", "友達", "217,187,000", "50,000", "5,800,000,000",
                 "26.00", "27.20", "25.90", "27.10", "+", "1.30"],
                ["0050", "元大台灣50", "10,000,000", "100", "0",
                 "200.0", "201.0", "199.0", "200.5", "+", "0.50"],
                ["2330", "台積電", "30,000,000", "100", "0",
                 "2400", "2410", "2380", "2385", "-", "15.00"],
            ],
        },
    ]
}
S.fetch_json = lambda url, cache_key=None: twse_payload  # noqa: E731
bars = S.fetch_twse_day(dt.date(2026, 8, 17))
check("2409" in bars, "解析出 2409")
check("0050" not in bars, "ETF 0050 被過濾")
check(abs(bars["2409"].close - 27.10) < 1e-9, "收盤價正確")
check(abs(bars["2409"].volume - 217187.0) < 1e-6, "成交股數換算為張")
check(bars["2409"].name == "友達" and bars["2409"].market == "上市", "名稱與市場正確")

print("\n證交所舊版 data9 格式回退")
S.fetch_json = lambda url, cache_key=None: {  # noqa: E731
    "data9": [["1815", "富喬", "12,000,000", "1", "0",
               "30.0", "32.0", "29.5", "31.8", "+", "1.80"]]
}
bars_old = S.fetch_twse_day(dt.date(2026, 8, 17))
check("1815" in bars_old and abs(bars_old["1815"].close - 31.8) < 1e-9, "舊版格式仍可解析")

print("\n櫃買中心解析（欄序與上市不同）")
S.fetch_json = lambda url, cache_key=None: {  # noqa: E731
    "tables": [
        {
            "data": [
                # 代號 名稱 收盤 漲跌 開盤 最高 最低 成交股數 成交金額
                ["6141", "柏承", "42.40", "3.85", "39.00", "42.40", "38.90",
                 "1,302,000", "52,000,000"],
            ]
        }
    ]
}
tp = S.fetch_tpex_day(dt.date(2026, 8, 17))
check("6141" in tp, "解析出上櫃 6141")
check(abs(tp["6141"].close - 42.40) < 1e-9, "上櫃收盤價取自第 3 欄")
check(abs(tp["6141"].open - 39.00) < 1e-9, "上櫃開盤價取自第 5 欄")
check(tp["6141"].market == "上櫃", "市場標記為上櫃")

print("\n三大法人解析")
S.fetch_json = lambda url, cache_key=None: {  # noqa: E731
    "data": [["2409", "友達", "1", "2", "3", "56,942,000"]]
}
inst = S.fetch_twse_inst(dt.date(2026, 8, 17))
check(abs(inst.get("2409", 0) - 56942.0) < 1e-6, "法人買賣超換算為張")

# --------------------------------------------------------------------------
print("\n評分：硬性過濾")
base = dict(min_price=20.0, max_price=59.95, min_avg_vol=3000.0)

up = [20 + i * 0.55 for i in range(30)]  # 20 → 36 穩定上升
c = S.score_stock("9999", make_bars(up), 6000.0, **base)
check(c is not None, "多頭結構個股入選")

too_expensive = [100 + i for i in range(30)]
check(
    S.score_stock("9998", make_bars(too_expensive), 0.0, **base) is None,
    "價格 >59.95 被剔除",
)
too_cheap = [8 + i * 0.05 for i in range(30)]
check(S.score_stock("9997", make_bars(too_cheap), 0.0, **base) is None, "價格 <20 被剔除")

thin = S.score_stock("9996", make_bars(up, vols=[500.0] * 30), 0.0, **base)
check(thin is None, "20 日均量不足 3000 張被剔除")

down = [50 - i * 0.8 for i in range(30)]
check(S.score_stock("9995", make_bars(down), 0.0, **base) is None, "跌破 MA20 被剔除")

limit_down = up[:-1] + [up[-2] * 0.90]
check(
    S.score_stock("9994", make_bars(limit_down), 0.0, **base) is None,
    "當日接近跌停被剔除",
)
check(S.score_stock("9993", make_bars(up[:10]), 0.0, **base) is None, "歷史不足 22 根被剔除")

print("\n評分：分項行為")
check(0 <= c.total <= 100, f"總分落在 0~100（{c.total:.0f}）")
check(abs(sum(c.parts.values()) - c.total) < 1e-9, "分項加總等於總分")

# 健康量增（約 2.5 倍）應該是量能分最高的一組
healthy = S.score_stock("9989", make_bars(up, vols=[5000.0] * 29 + [12500.0]), 6000.0, **base)
hot = S.score_stock("9992", make_bars(up, vols=[5000.0] * 29 + [60000.0]), 6000.0, **base)
check(healthy.parts["量能"] > hot.parts["量能"], "健康量增 2.5 倍的量能分高於爆量 12 倍")
check(healthy.parts["量能"] > c.parts["量能"], "健康量增的量能分高於量能持平")
check(any("過熱" in n for n in hot.notes), "爆量會產生過熱備註")
check(healthy.total > hot.total, "健康量增總分高於爆量")

no_inst = S.score_stock("9991", make_bars(up), None, **base)
check(no_inst.parts["籌碼"] == 5.0 and any("無法人" in n for n in no_inst.notes),
      "缺法人資料時給中性分並註記")

sell_inst = S.score_stock("9990", make_bars(up), -9000.0, **base)
check(sell_inst.parts["籌碼"] == 0.0, "法人賣超籌碼給 0 分")
check(sell_inst.total < c.total, "法人賣超總分低於法人買超")

print("\n評分：交易參考位")
check(c.stop < c.close < c.target, "停損 < 收盤 < 目標")
check(c.buy_low <= c.close, "買進區下緣不高於收盤")
check(c.rr > 0, f"風險報酬比為正（{c.rr:.2f}）")
check(abs(c.stop / 0.05 - round(c.stop / 0.05)) < 1e-6, "停損價符合檔位")

print("\n輸出渲染")
rows = sorted([c, hot, no_inst], key=lambda x: -x.total)
md = S.render_markdown(rows, "2026-08-17", 5, 120)
check("| # | 代號 |" in md and md.count("\n|") >= 5, "Markdown 表格生成")
check("不構成投資建議" in md, "Markdown 含風險聲明")
html = S.render_html(rows, "2026-08-17")
check("<!doctype html>" in html and "9999" in html, "HTML 報表生成")
check(html.count("<tr>") == len(rows) + 1, "HTML 列數符合候選數")

# --------------------------------------------------------------------------
print("\n櫃買連線失敗不可被吞掉（否則上櫃整段消失卻沒人發現）")


def _fetch_boom(url, cache_key=None):
    raise RuntimeError("connection refused")


S.fetch_json = _fetch_boom
try:
    S.fetch_tpex_day(dt.date(2026, 8, 17))
    check(False, "所有櫃買端點連不上時應拋出 RuntimeError")
except RuntimeError:
    check(True, "所有櫃買端點連不上時拋出 RuntimeError")

# 端點有回應、但當天沒資料（假日）→ 要安靜回空，不是錯誤
S.fetch_json = lambda url, cache_key=None: {"tables": [{"data": []}]}  # noqa: E731
check(S.fetch_tpex_day(dt.date(2026, 8, 17)) == {}, "端點有回應但無資料時回空 dict")

print("\n離線失敗處理：連線錯誤與假日要能分辨")


def _raise_net(_d):
    raise RuntimeError("connection refused")


_orig_twse, _orig_tpex = S.fetch_twse_day, S.fetch_tpex_day

# 情境一：交易所連不上 → 必須回報 net_errors，且不能讓例外炸開
S.fetch_twse_day = _raise_net
S.fetch_tpex_day = _raise_net
_, latest, _, _, net_errors = S.build_history(dt.date(2026, 8, 17), 3, verbose=False)
check(latest is None, "連線全失敗時沒有最新交易日")
check(net_errors == 6, f"連線失敗次數被記錄（每日 2 個來源 ×3 日 = 6，得到 {net_errors}）")

# 情境二：連得上但當日無資料（假日）→ net_errors 必須是 0
S.fetch_twse_day = lambda d: {}
S.fetch_tpex_day = lambda d: {}
_, latest_h, _, _, net_h = S.build_history(dt.date(2026, 8, 17), 3, verbose=False)
check(latest_h is None and net_h == 0, "假日無資料不計為連線失敗")

S.fetch_twse_day, S.fetch_tpex_day = _orig_twse, _orig_tpex

print("\n交易日回推")
days = S.trading_days_back(dt.date(2026, 8, 17), 10)
check(len(days) == 10, "回推出 10 個日期")
check(all(d.weekday() < 5 for d in days), "全部避開週末")
check(days == sorted(days), "日期為由舊到新排序")

print()
if FAILURES:
    print(f"❌ {len(FAILURES)} 項未通過：")
    for f in FAILURES:
        print(f"   - {f}")
    sys.exit(1)
print("✅ 全部測試通過")
