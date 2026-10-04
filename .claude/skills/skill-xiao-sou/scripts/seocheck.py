#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seocheck.py — Sixhands Studio AI 數字員工 · 小搜 的 SEO 檢查引擎

零第三方依賴（只用 Python 標準庫），Mac / Windows / Linux 通用。

指令：
  scan     掃描單頁或整個資料夾，列出 SEO 問題（分 [X] 必修 / [!] 建議 / [v] 通過）
  report   產出 Markdown 健檢報告
  sitemap  產生 sitemap.xml + robots.txt
  schema   產生 JSON-LD 結構化資料樣板
  yt       YouTube 影片 SEO 檢查（標題 / 描述 / 標籤）

用法：
  python3 seocheck.py scan ./site --base https://example.com
  python3 seocheck.py report ./site --base https://example.com --out SEO健檢報告.md
  python3 seocheck.py sitemap ./site --base https://example.com
  python3 seocheck.py schema event --out event.json
  python3 seocheck.py yt --title "標題" --desc desc.txt --tags "a,b,c"
"""

import argparse
import datetime as _dt
import html
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

# Windows 主控台預設 cp950，強制 UTF-8 輸出避免 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

MARK_BAD = "[X]"
MARK_WARN = "[!]"
MARK_OK = "[v]"

# Google 中文搜尋結果的顯示寬度（以半形字元計；一個中文字 = 2）
TITLE_W_MIN, TITLE_W_MAX = 20, 60
DESC_W_MIN, DESC_W_MAX = 100, 160

SKIP_NAME_HINTS = ("備份", "未採用", "backup", "_bak", "old")

# 掛了 noindex 的頁面本來就不打算被搜尋引擎收錄（OAuth 回呼頁、感謝頁、預覽頁），
# 對它抱怨「沒有 description / 沒有 canonical」是純噪音，
# 會把真正該修的項目淹掉——2026-09-11 的健檢就是被這一頁佔掉全部 4 項必修。
NOINDEX_RE = re.compile(
    r"""<meta[^>]+name\s*=\s*["']robots["'][^>]*content\s*=\s*["'][^"']*\bnoindex\b""",
    re.I)

# 搜尋引擎的擁有權驗證檔：是網站資產但不是網頁，不該掃也不該進 sitemap
VERIFY_FILE_RE = re.compile(
    r"^(google[0-9a-f]{16}\.html|BingSiteAuth\.xml|yandex_[0-9a-f]+\.html)$", re.I)


def vwidth(s: str) -> int:
    """視覺寬度：CJK / 全形標點算 2，其餘算 1。"""
    w = 0
    for ch in s:
        o = ord(ch)
        if (
            0x1100 <= o <= 0x115F
            or 0x2E80 <= o <= 0xA4CF
            or 0xAC00 <= o <= 0xD7A3
            or 0xF900 <= o <= 0xFAFF
            or 0xFE30 <= o <= 0xFE6F
            or 0xFF00 <= o <= 0xFF60
            or 0xFFE0 <= o <= 0xFFE6
            or 0x20000 <= o <= 0x3FFFD
        ):
            w += 2
        else:
            w += 1
    return w


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self._in_title = False
        self.metas = []           # list[dict]
        self.links = []           # list[dict] (<link>)
        self.headings = []        # list[(level, text)]
        self._heading_level = None
        self._heading_buf = []
        self.imgs = []            # list[dict]
        self.anchors = []         # list[dict]
        self.ldjson = []          # list[str] 原始文字
        self._in_ldjson = False
        self._ld_buf = []
        self._skip_depth = 0      # script/style 內文字不計入正文
        self.text_chunks = []
        self.html_lang = None
        self.has_viewport = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.html_lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            self.metas.append(a)
            if a.get("name", "").lower() == "viewport":
                self.has_viewport = True
        elif tag == "link":
            self.links.append(a)
        elif tag in ("h1", "h2", "h3", "h4"):
            self._heading_level = int(tag[1])
            self._heading_buf = []
        elif tag == "img":
            self.imgs.append(a)
        elif tag == "a":
            self.anchors.append(a)
        elif tag == "script":
            self._skip_depth += 1
            if a.get("type", "").lower() in ("application/ld+json", "application/ld json"):
                self._in_ldjson = True
                self._ld_buf = []
        elif tag == "style":
            self._skip_depth += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in ("h1", "h2", "h3", "h4") and self._heading_level:
            self.headings.append((self._heading_level, "".join(self._heading_buf).strip()))
            self._heading_level = None
            self._heading_buf = []
        elif tag == "script":
            self._skip_depth = max(0, self._skip_depth - 1)
            if self._in_ldjson:
                self.ldjson.append("".join(self._ld_buf))
                self._in_ldjson = False
        elif tag == "style":
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or "") + data
        if self._in_ldjson:
            self._ld_buf.append(data)
        if self._heading_level:
            self._heading_buf.append(data)
        if self._skip_depth == 0:
            t = data.strip()
            if t:
                self.text_chunks.append(t)

    # 便利存取
    def meta_by_name(self, name):
        for m in self.metas:
            if m.get("name", "").lower() == name.lower():
                return m.get("content", "")
        return None

    def meta_by_prop(self, prop):
        for m in self.metas:
            if m.get("property", "").lower() == prop.lower():
                return m.get("content", "")
        return None

    def link_rel(self, rel):
        for l in self.links:
            if rel.lower() in l.get("rel", "").lower():
                return l.get("href", "")
        return None

    @property
    def body_text(self):
        return " ".join(self.text_chunks)


# ---------------------------------------------------------------- 過期日期偵測

_DATE_PATTERNS = [
    re.compile(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)"),      # 9/7
    re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日"),        # 9月7日
]


def find_stale_dates(text, today=None):
    """在文字中找出已過期的『月/日』。回傳 [(原字串, 推定日期)]。"""
    today = today or _dt.date.today()
    out = []
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(text or ""):
            try:
                mo, d = int(m.group(1)), int(m.group(2))
            except ValueError:
                continue
            if not (1 <= mo <= 12 and 1 <= d <= 31):
                continue
            try:
                cand = _dt.date(today.year, mo, d)
            except ValueError:
                continue
            # 只判定「同年且已過去」；跨年的未來場次不誤報
            if cand < today and (today - cand).days <= 300:
                out.append((m.group(0), cand.isoformat()))
    return out


# ---------------------------------------------------------------- 單頁檢查

def check_page(path: Path, base: str = None, all_titles=None, all_descs=None):
    """回傳 dict：{'file':..., 'issues':[(level, code, msg)], 'facts':{...}}"""
    raw = path.read_text(encoding="utf-8", errors="replace")
    p = PageParser()
    try:
        p.feed(raw)
    except Exception as e:
        return {"file": str(path), "issues": [("bad", "PARSE", f"HTML 解析失敗：{e}")], "facts": {}}

    issues = []
    add = lambda lv, code, msg: issues.append((lv, code, msg))

    title = (p.title or "").strip()
    desc = (p.meta_by_name("description") or "").strip()

    # --- title
    if not title:
        add("bad", "TITLE_MISSING", "沒有 <title>，搜尋結果會抓不到標題")
    else:
        w = vwidth(title)
        if w > TITLE_W_MAX:
            add("warn", "TITLE_LONG", f"title 寬度 {w}（建議 ≤{TITLE_W_MAX}，約 30 個中文字），搜尋結果會被截斷：{title}")
        elif w < TITLE_W_MIN:
            add("warn", "TITLE_SHORT", f"title 太短（寬度 {w}），塞不下關鍵字：{title}")
        if all_titles is not None and all_titles.get(title, 0) > 1:
            add("bad", "TITLE_DUP", f"title 與其他頁重複（{all_titles[title]} 頁共用）：{title}")

    # --- description
    if not desc:
        add("bad", "DESC_MISSING", "沒有 meta description，Google 會自己亂抓一段當摘要")
    else:
        w = vwidth(desc)
        if w > DESC_W_MAX:
            add("warn", "DESC_LONG", f"description 寬度 {w}（建議 ≤{DESC_W_MAX}），尾巴會被切掉")
        elif w < DESC_W_MIN:
            add("warn", "DESC_SHORT", f"description 太短（寬度 {w}），沒把賣點與行動呼籲寫進去")
        if all_descs is not None and all_descs.get(desc, 0) > 1:
            add("bad", "DESC_DUP", f"description 與其他頁重複（{all_descs[desc]} 頁共用）")

    # --- canonical
    canon = p.link_rel("canonical")
    if not canon:
        add("bad", "CANONICAL_MISSING", "沒有 rel=canonical，同一頁被多個網址索引時權重會被拆散")
    elif base and not canon.startswith(("http://", "https://")):
        add("warn", "CANONICAL_RELATIVE", f"canonical 用相對路徑（{canon}），建議寫完整網址")

    # --- Open Graph / Twitter
    og_needed = ["og:title", "og:description", "og:image", "og:url", "og:type"]
    og_missing = [k for k in og_needed if not p.meta_by_prop(k)]
    if len(og_missing) == len(og_needed):
        add("bad", "OG_MISSING", "完全沒有 Open Graph 標籤，分享到 FB / LINE 會沒有預覽圖")
    elif og_missing:
        add("warn", "OG_PARTIAL", f"Open Graph 缺：{', '.join(og_missing)}")
    if not p.meta_by_name("twitter:card") and not p.meta_by_prop("twitter:card"):
        add("warn", "TWITTER_MISSING", "沒有 twitter:card，X / 部分聊天軟體的預覽會退化成純連結")

    # --- 結構化資料
    ld_types = []
    for blob in p.ldjson:
        try:
            data = json.loads(blob)
        except Exception:
            add("bad", "LD_INVALID", "有 JSON-LD 但格式錯誤，Google 會整段忽略")
            continue
        for node in (data if isinstance(data, list) else [data]):
            if isinstance(node, dict):
                t = node.get("@type")
                if isinstance(t, list):
                    ld_types.extend(t)
                elif t:
                    ld_types.append(t)
    if not ld_types:
        add("bad", "LD_MISSING", "沒有 JSON-LD 結構化資料，拿不到搜尋結果的複合式摘要（活動日期、評分、FAQ）")

    # --- 標題階層
    h1s = [t for lv, t in p.headings if lv == 1]
    if len(h1s) == 0:
        add("bad", "H1_MISSING", "沒有 <h1>")
    elif len(h1s) > 1:
        add("warn", "H1_MULTI", f"有 {len(h1s)} 個 <h1>，主題會被稀釋")
    if not any(lv == 2 for lv, _ in p.headings):
        add("warn", "H2_MISSING", "沒有任何 <h2>，內容缺少可被抓取的段落結構")

    # --- 圖片 alt
    if p.imgs:
        def _is_pixel(i):
            return (i.get("width", "") in ("1", "1px") and i.get("height", "") in ("1", "1px")) \
                or "display:none" in i.get("style", "").replace(" ", "")
        real_imgs = [i for i in p.imgs if not _is_pixel(i)]
        no_alt = [i for i in real_imgs if not i.get("alt", "").strip()]
        if no_alt:
            srcs = ", ".join(os.path.basename(i.get("src", "?")) for i in no_alt[:4])
            add("warn", "IMG_ALT", f"{len(no_alt)}/{len(real_imgs)} 張圖沒有 alt 文字（{srcs}）")

    # --- 基本設定
    if not p.html_lang:
        add("warn", "LANG_MISSING", "<html> 沒有 lang 屬性，建議 lang=\"zh-TW\"")
    elif p.html_lang.lower() not in ("zh-tw", "zh-hant", "zh-hant-tw"):
        add("warn", "LANG_ODD", f"lang=\"{p.html_lang}\"，台灣繁中建議用 zh-TW")
    if not p.has_viewport:
        add("bad", "VIEWPORT_MISSING", "沒有 viewport，手機版排版會爆掉，行動裝置排名直接受罰")

    # --- 內容量
    body_len = vwidth(re.sub(r"\s+", "", p.body_text)) // 2
    if body_len < 300:
        add("warn", "THIN_CONTENT", f"正文只有約 {body_len} 字，內容太薄很難靠自然搜尋排上")

    # --- 內部連結
    internal = [a for a in p.anchors
                if a.get("href", "") and not a["href"].startswith(("http", "mailto:", "tel:", "#", "javascript:"))]
    if len(internal) < 3:
        add("warn", "INTERNAL_LINKS", f"內部連結只有 {len(internal)} 個，權重無法在站內流動")

    # --- 過期日期
    stale = find_stale_dates(title) + find_stale_dates(desc)
    if stale:
        uniq = sorted({s[0] for s in stale})
        add("bad", "STALE_DATE", f"title/description 出現已過期的日期：{', '.join(uniq)}")

    # --- 隨機網域
    if re.search(r"[a-z]+-[a-z]+-[0-9a-f]{6}\.netlify\.app", raw):
        add("warn", "RANDOM_DOMAIN", "頁面寫死 netlify 隨機網域，建議改綁自訂網域再全站替換")

    return {
        "file": str(path),
        "issues": issues,
        "facts": {
            "title": title,
            "desc": desc,
            "canonical": canon,
            "ld_types": ld_types,
            "h1": h1s[0] if h1s else "",
            "imgs": len(p.imgs),
            "words": body_len,
            "internal_links": len(internal),
        },
    }


def collect_html(target: Path, include_backups=False, exclude=None):
    exclude = [e for e in (exclude or []) if e]
    if target.is_file():
        return [target]
    files = sorted(target.glob("*.html")) + sorted(target.glob("**/*.html"))
    seen, out = set(), []
    for f in files:
        if f in seen:
            continue
        seen.add(f)
        # 比對整個相對路徑，不是只比對檔名——備份「資料夾」裡的整站複本
        # 也必須跳過，否則會被當成正式頁掃描並塞進 sitemap
        try:
            rel_path = f.relative_to(target if target.is_dir() else target.parent).as_posix()
        except ValueError:
            rel_path = f.name
        if not include_backups and any(h in rel_path for h in SKIP_NAME_HINTS):
            continue
        if any(e in f.as_posix() for e in exclude):
            continue
        if VERIFY_FILE_RE.match(f.name):
            continue
        try:
            if NOINDEX_RE.search(f.read_text(encoding="utf-8", errors="replace")):
                continue
        except OSError:
            pass
        out.append(f)
    return out


def scan_all(target: Path, base=None, include_backups=False, exclude=None):
    files = collect_html(target, include_backups, (exclude or "").split(","))
    titles, descs = {}, {}
    for f in files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        p = PageParser()
        try:
            p.feed(raw)
        except Exception:
            continue
        t = (p.title or "").strip()
        d = (p.meta_by_name("description") or "").strip()
        if t:
            titles[t] = titles.get(t, 0) + 1
        if d:
            descs[d] = descs.get(d, 0) + 1
    results = [check_page(f, base, titles, descs) for f in files]

    site_issues = []
    root = target if target.is_dir() else target.parent
    # 掃子目錄時，sitemap/robots 通常在站台根目錄，往上找兩層
    def _has(name):
        r = root
        for _ in range(3):
            if (r / name).exists():
                return True
            if r.parent == r:
                break
            r = r.parent
        return False
    if not _has("sitemap.xml"):
        site_issues.append(("bad", "NO_SITEMAP", "整站沒有 sitemap.xml，Google 只能靠爬連結慢慢發現頁面"))
    if not _has("robots.txt"):
        site_issues.append(("bad", "NO_ROBOTS", "整站沒有 robots.txt，也沒有指向 sitemap 的入口"))
    return results, site_issues


# ---------------------------------------------------------------- 輸出

def cmd_scan(args):
    target = Path(args.path).expanduser().resolve()
    results, site_issues = scan_all(target, args.base, args.all, args.exclude)
    nbad = nwarn = 0
    print(f"\n=== 小搜 SEO 掃描：{target} ===")
    if site_issues:
        print("\n[整站層級]")
        for lv, code, msg in site_issues:
            print(f"  {MARK_BAD if lv=='bad' else MARK_WARN} {code}  {msg}")
            nbad += lv == "bad"
            nwarn += lv == "warn"
    for r in results:
        name = os.path.basename(r["file"])
        bad = [i for i in r["issues"] if i[0] == "bad"]
        warn = [i for i in r["issues"] if i[0] == "warn"]
        nbad += len(bad)
        nwarn += len(warn)
        status = MARK_OK if not bad and not warn else (MARK_BAD if bad else MARK_WARN)
        print(f"\n{status} {name}  （{r['facts'].get('words',0)} 字 / {len(bad)} 必修 / {len(warn)} 建議）")
        for lv, code, msg in bad + warn:
            print(f"    {MARK_BAD if lv=='bad' else MARK_WARN} {code}  {msg}")
    print(f"\n--- 合計：{nbad} 項必修、{nwarn} 項建議，共掃 {len(results)} 頁 ---\n")
    return 0


def cmd_report(args):
    target = Path(args.path).expanduser().resolve()
    results, site_issues = scan_all(target, args.base, args.all, args.exclude)
    today = _dt.date.today().isoformat()
    L = []
    L.append(f"# SEO 健檢報告 — {target.name}\n")
    L.append(f"> 檢測日期：{today}　·　檢測員：小搜（Sixhands Studio AI 數字員工）\n")
    tb = sum(1 for r in results for i in r["issues"] if i[0] == "bad") + sum(1 for i in site_issues if i[0] == "bad")
    tw = sum(1 for r in results for i in r["issues"] if i[0] == "warn") + sum(1 for i in site_issues if i[0] == "warn")
    L.append(f"\n**總覽**：{len(results)} 頁／**{tb} 項必修**／{tw} 項建議\n")
    if site_issues:
        L.append("\n## 整站層級問題\n")
        for lv, code, msg in site_issues:
            L.append(f"- {'**必修**' if lv=='bad' else '建議'}　`{code}`　{msg}")
    L.append("\n## 逐頁明細\n")
    L.append("| 頁面 | 字數 | 必修 | 建議 | title |")
    L.append("|---|---:|---:|---:|---|")
    for r in results:
        b = sum(1 for i in r["issues"] if i[0] == "bad")
        w = sum(1 for i in r["issues"] if i[0] == "warn")
        t = (r["facts"].get("title") or "").replace("|", "／")
        L.append(f"| {os.path.basename(r['file'])} | {r['facts'].get('words',0)} | {b} | {w} | {t} |")
    for r in results:
        if not r["issues"]:
            continue
        L.append(f"\n### {os.path.basename(r['file'])}\n")
        for lv, code, msg in r["issues"]:
            L.append(f"- {'**必修**' if lv=='bad' else '建議'}　`{code}`　{msg}")
    out = Path(args.out).expanduser() if args.out else (target if target.is_dir() else target.parent) / "SEO健檢報告.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{MARK_OK} 報告已寫入：{out}")
    return 0


def cmd_sitemap(args):
    target = Path(args.path).expanduser()
    base = args.base.rstrip("/")
    files = collect_html(target, args.all, (args.exclude or "").split(","))
    root = target if target.is_dir() else target.parent
    out_dir = Path(args.out).expanduser() if args.out else root
    rows = []
    for f in files:
        rel = f.relative_to(root).as_posix()
        loc = f"{base}/" if rel == "index.html" else f"{base}/{rel}"
        mtime = _dt.date.fromtimestamp(f.stat().st_mtime).isoformat()
        prio = "1.0" if rel == "index.html" else ("0.9" if "workshop" in rel else "0.6")
        rows.append(f"  <url>\n    <loc>{html.escape(loc)}</loc>\n"
                    f"    <lastmod>{mtime}</lastmod>\n    <priority>{prio}</priority>\n  </url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(rows) + "\n</urlset>\n")
    (out_dir / "sitemap.xml").write_text(xml, encoding="utf-8")
    ai_bots = [
        # OpenAI
        "GPTBot", "OAI-SearchBot", "ChatGPT-User",
        # Anthropic
        "ClaudeBot", "Claude-User", "Claude-SearchBot", "anthropic-ai",
        # Perplexity
        "PerplexityBot", "Perplexity-User",
        # Google Gemini / AI Overviews 的接地內容
        "Google-Extended",
        # Apple Intelligence
        "Applebot-Extended",
        # Microsoft Copilot
        "Bingbot",
        # Common Crawl（多數開源模型的語料來源）
        "CCBot",
    ]
    ai_block = "\n".join(f"User-agent: {b}\nAllow: /\n" for b in ai_bots)
    robots = (f"User-agent: *\nAllow: /\n\n"
              f"# 別讓搜尋引擎索引備份檔\nDisallow: /*備份*\nDisallow: /*未採用*\n\n"
              f"# ---- 生成式搜尋引擎最佳化（GEO）----\n"
              f"# 明確允許主要 AI 爬蟲，讓內容有機會被 AI 助理引用。\n"
              f"# 取捨：允許 CCBot 與 Google-Extended 等於同意內容被用於訓練與接地；\n"
              f"# 若哪天不想被拿去訓練，把該行改成 Disallow: / 即可。\n"
              f"{ai_block}\n"
              f"Sitemap: {base}/sitemap.xml\n")
    (out_dir / "robots.txt").write_text(robots, encoding="utf-8")
    print(f"{MARK_OK} 已產生 {out_dir/'sitemap.xml'}（{len(rows)} 個網址）與 {out_dir/'robots.txt'}")
    return 0


SCHEMA_TEMPLATES = {
    "event": {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": "活動名稱",
        "description": "活動一句話描述",
        "startDate": "2026-01-01T13:30:00+08:00",
        "endDate": "2026-01-01T17:30:00+08:00",
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": {"@type": "Place", "name": "場地名稱",
                     "address": {"@type": "PostalAddress", "streetAddress": "街道",
                                 "addressLocality": "行政區", "addressRegion": "縣市",
                                 "addressCountry": "TW"}},
        "image": ["https://example.com/cover.jpg"],
        "offers": {"@type": "Offer", "price": "500", "priceCurrency": "TWD",
                   "availability": "https://schema.org/InStock",
                   "url": "https://example.com/報名頁", "validFrom": "2026-01-01"},
        "organizer": {"@type": "Organization", "name": "主辦單位", "url": "https://example.com"},
        "performer": {"@type": "Person", "name": "講師姓名"},
    },
    "organization": {
        "@context": "https://schema.org", "@type": "Organization",
        "name": "品牌名", "url": "https://example.com",
        "logo": "https://example.com/logo.png",
        "description": "品牌一句話描述",
        "sameAs": ["https://www.facebook.com/xxx", "https://www.youtube.com/@xxx"],
        "contactPoint": {"@type": "ContactPoint", "contactType": "customer service",
                         "areaServed": "TW", "availableLanguage": ["zh-TW"]},
    },
    "course": {
        "@context": "https://schema.org", "@type": "Course",
        "name": "課程名", "description": "課程描述",
        "provider": {"@type": "Organization", "name": "品牌名", "sameAs": "https://example.com"},
        "hasCourseInstance": {"@type": "CourseInstance", "courseMode": "onsite",
                              "courseWorkload": "PT4H",
                              "instructor": {"@type": "Person", "name": "講師"}},
        "offers": {"@type": "Offer", "price": "500", "priceCurrency": "TWD",
                   "category": "Paid", "url": "https://example.com"},
    },
    "faq": {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": "問題一？",
                        "acceptedAnswer": {"@type": "Answer", "text": "答案一。"}}],
    },
    "localbusiness": {
        "@context": "https://schema.org", "@type": "LocalBusiness",
        "name": "店名", "image": "https://example.com/store.jpg",
        "address": {"@type": "PostalAddress", "streetAddress": "街道",
                    "addressLocality": "行政區", "addressRegion": "縣市", "addressCountry": "TW"},
        "telephone": "+886-x-xxxxxxx",
        "openingHoursSpecification": [{"@type": "OpeningHoursSpecification",
                                       "dayOfWeek": ["Monday"], "opens": "11:00", "closes": "21:00"}],
        "priceRange": "$$",
    },
    "breadcrumb": {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "首頁", "item": "https://example.com/"},
            {"@type": "ListItem", "position": 2, "name": "第二層", "item": "https://example.com/x"},
        ],
    },
    "video": {
        "@context": "https://schema.org", "@type": "VideoObject",
        "name": "影片標題", "description": "影片描述",
        "thumbnailUrl": ["https://example.com/thumb.jpg"],
        "uploadDate": "2026-01-01T20:00:00+08:00", "duration": "PT8M30S",
        "embedUrl": "https://www.youtube.com/embed/VIDEO_ID",
    },
}


def cmd_schema(args):
    key = args.type.lower()
    if key not in SCHEMA_TEMPLATES:
        print(f"{MARK_BAD} 不認識的類型：{args.type}。可用：{', '.join(SCHEMA_TEMPLATES)}")
        return 1
    body = json.dumps(SCHEMA_TEMPLATES[key], ensure_ascii=False, indent=2)
    block = f'<script type="application/ld+json">\n{body}\n</script>'
    if args.out:
        Path(args.out).expanduser().write_text(block + "\n", encoding="utf-8")
        print(f"{MARK_OK} 已寫入 {args.out}")
    else:
        print(block)
    return 0


# ---------------------------------------------------------------- YouTube SEO

YT_TITLE_MAX = 60          # 顯示上限（半形寬），中文約 30 字
YT_TITLE_HARD = 100        # YouTube 硬上限（字元數）
YT_DESC_FOLD = 120         # 「顯示更多」摺疊前約可見的字元
YT_TAGS_MAX_CHARS = 500


def cmd_yt(args):
    title = args.title or ""
    desc = ""
    if args.desc:
        p = Path(args.desc).expanduser()
        desc = p.read_text(encoding="utf-8", errors="replace") if p.exists() else args.desc
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    bad, warn, ok = [], [], []

    if not title:
        bad.append("沒有標題")
    else:
        if len(title) > YT_TITLE_HARD:
            bad.append(f"標題 {len(title)} 字元，超過 YouTube 上限 {YT_TITLE_HARD}")
        w = vwidth(title)
        if w > YT_TITLE_MAX:
            warn.append(f"標題視覺寬度 {w}，手機版會截斷（建議 ≤{YT_TITLE_MAX}，約 30 個中文字）")
        else:
            ok.append(f"標題長度剛好（寬度 {w}）")
        if re.search(r"[0-9]", title):
            ok.append("標題含數字，點閱率通常較高")
        else:
            warn.append("標題沒有數字，考慮加入「3 個」「90 天」這類具體量詞")
        if any(k in title for k in ("？", "?", "為什麼", "怎麼", "如何", "竟然", "別再")):
            ok.append("標題有鉤子（提問／反常識）")
        else:
            warn.append("標題缺少鉤子，考慮改成提問句或反常識句")
        if title.count("|") + title.count("｜") > 2:
            warn.append("標題分隔線太多，關鍵字被切碎")

    if not desc.strip():
        bad.append("沒有描述，YouTube 只能靠標題理解影片主題")
    else:
        head = desc.strip()[:YT_DESC_FOLD]
        if len(desc.strip()) < 200:
            warn.append(f"描述只有 {len(desc.strip())} 字元，建議 300 字以上並自然帶入主關鍵字")
        else:
            ok.append(f"描述長度足夠（{len(desc.strip())} 字元）")
        if "http" not in head:
            warn.append("描述前 120 字元沒有連結，導流效率低（把報名／官網連結提到最前面）")
        else:
            ok.append("描述開頭就有連結，摺疊前可見")
        if not re.search(r"\d{1,2}:\d{2}", desc):
            warn.append("描述沒有時間戳章節（0:00 這種），影片抓不到 key moments")
        else:
            ok.append("有時間戳章節")
        if "#" not in desc:
            warn.append("描述沒有 hashtag，前 3 個會顯示在標題上方")

    if not tags:
        warn.append("沒有標籤；標籤權重雖低，但拼字變體與品牌詞仍值得填")
    else:
        total = sum(len(t) for t in tags) + len(tags) - 1
        if total > YT_TAGS_MAX_CHARS:
            bad.append(f"標籤總長 {total} 字元，超過 {YT_TAGS_MAX_CHARS} 上限")
        else:
            ok.append(f"標籤 {len(tags)} 個、共 {total} 字元")

    print("\n=== 小搜 · YouTube SEO 檢查 ===")
    for m in bad:
        print(f"  {MARK_BAD} {m}")
    for m in warn:
        print(f"  {MARK_WARN} {m}")
    for m in ok:
        print(f"  {MARK_OK} {m}")
    print(f"\n--- {len(bad)} 必修 / {len(warn)} 建議 ---\n")
    return 0


def main():
    ap = argparse.ArgumentParser(description="小搜 · SEO 檢查引擎")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="掃描頁面 / 資料夾")
    s.add_argument("path")
    s.add_argument("--base", default=None, help="網站正式網址")
    s.add_argument("--all", action="store_true", help="連備份檔一起掃")
    s.add_argument("--exclude", default="", help="逗號分隔的路徑片段，命中就不掃")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("report", help="產出 Markdown 健檢報告")
    s.add_argument("path")
    s.add_argument("--base", default=None)
    s.add_argument("--out", default=None)
    s.add_argument("--all", action="store_true")
    s.add_argument("--exclude", default="")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("sitemap", help="產生 sitemap.xml + robots.txt")
    s.add_argument("path")
    s.add_argument("--base", required=True)
    s.add_argument("--out", default=None)
    s.add_argument("--all", action="store_true")
    s.add_argument("--exclude", default="", help="逗號分隔的路徑片段，命中就不進 sitemap")
    s.set_defaults(func=cmd_sitemap)

    s = sub.add_parser("schema", help="產生 JSON-LD 樣板")
    s.add_argument("type", help="event / organization / course / faq / localbusiness / breadcrumb / video")
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_schema)

    s = sub.add_parser("yt", help="YouTube 影片 SEO 檢查")
    s.add_argument("--title", default="")
    s.add_argument("--desc", default="", help="描述文字或 .txt 檔路徑")
    s.add_argument("--tags", default="", help="逗號分隔")
    s.set_defaults(func=cmd_yt)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
