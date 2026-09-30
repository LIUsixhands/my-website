#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
webcheck.py — Sixhands Studio AI 數字員工「小維」網站維運巡檢工具
零第三方依賴，只用 Python 標準庫。

指令：
  check <url|client_id>          單站全項健檢
  scan [--client ID]             讀清冊巡檢所有客戶站
  links <url> [--max N]          連結失效掃描
  cert <domain>                  SSL 憑證 + 網域到期查詢
  audit <url> --industry X       合規字串稽核（禁字/必載）
  snap <url|client_id>           拍內容快照
  diff <url|client_id>           與上次快照比對（偵測內容被改/掉字）
  report <client_id>             產出當月維運月報 Markdown
  industries                     列出可用的產業合規規則

共用參數：--json  --md <路徑>  --quiet
清冊：~/AI員工_小維/clients/sites.json
"""
import sys, os, re, json, ssl, socket, argparse, subprocess, time
import urllib.request, urllib.error
from urllib.parse import urljoin, urlparse, quote, urlsplit, urlunsplit
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

BASE = os.path.expanduser("~/AI員工_小維")
SITES = os.path.join(BASE, "clients", "sites.json")
SNAPDIR = os.path.join(BASE, "snapshots")
REPORTDIR = os.path.join(BASE, "reports")
LOGDIR = os.path.join(BASE, "logs")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36 XiaoWei-Webcheck/1.0"
TIMEOUT = 20

OK, WARN, BAD, INFO = "PASS", "WARN", "FAIL", "INFO"

# ---------------------------------------------------------------- 合規規則庫
# forbidden: (正規表示式, 說明, 法源, 嚴重度)  嚴重度 "FAIL"=法律硬紅線必改, "WARN"=修辭風險請人工判斷
# required:  (正規表示式, 說明)
RULES = {
    "realestate": {
        "label": "不動產仲介／代銷",
        "forbidden": [
            (r"保證(增值|獲利|漲|賺)", "不得保證投資報酬", "公平交易法§21 不實廣告", "FAIL"),
            (r"穩賺|穩賠不了|包賺|零風險", "不得宣稱穩賺零風險", "公平交易法§21", "FAIL"),
            (r"包租(保證|保障)(獲利|收益|報酬)", "包租保證收益屬高風險宣稱", "公平交易法§21", "FAIL"),
            (r"(絕對|一定)(會)?(漲|增值)", "不得絕對化增值宣稱", "公平交易法§21", "FAIL"),
        ],
        "required": [
            (r"(經紀業|不動產經紀業|公司名稱)", "應揭露經紀業名稱"),
            (r"(經紀人|營業員)", "應揭露經紀人／營業員"),
            (r"(字號|證號|證書字號|\(\d{2,4}\)|北市地|字第)", "應揭露證書字號"),
        ],
    },
    "medical": {
        "label": "醫療／診所／醫事人員",
        "forbidden": [
            (r"根治|治癒|痊癒|保證(有效|見效|治好)", "不得為療效保證", "醫療法§86、醫療廣告", "FAIL"),
            (r"最(有效|好|強|權威)|第一名|唯一", "不得誇大比較性用語", "醫療法§86", "FAIL"),
            (r"免費(看診|診療|療程)|買一送一|折扣|優惠價", "醫療不得為價格促銷", "醫療法§86 招徠", "FAIL"),
            (r"術前.{0,6}術後|前後對比", "不得使用療程前後對比影像", "醫療廣告管理辦法", "FAIL"),
        ],
        "required": [(r"(醫師|院所|診所|醫療機構)", "應揭露醫療機構或醫師身分")],
    },
    "counseling": {
        "label": "心理諮商／催眠／身心靈",
        "forbidden": [
            (r"心理(諮商|治療)", "非心理師不得使用『諮商／心理治療』（客戶若為執業心理師則免）", "心理師法§42", "WARN"),
            (r"(治療|療癒)(憂鬱|焦慮|創傷|精神)", "不得宣稱治療精神疾患", "心理師法§42", "FAIL"),
            (r"保證(改善|痊癒|見效)", "不得保證療效", "公平交易法§21", "FAIL"),
        ],
        "required": [(r"(非醫療|不具醫療|不能取代|非屬醫療行為)", "應有非醫療行為聲明")],
    },
    "health": {
        "label": "保健食品／保健器材／美容",
        "forbidden": [
            (r"治療|療效|根治|痊癒|抗癌|降血(壓|糖|脂)|消炎|殺菌治病", "食品／器材不得宣稱醫療效能", "食安法§28、藥事法§69", "FAIL"),
            (r"保證(瘦|見效|有效)|一定(瘦|有效)", "不得為效果保證", "公平交易法§21", "FAIL"),
            (r"衛福部(認證|核可推薦)|國家認證有效", "不得假借機關認證", "食安法§28", "FAIL"),
        ],
        "required": [],
    },
    "finance": {
        "label": "金融／保險／投資",
        "forbidden": [
            (r"保證(獲利|收益|報酬|還本)|穩賺|保本保息|零風險", "不得保證獲利", "銀行法§29-1、金融消保法", "FAIL"),
            (r"(月|年)(收益|報酬)率?\s*\d+\s*%以上", "不得承諾具體報酬率", "銀行法§29-1", "FAIL"),
            (r"代操|全權委託操作", "涉及代客操作須具備許可", "證券投資信託及顧問法", "FAIL"),
        ],
        "required": [(r"(投資有風險|風險(說明|警語)|不保證)", "應有投資風險警語")],
    },
    "education": {
        "label": "補教／課程／招生",
        "forbidden": [
            (r"保證(錄取|考上|上榜|過關|就業|月入)", "不得為升學／就業保證", "補習及進修教育法、公平交易法§21", "FAIL"),
            (r"(百分之百|100%)(錄取|上榜|成功)", "不得絕對化錄取宣稱", "公平交易法§21", "FAIL"),
            (r"免費", "『免費』若附條件必須同頁標明條件", "公平交易法§21 不實廣告", "WARN"),
        ],
        "required": [(r"(退費|退款|終止)", "招生頁應載明退費規定")],
    },
    "food": {
        "label": "餐飲／食品",
        "forbidden": [
            (r"治療|療效|抗癌|降三高|治百病|藥用", "食品不得宣稱醫療效能", "食安法§28", "FAIL"),
            (r"最(好吃|便宜|大)|第一名|唯一", "最高級用語須有客觀依據（若為菜色形容詞屬修辭，人工判斷即可）", "公平交易法§21", "WARN"),
        ],
        "required": [(r"(營業時間|營業|電話|訂位|地址)", "應有營業資訊與聯絡方式")],
    },
    "beauty": {
        "label": "美業／美容工作室／民俗調理",
        "forbidden": [
            (r"整脊|矯正脊椎|推拿治療|治療", "民俗調理不得使用醫療用語", "醫療法§84、民俗調理業管理", "FAIL"),
            (r"醫美級|微整|雷射除斑|針劑", "非醫療機構不得宣稱醫療美容處置", "醫療法§84", "FAIL"),
            (r"保證(變瘦|見效|白)", "不得為效果保證", "公平交易法§21", "FAIL"),
        ],
        "required": [(r"(非醫療|不具醫療|舒緩|放鬆)", "應有非醫療性質說明")],
    },
    "general": {
        "label": "一般商業網站",
        "forbidden": [
            (r"保證(獲利|有效|見效|成功)", "不得為絕對效果保證", "公平交易法§21", "FAIL"),
            (r"零風險|穩賺不賠", "不得宣稱零風險", "公平交易法§21", "FAIL"),
        ],
        "required": [],
    },
}

# 上線前必須清掉的佔位／未完成殘留
PLACEHOLDER = [
    (r"lorem ipsum", "Lorem Ipsum 假文未替換"),
    (r"待補|待確認|TBD|TODO|FIXME|XXX待", "『待補／TODO』佔位文字未清"),
    (r"\.todo|<!--\s*todo", "HTML TODO 註解區塊未刪"),
    (r"0000-000-000|000-0000000|123-456-7890|09XX|09xx", "假電話號碼未替換"),
    (r"example\.com|your-?email|test@test", "範例信箱／網域未替換"),
    (r"請?(在此)?輸入(標題|內容|文字)|圖片說明文字", "樣板預設文字未替換"),
]

# ---------------------------------------------------------------- HTML 解析
class Doc(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.desc, self.viewport = "", "", ""
        self.links, self.imgs, self.scripts, self.styles = [], [], [], []
        self.forms, self.h1 = [], []
        self.favicon = False
        self.lang = ""
        self._grab = None
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "title":
            self._grab = "title"
        elif tag == "meta":
            n = (a.get("name") or a.get("property") or "").lower()
            if n == "description":
                self.desc = a.get("content", "")
            elif n == "viewport":
                self.viewport = a.get("content", "")
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            if "icon" in rel:
                self.favicon = True
            if "stylesheet" in rel and a.get("href"):
                self.styles.append(a["href"])
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "img":
            self.imgs.append((a.get("src", ""), a.get("alt")))
        elif tag == "script" and a.get("src"):
            self.scripts.append(a["src"])
        elif tag == "form":
            self.forms.append(a.get("action", ""))
        elif tag == "h1":
            self._grab = "h1"

    def handle_endtag(self, tag):
        self._grab = None

    def handle_data(self, d):
        if self._grab == "title":
            self.title += d.strip()
        elif self._grab == "h1":
            s = d.strip()
            if s:
                self.h1.append(s)
        self.text_parts.append(d)

    @property
    def text(self):
        return re.sub(r"\s+", " ", " ".join(self.text_parts))

# ---------------------------------------------------------------- 網路工具
def encode_url(u):
    """把含中文/空白的 IRI 轉成合法 URI，避免 urllib 噴 UnicodeEncodeError。"""
    try:
        u.encode("ascii")
        return u
    except UnicodeEncodeError:
        pass
    p = urlsplit(u)
    host = p.netloc
    try:
        host = host.encode("idna").decode("ascii")
    except Exception:
        pass
    return urlunsplit((p.scheme, host,
                       quote(p.path, safe="/%:@&=+$,~()!*'"),
                       quote(p.query, safe="/%:@&=+$,~()!*'?"),
                       quote(p.fragment, safe="/%:@&=+$,~")))

# 社群平台對機器人一律回 4xx，不代表連結真的壞掉
SOCIAL = ("facebook.com", "m.me", "instagram.com", "x.com", "twitter.com",
          "linkedin.com", "tiktok.com", "threads.net", "youtube.com", "youtu.be",
          "line.me", "lin.ee", "maps.google.com", "goo.gl")

def fetch(url, method="GET"):
    """回傳 (status, headers, body_str, elapsed_ms, final_url, err)"""
    url = encode_url(url)
    req = urllib.request.Request(url, method=method, headers={
        "User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})
    t0 = time.time()
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            raw = r.read() if method == "GET" else b""
            ms = int((time.time() - t0) * 1000)
            enc = "utf-8"
            ct = r.headers.get("Content-Type", "")
            m = re.search(r"charset=([\w-]+)", ct, re.I)
            if m:
                enc = m.group(1)
            body = raw.decode(enc, errors="replace")
            if not m and re.search(r'charset=["\']?big5', body[:2000], re.I):
                body = raw.decode("big5", errors="replace")
            return r.status, dict(r.headers), body, ms, r.url, None
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), "", int((time.time() - t0) * 1000), url, None
    except Exception as e:
        return 0, {}, "", int((time.time() - t0) * 1000), url, f"{type(e).__name__}: {e}"

def cert_info(host, port=443):
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=TIMEOUT) as s:
            with ctx.wrap_socket(s, server_hostname=host) as ss:
                c = ss.getpeercert()
        exp = datetime.strptime(c["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days = (exp - datetime.now(timezone.utc)).days
        issuer = dict(x[0] for x in c.get("issuer", []))
        return {"expires": exp.strftime("%Y-%m-%d"), "days_left": days,
                "issuer": issuer.get("organizationName", "?"), "error": None}
    except Exception as e:
        return {"expires": None, "days_left": None, "issuer": None, "error": f"{type(e).__name__}: {e}"}

def domain_expiry(domain):
    """用系統 whois 抓網域到期日；抓不到回 None（不當成錯誤）。"""
    root = ".".join(domain.split(".")[-2:]) if domain.count(".") >= 1 else domain
    for free in ("netlify.app", "github.io", "vercel.app", "pages.dev", "web.app", "firebaseapp.com"):
        if domain.endswith(free):
            return {"domain": domain, "expires": None, "days_left": None, "note": f"{free} 免費子網域，無需續約"}
    try:
        out = subprocess.run(["whois", root], capture_output=True, text=True, timeout=25).stdout
    except Exception as e:
        return {"domain": root, "expires": None, "days_left": None, "note": f"whois 不可用：{e}"}
    m = re.search(r"(?:Registry Expiry Date|Expiration Date|paid-till|Expiry Date|expires?)\s*:?\s*"
                  r"(\d{4}-\d{2}-\d{2})", out, re.I)
    if not m:
        return {"domain": root, "expires": None, "days_left": None, "note": "whois 未提供到期日"}
    exp = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return {"domain": root, "expires": m.group(1),
            "days_left": (exp - datetime.now(timezone.utc)).days, "note": ""}

# ---------------------------------------------------------------- 檢查項目
def add(rows, level, item, detail, fix=""):
    rows.append({"level": level, "item": item, "detail": detail, "fix": fix})

def check_stale_dates(text, today=None):
    """抓頁面上早於今天的寫死日期（講座頁／活動頁最常見的死法）。"""
    today = today or datetime.now()
    hits = []
    pats = [
        (r"(20\d{2})\s*[/年\-\.]\s*(\d{1,2})\s*[/月\-\.]\s*(\d{1,2})", 3),
        (r"(20\d{2})\s*[/年\-\.]\s*(\d{1,2})\s*月?(?![\d/年\-\.])", 2),
    ]
    for pat, g in pats:
        for m in re.finditer(pat, text):
            try:
                y, mo = int(m.group(1)), int(m.group(2))
                d = int(m.group(3)) if g == 3 else 28
                if not (1 <= mo <= 12 and 1 <= d <= 31):
                    continue
                dt = datetime(y, mo, d)
            except ValueError:
                continue
            if dt < today - timedelta(days=1):
                hits.append((m.group(0).strip(), dt.strftime("%Y-%m-%d")))
    seen, out = set(), []
    for raw, iso in hits:
        if iso not in seen:
            seen.add(iso)
            out.append((raw, iso))
    return out[:12]

def audit_text(text, industry):
    ind = RULES.get(industry, RULES["general"])
    res = {"industry": industry, "label": ind["label"], "forbidden": [], "missing": [], "placeholder": []}
    low = text.lower()
    for rule in ind["forbidden"]:
        pat, why, law = rule[0], rule[1], rule[2]
        sev = rule[3] if len(rule) > 3 else "FAIL"
        for m in re.finditer(pat, text, re.I):
            ctx = text[max(0, m.start() - 25):m.end() + 25].strip()
            res["forbidden"].append({"hit": m.group(0), "why": why, "law": law,
                                     "context": ctx, "severity": sev})
            break
    for pat, why in ind["required"]:
        if not re.search(pat, text, re.I):
            res["missing"].append({"why": why, "pattern": pat})
    for pat, why in PLACEHOLDER:
        m = re.search(pat, low if pat.islower() else text, re.I)
        if m:
            res["placeholder"].append({"hit": m.group(0), "why": why})
    return res

def check_links(base_url, hrefs, limit=60):
    seen, results = set(), []
    for h in hrefs:
        h = h.strip()
        if not h or h.startswith(("#", "javascript:", "data:")):
            continue
        if h.startswith(("mailto:", "tel:", "line:", "https://line.me", "https://lin.ee")):
            continue
        u = urljoin(base_url, h)
        if u in seen:
            continue
        seen.add(u)
        if len(seen) > limit:
            break
        st, _, _, ms, _, err = fetch(u, method="HEAD")
        if st in (0, 405, 403, 501):  # HEAD 常被擋，退回 GET
            st, _, _, ms, _, err = fetch(u, method="GET")
        host = (urlparse(u).hostname or "").lower()
        social = any(host == d or host.endswith("." + d) for d in SOCIAL)
        results.append({"url": u, "status": st, "ms": ms, "error": err, "social": social})
    return results

def check_site(url, industry="general", must_contain=None, do_links=True, link_limit=60):
    rows, data = [], {"url": url, "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    st, hdr, body, ms, final, err = fetch(url)
    data["status"], data["ms"], data["final_url"] = st, ms, final

    if err or st == 0:
        add(rows, BAD, "可用性", f"完全連不上：{err}", "先確認網域 DNS／主機是否還活著，再查部署狀態")
        data["rows"] = rows
        return data
    if st >= 500:
        add(rows, BAD, "可用性", f"伺服器錯誤 HTTP {st}", "查主機／函式錯誤日誌")
    elif st >= 400:
        add(rows, BAD, "可用性", f"HTTP {st} 頁面不存在或被拒", "確認部署路徑與首頁檔名")
    else:
        add(rows, OK, "可用性", f"HTTP {st}（{ms} ms）")

    if ms > 4000:
        add(rows, BAD, "載入速度", f"{ms} ms 過慢（>4s 跳出率暴增）", "壓縮圖片、移除未用的外部字型／腳本")
    elif ms > 2000:
        add(rows, WARN, "載入速度", f"{ms} ms 偏慢（建議 <2s）", "首屏圖片轉 WebP、加 loading=lazy")
    else:
        add(rows, OK, "載入速度", f"{ms} ms")

    # HTTPS / 憑證
    p = urlparse(final if final else url)
    host = p.hostname or ""
    data["host"] = host
    if p.scheme != "https":
        add(rows, BAD, "HTTPS", "網站未走 HTTPS", "Netlify/GitHub Pages 開強制 HTTPS；自架主機裝 Let's Encrypt")
    else:
        ci = cert_info(host)
        data["cert"] = ci
        if ci["error"]:
            add(rows, BAD, "SSL 憑證", f"讀取失敗：{ci['error']}", "確認憑證是否過期或網域未綁定")
        elif ci["days_left"] is None:
            add(rows, WARN, "SSL 憑證", "無法判讀到期日")
        elif ci["days_left"] < 0:
            add(rows, BAD, "SSL 憑證", f"已過期（{ci['expires']}）", "立刻續發，過期會整站跳紅色警告")
        elif ci["days_left"] < 21:
            add(rows, WARN, "SSL 憑證", f"剩 {ci['days_left']} 天（{ci['expires']}）", "確認自動續期有沒有壞掉")
        else:
            add(rows, OK, "SSL 憑證", f"剩 {ci['days_left']} 天（{ci['expires']}，{ci['issuer']}）")

    de = domain_expiry(host)
    data["domain"] = de
    if de["days_left"] is None:
        add(rows, INFO, "網域到期", de["note"] or "未取得")
    elif de["days_left"] < 0:
        add(rows, BAD, "網域到期", f"已過期（{de['expires']}）", "立刻續約，過期網域會被搶註")
    elif de["days_left"] < 45:
        add(rows, WARN, "網域到期", f"剩 {de['days_left']} 天（{de['expires']}）", "提醒客戶續約並開自動續約")
    else:
        add(rows, OK, "網域到期", f"剩 {de['days_left']} 天（{de['expires']}）")

    # HTML 解析
    doc = Doc()
    try:
        doc.feed(body)
    except Exception:
        pass
    text = doc.text
    data["title"], data["desc"] = doc.title, doc.desc

    if not doc.title:
        add(rows, BAD, "SEO 標題", "缺 <title>", "補上『品牌｜主要服務｜地區』")
    elif len(doc.title) > 40:
        add(rows, WARN, "SEO 標題", f"{len(doc.title)} 字偏長，搜尋結果會被截斷", "壓到 30 字內")
    else:
        add(rows, OK, "SEO 標題", doc.title)

    if not doc.desc:
        add(rows, WARN, "SEO 描述", "缺 meta description", "補 60-80 字，含服務＋地區＋行動呼籲")
    elif len(doc.desc) > 90:
        add(rows, WARN, "SEO 描述", f"{len(doc.desc)} 字偏長", "壓到 80 字內")
    else:
        add(rows, OK, "SEO 描述", f"{len(doc.desc)} 字")

    if not doc.viewport:
        add(rows, BAD, "手機版", "缺 viewport meta，手機會整頁縮小", '補 <meta name="viewport" content="width=device-width, initial-scale=1">')
    else:
        add(rows, OK, "手機版", "viewport 已設定")

    if not doc.lang:
        add(rows, WARN, "語系", "html 缺 lang 屬性", '設 lang="zh-Hant-TW"')
    else:
        add(rows, OK, "語系", doc.lang)

    if not doc.h1:
        add(rows, WARN, "H1 標題", "整頁沒有 H1", "首屏主標改用 h1")
    else:
        add(rows, OK, "H1 標題", doc.h1[0][:40])

    add(rows, OK if doc.favicon else WARN, "Favicon",
        "已設定" if doc.favicon else "未設定（分頁顯示空白圖示）", "" if doc.favicon else "加 <link rel=icon>")

    noalt = [s for s, a in doc.imgs if a is None or not a.strip()]
    if doc.imgs:
        if len(noalt) > len(doc.imgs) * 0.5:
            add(rows, WARN, "圖片 alt", f"{len(noalt)}/{len(doc.imgs)} 張缺 alt", "補 alt 有助 SEO 與無障礙")
        else:
            add(rows, OK, "圖片 alt", f"{len(doc.imgs)-len(noalt)}/{len(doc.imgs)} 張已補")

    # 混合內容
    if p.scheme == "https":
        mixed = [u for u in (doc.imgs and [s for s, _ in doc.imgs] or []) + doc.scripts + doc.styles
                 if u.startswith("http://")]
        if mixed:
            add(rows, BAD, "混合內容", f"{len(mixed)} 個資源走 http://（瀏覽器會擋）", f"改成 https:// — 例：{mixed[0][:60]}")
        else:
            add(rows, OK, "混合內容", "無 http 資源")

    # 聯絡管道（客戶網站沒聯絡方式＝白做）
    contact = {
        "電話": bool(re.search(r"tel:|0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{3,4}|09\d{2}[-\s]?\d{3}[-\s]?\d{3}", body)),
        "LINE": bool(re.search(r"line\.me|lin\.ee|LINE\s*(ID|官方)|@[\w\-]{4,}", body, re.I)),
        "Email": bool(re.search(r"mailto:|[\w\.\-]+@[\w\-]+\.\w{2,}", body)),
        "表單": bool(doc.forms),
    }
    data["contact"] = contact
    have = [k for k, v in contact.items() if v]
    if not have:
        add(rows, BAD, "聯絡管道", "頁面上找不到任何電話／LINE／Email／表單", "沒有轉換出口＝這個網站不會帶來生意，立刻補")
    else:
        add(rows, OK, "聯絡管道", "、".join(have))

    # 過期日期
    stale = check_stale_dates(text)
    data["stale_dates"] = stale
    if stale:
        add(rows, WARN, "過期日期", "、".join(f"{r}" for r, _ in stale[:5]),
            "活動／講座頁最常見的死法：日期過了還掛在首頁，客戶點進來就跳出")
    else:
        add(rows, OK, "過期日期", "未發現已過期的寫死日期")

    # 必含關鍵字
    if must_contain:
        miss = [k for k in must_contain if k not in body]
        data["must_contain_missing"] = miss
        if miss:
            add(rows, BAD, "必載內容", f"缺少：{'、'.join(miss)}", "客戶指定必須出現的資訊消失了，多半是改版時被覆蓋")
        else:
            add(rows, OK, "必載內容", f"{len(must_contain)} 項全在")

    # 合規稽核
    au = audit_text(text, industry)
    data["audit"] = au
    if au["forbidden"]:
        for f in au["forbidden"]:
            lv = BAD if f.get("severity", "FAIL") == "FAIL" else WARN
            add(rows, lv, f"合規禁字（{au['label']}）", f"「{f['hit']}」— {f['why']}", f"法源：{f['law']}｜原文：…{f['context']}…")
    else:
        add(rows, OK, f"合規禁字（{au['label']}）", "未命中禁用字")
    for m in au["missing"]:
        add(rows, WARN, "合規必載", m["why"], "缺法定必載資訊，上線狀態有風險")
    for ph in au["placeholder"]:
        add(rows, BAD, "佔位殘留", f"「{ph['hit']}」— {ph['why']}", "上線頁面出現未完成內容，立刻清掉")

    # 連結
    if do_links:
        lk = check_links(final or url, doc.links, link_limit)
        data["links"] = lk
        bad_l = [l for l in lk if (l["status"] == 0 or l["status"] >= 400) and not l["social"]]
        soc_l = [l for l in lk if (l["status"] == 0 or l["status"] >= 400) and l["social"]]
        if bad_l:
            for d in bad_l[:8]:
                add(rows, BAD, "失效連結", f"HTTP {d['status'] or 'ERR'} → {d['url'][:70]}", d["error"] or "更新或移除這個連結")
        for d in soc_l[:5]:
            add(rows, INFO, "社群連結", f"{d['url'][:70]} 回 {d['status'] or 'ERR'}",
                "社群平台會擋自動檢測，這不代表壞掉 — 請人工點開確認一次")
        if not bad_l:
            add(rows, OK, "連結檢查", f"{len(lk)} 個連結中，{len(lk)-len(soc_l)} 個確認可達")

    data["rows"] = rows
    data["score"] = score_of(rows)
    return data

def score_of(rows):
    f = sum(1 for r in rows if r["level"] == BAD)
    w = sum(1 for r in rows if r["level"] == WARN)
    return max(0, 100 - f * 12 - w * 4)

# ---------------------------------------------------------------- 快照 / 比對
def snap_path(key):
    safe = re.sub(r"[^\w\-.]", "_", key)
    return os.path.join(SNAPDIR, f"{safe}.json")

def do_snap(url, key=None):
    os.makedirs(SNAPDIR, exist_ok=True)
    st, _, body, ms, final, err = fetch(url)
    if err or st >= 400:
        return {"error": err or f"HTTP {st}"}
    doc = Doc()
    try:
        doc.feed(body)
    except Exception:
        pass
    snap = {"url": url, "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "status": st,
            "title": doc.title, "desc": doc.desc, "bytes": len(body),
            "text": doc.text[:200000], "links": sorted(set(doc.links)), "imgs": [s for s, _ in doc.imgs]}
    prev_p = snap_path(key or url)
    if os.path.exists(prev_p):
        with open(prev_p, encoding="utf-8") as f:
            old = json.load(f)
        hist = old.get("_prev_at", [])[-9:]
        snap["_prev_at"] = hist + [old["at"]]
        os.replace(prev_p, prev_p + ".prev")
    with open(prev_p, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    return snap

def do_diff(url, key=None):
    p = snap_path(key or url) 
    prev_file = p + ".prev" if os.path.exists(p + ".prev") else p
    if not os.path.exists(p):
        return {"error": "沒有舊快照，先跑 snap 建立基準"}
    with open(p, encoding="utf-8") as f:
        base = json.load(f)
    st, _, body, ms, final, err = fetch(url)
    if err:
        return {"error": err}
    doc = Doc()
    try:
        doc.feed(body)
    except Exception:
        pass
    now_text, old_text = doc.text, base.get("text", "")
    old_sent = set(s.strip() for s in re.split(r"[。！？\n｜|]", old_text) if len(s.strip()) > 8)
    new_sent = set(s.strip() for s in re.split(r"[。！？\n｜|]", now_text) if len(s.strip()) > 8)
    return {
        "url": url, "base_at": base["at"], "now_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "title_changed": (base.get("title") or "") != doc.title,
        "title_before": base.get("title"), "title_after": doc.title,
        "bytes_before": base.get("bytes"), "bytes_after": len(body),
        "removed": sorted(old_sent - new_sent)[:20],
        "added": sorted(new_sent - old_sent)[:20],
        "links_removed": sorted(set(base.get("links", [])) - set(doc.links))[:20],
        "links_added": sorted(set(doc.links) - set(base.get("links", [])))[:20],
    }

# ---------------------------------------------------------------- 清冊
def load_sites():
    if not os.path.exists(SITES):
        return {"clients": []}
    with open(SITES, encoding="utf-8") as f:
        return json.load(f)

def find_client(cid):
    for c in load_sites().get("clients", []):
        if c.get("id") == cid or c.get("name") == cid:
            return c
    return None

def resolve(target):
    """target 可以是 url 或 client id"""
    c = find_client(target)
    if c:
        return c
    if target.startswith("http"):
        return {"id": urlparse(target).hostname, "name": target, "url": target, "industry": "general"}
    return None

# ---------------------------------------------------------------- 輸出
ICON = {OK: "✅", WARN: "⚠️ ", BAD: "❌", INFO: "ℹ️ "}

def print_report(d, quiet=False):
    print(f"\n{'='*64}\n🔧 小維巡檢報告　{d.get('name') or d['url']}\n   {d['url']}　|　{d['checked_at']}")
    if "score" in d:
        s = d["score"]
        mark = "健康" if s >= 90 else ("要處理" if s >= 70 else "急件")
        print(f"   健檢分數：{s}/100（{mark}）")
    print("=" * 64)
    for r in d["rows"]:
        if quiet and r["level"] == OK:
            continue
        print(f"{ICON[r['level']]} {r['item']}：{r['detail']}")
        if r["fix"] and r["level"] in (BAD, WARN):
            print(f"      ↳ {r['fix']}")
    f = sum(1 for r in d["rows"] if r["level"] == BAD)
    w = sum(1 for r in d["rows"] if r["level"] == WARN)
    print("-" * 64)
    print(f"結論：{f} 項必修、{w} 項建議改善\n")

def md_report(d):
    L = [f"# 網站健檢報告｜{d.get('name') or d['url']}", "",
         f"- 網址：{d['url']}", f"- 檢查時間：{d['checked_at']}",
         f"- 健檢分數：**{d.get('score','-')}/100**", "",
         "| 判定 | 檢查項目 | 結果 | 建議 |", "|---|---|---|---|"]
    for r in d["rows"]:
        L.append(f"| {ICON[r['level']].strip()} | {r['item']} | {r['detail']} | {r['fix']} |")
    L += ["", "---", "🦞 Sixhands Studio AI數字員工｜維運專員 小維"]
    return "\n".join(L)

# ---------------------------------------------------------------- 主程式
def main():
    ap = argparse.ArgumentParser(description="小維 — 網站維運巡檢工具", add_help=True)
    ap.add_argument("cmd", choices=["check", "scan", "links", "cert", "audit", "snap", "diff", "report", "industries"])
    ap.add_argument("target", nargs="?", default="")
    ap.add_argument("--industry", default=None)
    ap.add_argument("--client", default=None)
    ap.add_argument("--max", type=int, default=60)
    ap.add_argument("--no-links", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--md", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    for d in (SNAPDIR, REPORTDIR, LOGDIR, os.path.dirname(SITES)):
        os.makedirs(d, exist_ok=True)

    if a.cmd == "industries":
        print("\n可用產業合規規則：")
        for k, v in RULES.items():
            print(f"  {k:<12} {v['label']}　禁字 {len(v['forbidden'])} 條／必載 {len(v['required'])} 條")
        print()
        return

    if a.cmd == "scan":
        sites = load_sites().get("clients", [])
        if a.client:
            sites = [c for c in sites if c.get("id") == a.client]
        if not sites:
            print(f"⚠️  清冊沒有站台。編輯：{SITES}")
            return
        summary = []
        for c in sites:
            d = check_site(c["url"], c.get("industry", "general"), c.get("must_contain"),
                           not a.no_links, a.max)
            d["name"] = c.get("name")
            print_report(d, quiet=True)
            summary.append((c.get("name"), d.get("score", 0),
                            sum(1 for r in d["rows"] if r["level"] == BAD)))
        print("=" * 64)
        print("📋 全客戶巡檢總表")
        for n, s, f in sorted(summary, key=lambda x: x[1]):
            flag = "🔴" if f else ("🟡" if s < 90 else "🟢")
            print(f"  {flag} {s:>3}/100　{f} 項必修　{n}")
        print()
        return

    if not a.target:
        print("請給網址或客戶代號"); sys.exit(1)

    if a.cmd == "cert":
        host = urlparse(a.target).hostname or a.target
        ci, de = cert_info(host), domain_expiry(host)
        print(f"\n🔐 {host}")
        print(f"  SSL 憑證：{ci['expires']}（剩 {ci['days_left']} 天，{ci['issuer']}）" if not ci["error"] else f"  SSL 讀取失敗：{ci['error']}")
        print(f"  網域到期：{de['expires'] or de['note']}" + (f"（剩 {de['days_left']} 天）" if de["days_left"] is not None else "") + "\n")
        return

    c = resolve(a.target)
    if not c:
        print(f"❌ 找不到客戶代號「{a.target}」，也不是網址"); sys.exit(1)
    url = c["url"]
    industry = a.industry or c.get("industry", "general")

    if a.cmd == "links":
        st, _, body, _, final, err = fetch(url)
        if err:
            print(f"❌ {err}"); sys.exit(1)
        doc = Doc(); doc.feed(body)
        res = check_links(final, doc.links, a.max)
        dead = [r for r in res if (r["status"] == 0 or r["status"] >= 400) and not r["social"]]
        soc = [r for r in res if (r["status"] == 0 or r["status"] >= 400) and r["social"]]
        print(f"\n🔗 {url}　共檢 {len(res)} 個連結，失效 {len(dead)} 個")
        for r in dead:
            print(f"  ❌ HTTP {r['status'] or 'ERR'}　{r['url']}")
        for r in soc:
            print(f"  ℹ️  HTTP {r['status'] or 'ERR'}　{r['url']}（社群平台擋機器人，請人工確認）")
        if not dead:
            print("  ✅ 無確認失效的連結")
        print()
        return

    if a.cmd == "audit":
        st, _, body, _, _, err = fetch(url)
        if err:
            print(f"❌ {err}"); sys.exit(1)
        doc = Doc(); doc.feed(body)
        au = audit_text(doc.text, industry)
        print(f"\n⚖️  合規稽核　{url}　產業：{au['label']}")
        for f in au["forbidden"]:
            ic = "❌" if f.get("severity", "FAIL") == "FAIL" else "⚠️ "
            print(f"  {ic} 禁字「{f['hit']}」— {f['why']}\n       法源：{f['law']}\n       原文：…{f['context']}…")
        for m in au["missing"]:
            print(f"  ⚠️  必載缺漏：{m['why']}")
        for p in au["placeholder"]:
            print(f"  ❌ 佔位殘留「{p['hit']}」— {p['why']}")
        if not (au["forbidden"] or au["missing"] or au["placeholder"]):
            print("  ✅ 未發現違規字串與佔位殘留")
        print()
        return

    if a.cmd == "snap":
        s = do_snap(url, c.get("id"))
        print(f"📸 快照已存：{snap_path(c.get('id') or url)}" if "error" not in s else f"❌ {s['error']}")
        return

    if a.cmd == "diff":
        d = do_diff(url, c.get("id"))
        if "error" in d:
            print(f"❌ {d['error']}"); return
        print(f"\n🔍 內容比對　{url}\n   基準 {d['base_at']} → 現在 {d['now_at']}")
        print(f"   頁面大小：{d['bytes_before']} → {d['bytes_after']} bytes")
        if d["title_changed"]:
            print(f"   ⚠️  標題已變：「{d['title_before']}」→「{d['title_after']}」")
        if d["removed"]:
            print(f"   ❌ 消失的內容（{len(d['removed'])} 段）：")
            for s in d["removed"][:10]:
                print(f"      - {s[:60]}")
        if d["added"]:
            print(f"   ➕ 新增的內容（{len(d['added'])} 段）：")
            for s in d["added"][:10]:
                print(f"      + {s[:60]}")
        if d["links_removed"]:
            print(f"   ❌ 消失的連結：{'、'.join(x[:40] for x in d['links_removed'][:5])}")
        if not (d["removed"] or d["added"] or d["title_changed"]):
            print("   ✅ 與基準一致，沒有被動過")
        print()
        return

    # check / report
    d = check_site(url, industry, c.get("must_contain"), not a.no_links, a.max)
    d["name"] = c.get("name")
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=2)); return
    print_report(d, a.quiet)
    out = a.md
    if a.cmd == "report" and not out:
        os.makedirs(REPORTDIR, exist_ok=True)
        out = os.path.join(REPORTDIR, f"{c.get('id','site')}_{datetime.now():%Y%m}.md")
    if out:
        with open(os.path.expanduser(out), "w", encoding="utf-8") as f:
            f.write(md_report(d))
        print(f"📄 報告已存：{out}\n")

if __name__ == "__main__":
    main()
