# -*- coding: utf-8 -*-
"""
小美・送印前體檢（preflight）

用法：
    python3 preflight.py 海報_送印.pdf --size 420x594 --bleed 3
    python3 preflight.py 內頁.pdf --size 210x297 --bleed 3 --binding saddle   # 檢查頁數是否 4 的倍數
    python3 preflight.py 主視覺.png --size 420x594 --dpi 300
    python3 preflight.py --text "Misa'ilisin ʉ 豐年祭" --role latin           # 只跑缺字檢查
    python3 preflight.py 海報_送印.pdf --size 420x594 --report 送印前檢查表.md

檢查項目對應 references/印刷生產規格.md §7：
    尺寸／出血・解析度・色彩・字型內嵌與缺字・頁數台數
"""
import argparse, os, sys, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fonts as F

MM = 72.0 / 25.4
OK, WARN, BAD = "✅", "⚠️", "🚨"


def pt2mm(v):
    return v / MM


class Report:
    def __init__(self, target):
        self.target = target
        self.rows = []

    def add(self, level, item, detail):
        self.rows.append((level, item, detail))

    def bad_count(self):
        return sum(1 for l, _, _ in self.rows if l == BAD)

    def render(self):
        out = [f"# 送印前檢查表　{os.path.basename(self.target)}", ""]
        out.append("| | 項目 | 說明 |")
        out.append("|:--|:---|:---|")
        for l, i, d in self.rows:
            out.append(f"| {l} | {i} | {d} |")
        n = self.bad_count()
        out.append("")
        out.append(f"**結論：{'不可送印，請先修正上列 🚨 項目' if n else '四檢通過，可進入送印流程'}**"
                   f"（🚨 {n} 項）")
        out.append("")
        out.append("> 色彩最終以印廠打樣為準；包裝案另須取得印廠刀模並以白樣實摺驗證。")
        out.append("")
        out.append("**Sixhands Studio AI數字員工**　🦞　小美 Xiao Mei")
        return "\n".join(out)


def check_pdf(path, size_mm, bleed, binding, rep):
    import fitz
    doc = fitz.open(path)
    rep.add(OK, "頁數", f"{doc.page_count} 頁")
    if binding in ("saddle", "perfect"):
        if doc.page_count % 4 == 0:
            rep.add(OK, "台數", f"{doc.page_count} 頁為 4 的倍數")
        else:
            rep.add(BAD, "台數", f"{doc.page_count} 頁不是 4 的倍數，"
                                 f"騎馬釘／膠裝須補至 {math.ceil(doc.page_count/4)*4} 頁")
    pg = doc[0]
    w, h = pt2mm(pg.rect.width), pt2mm(pg.rect.height)
    if size_mm:
        tw, th = size_mm
        exp_bleed = (tw + 2 * bleed, th + 2 * bleed)
        if abs(w - tw) < 0.6 and abs(h - th) < 0.6:
            rep.add(BAD, "出血", f"頁面 {w:.1f}×{h:.1f}mm 剛好等於成品尺寸，**沒有出血**，"
                                 f"請輸出 {exp_bleed[0]:.0f}×{exp_bleed[1]:.0f}mm（含 {bleed}mm 出血）")
        elif w >= exp_bleed[0] - 0.6 and h >= exp_bleed[1] - 0.6:
            extra = (w - tw) / 2
            rep.add(OK, "尺寸與出血", f"頁面 {w:.1f}×{h:.1f}mm，成品 {tw}×{th}mm，"
                                      f"四邊各多 {extra:.1f}mm（出血 {bleed}mm＋裁切標記區）")
        else:
            rep.add(BAD, "尺寸", f"頁面 {w:.1f}×{h:.1f}mm 小於成品＋出血 "
                                 f"{exp_bleed[0]:.0f}×{exp_bleed[1]:.0f}mm")
    else:
        rep.add(OK, "頁面尺寸", f"{w:.1f}×{h:.1f}mm")

    # 影像解析度與色彩
    worst = None
    cs_set = set()
    for pno in range(doc.page_count):
        p = doc[pno]
        for im in p.get_images(full=True):
            xref = im[0]
            try:
                info = doc.extract_image(xref)
            except Exception:
                continue
            cs_set.add(info.get("colorspace", 0))
            rects = p.get_image_rects(xref)
            for r in rects:
                mm_w = pt2mm(r.width)
                if mm_w <= 0:
                    continue
                dpi = info["width"] / (mm_w / 25.4)
                if worst is None or dpi < worst[0]:
                    worst = (dpi, pno + 1, info["width"], round(mm_w, 1))
    if worst:
        dpi, pno, px, mmw = worst
        lvl = OK if dpi >= 290 else (WARN if dpi >= 140 else BAD)
        note = "" if lvl == OK else ("（大圖輸出可接受，須註明觀看距離）" if lvl == WARN else "（平面印刷會糊）")
        rep.add(lvl, "影像解析度", f"最低 {dpi:.0f} dpi（第 {pno} 頁，{px}px 輸出寬 {mmw}mm）{note}")
    else:
        rep.add(OK, "影像解析度", "未偵測到點陣影像（純向量）")

    # 色彩空間
    n_cs = {1: "灰階", 3: "RGB", 4: "CMYK"}
    if cs_set:
        names = "／".join(n_cs.get(c, str(c)) for c in sorted(cs_set))
        lvl = OK if cs_set <= {1, 4} else WARN
        rep.add(lvl, "色彩模式", f"影像為 {names}"
                + ("" if lvl == OK else "　→ RGB 檔多數印廠可代轉，但顏色會位移；建議交 CMYK 或先與印廠確認 ICC"))

    # 字型內嵌
    not_embedded = set()
    used = set()
    for pno in range(doc.page_count):
        for f in doc[pno].get_fonts(full=True):
            xref, ext, ftype, basefont = f[0], f[1], f[2], f[3]
            used.add(basefont)
            if ext in ("n/a", "") or ftype == "Type3" and False:
                not_embedded.add(basefont)
    if used:
        if not_embedded:
            rep.add(BAD, "字型內嵌", f"未內嵌：{'、'.join(sorted(not_embedded))} → 印廠會缺字，請外框化或內嵌")
        else:
            rep.add(OK, "字型內嵌", f"{len(used)} 個字型皆已內嵌")
    else:
        rep.add(OK, "字型", "頁面文字皆已外框化（無字型物件）")
    doc.close()


def check_raster(path, size_mm, dpi_want, rep):
    from PIL import Image
    im = Image.open(path)
    rep.add(OK, "檔案", f"{im.format} {im.width}×{im.height}px，模式 {im.mode}")
    if size_mm:
        w_mm, h_mm = size_mm
        dpi_x = im.width / (w_mm / 25.4)
        lvl = OK if dpi_x >= dpi_want - 10 else (WARN if dpi_x >= 140 else BAD)
        rep.add(lvl, "解析度", f"於 {w_mm}×{h_mm}mm 輸出為 {dpi_x:.0f} dpi（目標 {dpi_want}）")
    if im.mode == "CMYK":
        rep.add(OK, "色彩模式", "CMYK")
    elif im.mode in ("RGB", "RGBA"):
        rep.add(WARN, "色彩模式", "RGB → 送印前需轉 CMYK（建議交 PDF 由印廠依 ICC 轉換）")
    elif im.mode in ("L", "1"):
        rep.add(OK, "色彩模式", "灰階／黑白")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="要檢查的 PDF / PNG / JPG / TIF")
    ap.add_argument("--size", help="成品尺寸 mm，例 420x594")
    ap.add_argument("--bleed", type=float, default=3.0)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--binding", choices=["none", "saddle", "perfect"], default="none")
    ap.add_argument("--text", help="缺字檢查用文字")
    ap.add_argument("--role", default="heavy", help="字型角色 heavy/bold/regular/serif/latin/latin_bold")
    ap.add_argument("--report", help="輸出檢查表 md 檔")
    a = ap.parse_args()

    if a.text and not a.file:
        miss = F.check_glyphs(a.text, a.role)
        path, idx = F.resolve(a.role)
        print(f"字型：{os.path.basename(path)}[{idx}]（角色 {a.role}）")
        print("缺字：", "".join(miss) if miss else "無 ✅")
        if miss:
            print("→ 族語羅馬字（ʉ ʼ ʔ）請改用 --role latin／latin_bold；生僻中文請換含該字的字型或改用外框圖。")
        return

    if not a.file:
        print(__doc__); return

    size = None
    if a.size:
        w, h = a.size.lower().split("x")
        size = (float(w), float(h))

    rep = Report(a.file)
    ext = os.path.splitext(a.file)[1].lower()
    if ext == ".pdf":
        check_pdf(a.file, size, a.bleed, a.binding, rep)
    else:
        check_raster(a.file, size, a.dpi, rep)

    if a.text:
        miss = F.check_glyphs(a.text, a.role)
        rep.add(OK if not miss else BAD, "缺字檢查",
                "無缺字" if not miss else f"字型畫不出：{''.join(miss)}（角色 {a.role}）")

    out = rep.render()
    print(out)
    if a.report:
        open(a.report, "w", encoding="utf-8").write(out)
        print(f"\n📄 已寫出 {a.report}")
    sys.exit(1 if rep.bad_count() else 0)


if __name__ == "__main__":
    main()
