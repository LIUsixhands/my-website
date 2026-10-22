"""
moi.py — 內政部實價登錄開放資料：抓同路段／同區的成交，算扣掉車位後的單價。只用標準庫。

資料來源：不動產成交案件實際資訊資料供應系統（plvr.land.moi.gov.tw），每季一個 CSV：
  https://plvr.land.moi.gov.tw/DownloadSeason?season=115S2&fileName=B_lvr_land_A.csv
  （B=臺中市、A=不動產買賣）

過去的季別不會再變，下載一次就存在 cache/moi/，之後秒回。
"""
from __future__ import annotations

import csv
import io
import re
import statistics
import time
import unicodedata
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache" / "moi"
PING = 3.305785                     # 1 坪 = 3.305785 平方公尺

CITY_CODES = {
    "臺北市": "A", "臺中市": "B", "基隆市": "C", "臺南市": "D", "高雄市": "E", "新北市": "F",
    "宜蘭縣": "G", "桃園市": "H", "嘉義市": "I", "新竹縣": "J", "苗栗縣": "K", "南投縣": "M",
    "彰化縣": "N", "新竹市": "O", "雲林縣": "P", "嘉義縣": "Q", "屏東縣": "T", "花蓮縣": "U",
    "臺東縣": "V", "金門縣": "W", "澎湖縣": "X", "連江縣": "Z",
}

# 備註有這些字的成交不代表市場行情（親友交易、瑕疵、含增建…），不拿來比
SPECIAL_DEAL = ["親友", "員工", "特殊關係", "瑕疵", "凶宅", "增建", "頂加", "毛胚", "急買急賣",
                "債權債務", "法拍", "持分", "含租約", "地上權", "政府機關"]
MIN_COMPS = 3                       # 同路段（或屋齡相近）少於這個數就放寬
AGE_BAND = 8                        # 屋齡 ±8 年算相近


CN_DIGITS = "〇一二三四五六七八九"


def norm(s: str) -> str:
    """台→臺、全形數字→半形、「3段」→「三段」，門牌與使用者打的字才比得起來。"""
    s = unicodedata.normalize("NFKC", s or "").replace("台", "臺").strip()
    return re.sub(r"(\d)段", lambda m: CN_DIGITS[int(m.group(1))] + "段", s)


def recent_seasons(n: int = 6, now: float | None = None) -> list[str]:
    """由新到舊的民國季別，例：['115S4', '115S3', ...]。最新一季通常還沒公布，抓不到會自動跳過。"""
    t = time.localtime(now)
    y, q = t.tm_year - 1911, (t.tm_mon - 1) // 3 + 1
    out = []
    for _ in range(n):
        out.append(f"{y}S{q}")
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return out


def download(city_code: str, season: str) -> str:
    """回傳 CSV 文字；該季還沒公布回空字串。過去的季別會快取。"""
    f = CACHE_DIR / f"{season}_{city_code}_A.csv"
    if f.exists():
        return f.read_text(encoding="utf-8-sig")
    url = (f"https://plvr.land.moi.gov.tw/DownloadSeason?season={season}"
           f"&fileName={city_code}_lvr_land_A.csv")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (xiaoke real-price client)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode("utf-8-sig", "replace")
    if len(text) < 200 or text.lstrip().startswith("<"):    # 還沒公布的季別會回錯誤頁
        return ""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(f)
    return text


def parse(text: str) -> list[dict]:
    """第一列中文欄名，第二列英文欄名（跳過）。"""
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 3:
        return []
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[2:]]


def _num(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return 0.0


def roc_age(done: str, today: float | None = None) -> float | None:
    """建築完成年月（民國 1050312）→ 屋齡（年）。"""
    s = re.sub(r"\D", "", done or "")
    if len(s) < 5:
        return None
    y, m = int(s[:-4]) + 1911, int(s[-4:-2] or 1)
    t = time.localtime(today)
    return round(t.tm_year - y + (t.tm_mon - m) / 12, 1)


def car_count(r: dict) -> int:
    m = re.search(r"車位(\d+)", r.get("交易筆棟數", ""))
    return max(int(m.group(1)), 1) if m else 1


def car_estimates(rows: list[dict]) -> dict[str, float]:
    """有拆價的車位，各車位類別（坡道平面、坡道機械…）的單一車位中位價（元）。
    "" 是不分類別的中位價。很多成交車位沒拆價，拿這個推估來扣。"""
    by: dict[str, list[float]] = {}
    for r in rows:
        price = _num(r.get("車位總價元"))
        if price > 0 and "建物" in r.get("交易標的", ""):
            each = price / car_count(r)
            by.setdefault(r.get("車位類別", ""), []).append(each)
            by.setdefault("", []).append(each)
    return {k: statistics.median(v) for k, v in by.items()}


def to_deal(r: dict, car_est: dict[str, float] | None = None) -> dict | None:
    """一筆成交 → 扣掉車位後的單價（萬/坪）。不能拿來比的回 None。
    車位沒拆價的用 car_est 推估；連推估都沒有就不拿來比。"""
    if "建物" not in r.get("交易標的", ""):
        return None                                  # 純土地、純車位
    if any(k in r.get("備註", "") for k in SPECIAL_DEAL):
        return None
    total = _num(r.get("總價元"))
    area = _num(r.get("建物移轉總面積平方公尺"))
    car_price = _num(r.get("車位總價元"))
    car_area = _num(r.get("車位移轉總面積平方公尺"))
    has_car = bool(r.get("車位類別")) or car_area > 0
    car_est = car_est or {}
    est = has_car and car_price <= 0
    if est:                                          # 車位沒拆價：用同區同類別車位行情扣
        each = car_est.get(r.get("車位類別", "")) or car_est.get("")
        if not each:
            return None
        car_price = each * car_count(r)
    net_ping = (area - car_area) / PING
    if total <= 0 or net_ping < 5:
        return None
    unit = (total - car_price) / 10000 / net_ping
    return {
        "date": r.get("交易年月日", ""),
        "addr": norm(r.get("土地位置建物門牌", "")),
        "district": r.get("鄉鎮市區", ""),
        "type": r.get("建物型態", ""),
        "floor": f"{r.get('移轉層次', '')}/{r.get('總樓層數', '')}",
        "age": roc_age(r.get("建築完成年月", "")),
        "total_wan": round(total / 10000),
        "ping": round(area / PING, 1),
        "car_wan": round(car_price / 10000),
        "car_ping": round(car_area / PING, 1),
        "car_est": est,
        "unit": round(unit, 1),
    }


def road_key(road: str) -> str:
    """「崇德路三段 123 號」→「崇德路三段」；門牌是「臺中市北屯區崇德路三段1~30號」這種格式。"""
    s = norm(road)
    for city in CITY_CODES:                       # 去掉「臺中市北屯區」
        s = s.removeprefix(city)
    s = re.sub(r"^.{1,3}?[區鄉鎮市](?!路|街)", "", s)
    m = re.match(r"(.+?(?:路|街|大道)(?:[一二三四五六七八九十]+段)?)", s)
    return m.group(1) if m else s


def type_key(btype: str) -> str:
    for k in ("住宅大樓", "華廈", "公寓", "透天厝", "套房"):
        if k in (btype or ""):
            return k
    return ""


def pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def comps(city: str, district: str, road: str = "", btype: str = "", age: float | None = None,
          seasons: int = 4, fetch=download, now: float | None = None) -> dict:
    """近 seasons 季同路段（不夠就同區）、同建物型態、屋齡相近的成交統計。
    fetch 可換成假的做離線測試。"""
    city = norm(city)
    code = CITY_CODES.get(city)
    if not code:
        raise ValueError(f"不支援的縣市：{city}")
    used, rows, last_err = [], [], ""
    for s in recent_seasons(seasons + 2, now):
        if len(used) == seasons:
            break
        try:
            text = fetch(code, s)
        except OSError as e:                     # 斷線、憑證、逾時：記下來，全部失敗時要讓人看得到原因
            last_err = f"{type(e).__name__}: {e}"[:200]
            continue
        if text:
            used.append(s)
            rows += parse(text)
    if not used:
        raise RuntimeError("實價登錄抓不到資料：" + (last_err or "內政部網站可能在維護"))

    dist, rk, tk = norm(district), road_key(road) if road else "", type_key(btype)
    rows = [r for r in rows if not dist or r.get("鄉鎮市區") == dist]
    car_est = car_estimates(rows)
    deals = [d for d in (to_deal(r, car_est) for r in rows) if d]
    if tk:
        deals = [d for d in deals if d["type"].startswith(tk)]
    # 由嚴到寬：同路段＋屋齡相近 → 同路段 → 全區＋屋齡相近 → 全區，取第一個夠 MIN_COMPS 筆的
    on_road = [d for d in deals if rk and rk in norm(d["addr"])]
    near = (lambda ds: [d for d in ds if d["age"] is not None and abs(d["age"] - age) <= AGE_BAND]) \
        if age is not None else (lambda ds: [])
    band = f"屋齡 {max(age - AGE_BAND, 0):g}～{age + AGE_BAND:g} 年" if age is not None else ""
    for cand, scope, age_band in ((near(on_road), "同路段", band), (on_road, "同路段", ""),
                                  (near(deals), "全區", band), (deals, "全區", "")):
        if len(cand) >= MIN_COMPS:
            deals = cand
            break
    else:
        scope, age_band = "全區", ""
    units = [d["unit"] for d in deals]
    car_price = car_est.get("坡道平面") or car_est.get("")
    car_pings = [d["car_ping"] for d in deals if d["car_ping"] > 0]
    deals.sort(key=lambda d: d["date"], reverse=True)
    return {
        "seasons": used, "scope": scope, "age_band": age_band, "road": rk, "type": tk, "district": dist,
        "n": len(units),
        "median": round(statistics.median(units), 1) if units else None,
        "p25": pct(units, .25) if units else None,
        "p75": pct(units, .75) if units else None,
        # 物件沒寫車位價時用來推估：跟成交扣車位用同一個數字（同區坡道平面中位價），前後一致
        "car_median_wan": round(car_price / 10000) if car_price else None,
        "car_ping_median": round(statistics.median(car_pings), 1) if car_pings else None,
        "latest": deals[:3],
    }
