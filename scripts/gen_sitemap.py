#!/usr/bin/env python3
"""產生 sitemap.xml。

掃描 repo 內所有 HTML 頁面，排除宣告 noindex 的，依 git 最後一次異動日期
填入 lastmod，輸出 sitemap.xml。

設計原則：
- 既有條目的 priority / changefreq 一律沿用原值，不覆寫人工調過的權重。
- 既有條目的排列順序保持不變，新頁面追加在最後，讓 diff 只顯示真正的變動。
- 只依賴標準庫與 git，沒有外部套件。

用法：從 repo 根目錄執行 `python3 scripts/gen_sitemap.py`。
"""

import os
import re
import subprocess
import sys
import urllib.parse
from datetime import date

SITE = "https://sixhands-studio.netlify.app/"
SITEMAP = "sitemap.xml"

# 不掃描的目錄
SKIP_DIRS = {".git", ".github", "scripts", "node_modules", "assets"}

# 新頁面的預設值；既有頁面不套用這裡，一律沿用原本的設定
DEFAULTS = [
    # (判斷函式, priority, changefreq)
    (lambda p: p == "index.html", "1.0", "weekly"),
    (lambda p: p == "blog/index.html", "0.8", "weekly"),
    (lambda p: p.startswith("blog/"), "0.7", "monthly"),
    (lambda p: True, "0.5", "monthly"),
]

NOINDEX_RE = re.compile(
    r"""<meta\s+name=["']robots["']\s+content=["'][^"']*noindex""",
    re.IGNORECASE,
)
URL_BLOCK_RE = re.compile(r"<url>.*?</url>", re.DOTALL)


def tag(block, name):
    """從一個 <url> 區塊取出某個標籤的值，沒有就回傳 None。"""
    m = re.search(rf"<{name}>(.*?)</{name}>", block)
    return m.group(1) if m else None


def read_existing(path):
    """讀取現行 sitemap，回傳 (順序清單, {loc: {priority, changefreq}})。"""
    if not os.path.exists(path):
        return [], {}
    text = open(path, encoding="utf-8").read()
    order, meta = [], {}
    for block in URL_BLOCK_RE.findall(text):
        loc = tag(block, "loc")
        if not loc:
            continue
        order.append(loc)
        meta[loc] = {
            "priority": tag(block, "priority"),
            "changefreq": tag(block, "changefreq"),
        }
    return order, meta


def find_pages(root="."):
    """找出所有該收錄的 HTML 檔（相對路徑），排除 noindex。"""
    pages = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if not fn.endswith(".html"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                content = open(full, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError) as e:
                print(f"  ! 讀取失敗，跳過：{rel}（{e}）", file=sys.stderr)
                continue
            if NOINDEX_RE.search(content):
                print(f"  - 排除（noindex）：{rel}")
                continue
            pages.append(rel)
    return sorted(pages)


def to_url(rel):
    """相對路徑 → 完整網址。目錄索引頁收斂成目錄形式。"""
    if rel == "index.html":
        path = ""
    elif rel.endswith("/index.html"):
        path = rel[: -len("index.html")]
    else:
        path = rel
    return SITE + urllib.parse.quote(path, safe="/")


def git_date(rel):
    """該檔案最後一次被 commit 的日期；沒有紀錄就用今天。"""
    out = subprocess.run(
        ["git", "log", "-1", "--format=%ad", "--date=short", "--", rel],
        capture_output=True,
        text=True,
    ).stdout.strip()
    return out or date.today().isoformat()


def defaults_for(rel):
    for matches, priority, changefreq in DEFAULTS:
        if matches(rel):
            return priority, changefreq
    return "0.5", "monthly"


def main():
    order, meta = read_existing(SITEMAP)
    pages = find_pages()

    # 網址 → 檔案路徑
    url_to_page = {to_url(rel): rel for rel in pages}

    # 既有順序優先（只留還存在的），新網址追加在後
    known = [u for u in order if u in url_to_page]
    new = sorted(u for u in url_to_page if u not in set(order))
    if new:
        for u in new:
            print(f"  + 新增：{u}")
    dropped = [u for u in order if u not in url_to_page]
    for u in dropped:
        print(f"  - 移除（檔案不存在或已設 noindex）：{u}")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in known + new:
        rel = url_to_page[url]
        lastmod = git_date(rel)
        existing = meta.get(url) or {}
        priority = existing.get("priority")
        changefreq = existing.get("changefreq")
        if url not in meta:
            priority, changefreq = defaults_for(rel)

        entry = f"  <url><loc>{url}</loc><lastmod>{lastmod}</lastmod>"
        if priority:
            entry += f"<priority>{priority}</priority>"
        if changefreq:
            entry += f"<changefreq>{changefreq}</changefreq>"
        lines.append(entry + "</url>")
    lines.append("</urlset>")

    output = "\n".join(lines) + "\n"
    before = open(SITEMAP, encoding="utf-8").read() if os.path.exists(SITEMAP) else ""
    if output == before:
        print(f"sitemap.xml 無變動（{len(known) + len(new)} 筆）")
        return
    open(SITEMAP, "w", encoding="utf-8").write(output)
    print(f"sitemap.xml 已更新：{len(known) + len(new)} 筆")


if __name__ == "__main__":
    main()
