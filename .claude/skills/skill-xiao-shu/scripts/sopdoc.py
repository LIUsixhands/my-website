#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小書 · 作業說明書產線 (sopdoc.py)
Sixhands Studio AI數字員工

  init  --dir 專案 --title 標題 [--owner 維護人]   建立專案結構
  scan  --dir 專案 [--order name|mtime]            掃圖檔、編號、產草稿骨架
  check --dir 專案                                 交付前七項自檢
  build --dir 專案 [--version 1.0]                 出 HTML + PDF（逐頁掛 logo）

專案一律建在本機碟（~/ 底下），不要放 iCloud 桌面。
"""
import argparse, json, os, re, shutil, subprocess, sys, datetime, html as htmllib

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, "references", "config.json")
LOGO_PATH = os.path.join(SKILL_DIR, "assets", "logo.png")
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".heic", ".gif", ".bmp", ".tif", ".tiff")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def meta_path(d):
    return os.path.join(d, "meta.json")


def read_meta(d):
    p = meta_path(d)
    if not os.path.exists(p):
        sys.exit(f"✗ 找不到 {p}，先跑 init")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_meta(d, meta):
    with open(meta_path(d), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


# ────────────────────────────── init ──────────────────────────────
def cmd_init(a):
    d = os.path.abspath(os.path.expanduser(a.dir))
    if "/Desktop/" in d or d.endswith("/Desktop"):
        print("⚠️  警告：這是 iCloud 桌面路徑，讀圖可能間歇性失敗（EPERM / Errno 60）。建議改建在 ~/ 底下。")
    for sub in ("圖檔", "圖檔_已編號", "輸出", "輸出/舊版"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    cfg = load_config()
    meta = {
        "標題": a.title,
        "維護人": a.owner or "待確認",
        "適用對象": a.audience or "待確認",
        "版本": cfg["說明書"]["起始版本"],
        "建立日": datetime.date.today().isoformat(),
        "更新日": datetime.date.today().isoformat(),
        "步驟數": 0,
    }
    write_meta(d, meta)
    print(f"✓ 專案建好：{d}")
    print("  下一步：把過程圖檔丟進  圖檔/  然後跑 scan")


# ────────────────────────────── scan ──────────────────────────────
def img_info(p):
    try:
        from PIL import Image
        with Image.open(p) as im:
            return im.size
    except Exception:
        return (0, 0)


def cmd_scan(a):
    d = os.path.abspath(os.path.expanduser(a.dir))
    meta = read_meta(d)
    cfg = load_config()
    src = os.path.join(d, "圖檔")
    dst = os.path.join(d, "圖檔_已編號")
    files = [f for f in os.listdir(src) if f.lower().endswith(IMG_EXT) and not f.startswith(".")]
    if not files:
        sys.exit(f"✗ {src} 裡沒有圖檔")
    if a.order == "mtime":
        files.sort(key=lambda f: os.path.getmtime(os.path.join(src, f)))
    else:
        files.sort(key=natural_key)

    os.makedirs(dst, exist_ok=True)
    minw = cfg["說明書"]["圖片最小寬度"]
    rows, warn = [], []
    for i, f in enumerate(files, 1):
        base = re.sub(r"[^\w一-鿿.-]", "_", f)
        new = f"step{i:02d}_{base}"
        shutil.copy2(os.path.join(src, f), os.path.join(dst, new))
        w, h = img_info(os.path.join(dst, new))
        flags = []
        if w and w < minw:
            flags.append(f"解析度偏低({w}px)")
        if re.search(r"(screenshot|截圖|螢幕快照|CleanShot)", f, re.I):
            flags.append("疑似螢幕截圖→查個資")
        rows.append({"step": i, "file": new, "orig": f, "size": f"{w}x{h}", "flags": flags})
        if flags:
            warn.append(rows[-1])

    meta["步驟數"] = len(rows)
    meta["更新日"] = datetime.date.today().isoformat()
    meta["圖檔"] = rows
    write_meta(d, meta)

    draft = os.path.join(d, "作業說明書_草稿.md")
    if os.path.exists(draft):
        bak = draft.replace(".md", f".bak{datetime.datetime.now().strftime('%H%M%S')}.md")
        shutil.copy2(draft, bak)
        print(f"  （已存在草稿，備份成 {os.path.basename(bak)}）")
    with open(draft, "w", encoding="utf-8") as f:
        f.write(build_skeleton(meta, rows))

    print(f"✓ 已編號 {len(rows)} 張圖 → 圖檔_已編號/")
    print(f"✓ 草稿骨架 → {draft}")
    if warn:
        print(f"\n⚠️  {len(warn)} 張圖要人工複查：")
        for r in warn:
            print(f"   step{r['step']:02d} {r['orig']} — {'、'.join(r['flags'])}")
    print("\n下一步：逐步填『動作／位置／判斷點／常見錯誤／耗時』，填完跑 check")


def build_skeleton(meta, rows):
    t = meta["標題"]
    out = [f"# {t}\n",
           f"> 版本 v{meta['版本']}　|　更新日 {meta['更新日']}　|　維護人 {meta['維護人']}　|　適用對象 {meta['適用對象']}\n",
           "## 1. 目的\n\nTODO：一段話說明為什麼有這份文件。\n",
           "## 2. 適用範圍\n\n- 適用：TODO\n- 不適用：TODO\n",
           "## 3. 事前準備\n\n- [ ] TODO：需要的帳號 / 權限\n- [ ] TODO：需要的檔案 / 資料\n",
           "## 4. 操作步驟\n"]
    for r in rows:
        out.append(f"""### 步驟 {r['step']}｜TODO 這步在做什麼

![圖 {r['step']}｜TODO 圖說](圖檔_已編號/{r['file']})

- **動作**：TODO（祈使句、動詞開頭）
- **位置**：TODO（畫面上哪裡）
- **判斷點**：看到 TODO 代表成功；看到 TODO 請跳到 §5
- **常見錯誤**：TODO
- **耗時**：TODO
""")
    out.append("""## 5. 例外處理

| 狀況 | 畫面長怎樣 | 怎麼辦 | 找誰 |
|:---|:---|:---|:---|
| TODO | TODO | TODO | TODO |

## 6. 驗收標準

做完以下全部成立才算完成：

- [ ] TODO
- [ ] TODO

## 7. 常見問題

（第二版以後補）

## 8. 名詞對照

| 系統用詞 | 白話 |
|:---|:---|
| TODO | TODO |

## 9. 變更紀錄

| 版本 | 日期 | 修改內容 | 原因 | 修改人 |
|:---|:---|:---|:---|:---|
| v{v} | {d} | 初版 | 建立文件 | 小書 |

## ❓ 待確認清單

- TODO：圖上看不出來、需要教練確認的事項寫這裡（不要自己填進步驟）
""".replace("{v}", meta["版本"]).replace("{d}", meta["更新日"]))
    return "\n".join(out)


# ────────────────────────────── check ──────────────────────────────
def find_doc(d):
    for name in ("作業說明書.md", "作業說明書_草稿.md"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    cands = [f for f in os.listdir(d) if f.endswith(".md") and not f.endswith(".bak.md")]
    if not cands:
        sys.exit("✗ 找不到 .md 說明書檔")
    return os.path.join(d, sorted(cands)[0])


def cmd_check(a):
    d = os.path.abspath(os.path.expanduser(a.dir))
    meta = read_meta(d)
    cfg = load_config()["說明書"]
    doc = find_doc(d)
    text = open(doc, encoding="utf-8").read()
    lines = text.splitlines()
    issues = {"🔴": [], "🟠": [], "🟡": []}

    # 1 TODO / 待補
    for i, ln in enumerate(lines, 1):
        marks = cfg["TODO標記"]
        if ln.lstrip().startswith("#") or "待確認清單" in ln:
            marks = [m for m in marks if m not in ("待確認", "待補")]
        if any(k in ln for k in marks):
            issues["🔴"].append(f"L{i} 未填：{ln.strip()[:60]}")
    # 2 圖片引用
    used = set(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text))
    used_base = {os.path.basename(u) for u in used}
    numbered = os.path.join(d, "圖檔_已編號")
    if os.path.isdir(numbered):
        for f in sorted(os.listdir(numbered)):
            if f.lower().endswith(IMG_EXT) and f not in used_base:
                issues["🟠"].append(f"圖沒被引用：{f}")
    for u in used_base:
        if os.path.isdir(numbered) and u not in os.listdir(numbered):
            issues["🔴"].append(f"引用了不存在的圖：{u}")
    # 3 步驟缺判斷點
    steps = re.split(r"^### ", text, flags=re.M)[1:]
    for s in steps:
        title = s.splitlines()[0][:40]
        if "判斷點" not in s:
            issues["🔴"].append(f"步驟缺判斷點：{title}")
        if "![" not in s:
            issues["🟠"].append(f"步驟沒有圖：{title}")
    # 4 模糊詞
    for i, ln in enumerate(lines, 1):
        for w in cfg["禁用模糊詞"]:
            if w in ln:
                issues["🟡"].append(f"L{i} 模糊詞「{w}」：{ln.strip()[:50]}")
                break
    # 5 驗收標準
    if "驗收標準" not in text:
        issues["🔴"].append("缺『驗收標準』章節")
    if "例外處理" not in text:
        issues["🟠"].append("缺『例外處理』章節")
    # 6 版本日期
    if "版本" not in text or "更新日" not in text:
        issues["🔴"].append("開頭缺版本／更新日")
    if "變更紀錄" not in text:
        issues["🟠"].append("缺『變更紀錄』章節")
    # 7 高風險圖
    for r in meta.get("圖檔", []):
        if r.get("flags"):
            issues["🟡"].append(f"圖需人工複查去識別化：{r['file']}（{'、'.join(r['flags'])}）")

    print(f"\n📘 自檢：{os.path.basename(doc)}　步驟 {len(steps)} 步　圖 {len(used_base)} 張\n")
    total = 0
    for lvl, name in (("🔴", "出稿前必修"), ("🟠", "強烈建議修"), ("🟡", "人工複查")):
        items = issues[lvl]
        total += len(items)
        print(f"{lvl} {name}（{len(items)}）")
        for it in items[:40]:
            print(f"   - {it}")
        if len(items) > 40:
            print(f"   …另外 {len(items)-40} 條")
        print()
    if not issues["🔴"]:
        print("✓ 沒有紅燈，可以 build 了。")
    else:
        print("✗ 有紅燈，先修完再 build。")
    return 0 if not issues["🔴"] else 1


# ────────────────────────────── build ──────────────────────────────
def md_to_html(md, base_dir, title):
    """支援：標題、表格、清單、勾選框、圖片、粗體、行內碼、引言、分隔線、段落。"""
    def inline(s):
        s = htmllib.escape(s)
        s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)",
                   lambda m: f'<figure><img src="{os.path.join(base_dir, m.group(2))}"><figcaption>{m.group(1)}</figcaption></figure>', s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        return s

    out, i, lines = [], 0, md.splitlines()
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        if ln.startswith("```"):
            i += 1; buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(htmllib.escape(lines[i])); i += 1
            i += 1
            out.append("<pre>" + "\n".join(buf) + "</pre>"); continue
        m = re.match(r"^(#{1,6})\s+(.*)", ln)
        if m:
            lv = len(m.group(1))
            out.append(f"<h{lv}>{inline(m.group(2))}</h{lv}>"); i += 1; continue
        if ln.startswith(">"):
            out.append(f"<blockquote>{inline(ln.lstrip('> '))}</blockquote>"); i += 1; continue
        if re.match(r"^(-{3,}|\*{3,})$", ln.strip()):
            out.append("<hr>"); i += 1; continue
        if ln.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i+1]):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2; body = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                body.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            t = ["<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"]
            for r in body:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t)); continue
        if re.match(r"^\s*[-*]\s+", ln):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                c = re.sub(r"^\s*[-*]\s+", "", lines[i])
                c = c.replace("[ ]", "☐").replace("[x]", "☑").replace("[X]", "☑")
                items.append(f"<li>{inline(c)}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>"); continue
        if re.match(r"^\s*\d+\.\s+", ln):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
                items.append(f"<li>{inline(re.sub(r'^\s*\d+\.\s+', '', lines[i]))}</li>"); i += 1
            out.append("<ol>" + "".join(items) + "</ol>"); continue
        out.append(f"<p>{inline(ln)}</p>"); i += 1

    css = """
@page { size: A4; margin: 24mm 16mm 18mm 16mm; }
body { font-family: "PingFang TC","Heiti TC","Helvetica Neue",sans-serif; color:#1b1b1b; line-height:1.75; font-size:11.5pt; }
h1 { font-size:22pt; color:#8B1A1A; border-bottom:3px solid #C8A24B; padding-bottom:8px; margin:0 0 6px; }
h2 { font-size:15pt; color:#8B1A1A; margin:26px 0 8px; padding-left:10px; border-left:6px solid #C8A24B; page-break-after:avoid; }
h3 { font-size:12.5pt; color:#222; background:#F5EFE2; padding:6px 10px; border-radius:4px; margin:20px 0 8px; page-break-after:avoid; page-break-before:auto; }
h3 + figure { page-break-before:avoid; }
blockquote { margin:8px 0 18px; padding:8px 12px; background:#FAF6EC; border-left:4px solid #C8A24B; color:#555; font-size:10.5pt; }
table { border-collapse:collapse; width:100%; margin:10px 0 16px; font-size:10.5pt; }
th { background:#8B1A1A; color:#fff; text-align:left; }
th,td { border:1px solid #d8d2c4; padding:6px 9px; vertical-align:top; }
tbody tr:nth-child(even) { background:#FBF9F4; }
thead { display:table-header-group; }
tr,figure,li { page-break-inside:avoid; }
.step { page-break-inside:avoid; break-inside:avoid; }
figure { margin:12px 0 6px; page-break-inside:avoid; }
img { max-width:100%; max-height:98mm; object-fit:contain; border:1px solid #ddd; border-radius:4px; }
figcaption { font-size:9.5pt; color:#777; margin-top:4px; }
code { background:#F3F0E9; padding:1px 5px; border-radius:3px; font-size:10pt; }
pre { background:#2b2b2b; color:#eee; padding:10px 12px; border-radius:5px; font-size:9.5pt; overflow-x:auto; }
ul,ol { padding-left:22px; }
hr { border:0; border-top:1px solid #ddd; margin:18px 0; }
"""
    body_html = wrap_steps(out)
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{htmllib.escape(title)}</title><style>{css}</style></head><body>{body_html}</body></html>"


def wrap_steps(blocks):
    """把每個 <h3> 到下一個 <h2>/<h3> 之間包成 .step，讓一個步驟不被切到兩頁。"""
    out, buf = [], None
    for b in blocks:
        starts_new = b.startswith("<h3") or b.startswith("<h2") or b.startswith("<h1")
        if starts_new and buf is not None:
            out.append('<section class="step">' + "".join(buf) + "</section>")
            buf = None
        if b.startswith("<h3"):
            buf = [b]
        elif buf is not None:
            buf.append(b)
        else:
            out.append(b)
    if buf is not None:
        out.append('<section class="step">' + "".join(buf) + "</section>")
    return "".join(out)


def cjk_font_candidates():
    """macOS 可用中文字型（/System/Library/Fonts/PingFang.ttc 在新版 macOS 上 PIL 開不起來，
    真正的檔案搬到 AssetsV2）。"""
    import glob
    return (glob.glob("/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/PingFang.ttc")
            + ["/System/Library/Fonts/Hiragino Sans GB.ttc",
               "/System/Library/Fonts/STHeiti Medium.ttc",
               "/System/Library/Fonts/Supplemental/Songti.ttc",
               "/System/Library/Fonts/PingFang.ttc"])


def make_header_png(text, out_png, w=860, h=110):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    dr = ImageDraw.Draw(im)
    font = None
    for fp in cjk_font_candidates():
        try:
            font = ImageFont.truetype(fp, 52); break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    logo_w = 0
    if os.path.exists(LOGO_PATH):
        lg = Image.open(LOGO_PATH).convert("RGBA")
        r = h / lg.height
        lg = lg.resize((int(lg.width * r), h), Image.LANCZOS)
        im.paste(lg, (w - lg.width, 0), lg)
        logo_w = lg.width
    bbox = dr.textbbox((0, 0), text, font=font)
    dr.text((w - logo_w - 16 - (bbox[2] - bbox[0]), (h - (bbox[3] - bbox[1])) // 2 - 6),
            text, font=font, fill=(139, 26, 26, 255))
    im.save(out_png)
    return out_png


def stamp_pdf(pdf_path, header_png):
    import fitz
    doc = fitz.open(pdf_path)
    for n, page in enumerate(doc, 1):
        W, H = page.rect.width, page.rect.height
        hw = 168; hh = hw * 110 / 860
        page.insert_image(fitz.Rect(W - 20 - hw, 14, W - 20, 14 + hh), filename=header_png, overlay=True)
        page.insert_text((W / 2 - 12, H - 20), f"- {n} -", fontsize=9, fontname="helv", color=(0.45, 0.45, 0.45))
    tmp = pdf_path + ".tmp"
    doc.save(tmp); doc.close()
    os.replace(tmp, pdf_path)


def cmd_build(a):
    d = os.path.abspath(os.path.expanduser(a.dir))
    meta = read_meta(d)
    doc = find_doc(d)
    ver = a.version or meta.get("版本", "1.0")
    md = open(doc, encoding="utf-8").read()
    title = meta.get("標題", "作業說明書")
    outdir = os.path.join(d, "輸出")
    os.makedirs(outdir, exist_ok=True)
    stem = f"{title}_v{ver}"
    html_path = os.path.join(outdir, stem + ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(md_to_html(md, d, title))
    print(f"✓ HTML → {html_path}")

    pdf_path = os.path.join(outdir, stem + ".pdf")
    if os.path.exists(pdf_path):
        shutil.move(pdf_path, os.path.join(outdir, "舊版", os.path.basename(pdf_path)))
    if not os.path.exists(CHROME):
        print("⚠️  找不到 Chrome，只出 HTML。手動列印成 PDF 亦可。")
        return
    cmd = [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={pdf_path}", "file://" + html_path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not os.path.exists(pdf_path):
        print("✗ PDF 產製失敗：", r.stderr[-500:]); return
    hdr = make_header_png("Sixhands Studio AI數字員工", os.path.join(outdir, ".header.png"))
    stamp_pdf(pdf_path, hdr)
    import fitz
    n = fitz.open(pdf_path).page_count
    meta["版本"] = ver; meta["更新日"] = datetime.date.today().isoformat()
    write_meta(d, meta)
    print(f"✓ PDF → {pdf_path}（{n} 頁，每頁已掛 logo）")
    print("  🔎 出稿後請開 PDF 目視：圖有沒有爆版、中文有沒有變空白框。")


def main():
    p = argparse.ArgumentParser(description="小書 · 作業說明書產線")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("--dir", required=True); s.add_argument("--title", required=True)
    s.add_argument("--owner"); s.add_argument("--audience"); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("scan"); s.add_argument("--dir", required=True)
    s.add_argument("--order", choices=["name", "mtime"], default="name"); s.set_defaults(fn=cmd_scan)
    s = sub.add_parser("check"); s.add_argument("--dir", required=True); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("build"); s.add_argument("--dir", required=True); s.add_argument("--version"); s.set_defaults(fn=cmd_build)
    a = p.parse_args()
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
