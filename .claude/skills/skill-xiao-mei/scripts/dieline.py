# -*- coding: utf-8 -*-
"""
小美・包裝刀模展開圖產生器（reverse tuck-end 直立摺盒）

用法：
    python3 dieline.py --L 100 --W 60 --H 160 --name 茶葉禮盒
    python3 dieline.py --L 90 --W 90 --H 120 --thickness 0.5 --bleed 3 --out ./03_送印

輸出：<name>_刀模.svg / <name>_刀模.pdf / <name>_刀模_預覽.png

製圖慣例（見 references/包裝設計SOP.md）：
    裁切線 cut    = 洋紅實線 Magenta
    摺線   crease = 青色虛線 Cyan
    糊口   glue   = 標註「膠合面不印刷」
⚠️ 本圖供設計配置與提案用。**實際生產一律以印刷廠回傳之刀模為準**，並務必用白樣實摺驗證。
"""
import argparse, os, math

MM = 72.0 / 25.4
CUT = (1, 0, 1)        # magenta
CREASE = (0, 0.7, 1)   # cyan
BLEED = (0.6, 0.6, 0.6)
TXT = (0.25, 0.25, 0.25)


class Die:
    def __init__(self, L, W, H, thickness=0.4, glue=15.0, bleed=3.0, name="box"):
        self.L, self.W, self.H = L, W, H
        self.t = thickness
        self.glue = glue
        self.bleed = bleed
        self.name = name
        self.dust = round(W * 0.75, 1)            # 防塵翼高
        self.tuck_panel = round(W, 1)             # 頂／底蓋深度＝盒厚
        self.tuck_flap = round(min(W * 0.8, 18), 1)  # 插舌長
        self.margin = 18.0
        self.segs = []   # (x0,y0,x1,y1,kind)
        self.labels = []
        self._build()

    # ---- 幾何 ----
    def _build(self):
        L, W, H, g = self.L, self.W, self.H, self.glue
        top = self.tuck_panel + self.tuck_flap
        m = self.margin
        self.body_w = g + L + W + L + W
        self.body_h = H
        self.total_w = self.body_w + 2 * m
        self.total_h = H + 2 * top + 2 * m
        ox, oy = m, m + top            # 主帶左上角
        self.ox, self.oy = ox, oy

        # 面的 x 邊界：glue | back(L) | side(W) | front(L) | side(W)
        xs = [ox, ox + g, ox + g + L, ox + g + L + W, ox + g + L + W + L, ox + self.body_w]
        self.xs = xs
        y0, y1 = oy, oy + H

        c = self.segs.append
        # --- 糊口（左側梯形，斜 5mm）---
        sl = min(5.0, H * 0.05)
        c((xs[0] + sl, y0, xs[1], y0, "cut"))
        c((xs[0], y0 + sl, xs[0] + sl, y0, "cut"))
        c((xs[0], y0 + sl, xs[0], y1 - sl, "cut"))
        c((xs[0], y1 - sl, xs[0] + sl, y1, "cut"))
        c((xs[0] + sl, y1, xs[1], y1, "cut"))
        c((xs[1], y0, xs[1], y1, "crease"))          # 糊口摺線

        # --- 主帶四面之間的摺線 + 上下輪廓 ---
        for i in (2, 3, 4):
            c((xs[i], y0, xs[i], y1, "crease"))
        c((xs[5], y0, xs[5], y1, "cut"))             # 最右外緣

        # 主帶上下緣：有蓋／翼的地方為摺線，其餘為裁切線
        # 面順序 idx1..4 = back(L), side(W), front(L), side(W)
        panels = [(xs[1], xs[2], "back"), (xs[2], xs[3], "side"),
                  (xs[3], xs[4], "front"), (xs[4], xs[5], "side")]
        for a, b, kind in panels:
            c((a, y0, b, y0, "crease"))
            c((a, y0 + H, b, y0 + H, "crease"))

        # --- 頂蓋（接在 back 上方）＋ 底蓋（接在 front 下方）---
        self._tuck(xs[1], xs[2], y0, up=True)
        self._tuck(xs[3], xs[4], y1, up=False)
        # --- 防塵翼（兩個 side 的上下）---
        for a, b in [(xs[2], xs[3]), (xs[4], xs[5])]:
            self._dust(a, b, y0, up=True)
            self._dust(a, b, y1, up=False)

        # --- 標註 ---
        self.labels = [
            ((xs[1] + xs[2]) / 2, y0 + H / 2, f"背面\n{L} × {H}"),
            ((xs[2] + xs[3]) / 2, y0 + H / 2, f"側\n{W}"),
            ((xs[3] + xs[4]) / 2, y0 + H / 2, f"正面\n{L} × {H}"),
            ((xs[4] + xs[5]) / 2, y0 + H / 2, f"側\n{W}"),
            ((xs[0] + xs[1]) / 2, y0 + H / 2, "糊口\n不印刷"),
            ((xs[1] + xs[2]) / 2, y0 - self.tuck_panel / 2, f"頂蓋 {self.tuck_panel}"),
            ((xs[3] + xs[4]) / 2, y1 + self.tuck_panel / 2, f"底蓋 {self.tuck_panel}"),
        ]

    def _tuck(self, a, b, y, up=True):
        s = -1 if up else 1
        tp, tf = self.tuck_panel, self.tuck_flap
        inset = 1.5           # 插舌兩側內縮（塞得進去）
        c = self.segs.append
        y1 = y + s * tp
        y2 = y + s * (tp + tf)
        c((a, y, a, y1, "cut")); c((b, y, b, y1, "cut"))
        c((a, y1, b, y1, "crease"))                       # 蓋與插舌之間的摺線
        c((a + inset, y1, a + inset, y2, "cut"))
        c((a + inset, y2, b - inset, y2, "cut"))
        c((b - inset, y1, b - inset, y2, "cut"))

    def _dust(self, a, b, y, up=True):
        """防塵翼：兩側各倒角，摺合時不與蓋板互卡"""
        s = -1 if up else 1
        d = self.dust
        sl = min(4.0, d * 0.35)
        y1 = y + s * d
        c = self.segs.append
        c((a, y, a + sl, y1, "cut"))
        c((a + sl, y1, b - sl, y1, "cut"))
        c((b - sl, y1, b, y, "cut"))

    # ---- 輸出 ----
    def to_svg(self, path):
        W, H = self.total_w, self.total_h
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" '
               f'viewBox="0 0 {W} {H}">',
               f'<rect width="{W}" height="{H}" fill="white"/>',
               '<g fill="none" stroke-linecap="round">']
        for x0, y0, x1, y1, k in self.segs:
            if k == "cut":
                out.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" stroke="#FF00FF" stroke-width="0.25"/>')
            else:
                out.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" stroke="#00B3FF" stroke-width="0.25" stroke-dasharray="3 2"/>')
        out.append('</g><g font-family="Helvetica" font-size="4" fill="#404040" text-anchor="middle">')
        for x, y, t in self.labels:
            for i, ln in enumerate(t.split("\n")):
                out.append(f'<text x="{x:.2f}" y="{y + i * 5:.2f}">{ln}</text>')
        out.append(f'<text x="{W/2:.2f}" y="{H - 6:.2f}" font-size="4.5">'
                   f'{self.name}　L{self.L} × W{self.W} × H{self.H} mm　紙厚 {self.t}mm　出血 {self.bleed}mm　'
                   f'洋紅=裁切　青色虛線=摺線　※以印廠刀模為準</text>')
        out.append('</g></svg>')
        open(path, "w", encoding="utf-8").write("\n".join(out))
        return path

    def to_pdf(self, path, png=None):
        import fitz
        doc = fitz.open()
        pg = doc.new_page(width=self.total_w * MM, height=self.total_h * MM)
        for x0, y0, x1, y1, k in self.segs:
            p0, p1 = fitz.Point(x0 * MM, y0 * MM), fitz.Point(x1 * MM, y1 * MM)
            if k == "cut":
                pg.draw_line(p0, p1, color=CUT, width=0.5)
            else:
                pg.draw_line(p0, p1, color=CREASE, width=0.5, dashes="[3 2] 0")
        cjk = "china-t"   # PyMuPDF 內建繁體 CJK 字型（helv 會把中文印成點）
        for x, y, t in self.labels:
            for i, ln in enumerate(t.split("\n")):
                try:
                    w = fitz.get_text_length(ln, fontname=cjk, fontsize=8)
                    pg.insert_text(fitz.Point(x * MM - w / 2, (y + i * 4) * MM), ln,
                                   fontsize=8, fontname=cjk, color=TXT)
                except Exception:
                    w = fitz.get_text_length(ln, fontname="helv", fontsize=8)
                    pg.insert_text(fitz.Point(x * MM - w / 2, (y + i * 4) * MM), ln,
                                   fontsize=8, color=TXT)
        foot = (f"{self.name}　L{self.L} × W{self.W} × H{self.H} mm｜紙厚 {self.t}mm｜出血 {self.bleed}mm｜"
                f"洋紅=裁切　青虛線=摺線｜※實際生產以印刷廠刀模為準，並以白樣實摺驗證")
        try:
            pg.insert_text(fitz.Point(self.margin * MM, (self.total_h - 6) * MM), foot,
                           fontsize=7, fontname=cjk, color=TXT)
        except Exception:
            pg.insert_text(fitz.Point(self.margin * MM, (self.total_h - 6) * MM), foot, fontsize=7, color=TXT)
        doc.save(path)
        if png:
            doc[0].get_pixmap(dpi=110).save(png)
        doc.close()
        return path

    def spec(self):
        area = self.total_w * self.total_h / 100.0
        return (f"展開尺寸 {self.total_w:.1f} × {self.total_h:.1f} mm（含 {self.margin}mm 製圖邊界）\n"
                f"盒體 L{self.L} × W{self.W} × H{self.H} mm｜糊口 {self.glue}mm｜"
                f"防塵翼 {self.dust}mm｜頂底蓋 {self.tuck_panel}mm｜插舌 {self.tuck_flap}mm\n"
                f"單片面積約 {area:.0f} cm²（估紙材用量用）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--L", type=float, required=True, help="正面寬 mm")
    ap.add_argument("--W", type=float, required=True, help="盒厚（側面）mm")
    ap.add_argument("--H", type=float, required=True, help="盒高 mm")
    ap.add_argument("--thickness", type=float, default=0.4, help="紙材厚度 mm")
    ap.add_argument("--glue", type=float, default=15.0, help="糊口寬 mm")
    ap.add_argument("--bleed", type=float, default=3.0)
    ap.add_argument("--name", default="包裝盒")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    d = Die(a.L, a.W, a.H, a.thickness, a.glue, a.bleed, a.name)
    svg = d.to_svg(os.path.join(a.out, f"{a.name}_刀模.svg"))
    pdf = d.to_pdf(os.path.join(a.out, f"{a.name}_刀模.pdf"),
                   os.path.join(a.out, f"{a.name}_刀模_預覽.png"))
    print("✅", svg); print("✅", pdf)
    print("✅", os.path.join(a.out, f"{a.name}_刀模_預覽.png"))
    print("\n" + d.spec())
    print("\n⚠️ 提醒：①內尺寸須加 1–3mm 商品餘裕　②有效日期噴印區留淺色空白 ≥30×10mm"
          "　③條碼四周留白 ≥2.3mm 且不跨摺線　④送印前務必取得印廠刀模並做白樣實摺")


if __name__ == "__main__":
    main()
