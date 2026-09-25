#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lecture_pages.py — 把 YouTube 影片的配音稿變成網站上的「精讀筆記頁」

為什麼要做：Google AI Overviews 的引用有近三成來自 YouTube，而 AI 讀的是
**文字不是影片**。影片的逐字稿放在自己的網域上，等於把原本只存在 YouTube
的內容，變成自己網站可被索引、可被 AI 引用的資產。

頁面不是把逐字稿倒上去而已，每頁包含：
  影片嵌入 → 這集在講什麼 → 分段全文 → 延伸行動
並掛 Article + VideoObject + BreadcrumbList 三種結構化資料。

用法：
  python3 lecture_pages.py build --map ep_video_map.json --scripts <配音稿目錄> \\
      --site <網站根> --base https://example.com [--limit N]
"""

import argparse
import html as _html
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BRAND = "Sixhands Studio AI數字員工"
BRAND_SHORT = "Sixhands Studio"

# ── 追蹤碼（Meta Pixel + Google Tag Manager）──────────────────────────
# 🚨 2026-09-09：追蹤碼一定要寫在模板裡。
#    之前是產完頁面再手動插，結果 blog 重新產生一次就被整段洗掉、而且沒有任何警告。
#    改成常數後，每次產生的頁面都自帶追蹤碼。
PIXEL_ID = "［待填：Pixel ID］"
GTM_ID = "GTM-5D6Z25BQ"

_GTM_HEAD_TPL = """  <!-- Google Tag Manager -->
  <script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
  new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
  j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
  'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
  })(window,document,'script','dataLayer','__GTM_ID__');</script>
  <!-- End Google Tag Manager -->"""

_GTM_BODY_TPL = """  <!-- Google Tag Manager (noscript) -->
  <noscript><iframe src="https://www.googletagmanager.com/ns.html?id=__GTM_ID__"
  height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
  <!-- End Google Tag Manager (noscript) -->"""

_PIXEL_TPL = """  <!-- Meta Pixel Code -->
  <script>
  !function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
  n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
  n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
  t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,
  document,'script','https://connect.facebook.net/en_US/fbevents.js');
  fbq('init', '__PIXEL_ID__');
  fbq('track', 'PageView');
  </script>
  <noscript><img height="1" width="1" style="display:none"
  src="https://www.facebook.com/tr?id=__PIXEL_ID__&ev=PageView&noscript=1"/></noscript>
  <!-- End Meta Pixel Code -->"""

GTM_HEAD = _GTM_HEAD_TPL.replace("__GTM_ID__", GTM_ID)
GTM_BODY = _GTM_BODY_TPL.replace("__GTM_ID__", GTM_ID)
META_PIXEL = _PIXEL_TPL.replace("__PIXEL_ID__", PIXEL_ID)
# ─────────────────────────────────────────────────────────────────────
DIR = "books"


# ------------------------------------------------------------------ 解析配音稿

def parse_script(path: Path):
    """回傳 {ep, book, subtitle, blocks[]}。配音稿用 /// 分段。"""
    raw = path.read_text(encoding="utf-8")
    ep = book = subtitle = ""
    m = re.search(r"EP\.?\s*(\d+)", raw[:200])
    if m:
        ep = f"EP{int(m.group(1)):02d}"
    m = re.search(r"《(.+?)》", raw[:400])
    if m:
        book = m.group(1)
    m = re.search(r"^>\s*(.+)$", raw[:600], re.M)
    if m:
        subtitle = m.group(1).strip()

    # 砍掉檔頭（第一個 --- 之前）
    body = raw
    cut = raw.find("\n---")
    if 0 < cut < 600:
        body = raw[cut + 4:]

    blocks = []
    for chunk in re.split(r"\n\s*///\s*\n", body):
        paras = [p.strip() for p in chunk.strip().split("\n") if p.strip()]
        paras = [p for p in paras if not re.match(r"^#{1,6}\s", p) and p != "---"]
        if paras:
            blocks.append(paras)
    return {"ep": ep, "book": book, "subtitle": subtitle, "blocks": blocks}


def inline(s):
    s = _html.escape(s, quote=False)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def plain(s):
    return re.sub(r"[*_`#>]", "", s).strip()


# ------------------------------------------------------------------ 版型

CSS = """<style>
  .lec{max-width:780px;margin:0 auto;padding:120px 22px 40px}
  .crumb{font-size:13px;color:var(--text-muted);margin-bottom:16px}
  .crumb a{color:var(--text-sub);text-decoration:none}
  .crumb a:hover{text-decoration:underline}
  .lec h1{font-size:clamp(26px,4.6vw,38px);line-height:1.32;margin:0 0 12px;text-wrap:balance}
  .lec .sub{font-size:17px;color:var(--text-sub);margin:0 0 8px}
  .lec .meta{font-size:14px;color:var(--text-muted);padding-bottom:22px;
    border-bottom:1px solid var(--green-border);margin-bottom:26px}
  .video{position:relative;padding-top:56.25%;border-radius:12px;overflow:hidden;
    background:#000;margin:0 0 28px}
  .video iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
  .kicker{font-size:12px;letter-spacing:.14em;text-transform:uppercase;
    color:var(--green);margin:36px 0 8px;font-weight:700}
  .lead-box{background:var(--green-light);border:1px solid var(--green-border);
    border-radius:12px;padding:20px 24px;margin:0 0 30px}
  .lead-box p{margin:0 0 10px;line-height:1.9}
  .lead-box p:last-child{margin:0}
  .body{font-size:17px;line-height:2.0}
  .body section{padding:22px 0;border-bottom:1px solid var(--green-border)}
  .body section:last-child{border-bottom:none}
  .body p{margin:0 0 16px}
  .body p:last-child{margin:0}
  .body .n{font-family:ui-monospace,monospace;font-size:12px;color:var(--text-muted);
    display:block;margin-bottom:10px;letter-spacing:.06em}
  .note{border-left:3px solid var(--green);background:var(--green-light);
    padding:14px 18px;border-radius:0 10px 10px 0;margin:26px 0;
    font-size:14.5px;color:var(--text-sub)}
  .lec-cta{margin:44px 0 0;border:1px solid var(--green-border);border-radius:14px;
    padding:30px 26px;background:var(--green-light);text-align:center}
  .lec-cta h2{font-size:22px;margin:0 0 10px}
  .lec-cta p{color:var(--text-sub);margin:0 auto 18px;max-width:46ch}
  .lec-cta a{display:inline-block;background:var(--green);color:#fff;font-weight:800;
    padding:13px 30px;border-radius:999px;text-decoration:none}
  .more{margin:40px 0 0;padding-top:22px;border-top:1px solid var(--green-border)}
  .more h2{font-size:14px;letter-spacing:.06em;text-transform:uppercase;
    color:var(--text-muted);margin:0 0 12px}
  .more ul{list-style:none;padding:0;margin:0}
  .more li{margin-bottom:8px}
  .more a{color:var(--text-sub);text-decoration:none}
  .more a:hover{color:var(--green);text-decoration:underline}
  .idx{max-width:900px;margin:0 auto;padding:120px 22px 40px}
  .idx-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px;margin-top:30px}
  .idx-card{display:block;border:1px solid var(--green-border);border-radius:12px;
    padding:18px 20px;text-decoration:none;color:inherit;transition:border-color .2s}
  .idx-card:hover{border-color:var(--green)}
  .idx-card .e{font-family:ui-monospace,monospace;font-size:12px;color:var(--green);font-weight:700}
  .idx-card h2{font-size:17px;margin:6px 0 6px;line-height:1.45}
  .idx-card p{font-size:13.5px;color:var(--text-muted);margin:0;line-height:1.7}
</style>"""


def nav(active=""):
    return f"""<nav class="navbar">
  <a href="../index.html" class="navbar-logo-dark">
    <span class="emoji">🦞</span><span class="grad-text">AI Employee</span>
  </a>
  <button class="hamburger" onclick="toggleMenu()" aria-label="選單">
    <span></span><span></span><span></span>
  </button>
  <ul class="navbar-links" id="navMenu">
    <li><a href="../index.html">首頁</a></li>
    <li><a href="../about.html">關於我</a></li>
    <li><a href="../courses.html">課程</a></li>
    <li><a href="../blog/index.html">部落格</a></li>
    <li><a href="index.html"{' class="active"' if active=='books' else ''}>書籍精讀</a></li>
    <li><a href="../workshop.html" class="navbar-cta">講座報名</a></li>
  </ul>
</nav>"""


FOOTER = """<footer>
  <div class="footer-inner">
    <div class="footer-brand">
      <div class="brand-logo-wrap" style="display:inline-flex; margin-bottom:12px;"><span class="emoji" style="font-size:20px;">🦞</span><span class="brand-logo-text" style="font-size:20px;">AI Employee</span></div>
      <p>台灣最實戰的 AI 數字員工培訓品牌。幫每一位企業主打造自己的 AI 員工團隊。</p>
    </div>
    <div class="footer-links">
      <h4>頁面</h4>
      <ul>
        <li><a href="../index.html">首頁</a></li>
        <li><a href="../workshop.html">實體講座</a></li>
        <li><a href="../courses.html">課程介紹</a></li>
        <li><a href="../blog/index.html">部落格</a></li>
        <li><a href="index.html">書籍精讀</a></li>
        <li><a href="../works-grid.html">作品集</a></li>
      </ul>
    </div>
    <div class="footer-links">
      <h4>聯絡</h4>
      <ul>
        <li><a href="https://sixhands-studio.netlify.app/bio-links.html" target="_blank" rel="noopener">所有連結</a></li>
        <li><a href="../contact.html">聯絡我們</a></li>
      </ul>
    </div>
  </div>
  <div class="footer-bottom">
    <span>© 2026 Sixhands Studio</span>
    <span><a href="/refund.html">退費政策</a>　由 AI 數字員工協助維護 🦞</span>
  </div>
</footer>
<script>function toggleMenu(){document.getElementById('navMenu').classList.toggle('open');}</script>"""


def shell(title, desc, canonical, og_img, lds, body, active=""):
    blocks = "\n".join(
        '<script type="application/ld+json">\n'
        + json.dumps(x, ensure_ascii=False, indent=2) + "\n</script>" for x in lds)
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
{GTM_HEAD}
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_html.escape(title)}</title>
  <meta name="description" content="{_html.escape(desc)}">
  <link rel="stylesheet" href="../style.css">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🦞</text></svg>">
  <!-- SEO:小搜 -->
  <link rel="canonical" href="{canonical}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="{BRAND}">
  <meta property="og:locale" content="zh_TW">
  <meta property="og:title" content="{_html.escape(title)}">
  <meta property="og:description" content="{_html.escape(desc)}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:image" content="{og_img}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_html.escape(title)}">
  <meta name="twitter:description" content="{_html.escape(desc)}">
  <meta name="twitter:image" content="{og_img}">
{blocks}
{CSS}
{META_PIXEL}
</head>
<body>
{GTM_BODY}
{nav(active)}
{body}
{FOOTER}
</body>
</html>
"""


# ------------------------------------------------------------------ 產生單頁

def build_page(item, script, site: Path, base: str, others):
    b = base.rstrip("/")
    ep, book = item["ep"], item["book"]
    vid = item["video"]
    slug = ep.lower()
    canonical = f"{b}/{DIR}/{slug}.html"
    thumb = f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"

    blocks = script["blocks"]
    lead = blocks[0] if blocks else []
    rest = blocks[1:] if len(blocks) > 1 else []

    # description 目標 60-80 個中文字：串接開頭幾句，短了搜尋結果會顯得沒資訊
    buf = f"《{book}》精讀影片的完整文字版。"
    for para in lead:
        t = plain(para)
        if not t:
            continue
        if len(buf) + len(t) > 78:
            room = 78 - len(buf)
            if room > 12:
                buf += t[:room]
            break
        buf += t
    desc = buf.strip()

    lead_html = "".join(f"<p>{inline(p)}</p>" for p in lead)
    body_sections = []
    for i, blk in enumerate(rest, 1):
        ps = "".join(f"<p>{inline(p)}</p>" for p in blk)
        body_sections.append(f'<section><span class="n">— {i:02d} —</span>{ps}</section>')

    more = "".join(
        f'<li><a href="{o["ep"].lower()}.html">《{o["book"]}》精讀</a></li>'
        for o in others[:6])

    words = sum(len(plain(p)) for blk in blocks for p in blk)

    article_ld = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": f"《{book}》精讀重點與完整逐字稿"[:110],
        "description": desc, "image": [thumb],
        "datePublished": item.get("date") or date.today().isoformat(),
        "dateModified": date.today().isoformat(),
        "inLanguage": "zh-TW", "wordCount": words,
        "author": {"@type": "Person", "name": "助哥"},
        "publisher": {"@type": "Organization", "name": BRAND, "url": b + "/"},
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "about": {"@type": "Book", "name": book},
    }
    video_ld = {
        "@context": "https://schema.org", "@type": "VideoObject",
        "name": item.get("yt_title") or f"《{book}》精讀",
        "description": desc, "thumbnailUrl": [thumb],
        "uploadDate": (item.get("date") or date.today().isoformat()) + "T20:00:00+08:00",
        "embedUrl": f"https://www.youtube.com/embed/{vid}",
        "contentUrl": f"https://www.youtube.com/watch?v={vid}",
        "inLanguage": "zh-TW",
        "publisher": {"@type": "Organization", "name": BRAND, "url": b + "/"},
        "transcript": " ".join(plain(p) for blk in blocks for p in blk)[:4000],
    }
    crumb_ld = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "首頁", "item": b + "/"},
            {"@type": "ListItem", "position": 2, "name": "書籍精讀", "item": f"{b}/{DIR}/"},
            {"@type": "ListItem", "position": 3, "name": f"《{book}》", "item": canonical},
        ],
    }

    sub = f'<p class="sub">{inline(script["subtitle"])}</p>' if script["subtitle"] else ""
    body = f"""
<article class="lec">
  <div class="crumb"><a href="../index.html">首頁</a> ／ <a href="index.html">書籍精讀</a></div>
  <h1>《{_html.escape(book)}》精讀重點與完整逐字稿</h1>
  {sub}
  <div class="meta">{ep}　·　助哥　·　約 {words:,} 字　·　{item.get('date','')}</div>

  <div class="video">
    <iframe src="https://www.youtube-nocookie.com/embed/{vid}" title="《{_html.escape(book)}》精讀"
      loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; picture-in-picture"
      allowfullscreen></iframe>
  </div>

  <div class="kicker">這集在講什麼</div>
  <div class="lead-box">{lead_html}</div>

  <div class="kicker">完整內容</div>
  <div class="body">
{chr(10).join(body_sections)}
  </div>

  <div class="note">
    這是影片《{_html.escape(book)}》精讀的文字版，內容與影片旁白一致，方便閱讀、搜尋與引用。
    書中觀點屬原作者，解讀與延伸為助哥個人看法。
  </div>

  <section class="lec-cta">
    <h2>把書裡的方法，變成公司裡真的在跑的流程</h2>
    <p>4 小時實體講座，助哥在大螢幕上用 AI 實際做給你看。台北・台中・台南每月開課。</p>
    <a href="../workshop.html">看講座場次與報名 →</a>
  </section>

  <nav class="more"><h2>其他精讀</h2><ul>{more}</ul></nav>
</article>
"""
    out = site / DIR
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{slug}.html").write_text(
        shell(f"《{book}》精讀重點與完整逐字稿｜{BRAND_SHORT}", desc, canonical, thumb,
              [article_ld, video_ld, crumb_ld], body, "books"),
        encoding="utf-8")
    return {"ep": ep, "book": book, "slug": slug, "desc": desc,
            "words": words, "date": item.get("date", "")}


def build_index(site: Path, base: str, pages):
    b = base.rstrip("/")
    canonical = f"{b}/{DIR}/"
    cards = "".join(
        f'<a class="idx-card" href="{p["slug"]}.html">'
        f'<div class="e">{p["ep"]}</div><h2>《{_html.escape(p["book"])}》</h2>'
        f'<p>約 {p["words"]:,} 字</p></a>' for p in pages)
    ld = [{
        "@context": "https://schema.org", "@type": "CollectionPage",
        "name": "書籍精讀｜貓咪經濟學", "url": canonical, "inLanguage": "zh-TW",
        "description": f"貓咪經濟學 YouTube 頻道 {len(pages)} 集書籍精讀的完整文字版，"
                       f"每篇含影片、重點與逐字稿。",
        "isPartOf": {"@type": "WebSite", "name": BRAND, "url": b + "/"},
    }, {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "首頁", "item": b + "/"},
            {"@type": "ListItem", "position": 2, "name": "書籍精讀", "item": canonical},
        ],
    }]
    body = f"""
<div class="idx">
  <div class="crumb"><a href="../index.html">首頁</a> ／ 書籍精讀</div>
  <h1 class="lec-title" style="font-size:clamp(26px,4.6vw,38px);margin:0 0 12px;">書籍精讀</h1>
  <p style="font-size:17px;color:var(--text-sub);max-width:62ch;line-height:1.9;margin:0 0 16px;">
    貓咪經濟學頻道每一集的完整文字版：影片講什麼，這裡就寫什麼。
    講給要做決定的人聽——每本書只留能拿去用的部分。目前 {len(pages)} 本。
  </p>
  <p style="font-size:16px;color:var(--text-sub);max-width:62ch;line-height:1.9;margin:0 0 10px;">
    每一頁都有三段：影片可以直接看、「這集在講什麼」是三十秒版本、
    再來才是完整內容。想快速判斷這本值不值得花時間，看前兩段就夠。
  </p>
  <p style="font-size:16px;color:var(--text-sub);max-width:62ch;line-height:1.9;margin:0;">
    這些書大多不是新書，但選的角度都一樣：<strong>老闆看完能不能拿去用</strong>。
    理論的部分會講，但重點放在「這件事在你的生意裡長什麼樣」。
    書中觀點屬原作者，解讀與延伸是助哥的個人看法。
  </p>
  <div class="idx-grid">{cards}</div>
</div>
"""
    out = site / DIR
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(
        shell(f"書籍精讀｜{len(pages)} 本商業書的重點與逐字稿｜{BRAND_SHORT}",
              f"貓咪經濟學頻道 {len(pages)} 集書籍精讀的完整文字版，"
              f"每篇含影片、這集在講什麼與逐字稿全文。講給要做決定的老闆聽。",
              canonical, f"{b}/photos/qiqi-view.jpg", ld, body, "books"),
        encoding="utf-8")
    return len(pages)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build")
    s.add_argument("--map", required=True)
    s.add_argument("--scripts", required=True)
    s.add_argument("--site", required=True)
    s.add_argument("--base", required=True)
    s.add_argument("--limit", type=int, default=0, help="只產前 N 篇（分批上線用）")
    args = ap.parse_args()

    items = [x for x in json.load(open(args.map, encoding="utf-8")) if x.get("video")]
    items.sort(key=lambda x: x["ep"])
    if args.limit:
        items = items[:args.limit]
    sdir = Path(args.scripts).expanduser()
    site = Path(args.site).expanduser()

    pages, skipped = [], []
    for it in items:
        f = sdir / it["file"]
        if not f.exists():
            skipped.append(it["file"]); continue
        sc = parse_script(f)
        if not sc["blocks"] or sum(len(plain(p)) for b in sc["blocks"] for p in b) < 800:
            skipped.append(f"{it['ep']}（內容太短）"); continue
        # 對照表的書名可能帶「（上）／（下）」，那是配音稿內文沒有的資訊，
        # 不能被內文解析出來的書名蓋掉，否則上下集會產生重複 title
        if re.search(r"（[上下]）", it.get("book", "")):
            sc["book"] = it["book"]
        else:
            sc["book"] = sc["book"] or it["book"]
            it["book"] = sc["book"]
        others = [x for x in items if x["ep"] != it["ep"]]
        pages.append(build_page(it, sc, site, args.base, others))
    pages.sort(key=lambda p: p["ep"])
    n = build_index(site, args.base, pages)
    print(f"[v] 產出 {len(pages)} 頁精讀 + index（{DIR}/）")
    if skipped:
        print(f"[!] 略過 {len(skipped)} 篇：{', '.join(skipped[:6])}")
    tot = sum(p["words"] for p in pages)
    print(f"    總字數約 {tot:,}")


if __name__ == "__main__":
    main()
