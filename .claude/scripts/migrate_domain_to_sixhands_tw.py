#!/usr/bin/env python3
"""網域遷移：sixhands-studio.netlify.app → sixhands.tw

用法（從 repo 根目錄）：
    python3 .claude/scripts/migrate_domain_to_sixhands_tw.py

做的事：
  1. 全站（.claude/ 與 netlify.toml 以外）把舊主機名換成新主機名
     —— canonical、og:url、JSON-LD 的 url／@id／mainEntityOfPage、
        robots.txt、scripts/gen_sitemap.py、sitemap.xml、根目錄 .md
  2. netlify.toml 加上「只比對舊主機名」的 301 轉址（可重跑，不會重複加）
  3. 重跑 scripts/gen_sitemap.py，並要求它回報「零新增、零移除」
  4. 驗證，任何一項不過就以非零碼結束

為什麼 sitemap.xml 要先換主機名、再跑產生器：
  gen_sitemap.py 用「完整網址」比對既有條目來保留人工調過的 priority、
  changefreq 與排列順序。若只改它的 SITE 常數就重跑，所有舊網址會被判定為
  「移除」、新網址為「新增」——人工權重全部被預設值覆蓋、順序改成字母序，
  而且不會報錯。先把 sitemap.xml 裡的主機名換掉，既有條目就能對上新網址，
  產生器應回報零新增、零移除；不是零，代表網址對應有漏。
  （這與「不要手改 sitemap.xml」的規矩一致：那條規矩保護的正是人工權重。）

為什麼 netlify.toml 不參與取代：
  轉址規則的 from 必須是舊主機名。若讓取代步驟碰到它，重跑時 from 會被
  換成 sixhands.tw，變成 sixhands.tw → sixhands.tw 的無窮轉址。

轉址規則的範圍：
  只比對 `sixhands-studio.netlify.app` 這個主機名本身。
  不影響 sixhands.tw，也不影響 deploy-preview-N--sixhands-studio.netlify.app
  （預覽網址的主機名不同，不會被比對到）。
  force = true 是必要的：舊網域上每個路徑都有實體檔案，不加 force，
  Netlify 會直接回傳檔案而不轉址。
"""

import json
import re
import subprocess
import sys
import tomllib

OLD = "sixhands-studio.netlify.app"
NEW = "sixhands.tw"
NEW_ROOT = f"https://{NEW}/"

# 這些路徑不參與主機名取代
EXCLUDE_PREFIXES = (".claude/",)
EXCLUDE_FILES = {"netlify.toml"}

REDIRECT_MARK = "# 舊網域 → 新網域（2026-10 網域遷移）"
REDIRECT_BLOCK = f'''
{REDIRECT_MARK}
# 只比對舊主機名；不影響 {NEW} 本身與 deploy-preview-*--{OLD}
[[redirects]]
  from = "https://{OLD}/*"
  to = "https://{NEW}/:splat"
  status = 301
  force = true

[[redirects]]
  from = "http://{OLD}/*"
  to = "https://{NEW}/:splat"
  status = 301
  force = true
'''


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def site_html():
    """網站頁面（.claude/ 以外的 .html）。

    用 -z 與 core.quotepath=false：預設設定會把中文檔名加上引號並轉義，
    路徑就對不上實際檔案。
    """
    out = sh("git", "-c", "core.quotepath=false", "ls-files", "-z", "*.html")
    return [f for f in out.split("\0")
            if f and not f.startswith(EXCLUDE_PREFIXES)]


def files_with_old_host():
    try:
        out = sh("git", "-c", "core.quotepath=false", "grep", "-l", "-z", "-F", OLD)
    except subprocess.CalledProcessError:
        return []                     # git grep 找不到任何結果時回 1
    files = [f for f in out.split("\0") if f]
    return [f for f in files
            if not f.startswith(EXCLUDE_PREFIXES) and f not in EXCLUDE_FILES]


def count_canonicals():
    n, bad = 0, []
    for f in site_html():
        html = open(f, encoding="utf-8").read()
        for href in re.findall(r'rel="canonical"\s+href="([^"]+)"', html):
            n += 1
            if not href.startswith(NEW_ROOT):
                bad.append(f"{f}: {href}")
    return n, bad


def jsonld_errors():
    errs = []
    for f in site_html():
        html = open(f, encoding="utf-8").read()
        blocks = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.S)
        for i, b in enumerate(blocks):
            try:
                json.loads(b)
            except json.JSONDecodeError as e:
                errs.append(f"{f} 第 {i + 1} 段：{e}")
    return errs


def main():
    if sh("git", "rev-parse", "--is-shallow-repository").strip() == "true":
        sys.exit("這是淺層 clone，sitemap 的 lastmod 會取到錯誤日期。\n"
                 "請先執行 `git fetch --unshallow` 再重跑。")
    canon_before, _ = count_canonicals()

    # 1. 取代主機名
    targets = files_with_old_host()
    total = 0
    for f in targets:
        text = open(f, encoding="utf-8").read()
        n = text.count(OLD)
        open(f, "w", encoding="utf-8").write(text.replace(OLD, NEW))
        total += n
    print(f"① 主機名取代：{len(targets)} 個檔、{total} 處")

    # 2. 轉址規則
    toml_text = open("netlify.toml", encoding="utf-8").read()
    if REDIRECT_MARK in toml_text:
        print("② netlify.toml 轉址規則：已存在，略過")
    else:
        open("netlify.toml", "w", encoding="utf-8").write(
            toml_text.rstrip("\n") + "\n" + REDIRECT_BLOCK)
        print("② netlify.toml 轉址規則：已加入")

    # 3. 重跑 sitemap 產生器，必須零新增、零移除
    gen = subprocess.run([sys.executable, "scripts/gen_sitemap.py"],
                         capture_output=True, text=True)
    gen_out = gen.stdout + gen.stderr
    added = gen_out.count("+ 新增")
    dropped = gen_out.count("- 移除")
    print(f"③ sitemap 產生器：新增 {added}、移除 {dropped}")

    # 4. 驗證
    failures = []
    left = files_with_old_host()
    if left:
        failures.append(f"仍有舊主機名：{left}")
    if gen.returncode != 0:
        failures.append(f"gen_sitemap.py 失敗：{gen_out.strip()}")
    if added or dropped:
        failures.append(f"sitemap 條目對不上（新增 {added}、移除 {dropped}）：\n{gen_out}")

    canon_after, bad = count_canonicals()
    if canon_after != canon_before:
        failures.append(f"canonical 數量改變：{canon_before} → {canon_after}")
    if bad:
        failures.append("canonical 不在新網域：\n  " + "\n  ".join(bad))

    errs = jsonld_errors()
    if errs:
        failures.append("JSON-LD 解析失敗：\n  " + "\n  ".join(errs))

    try:
        conf = tomllib.load(open("netlify.toml", "rb"))
        froms = {r.get("from") for r in conf.get("redirects", [])}
        if f"https://{OLD}/*" not in froms:
            failures.append("netlify.toml 找不到 https 轉址規則")
        if any(r.get("from", "").startswith(f"https://{NEW}")
               for r in conf.get("redirects", [])):
            failures.append("netlify.toml 出現以新網域為來源的轉址（會造成迴圈）")
    except tomllib.TOMLDecodeError as e:
        failures.append(f"netlify.toml 語法錯誤：{e}")

    sm = open("sitemap.xml", encoding="utf-8").read()
    locs = re.findall(r"<loc>([^<]+)</loc>", sm)
    off = [u for u in locs if not u.startswith(NEW_ROOT)]
    if off:
        failures.append(f"sitemap 有 {len(off)} 筆不在新網域")

    robots = open("robots.txt", encoding="utf-8").read()
    if f"Sitemap: {NEW_ROOT}sitemap.xml" not in robots:
        failures.append("robots.txt 的 Sitemap 行沒有指向新網域")

    print(f"④ 驗證：canonical {canon_after} 個全在 {NEW}、"
          f"sitemap {len(locs)} 筆、JSON-LD 全部可解析")

    if failures:
        print("\n❌ 驗證未通過：")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\n✅ 全部通過")


if __name__ == "__main__":
    main()
