#!/usr/bin/env python3
"""台股短線進出候選股每日篩選器。

資料來源：台灣證券交易所（上市）與證券櫃檯買賣中心（上櫃）官方盤後開放資料。
只用 Python 標準函式庫，不需要 pip install。

用法：
    python3 screener.py                    # 篩選最近一個交易日
    python3 screener.py --date 2026-08-17  # 指定日期
    python3 screener.py --html report.html # 另外輸出 HTML 報表

免責聲明：本工具僅為量化篩選，輸出結果為研究候選名單，不構成投資建議。
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_GAP_SEC = 1.3  # 交易所對連續請求會擋，務必留間隔


# --------------------------------------------------------------------------
# 基本資料結構
# --------------------------------------------------------------------------


@dataclass
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float  # 張
    market: str  # "上市" / "上櫃"
    name: str = ""


@dataclass
class Candidate:
    code: str
    name: str
    market: str
    close: float
    change_pct: float
    vol: float
    vol_ratio: float
    avg_vol20: float
    ma5: float
    ma20: float
    bias20: float
    atr: float
    atr_pct: float
    inst_ratio: float | None
    breakout: bool
    total: float
    parts: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    # 交易參考位
    buy_low: float = 0.0
    stop: float = 0.0
    target: float = 0.0

    @property
    def rr(self) -> float:
        risk = self.close - self.stop
        reward = self.target - self.close
        return reward / risk if risk > 0 else 0.0


# --------------------------------------------------------------------------
# HTTP / 快取
# --------------------------------------------------------------------------


def _http_get(url: str, retries: int = 3) -> bytes:
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip",
                "Connection": "close",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_err = exc
            time.sleep((2**attempt) + random.random())
    raise RuntimeError(f"抓取失敗 {url}: {last_err}")


def fetch_json(url: str, cache_key: str | None = None):
    """抓 JSON，成功的結果會落地快取，之後同一天重跑不必再連線。"""
    if cache_key:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = os.path.join(CACHE_DIR, cache_key + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)

    raw = _http_get(url)
    time.sleep(REQUEST_GAP_SEC)
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except json.JSONDecodeError:
        return None

    if cache_key:
        with open(os.path.join(CACHE_DIR, cache_key + ".json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    return data


# --------------------------------------------------------------------------
# 解析工具
# --------------------------------------------------------------------------


def to_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("+", "").strip()
    if text in ("", "-", "--", "---", "X", "N/A"):
        return None
    # 櫃買的漲跌欄位偶爾長成 "-1.20" 或 "＋0.50"
    text = text.replace("＋", "").replace("−", "-").replace("–", "-")
    try:
        return float(text)
    except ValueError:
        return None


def roc_date(d: dt.date, sep: str = "/") -> str:
    return f"{d.year - 1911}{sep}{d.month:02d}{sep}{d.day:02d}"


def is_common_stock(code: str) -> bool:
    """只留普通股：四位數字，排除 00 開頭的 ETF/ETN。"""
    return bool(re.fullmatch(r"\d{4}", code)) and not code.startswith("00")


# --------------------------------------------------------------------------
# 上市（證交所）
# --------------------------------------------------------------------------


def fetch_twse_day(d: dt.date) -> dict[str, Bar]:
    ymd = d.strftime("%Y%m%d")
    url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
        f"?date={ymd}&type=ALLBUT0999&response=json"
    )
    data = fetch_json(url, cache_key=f"twse-{ymd}")
    if not data:
        return {}

    rows = []
    # 新版 API 回 tables，舊版回 data9/data8
    for table in data.get("tables", []):
        fields = table.get("fields") or []
        if fields and "證券代號" in fields[0]:
            rows = table.get("data") or []
            break
    if not rows:
        rows = data.get("data9") or data.get("data8") or data.get("data") or []
    if not rows:
        return {}

    bars: dict[str, Bar] = {}
    for row in rows:
        if len(row) < 9:
            continue
        code = str(row[0]).strip()
        if not is_common_stock(code):
            continue
        # 欄序：代號 名稱 成交股數 成交筆數 成交金額 開 高 低 收 漲跌(+/-) 漲跌價差
        shares = to_float(row[2])
        op, hi, lo, cl = (to_float(row[i]) for i in (5, 6, 7, 8))
        if None in (shares, op, hi, lo, cl) or cl <= 0 or hi <= 0:
            continue
        bars[code] = Bar(
            date=d.isoformat(),
            open=op,
            high=hi,
            low=lo,
            close=cl,
            volume=shares / 1000.0,
            market="上市",
            name=str(row[1]).strip(),
        )
    return bars


def fetch_twse_inst(d: dt.date) -> dict[str, float]:
    """三大法人買賣超（張）。"""
    ymd = d.strftime("%Y%m%d")
    url = (
        "https://www.twse.com.tw/rwd/zh/fund/T86"
        f"?date={ymd}&selectType=ALL&response=json"
    )
    try:
        data = fetch_json(url, cache_key=f"twse-inst-{ymd}")
    except RuntimeError:
        return {}
    if not data or not data.get("data"):
        return {}

    out: dict[str, float] = {}
    for row in data["data"]:
        code = str(row[0]).strip()
        if not is_common_stock(code):
            continue
        net = to_float(row[-1])  # 三大法人買賣超股數
        if net is not None:
            out[code] = net / 1000.0
    return out


# --------------------------------------------------------------------------
# 上櫃（櫃買中心）
# --------------------------------------------------------------------------


def fetch_tpex_day(d: dt.date) -> dict[str, Bar]:
    ymd = d.strftime("%Y%m%d")
    attempts = [
        (
            "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
            f"?date={d.strftime('%Y/%m/%d')}&type=EW&response=json"
        ),
        (
            "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/"
            f"stk_quote_result.php?l=zh-tw&d={roc_date(d)}&se=EW"
        ),
    ]
    data = None
    for idx, url in enumerate(attempts):
        try:
            data = fetch_json(url, cache_key=f"tpex-{ymd}-{idx}")
        except RuntimeError:
            data = None
        if data:
            break
    if not data:
        return {}

    rows = []
    for table in data.get("tables", []):
        candidate = table.get("data") or []
        if candidate and len(candidate[0]) >= 9:
            rows = candidate
            break
    if not rows:
        rows = data.get("aaData") or data.get("data") or []
    if not rows:
        return {}

    bars: dict[str, Bar] = {}
    for row in rows:
        if len(row) < 9:
            continue
        code = str(row[0]).strip()
        if not is_common_stock(code):
            continue
        # 櫃買欄序：代號 名稱 收盤 漲跌 開盤 最高 最低 成交股數 成交金額 ...
        cl = to_float(row[2])
        op, hi, lo = to_float(row[4]), to_float(row[5]), to_float(row[6])
        shares = to_float(row[7])
        if None in (cl, op, hi, lo, shares) or cl <= 0 or hi <= 0:
            continue
        bars[code] = Bar(
            date=d.isoformat(),
            open=op,
            high=hi,
            low=lo,
            close=cl,
            volume=shares / 1000.0,
            market="上櫃",
            name=str(row[1]).strip(),
        )
    return bars


def fetch_tpex_inst(d: dt.date) -> dict[str, float]:
    url = (
        "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"
        f"?type=Daily&sect=EW&date={d.strftime('%Y/%m/%d')}&response=json"
    )
    try:
        data = fetch_json(url, cache_key=f"tpex-inst-{d.strftime('%Y%m%d')}")
    except RuntimeError:
        return {}
    if not data:
        return {}

    rows = []
    for table in data.get("tables", []):
        candidate = table.get("data") or []
        if candidate:
            rows = candidate
            break
    if not rows:
        rows = data.get("aaData") or []

    out: dict[str, float] = {}
    for row in rows:
        code = str(row[0]).strip()
        if not is_common_stock(code):
            continue
        net = to_float(row[-1])
        if net is not None:
            out[code] = net / 1000.0
    return out


# --------------------------------------------------------------------------
# 歷史序列組裝
# --------------------------------------------------------------------------


def trading_days_back(end: dt.date, want: int) -> list[dt.date]:
    """回推日曆日，週末先剔除；遇到國定假日該日抓不到資料自然會是空的。"""
    days, cursor = [], end
    guard = 0
    while len(days) < want and guard < want * 3:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= dt.timedelta(days=1)
        guard += 1
    return sorted(days)


def build_history(end: dt.date, lookback: int, verbose: bool = True):
    """回傳 (history, latest_date, inst_by_code, inst_days)。"""
    history: dict[str, list[Bar]] = {}
    inst_totals: dict[str, float] = {}
    inst_days = 0
    latest: dt.date | None = None

    days = trading_days_back(end, lookback)
    for d in days:
        bars = {}
        bars.update(fetch_twse_day(d))
        bars.update(fetch_tpex_day(d))
        if not bars:
            if verbose:
                print(f"  {d} 無資料（假日或尚未更新），略過", file=sys.stderr)
            continue
        for code, bar in bars.items():
            history.setdefault(code, []).append(bar)
        latest = d
        if verbose:
            print(f"  {d} 取得 {len(bars)} 檔", file=sys.stderr)

    # 法人買賣超只取最近 5 個有資料的交易日
    if latest:
        for d in reversed(days):
            if d > latest or inst_days >= 5:
                continue
            inst = {}
            inst.update(fetch_twse_inst(d))
            inst.update(fetch_tpex_inst(d))
            if not inst:
                continue
            for code, net in inst.items():
                inst_totals[code] = inst_totals.get(code, 0.0) + net
            inst_days += 1

    return history, latest, inst_totals, inst_days


# --------------------------------------------------------------------------
# 技術指標
# --------------------------------------------------------------------------


def sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def atr(bars: list[Bar], n: int = 14) -> float | None:
    if len(bars) < n + 1:
        return None
    trs = []
    for prev, cur in zip(bars[-(n + 1) : -1], bars[-n:]):
        trs.append(
            max(cur.high - cur.low, abs(cur.high - prev.close), abs(prev.close - cur.low))
        )
    return sum(trs) / len(trs)


def round_tick(price: float) -> float:
    """依台股檔位進位：10~50 元 0.05、50~100 元 0.1。"""
    tick = 0.05 if price < 50 else 0.1
    return round(round(price / tick) * tick, 2)


# --------------------------------------------------------------------------
# 評分模型（總分 100）
# --------------------------------------------------------------------------


def score_stock(
    code: str,
    bars: list[Bar],
    inst_net: float | None,
    min_price: float,
    max_price: float,
    min_avg_vol: float,
) -> Candidate | None:
    if len(bars) < 22:
        return None

    closes = [b.close for b in bars]
    vols = [b.volume for b in bars]
    last = bars[-1]
    prev_close = closes[-2]

    # ---- 硬性過濾 ----
    if not (min_price <= last.close <= max_price):
        return None

    avg_vol20 = sma(vols[:-1], 20)
    if avg_vol20 is None or avg_vol20 < min_avg_vol:
        return None
    if last.volume <= 0:
        return None

    change_pct = (last.close - prev_close) / prev_close * 100
    if change_pct <= -8.5:  # 當日接近跌停，不作多方候選
        return None

    ma5, ma20 = sma(closes, 5), sma(closes, 20)
    atr14 = atr(bars, 14)
    if None in (ma5, ma20, atr14) or atr14 <= 0:
        return None
    if last.close < ma20:  # 短線只做站上季均以上的多方結構
        return None

    parts: dict[str, float] = {}
    notes: list[str] = []

    # ---- 1. 動能與均線結構（25）----
    momentum = 0.0
    if last.close > ma5:
        momentum += 6
    if ma5 > ma20:
        momentum += 6
    bias20 = (last.close - ma20) / ma20 * 100
    if 2 <= bias20 <= 12:
        momentum += 13
    elif 0 <= bias20 < 2:
        momentum += 8
    elif 12 < bias20 <= 20:
        momentum += 6
        notes.append("乖離偏大，留意回測均線")
    else:
        notes.append(f"乖離 {bias20:.1f}%，追高風險高")
    parts["動能"] = momentum

    # ---- 2. 量能（25）----
    vol_ratio = last.volume / avg_vol20
    if 1.5 <= vol_ratio <= 4:
        volume_pts = 15.0
    elif 1.2 <= vol_ratio < 1.5:
        volume_pts = 10.0
    elif 4 < vol_ratio <= 6:
        volume_pts = 9.0
        notes.append("爆量，慎防一日行情")
    elif vol_ratio > 6:
        volume_pts = 4.0
        notes.append(f"量增 {vol_ratio:.1f} 倍，過熱")
    else:
        volume_pts = 2.0
    if avg_vol20 >= 10000:
        volume_pts += 10
    elif avg_vol20 >= 5000:
        volume_pts += 8
    else:
        volume_pts += 6
    parts["量能"] = volume_pts

    # ---- 3. 籌碼（20）----
    if inst_net is None:
        inst_pts, inst_ratio = 5.0, None
        notes.append("無法人資料")
    else:
        inst_ratio = inst_net / avg_vol20
        if inst_ratio >= 1.0:
            inst_pts = 20.0
        elif inst_ratio >= 0.5:
            inst_pts = 16.0
        elif inst_ratio >= 0.2:
            inst_pts = 12.0
        elif inst_ratio > 0:
            inst_pts = 7.0
        elif inst_ratio == 0:
            inst_pts = 5.0
        else:
            inst_pts = 0.0
            notes.append("法人近 5 日站賣方")
    parts["籌碼"] = inst_pts

    # ---- 4. 波動空間（15）----
    atr_pct = atr14 / last.close * 100
    if 3 <= atr_pct <= 6:
        vola_pts = 15.0
    elif 2 <= atr_pct < 3:
        vola_pts = 11.0
    elif 6 < atr_pct <= 8:
        vola_pts = 9.0
    elif atr_pct > 8:
        vola_pts = 4.0
        notes.append("波動過大，部位要縮")
    else:
        vola_pts = 3.0
        notes.append("波動偏低，短線空間有限")
    parts["波動"] = vola_pts

    # ---- 5. 突破結構（15）----
    high20 = max(b.high for b in bars[-21:-1])
    breakout = last.close >= high20
    if breakout:
        struct_pts = 8.0
    elif last.close >= high20 * 0.97:
        struct_pts = 5.0
    else:
        struct_pts = 0.0
    day_range = last.high - last.low
    close_pos = (last.close - last.low) / day_range if day_range > 0 else 1.0
    if close_pos >= 0.7:
        struct_pts += 7
    elif close_pos >= 0.5:
        struct_pts += 4
    else:
        notes.append("收黑 K 下半部，隔日開盤先觀察")
    parts["結構"] = struct_pts

    if change_pct >= 9.5:
        notes.append("漲停鎖死，隔日不宜追價")

    cand = Candidate(
        code=code,
        name=last.name,
        market=last.market,
        close=last.close,
        change_pct=change_pct,
        vol=last.volume,
        vol_ratio=vol_ratio,
        avg_vol20=avg_vol20,
        ma5=ma5,
        ma20=ma20,
        bias20=bias20,
        atr=atr14,
        atr_pct=atr_pct,
        inst_ratio=inst_ratio,
        breakout=breakout,
        total=sum(parts.values()),
        parts=parts,
        notes=notes,
    )
    cand.buy_low = round_tick(max(ma5, last.close - 0.5 * atr14))
    cand.stop = round_tick(min(ma5, last.close - 1.5 * atr14))
    cand.target = round_tick(last.close + 2 * atr14)
    return cand


# --------------------------------------------------------------------------
# 輸出
# --------------------------------------------------------------------------


def render_markdown(rows: list[Candidate], date_str: str, inst_days: int, universe: int) -> str:
    out = [
        f"# 台股短線進出候選 Top {len(rows)}",
        "",
        f"- 資料日期：**{date_str}**（盤後）",
        f"- 篩選母體：{universe} 檔（上市＋上櫃普通股，已套用價格與流動性門檻）",
        f"- 法人籌碼：近 {inst_days} 個交易日累計三大法人買賣超"
        if inst_days
        else "- 法人籌碼：本次未取得，籌碼項以中性分計算",
        "",
        "| # | 代號 | 名稱 | 市場 | 收盤 | 漲跌% | 量增 | 總分 | 動能 | 量能 | 籌碼 | 波動 | 結構 | 買進區 | 停損 | 目標 | R:R |",
        "|---|------|------|------|------|-------|------|------|------|------|------|------|------|--------|------|------|-----|",
    ]
    for i, c in enumerate(rows, 1):
        out.append(
            f"| {i} | {c.code} | {c.name} | {c.market} | {c.close:.2f} | {c.change_pct:+.2f} | "
            f"{c.vol_ratio:.1f}x | **{c.total:.0f}** | {c.parts['動能']:.0f} | {c.parts['量能']:.0f} | "
            f"{c.parts['籌碼']:.0f} | {c.parts['波動']:.0f} | {c.parts['結構']:.0f} | "
            f"{c.buy_low:.2f}~{c.close:.2f} | {c.stop:.2f} | {c.target:.2f} | {c.rr:.1f} |"
        )

    out += ["", "## 個股備註", ""]
    for i, c in enumerate(rows, 1):
        bits = [
            f"MA5 {c.ma5:.2f} / MA20 {c.ma20:.2f}（乖離 {c.bias20:+.1f}%）",
            f"ATR14 {c.atr:.2f}（{c.atr_pct:.1f}%）",
            f"20 日均量 {c.avg_vol20:,.0f} 張",
        ]
        if c.breakout:
            bits.append("**突破 20 日新高**")
        if c.inst_ratio is not None:
            bits.append(f"法人 5 日淨額約 {c.inst_ratio:+.2f} 倍日均量")
        line = f"{i}. **{c.code} {c.name}** — " + "；".join(bits)
        if c.notes:
            line += "\n   - ⚠️ " + "；".join(c.notes)
        out.append(line)

    out += [
        "",
        "---",
        "",
        "**風險聲明**：以上為量化篩選產生的研究候選名單，不構成投資建議。買進前務必自行確認：",
        "個股是否列為處置／注意股、近期是否有財報或除權息事件、產業消息面，以及自身部位規模與風險承受度。",
    ]
    return "\n".join(out)


def render_html(rows: list[Candidate], date_str: str) -> str:
    cells = "".join(
        f"<tr><td>{i}</td><td>{c.code}</td><td>{c.name}</td><td>{c.market}</td>"
        f"<td>{c.close:.2f}</td><td class='{'up' if c.change_pct >= 0 else 'down'}'>{c.change_pct:+.2f}%</td>"
        f"<td>{c.vol_ratio:.1f}x</td><td><b>{c.total:.0f}</b></td>"
        f"<td>{c.buy_low:.2f}~{c.close:.2f}</td><td>{c.stop:.2f}</td><td>{c.target:.2f}</td>"
        f"<td>{c.rr:.1f}</td></tr>"
        for i, c in enumerate(rows, 1)
    )
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>台股短線候選 {date_str}</title>
<style>
 body{{font-family:system-ui,"Noto Sans TC",sans-serif;margin:0;padding:24px;
      background:#0f1115;color:#e6e8eb}}
 h1{{font-size:20px;margin:0 0 4px}} p.meta{{color:#8b939e;font-size:13px;margin:0 0 20px}}
 .wrap{{overflow-x:auto}}
 table{{border-collapse:collapse;width:100%;min-width:820px;font-size:14px}}
 th,td{{padding:9px 10px;text-align:right;border-bottom:1px solid #232833;white-space:nowrap}}
 th{{background:#171b23;color:#9aa4b2;font-weight:600;text-align:right;position:sticky;top:0}}
 td:nth-child(2),td:nth-child(3),td:nth-child(4),
 th:nth-child(2),th:nth-child(3),th:nth-child(4){{text-align:left}}
 tr:hover td{{background:#161a21}}
 .up{{color:#ff6b6b}} .down{{color:#4ade80}}
 footer{{margin-top:20px;color:#6b7280;font-size:12px;line-height:1.7}}
</style></head><body>
<h1>台股短線進出候選 Top {len(rows)}</h1>
<p class="meta">資料日期 {date_str}（盤後）· 資料來源：證交所 / 櫃買中心官方開放資料</p>
<div class="wrap"><table>
<thead><tr><th>#</th><th>代號</th><th>名稱</th><th>市場</th><th>收盤</th><th>漲跌</th>
<th>量增</th><th>總分</th><th>買進區</th><th>停損</th><th>目標</th><th>R:R</th></tr></thead>
<tbody>{cells}</tbody></table></div>
<footer>本頁為量化篩選之研究候選名單，不構成投資建議。<br>
買進前請自行確認處置／注意股狀態、財報與除權息事件，並控制部位規模。</footer>
</body></html>"""


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="台股短線進出候選股每日篩選器")
    ap.add_argument("--date", help="資料日期 YYYY-MM-DD，預設今天")
    ap.add_argument("--top", type=int, default=10, help="輸出檔數，預設 10")
    ap.add_argument("--min-price", type=float, default=20.0)
    ap.add_argument("--max-price", type=float, default=59.95)
    ap.add_argument("--min-avg-vol", type=float, default=3000.0, help="20 日均量下限（張）")
    ap.add_argument("--lookback", type=int, default=32, help="回補幾個交易日建立均線")
    ap.add_argument("--html", help="另存 HTML 報表路徑")
    ap.add_argument("--out", help="另存 Markdown 報表路徑")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    end = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    verbose = not args.quiet

    if verbose:
        print(f"抓取 {end} 起回推 {args.lookback} 個交易日……", file=sys.stderr)
    history, latest, inst, inst_days = build_history(end, args.lookback, verbose)

    if not latest:
        print(
            "錯誤：完全沒有取得盤後資料。可能原因：日期為假日、盤後資料尚未更新"
            "（證交所約 14:30 後、櫃買約 15:00 後），或網路無法連到交易所。",
            file=sys.stderr,
        )
        return 1

    candidates = []
    for code, bars in history.items():
        bars.sort(key=lambda b: b.date)
        if bars[-1].date != latest.isoformat():
            continue  # 最新交易日無成交，跳過
        cand = score_stock(
            code, bars, inst.get(code), args.min_price, args.max_price, args.min_avg_vol
        )
        if cand:
            candidates.append(cand)

    candidates.sort(key=lambda c: (-c.total, -c.vol_ratio))
    rows = candidates[: args.top]

    if not rows:
        print("在目前的價格與流動性條件下，沒有任何個股通過篩選。", file=sys.stderr)
        return 2

    md = render_markdown(rows, latest.isoformat(), inst_days, len(candidates))
    print(md)

    for path in (args.out, args.html):
        if path and os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md + "\n")
        if verbose:
            print(f"已輸出 {args.out}", file=sys.stderr)
    if args.html:
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(render_html(rows, latest.isoformat()))
        if verbose:
            print(f"已輸出 {args.html}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
