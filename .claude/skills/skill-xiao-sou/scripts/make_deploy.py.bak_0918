#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
只把「網站真的用到的檔案」打包成部署包。
不在正式頁面裡被引用的東西（工作檔、備份、未打碼照片）一律不上線。
"""
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import argparse
import tempfile

SRC = Path.home() / "Desktop" / "講座報名網站_上線用"
OUT = Path(tempfile.gettempdir()) / "xiaosou_deploy"

SKIP_HINTS = ("備份", "未採用", "backup", "_bak")

# 一定要上線的檔案（不靠引用分析）
ALWAYS = [
    "style.css", "sitemap.xml", "robots.txt",
    # 沒被頁面引用，但線上已存在且可能有外部連結（廣告／LINE）直接連，移掉會 404
    "AI-marketing-prompt-pack.pdf",
    "line_community_qr.png",          # LINE 社群 QR，可能被站外訊息連到
    "netlify.toml",
    "_redirects",                     # 舊網址 301 到新網域
    "llms.txt",                       # GEO：給 AI 助理的網站導覽
    # TikTok 網域驗證檔，移掉會讓開發者後台的網域驗證失效
    "tiktokR1gDmjnzjbtajYWGNB6RTM2T3jKU2Dw6.txt",
    "tiktokwwRtkp9kK47mXHSDctY46EVGKdkxlkeu.txt",
    # Google Search Console 擁有權驗證檔，驗證成功後也不能刪
    "googlea607dfaa45f4f6d8.html",
]

# 一定不准上線：含個資、金流、內部資訊
NEVER_PATTERNS = [
    r"line_welcome",          # 含銀行帳號與 PAYUNi 金流連結
    r"cert_demo\.jpg$",       # 未打碼，露學員本名
    r"instructor-tang\.jpg$", # 未打碼，露學員本名
    r"誤用備份",
    r"\.DS_Store",
]


def is_never(rel: str) -> bool:
    return any(re.search(p, rel) for p in NEVER_PATTERNS)


def pages():
    out = []
    for f in sorted(SRC.glob("*.html")):
        if any(h in f.name for h in SKIP_HINTS):
            continue
        out.append(f)
    for f in sorted(SRC.glob("*/*.html")):
        if any(h in f.name for h in SKIP_HINTS):
            continue
        out.append(f)
    return out


ASSET_RE = re.compile(r'(?:src|href|content|poster)\s*=\s*["\']([^"\']+)["\']', re.I)
CSS_URL_RE = re.compile(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', re.I)


def local_refs(text, base: Path):
    """挑出指向本地檔案的引用，回傳相對 SRC 的路徑字串。"""
    found = set()
    for m in list(ASSET_RE.finditer(text)) + list(CSS_URL_RE.finditer(text)):
        raw = m.group(1).strip()
        if not raw or raw.startswith(("http://", "https://", "//", "data:", "mailto:",
                                      "tel:", "#", "javascript:")):
            continue
        # meta content 多半是描述文字，不是路徑：沒有副檔名或帶空格的一律不算
        if " " in raw or not re.search(r"\.[A-Za-z0-9]{2,5}($|[?#])", raw):
            continue
        p = urlparse(raw).path
        if not p:
            continue
        target = (base.parent / unquote(p)).resolve()
        try:
            rel = target.relative_to(SRC.resolve())
        except ValueError:
            continue
        found.add(rel.as_posix())
    return found


def main(src=None, out=None, quiet=False):
    global SRC, OUT
    if src: SRC = Path(src).expanduser()
    if out: OUT = Path(out).expanduser()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    keep, skipped_never, missing = set(), [], []
    page_list = pages()

    for pg in page_list:
        keep.add(pg.relative_to(SRC).as_posix())
        keep |= local_refs(pg.read_text(encoding="utf-8", errors="replace"), pg)

    css = SRC / "style.css"
    if css.exists():
        keep |= local_refs(css.read_text(encoding="utf-8", errors="replace"), css)

    for a in ALWAYS:
        if (SRC / a).exists():
            keep.add(a)

    for rel in sorted(keep):
        if is_never(rel):
            skipped_never.append(rel)
            continue
        if any(h in rel for h in SKIP_HINTS):
            skipped_never.append(rel)
            continue
        s = SRC / rel
        if not s.exists():
            missing.append(rel)
            continue
        d = OUT / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)

    copied = sorted(p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())

    print(f"部署包：{OUT}")
    print(f"  頁面 {len(page_list)} 個 · 檔案 {len(copied)} 個 · {total/1024/1024:.1f} MB")
    if not quiet:
        print("\n== 會上線的檔案 ==")
        for c in copied:
            print(f"  {c}")
    if skipped_never and not quiet:
        print("\n== 擋下來、不上線 ==")
        for s in skipped_never:
            print(f"  {s}")
    if missing:
        print("\n== ⚠ 頁面引用了但檔案不存在（線上會 404）==")
        for m in missing:
            print(f"  {m}")

    # 沒被任何頁面引用、留在原資料夾的檔案（供人工確認）
    orphans = []
    for f in SRC.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(SRC).as_posix()
        if rel in keep or rel.startswith(".") or "/." in rel:
            continue
        orphans.append(rel)
    if orphans and not quiet:
        print(f"\n== 沒被引用、留在本機不上線（{len(orphans)} 個，抽樣）==")
        for o in sorted(orphans)[:25]:
            print(f"  {o}")
        if len(orphans) > 25:
            print(f"  …還有 {len(orphans)-25} 個")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="產生乾淨的部署包（只收正式頁面引用到的檔案）")
    ap.add_argument("--src", default=None, help="網站來源資料夾")
    ap.add_argument("--out", default=None, help="部署包輸出資料夾")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    main(a.src, a.out, a.quiet)
