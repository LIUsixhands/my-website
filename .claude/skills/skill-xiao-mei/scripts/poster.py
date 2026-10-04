# -*- coding: utf-8 -*-
"""
小美・海報／DM 產生器（設定檔驅動）

用法：
    python3 poster.py config.json            # 產生預覽 PNG + 送印 PDF
    python3 poster.py config.json --tiff     # 另存 CMYK TIFF（簡易轉換，正式色彩管理仍以印廠 ICC 為準）
    python3 poster.py config.json --lossless # 送印 PDF 改用無損 PNG 嵌入（檔案極大，一般不需要）
    python3 poster.py --demo out_dir         # 產生一份可直接改的示範設定與成品

設計原則（見 references/海報設計SOP.md）：
  L1 主角 : L2 決策資訊 : L3 行動細節 = 字級比 4 : 2 : 1
  出血 3mm、安全區 5–8mm、字級以「成品短邊」為基準（不是畫布寬）
"""
import json, os, sys, math
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fonts as F

PT_PER_MM = 72.0 / 25.4


def mm2px(mm, dpi):
    return int(round(mm / 25.4 * dpi))


def hex2rgb(c):
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def wrap(draw, text, font, max_w):
    """中英混排自動換行：中文逐字、西文按詞。手動 \n 保留。"""
    out = []
    for para in text.split("\n"):
        line = ""
        token = ""
        def flush_token():
            nonlocal line, token
            if token:
                line += token
                token = ""
        for ch in para:
            if ch.isascii() and not ch.isspace():
                token += ch
                continue
            cand = line + token + ch
            if draw.textlength(cand, font=font) <= max_w or not (line or token):
                flush_token(); line += ch
            else:
                out.append(line if line else token)
                if not line:
                    token = ""
                line = (token + ch).lstrip(); token = ""
        cand = line + token
        if draw.textlength(cand, font=font) <= max_w or not line:
            out.append(cand)
        else:
            out.append(line); out.append(token)
    return [l for l in out if l != ""] or [""]


def fit_cover(img, w, h):
    r = max(w / img.width, h / img.height)
    img = img.resize((max(1, int(img.width * r)), max(1, int(img.height * r))), Image.LANCZOS)
    return img.crop(((img.width - w) // 2, (img.height - h) // 2,
                     (img.width - w) // 2 + w, (img.height - h) // 2 + h))


class Poster:
    def __init__(self, cfg, base_dir="."):
        self.cfg = cfg
        self.base = base_dir
        self.dpi = cfg.get("dpi", 300)
        self.W_mm, self.H_mm = cfg["size_mm"]
        self.bleed_mm = cfg.get("bleed_mm", 3)
        self.safe_mm = cfg.get("safe_mm", 8 if min(self.W_mm, self.H_mm) >= 400 else 5)
        self.W = mm2px(self.W_mm, self.dpi)
        self.H = mm2px(self.H_mm, self.dpi)
        self.B = mm2px(self.bleed_mm, self.dpi)
        self.CW, self.CH = self.W + 2 * self.B, self.H + 2 * self.B   # 含出血畫布
        self.short = min(self.W, self.H)                              # 字級基準＝成品短邊
        self.img = Image.new("RGB", (self.CW, self.CH), hex2rgb(cfg.get("paper", "#ffffff")))
        self.d = ImageDraw.Draw(self.img, "RGBA")
        self.warnings = []
        self._roles_used = set()
        self._lossless = False

    # ---------- 座標：以「成品」為 0,0，回傳畫布座標 ----------
    def px(self, x_pct, y_pct):
        return self.B + x_pct * self.W, self.B + y_pct * self.H

    def draw_background(self):
        bg = self.cfg.get("background", {"type": "solid", "color": "#ffffff"})
        t = bg.get("type", "solid")
        if t == "solid":
            self.d.rectangle([0, 0, self.CW, self.CH], fill=hex2rgb(bg["color"]))
        elif t == "gradient":
            c1, c2 = hex2rgb(bg["from"]), hex2rgb(bg["to"])
            g = Image.new("RGB", (1, self.CH))
            for y in range(self.CH):
                k = y / max(1, self.CH - 1)
                g.putpixel((0, y), tuple(int(c1[i] + (c2[i] - c1[i]) * k) for i in range(3)))
            self.img.paste(g.resize((self.CW, self.CH)), (0, 0))
        elif t == "image":
            p = os.path.join(self.base, bg["path"])
            im = Image.open(p).convert("RGB")
            eff_dpi = im.width / (self.CW / self.dpi)
            if eff_dpi < 250:
                self.warnings.append(f"背景圖有效解析度僅 {eff_dpi:.0f} dpi（<300），大圖輸出可接受，平面印刷請換圖：{bg['path']}")
            self.img.paste(fit_cover(im, self.CW, self.CH), (0, 0))
            if bg.get("blur", 0):
                self.img = self.img.filter(ImageFilter.GaussianBlur(bg["blur"]))
                self.d = ImageDraw.Draw(self.img, "RGBA")
            if bg.get("darken", 0):
                ov = Image.new("RGBA", (self.CW, self.CH), (0, 0, 0, int(255 * bg["darken"])))
                self.img = Image.alpha_composite(self.img.convert("RGBA"), ov).convert("RGB")
                self.d = ImageDraw.Draw(self.img, "RGBA")

    # ---------- 區塊 ----------
    def block_band(self, b):
        x0 = self.B + b.get("x_pct", 0) * self.W
        y0 = self.B + b["y_pct"] * self.H
        w = b.get("width_pct", 1.0) * self.W
        h = b["height_pct"] * self.H
        if b.get("full_bleed", False):
            x0, w = 0, self.CW
            if b["y_pct"] <= 0.001: y0 = 0; h += self.B
            if b["y_pct"] + b["height_pct"] >= 0.999: h += self.B
        col = hex2rgb(b.get("color", "#000000")) + (int(255 * b.get("opacity", 1.0)),)
        self.d.rectangle([x0, y0, x0 + w, y0 + h], fill=col)

    def block_rule(self, b):
        x0, y0 = self.px(b.get("x_pct", 0.5) - b.get("width_pct", 0.2) / 2, b["y_pct"])
        w = b.get("width_pct", 0.2) * self.W
        th = max(1, int(b.get("thickness_pct", 0.004) * self.short))
        self.d.rectangle([x0, y0, x0 + w, y0 + th], fill=hex2rgb(b.get("color", "#ffffff")))

    def block_text(self, b):
        role = b.get("role") or ("latin_bold" if b.get("lang") == "indigenous" else "heavy")
        size = int(b["size_pct"] * self.short)
        self._roles_used.add(role)
        font = F.load(role, size)
        miss = F.check_glyphs(b["text"], role)
        if miss:
            self.warnings.append(f"🚨 缺字（{role} 字型畫不出）：{''.join(miss)} ← 出現在「{b['text'][:18]}」")
        maxw = b.get("max_width_pct", 0.86) * self.W
        lines = wrap(self.d, b["text"], font, maxw)
        ls = b.get("line_spacing", 1.25)
        lh = size * ls
        align = b.get("align", "center")
        cx_pct = b.get("x_pct", 0.5)
        y = self.B + b["y_pct"] * self.H
        col = hex2rgb(b.get("color", "#ffffff"))
        # 安全區檢查
        safe = mm2px(self.safe_mm, self.dpi)
        for ln in lines:
            w = self.d.textlength(ln, font=font)
            if align == "center":
                x = self.B + cx_pct * self.W - w / 2
            elif align == "right":
                x = self.B + cx_pct * self.W - w
            else:
                x = self.B + cx_pct * self.W
            if b.get("shadow"):
                self.d.text((x + size * 0.03, y + size * 0.03), ln, font=font, fill=(0, 0, 0, 140))
            self.d.text((x, y), ln, font=font, fill=col)
            if x < self.B + safe or x + w > self.B + self.W - safe:
                self.warnings.append(f"⚠️ 文字超出安全區（距成品邊 <{self.safe_mm}mm）：「{ln[:18]}」")
            y += lh
        b["_bottom_pct"] = (y - self.B) / self.H

    def block_image(self, b):
        p = os.path.join(self.base, b["path"])
        im = Image.open(p).convert("RGBA")
        w = int(b["width_pct"] * self.W)
        h = int(w * im.height / im.width)
        eff_dpi = im.width / (w / self.dpi)
        if eff_dpi < 280:
            self.warnings.append(f"圖片 {b['path']} 於輸出尺寸僅 {eff_dpi:.0f} dpi（建議 ≥300）")
        im = im.resize((w, h), Image.LANCZOS)
        align = b.get("align", "center")
        cx = self.B + b.get("x_pct", 0.5) * self.W
        x = int(cx - w / 2) if align == "center" else (int(cx) if align == "left" else int(cx - w))
        y = int(self.B + b["y_pct"] * self.H)
        self.img.paste(im, (x, y), im)
        self.d = ImageDraw.Draw(self.img, "RGBA")

    def render(self):
        self.draw_background()
        for b in self.cfg.get("blocks", []):
            t = b.get("type", "text")
            {"text": self.block_text, "band": self.block_band,
             "rule": self.block_rule, "image": self.block_image, "logo": self.block_image}[t](b)
        return self.img

    # ---------- 輸出 ----------
    def save_preview(self, path, max_px=2000):
        im = self.img.crop((self.B, self.B, self.B + self.W, self.B + self.H))  # 預覽裁掉出血
        r = min(1.0, max_px / max(im.size))
        im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS).save(path, quality=92)
        return path

    def save_print_pdf(self, path, marks_mm=5, lossless=False):
        """輸出含出血與裁切標記的送印 PDF

        預設以 JPEG q95（4:4:4 無色度抽樣）嵌入：A2/300dpi 檔案從 ~100MB 降到 ~10MB，
        多數印廠有上傳大小限制，太肥的檔傳不上去。需絕對無損時加 --lossless（PNG，檔案很大）。
        """
        import fitz
        self._lossless = lossless
        if lossless:
            tmp = path + ".tmp.png"
            self.img.save(tmp)
        else:
            tmp = path + ".tmp.jpg"
            self.img.save(tmp, quality=95, subsampling=0, dpi=(self.dpi, self.dpi))
        m = marks_mm
        pw = (self.W_mm + 2 * self.bleed_mm + 2 * m) * PT_PER_MM
        ph = (self.H_mm + 2 * self.bleed_mm + 2 * m) * PT_PER_MM
        doc = fitz.open()
        pg = doc.new_page(width=pw, height=ph)
        x0, y0 = m * PT_PER_MM, m * PT_PER_MM
        pg.insert_image(fitz.Rect(x0, y0,
                                  x0 + (self.W_mm + 2 * self.bleed_mm) * PT_PER_MM,
                                  y0 + (self.H_mm + 2 * self.bleed_mm) * PT_PER_MM), filename=tmp)
        # 裁切標記（成品四角，線長 4mm，距成品邊 = 出血 + 1mm）
        b, L, gap = self.bleed_mm, 4 * PT_PER_MM, 1 * PT_PER_MM
        tx0 = (m + b) * PT_PER_MM
        ty0 = (m + b) * PT_PER_MM
        tx1 = tx0 + self.W_mm * PT_PER_MM
        ty1 = ty0 + self.H_mm * PT_PER_MM
        for (cx, cy, sx, sy) in [(tx0, ty0, -1, -1), (tx1, ty0, 1, -1), (tx0, ty1, -1, 1), (tx1, ty1, 1, 1)]:
            off = (b * PT_PER_MM) + gap
            pg.draw_line(fitz.Point(cx + sx * off, cy), fitz.Point(cx + sx * (off + L), cy), width=0.5)
            pg.draw_line(fitz.Point(cx, cy + sy * off), fitz.Point(cx, cy + sy * (off + L)), width=0.5)
        doc.save(path); doc.close(); os.remove(tmp)
        return path

    def save_spec(self, path, files):
        """輸出規格書（交件五件之一）"""
        used = sorted(self._roles_used)
        lines = [f"# 規格書　{self.cfg.get('output','artwork')}", "",
                 "## 印刷規格", "",
                 f"- 成品尺寸：**{self.W_mm} × {self.H_mm} mm**",
                 f"- 出血：四邊各 **{self.bleed_mm} mm**（送印 PDF 另含 5mm 裁切標記區）",
                 f"- 安全區：重要文字距成品邊 ≥ **{self.safe_mm} mm**",
                 f"- 解析度：**{self.dpi} dpi**（畫布 {self.CW} × {self.CH} px）",
                 "- 色彩：交付 PDF 為 RGB 影像，**請印廠依其 ICC 轉 CMYK**；"
                 "純黑小字建議改 K100 單色、大面積黑用複色黑（C50 M40 Y40 K100）",
                 f"- 送印 PDF 影像壓縮：{'無損 PNG' if self._lossless else 'JPEG q95（4:4:4，無色度抽樣）'}",
                 "- 紙材／後加工／數量：**待客戶與印廠確認**", "",
                 "## 使用字型", ""]
        for r in used:
            fp, idx = F.resolve(r)
            from PIL import ImageFont
            fam, sty = ImageFont.truetype(fp, 20, index=idx).getname()
            lines.append(f"- `{r}` → {fam} {sty}（{os.path.basename(fp)}[{idx}]）")
        lines += ["", "> 繁體中文一律使用 TC 字型；族語羅馬字使用含 ʉ ʼ ʔ 之拉丁擴充字型（本檔為 latin 角色）。", "",
                  "## 交付檔案", ""]
        for f in files:
            lines.append(f"- `{os.path.basename(f)}`")
        lines += ["", "## 圖片來源與授權", "",
                  "| 檔案 | 來源 | 授權依據 | 備註 |", "|:---|:---|:---|:---|",
                  "| （請逐項填寫，原民案件另附《元素來源與授權清單》） | | | |", "",
                  "**Sixhands Studio AI數字員工**　🦞　小美 Xiao Mei"]
        open(path, "w", encoding="utf-8").write("\n".join(lines))
        return path

    def save_cmyk_tiff(self, path):
        """簡易 CMYK 轉換（無 ICC 色彩管理）。正式印刷請交 PDF 由印廠依其 ICC 轉換。"""
        self.img.convert("CMYK").save(path, dpi=(self.dpi, self.dpi))
        self.warnings.append("ℹ️ CMYK TIFF 為 PIL 簡易轉換，未套用 ICC profile；顏色以印廠打樣為準。")
        return path


DEMO = {
    "output": "示範_活動海報_A2",
    "_note": "中段 0.36–0.50 預留主視覺圖像區：請由部落指定族人藝術家繪製後，以 {type:image, path:...} 置入。切勿用 AI 生成圖騰。",
    "size_mm": [420, 594], "dpi": 300, "bleed_mm": 3, "safe_mm": 8,
    "paper": "#101c14",
    "background": {"type": "gradient", "from": "#0d1f16", "to": "#2f1c10"},
    "blocks": [
        {"type": "band", "y_pct": 0.0, "height_pct": 0.055, "color": "#c8a04a", "full_bleed": True},
        {"type": "text", "lang": "indigenous", "text": "Misa'ilisin", "size_pct": 0.115,
         "y_pct": 0.16, "color": "#f5e6c8", "align": "center", "line_spacing": 1.1},
        {"type": "rule", "y_pct": 0.30, "width_pct": 0.18, "color": "#c8a04a", "thickness_pct": 0.006},
        {"type": "text", "text": "〇〇部落 歲時祭儀", "size_pct": 0.062, "y_pct": 0.335,
         "color": "#ffffff", "role": "heavy"},
        {"type": "text", "text": "2026.08.15 SAT  15:00", "size_pct": 0.036, "y_pct": 0.545,
         "color": "#f0d9a8", "role": "latin_bold"},
        {"type": "text", "text": "〇〇鄉〇〇部落 集會所廣場", "size_pct": 0.030, "y_pct": 0.605,
         "color": "#ffffff", "role": "regular"},
        {"type": "band", "y_pct": 0.86, "height_pct": 0.14, "color": "#000000", "opacity": 0.55, "full_bleed": True},
        {"type": "text", "text": "指導單位：〇〇〇　主辦單位：〇〇〇　協辦：〇〇〇",
         "size_pct": 0.018, "y_pct": 0.885, "color": "#e8e8e8", "role": "regular"},
        {"type": "text", "text": "＊本活動為部落歲時祭儀，攝影請依部落公告規範　＊視覺元素使用依授權清單",
         "size_pct": 0.015, "y_pct": 0.925, "color": "#bdbdbd", "role": "regular"}
    ]
}


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    if args[0] == "--demo":
        out = args[1] if len(args) > 1 else "."
        os.makedirs(out, exist_ok=True)
        cfgp = os.path.join(out, "poster_config.json")
        json.dump(DEMO, open(cfgp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        cfg, base = DEMO, out
    else:
        cfgp = args[0]
        cfg = json.load(open(cfgp, encoding="utf-8"))
        base = os.path.dirname(os.path.abspath(cfgp))
        out = base
    p = Poster(cfg, base)
    p.render()
    name = cfg.get("output", "artwork")
    png = p.save_preview(os.path.join(out, f"{name}_預覽.png"))
    pdf = p.save_print_pdf(os.path.join(out, f"{name}_送印.pdf"), lossless=("--lossless" in args))
    print("✅", png)
    print("✅", pdf)
    files = [png, pdf]
    if "--tiff" in args:
        tif = p.save_cmyk_tiff(os.path.join(out, f"{name}_CMYK.tif"))
        files.append(tif); print("✅", tif)
    spec = p.save_spec(os.path.join(out, f"{name}_規格書.md"), files)
    print("✅", spec)
    print(f"\n規格：{p.W_mm}×{p.H_mm}mm　出血 {p.bleed_mm}mm　安全區 {p.safe_mm}mm　{p.dpi}dpi　畫布 {p.CW}×{p.CH}px")
    if p.warnings:
        print("\n--- 送印前警告 ---")
        for w in dict.fromkeys(p.warnings):
            print(" •", w)
    else:
        print("\n送印四檢：尺寸/解析度/安全區/缺字 皆通過 ✅（色彩仍須確認 CMYK 與 K100 黑字）")


if __name__ == "__main__":
    main()
