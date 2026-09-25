#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_chart.py — 紫微命盤「視覺圖卡」產生器（純 PIL，零 API）
Sixhands Studio AI數字員工 🦞 ▎AI 員工「小紫」產線元件

⚠️ 重要聲明：
    這是「畫圖工具」，不是「排盤引擎」。
    它不會自己算命盤 —— 星曜資料必須由老師本人（或專業排盤軟體）提供，
    寫進 chart.json 再交給它畫。這樣才不會在影片裡出現錯誤的命理資訊。

用法：
    python3 gen_chart.py                       # 用內建示範盤，輸出 chart.png
    python3 gen_chart.py my_chart.json out.png # 用自己的資料
    python3 gen_chart.py my_chart.json out.png 夫妻宮   # 並讓「夫妻宮」發光

chart.json 格式：
{
  "center":  {"title": "紫微命盤", "lines": ["示範盤 · 非真實命例", "講師：OOO 老師"]},
  "palaces": {
      "寅": {"name": "命宮",   "stars": ["紫微", "天府"]},
      "卯": {"name": "兄弟宮", "stars": ["太陰"]},
      ...  (十二地支寫滿)
  },
  "highlight": "命宮"
}
"""
import os, sys, json, math, random

W = H = 1080                       # 方形盤面；影片會再貼進 9:16 或 16:9 版面
BG_TOP    = (26, 11, 46)           # 深紫
BG_BOTTOM = (45, 27, 78)
GOLD      = (212, 175, 55)
GOLD_DIM  = (138, 113, 40)
CREAM     = (245, 240, 228)
PURPLE_LT = (176, 142, 232)
HL        = (255, 214, 102)        # 高亮宮位

# 繁體字型（Songti SC 缺繁體字會渲染成空白，務必用 TC 字面）
FONT_CANDIDATES = [
    ("/System/Library/Fonts/PingFang.ttc", 0),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 2),   # Songti TC Bold
    ("/Library/Fonts/Arial Unicode.ttf", 0),
]

def find_font():
    from PIL import ImageFont
    for path, idx in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                ImageFont.truetype(path, 40, index=idx)
                return (path, idx)
            except Exception:
                continue
    return None

FONT = find_font()

def font(sz):
    from PIL import ImageFont
    if not FONT:
        return ImageFont.load_default()
    return ImageFont.truetype(FONT[0], sz, index=FONT[1])

# 十二地支在 4×4 盤面上的固定格位 (col, row)
BRANCH_POS = {
    "巳": (0, 0), "午": (1, 0), "未": (2, 0), "申": (3, 0),
    "辰": (0, 1),                             "酉": (3, 1),
    "卯": (0, 2),                             "戌": (3, 2),
    "寅": (0, 3), "丑": (1, 3), "子": (2, 3), "亥": (3, 3),
}

DEMO = {
    "center": {"title": "紫微命盤",
               "lines": ["示範盤（非真實命例）", "僅供影片視覺使用"]},
    "palaces": {
        "寅": {"name": "命宮",   "stars": ["紫微", "天府"]},
        "丑": {"name": "兄弟宮", "stars": ["太陰"]},
        "子": {"name": "夫妻宮", "stars": ["貪狼"]},
        "亥": {"name": "子女宮", "stars": ["巨門"]},
        "戌": {"name": "財帛宮", "stars": ["天相"]},
        "酉": {"name": "疾厄宮", "stars": ["天梁"]},
        "申": {"name": "遷移宮", "stars": ["七殺"]},
        "未": {"name": "交友宮", "stars": ["天同"]},
        "午": {"name": "官祿宮", "stars": ["武曲"]},
        "巳": {"name": "田宅宮", "stars": ["太陽"]},
        "辰": {"name": "福德宮", "stars": ["天機"]},
        "卯": {"name": "父母宮", "stars": ["廉貞", "破軍"]},
    },
    "highlight": "命宮",
}

def draw_background(d, img):
    """深紫漸層 + 星點 + 外圈光暈。"""
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)],
               fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    rnd = random.Random(20260823)          # 固定種子 → 每次算出同一片星空
    for _ in range(260):
        x, y = rnd.randint(0, W), rnd.randint(0, H)
        r = rnd.choice([1, 1, 1, 2, 2, 3])
        a = rnd.randint(60, 200)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, a))

def text_center(d, cx, y, s, f, fill):
    bb = d.textbbox((0, 0), s, font=f)
    d.text((cx - (bb[2] - bb[0]) / 2, y), s, font=f, fill=fill)

def render(data, out_path, highlight=None):
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img, "RGBA")
    draw_background(d, img)

    M = 70                                   # 盤面外邊距
    size = W - M * 2
    cell = size / 4
    hl_name = highlight or data.get("highlight")

    # 盤面外框
    d.rectangle([M - 6, M - 6, M + size + 6, M + size + 6], outline=GOLD_DIM, width=3)

    for branch, (col, row) in BRANCH_POS.items():
        p = data["palaces"].get(branch, {})
        name = p.get("name", "")
        stars = p.get("stars", [])
        x0, y0 = M + col * cell, M + row * cell
        x1, y1 = x0 + cell, y0 + cell
        is_hl = (name and name == hl_name)

        d.rectangle([x0, y0, x1, y1],
                    fill=(255, 214, 102, 26) if is_hl else (255, 255, 255, 8),
                    outline=HL if is_hl else GOLD_DIM,
                    width=5 if is_hl else 2)

        # 主星（宮位上方，金色）
        sy = y0 + 24
        for s in stars[:4]:
            text_center(d, (x0 + x1) / 2, sy, s, font(40), HL if is_hl else GOLD)
            sy += 50
        # 宮名（宮位左下）
        d.text((x0 + 18, y1 - 56), name, font=font(36),
               fill=CREAM if is_hl else PURPLE_LT)
        # 地支（宮位右下）
        bb = d.textbbox((0, 0), branch, font=font(34))
        d.text((x1 - 18 - (bb[2] - bb[0]), y1 - 54), branch, font=font(34), fill=GOLD_DIM)

    # 中宮
    cx0, cy0 = M + cell, M + cell
    cx1, cy1 = M + cell * 3, M + cell * 3
    d.rectangle([cx0, cy0, cx1, cy1], fill=(20, 8, 38, 230), outline=GOLD, width=3)
    c = data.get("center", {})
    cx = (cx0 + cx1) / 2
    ty = cy0 + 90
    text_center(d, cx, ty, c.get("title", "紫微命盤"), font(74), GOLD)
    ty += 130
    for ln in c.get("lines", [])[:4]:
        text_center(d, cx, ty, ln, font(38), CREAM)
        ty += 60

    img = img.filter(ImageFilter.SMOOTH)
    img.save(out_path, quality=95)
    return out_path

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    out = sys.argv[2] if len(sys.argv) > 2 else "chart.png"
    hl  = sys.argv[3] if len(sys.argv) > 3 else None
    data = json.load(open(src, encoding="utf-8")) if src and os.path.exists(src) else DEMO
    if not FONT:
        print("⚠️ 找不到繁體中文字型，文字可能變空白方塊。")
    render(data, out, hl)
    print(f"✅ 命盤圖：{out}")

if __name__ == "__main__":
    main()
