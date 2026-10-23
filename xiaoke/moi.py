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
import ssl
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
MIN_SAME = 2                        # 同棟／同巷：2 筆就比整條路準
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


def moi_ssl_context() -> ssl.SSLContext:
    """照樣驗證憑證鏈與網域，只關掉 Python 3.13 起預設開啟的 X509 嚴格格式檢查。

    內政部的憑證少了 Subject Key Identifier 欄位，嚴格模式會直接拒絕
    （實機遇過：Windows Python 3.14「CERTIFICATE_VERIFY_FAILED ... Missing Subject Key Identifier」）。
    """
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    return ctx


def download(city_code: str, season: str) -> str:
    """回傳 CSV 文字；該季還沒公布回空字串。過去的季別會快取。"""
    f = CACHE_DIR / f"{season}_{city_code}_A.csv"
    if f.exists():
        return f.read_text(encoding="utf-8-sig")
    url = (f"https://plvr.land.moi.gov.tw/DownloadSeason?season={season}"
           f"&fileName={city_code}_lvr_land_A.csv")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (xiaoke real-price client)"})
    with urllib.request.urlopen(req, timeout=60, context=moi_ssl_context()) as r:
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


CN_NUM = {c: i for i, c in enumerate("零一二三四五六七八九")}


def cn_floor(s: str) -> int | None:
    """「十一層」→11、「二十一層」→21、「三層,四層」→3、「全」「地下一層」→None（透天、地下室不調樓層）。"""
    m = re.match(r"\s*([一二三四五六七八九十]+)層", s or "")
    if not m or (s or "").startswith("地下"):
        return None
    t = m.group(1)
    if "十" not in t:
        return CN_NUM[t[-1]] if len(t) == 1 else None
    tens, _, ones = t.partition("十")
    return (CN_NUM[tens] if tens else 1) * 10 + (CN_NUM[ones] if ones else 0)


FLOOR_RATE = 0.007                  # 樓層差每層 0.7%（估價常用的簡化值，不是精算）
FLOOR_CAP = 0.10                    # 最多調 ±10%


def floor_adjust(unit: float, deal_floor: int | None, floor: int) -> float:
    if not deal_floor:
        return unit
    k = max(-FLOOR_CAP, min(FLOOR_CAP, FLOOR_RATE * (floor - deal_floor)))
    return unit * (1 + k)


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
        "floor_n": cn_floor(r.get("移轉層次", "")),
        "age": roc_age(r.get("建築完成年月", "")),
        "total_wan": round(total / 10000),
        "ping": round(area / PING, 1),
        "car_wan": round(car_price / 10000),
        "car_ping": round(car_area / PING, 1),
        "car_est": est,
        "cars": car_count(r) if has_car else 0,
        "unit": round(unit, 1),
    }


def _strip_area(addr: str) -> str:
    s = norm(addr)
    for city in CITY_CODES:                       # 去掉「臺中市北屯區」
        s = s.removeprefix(city)
    return re.sub(r"^.{1,3}?[區鄉鎮市](?!路|街)", "", s)


ROAD_RE = r"(.+?(?:路|街|大道)(?:[一二三四五六七八九十]+段)?)"


def road_key(road: str) -> str:
    """「崇德路三段 123 號」→「崇德路三段」；門牌是「臺中市北屯區崇德路三段1~30號」這種格式。"""
    s = _strip_area(road)
    m = re.match(ROAD_RE, s)
    return m.group(1) if m else s


def addr_keys(addr: str) -> tuple[str, str]:
    """門牌 →（同棟鍵, 同巷鍵）。「五權三街55巷3號7樓」→（「五權三街55巷3號」,「五權三街55巷」）。
    用整段相等比對，不用子字串：「5號」不能對到「55號」。沒有巷就沒有同巷鍵。"""
    m = re.match(ROAD_RE + r"(\d+巷)?(\d+弄)?(\d+(?:之\d+)?號)?", _strip_area(addr))
    if not m:
        return "", ""
    road, lane, alley, no = (g or "" for g in m.groups())
    bldg = road + lane + alley + no if no else ""
    return bldg, (road + lane + alley if lane else "")


ELEVATOR = ("住宅大樓", "華廈")


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
          address: str = "", elevator: bool = False,
          floor: int | None = None, seasons: int = 4, same_seasons: int = 8, limit: int = 3,
          fetch=download, now: float | None = None) -> dict:
    """成交統計，比較對象由近到遠：同棟 → 同巷 → 同路段＋屋齡相近 → 全區＋屋齡相近
    → 同路段 → 全區。同棟／同巷成交少，往回看 same_seasons 季；其他看近 seasons 季。
    btype 沒寫但 elevator=True 時只比電梯大樓／華廈。fetch 可換成假的做離線測試。"""
    city = norm(city)
    code = CITY_CODES.get(city)
    if not code:
        raise ValueError(f"不支援的縣市：{city}")
    want = max(seasons, same_seasons if address else 0)
    used, rows, last_err = [], [], ""
    for s in recent_seasons(want + 2, now):
        if len(used) == want:
            break
        try:
            text = fetch(code, s)
        except OSError as e:                     # 斷線、憑證、逾時：記下來，全部失敗時要讓人看得到原因
            last_err = f"{type(e).__name__}: {e}"[:200]
            continue
        if text:
            used.append(s)
            rows += [dict(r, _season=s) for r in parse(text)]
    if not used:
        raise RuntimeError("實價登錄抓不到資料：" + (last_err or "內政部網站可能在維護"))

    dist, tk = norm(district), type_key(btype)
    rk = road_key(road or address) if (road or address) else ""
    bk, lk = addr_keys(address) if address else ("", "")
    rows = [r for r in rows if not dist or r.get("鄉鎮市區") == dist]
    car_est = car_estimates(rows)
    deals = []
    for r in rows:
        d = to_deal(r, car_est)
        if d:
            d["season"] = r["_season"]
            deals.append(d)
    for d in deals:
        d["bk"], d["lk"] = addr_keys(d["addr"])
    wide = deals              # 同棟／同巷：往回看較久，也不篩建物型態（同一棟就是同型態，AI 猜錯型態會把本棟濾掉）
    if tk in ELEVATOR or (not tk and elevator):  # 住宅大樓、華廈只差在 10 樓上下，都算電梯大樓
        deals, tk = [d for d in deals if d["type"].startswith(ELEVATOR)], "電梯大樓"
    elif tk:
        deals = [d for d in deals if d["type"].startswith(tk)]
    recent = set(used[:seasons])
    deals = [d for d in deals if d["season"] in recent]
    near = (lambda ds: [d for d in ds if d["age"] is not None and abs(d["age"] - age) <= AGE_BAND]) \
        if age is not None else (lambda ds: [])
    band = f"屋齡 {max(age - AGE_BAND, 0):g}～{age + AGE_BAND:g} 年" if age is not None else ""
    on_road = [d for d in deals if rk and rk in norm(d["addr"])]
    tiers = (([d for d in wide if bk and d["bk"] == bk], "同棟", bk, "", MIN_SAME),
             ([d for d in wide if lk and d["lk"] == lk], "同巷", lk, "", MIN_SAME),
             (near(on_road), "同路段", rk, band, MIN_COMPS),
             (near(deals), "全區", dist, band, MIN_COMPS),
             (on_road, "同路段", rk, "", MIN_COMPS),
             (deals, "全區", dist, "", 1))
    for cand, scope, key, age_band, need in tiers:
        if len(cand) >= need:
            deals = cand
            break
    else:
        deals, scope, key, age_band = [], "全區", dist, ""
    span = len(used) if scope in ("同棟", "同巷") else len(recent)
    units = [d["unit"] for d in deals]
    # 物件有樓層、而且是電梯大樓類：把每筆成交換算成「如果在這個樓層」的單價
    adj = [floor_adjust(d["unit"], d["floor_n"], floor) for d in deals] \
        if floor and not tk.startswith(("透天", "公寓")) and any(d["floor_n"] for d in deals) else []
    car_price = car_est.get("坡道平面") or car_est.get("")
    car_pings = [d["car_ping"] / d["cars"] for d in deals if d["car_ping"] > 0]
    deals.sort(key=lambda d: d["date"], reverse=True)
    return {
        "seasons": used[:span], "scope": scope, "scope_key": key, "age_band": age_band,
        "road": rk, "type": tk, "district": dist,
        "n": len(units),
        "median": round(statistics.median(units), 1) if units else None,
        "floor": floor if adj else None,
        "median_adj": round(statistics.median(adj), 1) if adj else None,
        "p25_adj": pct(adj, .25) if adj else None,
        "p75_adj": pct(adj, .75) if adj else None,
        "p25": pct(units, .25) if units else None,
        "p75": pct(units, .75) if units else None,
        # 物件沒寫車位價時用來推估：跟成交扣車位用同一個數字（同區坡道平面中位價），前後一致。都是「一個車位」
        "car_median_wan": round(car_price / 10000) if car_price else None,
        "car_ping_median": round(statistics.median(car_pings), 1) if car_pings else None,
        "latest": deals[:limit],
    }
