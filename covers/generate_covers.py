"""
Generate Gumroad covers for AI 空屋改造模板包
- Main Cover: 1280x720
- Thumbnail:  600x600
"""

from PIL import Image, ImageDraw, ImageFilter, ImageFont
import os

FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------- helpers ----------
def font(size):
    return ImageFont.truetype(FONT_PATH, size)


def vertical_gradient(size, top_color, bottom_color):
    w, h = size
    img = Image.new("RGB", (w, h), top_color)
    top = top_color
    bot = bottom_color
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def radial_glow(size, center, radius, color, alpha=170):
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
              fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(radius // 2))
    return layer


def draw_text_center(draw, xy, text, fnt, fill, stroke_width=0, stroke_fill=None):
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=fnt, stroke_width=stroke_width)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((x - w / 2 - bbox[0], y - h / 2 - bbox[1]),
              text, font=fnt, fill=fill,
              stroke_width=stroke_width, stroke_fill=stroke_fill)


def draw_text_left(draw, xy, text, fnt, fill, stroke_width=0, stroke_fill=None):
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=fnt, stroke_width=stroke_width)
    h = bbox[3] - bbox[1]
    draw.text((x - bbox[0], y - h / 2 - bbox[1]),
              text, font=fnt, fill=fill,
              stroke_width=stroke_width, stroke_fill=stroke_fill)


def text_size(draw, text, fnt):
    bbox = draw.textbbox((0, 0), text, font=fnt)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill,
                           outline=outline, width=width)


# ---------- mock room thumbnail (before / after) ----------
def make_room_panel(size, label, palette):
    """Stylized mock of a room for visual interest."""
    w, h = size
    img = Image.new("RGB", (w, h), palette["bg"])
    d = ImageDraw.Draw(img)

    # floor
    d.polygon([(0, h * 0.62), (w, h * 0.62), (w, h), (0, h)],
              fill=palette["floor"])
    # back wall already bg
    # left wall hint
    d.polygon([(0, 0), (w * 0.08, h * 0.10),
               (w * 0.08, h * 0.78), (0, h * 0.85)],
              fill=palette["wall_side"])
    # window
    win_x0 = int(w * 0.30)
    win_x1 = int(w * 0.70)
    win_y0 = int(h * 0.12)
    win_y1 = int(h * 0.45)
    d.rectangle([win_x0, win_y0, win_x1, win_y1], fill=palette["window"])
    d.line([(win_x0, (win_y0 + win_y1) // 2),
            (win_x1, (win_y0 + win_y1) // 2)],
           fill=palette["window_frame"], width=3)
    d.line([((win_x0 + win_x1) // 2, win_y0),
            ((win_x0 + win_x1) // 2, win_y1)],
           fill=palette["window_frame"], width=3)
    d.rectangle([win_x0, win_y0, win_x1, win_y1],
                outline=palette["window_frame"], width=4)

    # furniture (only after)
    if palette.get("furnished"):
        # sofa
        sx0, sy0 = int(w * 0.18), int(h * 0.58)
        sx1, sy1 = int(w * 0.62), int(h * 0.80)
        rounded_rect(d, (sx0, sy0, sx1, sy1), 10, fill=palette["sofa"])
        rounded_rect(d, (sx0, sy0 - 14, sx1, sy0 + 8), 6,
                     fill=palette["sofa_back"])
        # cushions
        d.rectangle([sx0 + 14, sy0 + 6, sx0 + 60, sy0 + 32],
                    fill=palette["cushion"])
        d.rectangle([sx1 - 60, sy0 + 6, sx1 - 14, sy0 + 32],
                    fill=palette["cushion"])
        # rug
        rounded_rect(d, (int(w * 0.14), int(h * 0.83),
                         int(w * 0.86), int(h * 0.95)), 6,
                     fill=palette["rug"])
        # lamp
        lx = int(w * 0.78)
        ly0 = int(h * 0.40)
        ly1 = int(h * 0.78)
        d.line([(lx, ly0), (lx, ly1)], fill=palette["lamp"], width=3)
        d.polygon([(lx - 18, ly0), (lx + 18, ly0),
                   (lx + 10, ly0 - 22), (lx - 10, ly0 - 22)],
                  fill=palette["lamp"])
        # plant
        px0 = int(w * 0.08)
        py0 = int(h * 0.55)
        d.ellipse([px0, py0, px0 + 36, py0 + 36], fill=palette["plant"])
        d.rectangle([px0 + 10, py0 + 28, px0 + 26, py0 + 50],
                    fill=palette["pot"])

    # subtle vignette
    vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vignette)
    vd.rectangle([0, 0, w, h], fill=(0, 0, 0, 0))
    for i in range(6):
        alpha = 8 + i * 6
        vd.rectangle([i * 2, i * 2, w - i * 2, h - i * 2],
                     outline=(0, 0, 0, alpha))
    img.paste(vignette, (0, 0), vignette)

    # label tag
    tag_h = 34
    tag_w = 110
    tx0 = 14
    ty0 = 14
    rounded_rect(d, (tx0, ty0, tx0 + tag_w, ty0 + tag_h), 8,
                 fill=palette["tag_bg"])
    f = font(20)
    draw_text_center(d, (tx0 + tag_w / 2, ty0 + tag_h / 2),
                     label, f, palette["tag_fg"])
    return img


BEFORE_PALETTE = {
    "bg": (210, 206, 198),
    "wall_side": (180, 175, 165),
    "floor": (150, 132, 110),
    "window": (200, 215, 225),
    "window_frame": (110, 100, 90),
    "tag_bg": (60, 60, 60),
    "tag_fg": (255, 255, 255),
    "furnished": False,
}

AFTER_PALETTE = {
    "bg": (244, 240, 232),
    "wall_side": (220, 214, 202),
    "floor": (188, 158, 124),
    "window": (210, 230, 240),
    "window_frame": (90, 80, 70),
    "sofa": (90, 110, 130),
    "sofa_back": (70, 90, 110),
    "cushion": (220, 170, 120),
    "rug": (200, 180, 150),
    "lamp": (180, 150, 100),
    "plant": (90, 140, 90),
    "pot": (120, 90, 70),
    "tag_bg": (255, 184, 76),
    "tag_fg": (40, 40, 40),
    "furnished": True,
}


def make_before_after(w, h):
    """Side-by-side before/after panel."""
    gap = max(6, w // 80)
    panel_w = (w - gap) // 2
    before = make_room_panel((panel_w, h), "BEFORE", BEFORE_PALETTE)
    after = make_room_panel((panel_w, h), "AFTER", AFTER_PALETTE)
    combo = Image.new("RGB", (w, h), (30, 30, 30))
    combo.paste(before, (0, 0))
    combo.paste(after, (panel_w + gap, 0))
    # arrow
    d = ImageDraw.Draw(combo)
    cx = panel_w + gap // 2
    cy = h // 2
    r = max(18, h // 14)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 184, 76))
    arrow_size = int(r * 0.55)
    d.polygon([(cx - arrow_size // 2, cy - arrow_size),
               (cx + arrow_size, cy),
               (cx - arrow_size // 2, cy + arrow_size)],
              fill=(30, 30, 30))
    return combo


# ---------- COVER 1280x720 ----------
def build_cover():
    W, H = 1280, 720
    img = vertical_gradient((W, H), (16, 24, 48), (44, 26, 72))

    # decorative glows
    g1 = radial_glow((W, H), (180, 120), 320, (90, 140, 255), alpha=110)
    g2 = radial_glow((W, H), (W - 220, H - 120), 360, (255, 140, 90), alpha=120)
    img.paste(g1, (0, 0), g1)
    img.paste(g2, (0, 0), g2)

    d = ImageDraw.Draw(img)

    # Right side: before / after panel
    panel_w = 540
    panel_h = 360
    panel_x = W - panel_w - 60
    panel_y = (H - panel_h) // 2 + 10
    ba = make_before_after(panel_w, panel_h)
    # shadow
    shadow = Image.new("RGBA", (panel_w + 60, panel_h + 60), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([30, 30, panel_w + 30, panel_h + 30],
                         radius=18, fill=(0, 0, 0, 140))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    img.paste(shadow, (panel_x - 30, panel_y - 20), shadow)
    # rounded mask for ba
    mask = Image.new("L", (panel_w, panel_h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, panel_w, panel_h], radius=18, fill=255)
    img.paste(ba, (panel_x, panel_y), mask)
    # frame
    d.rounded_rectangle(
        [panel_x, panel_y, panel_x + panel_w, panel_y + panel_h],
        radius=18, outline=(255, 255, 255), width=3,
    )

    # Left side: text block
    left_x = 70

    # eyebrow tag
    tag_text = "FOR 房仲｜AI 工具實戰"
    f_tag = font(22)
    tw, th = text_size(d, tag_text, f_tag)
    pad_x, pad_y = 18, 10
    d.rounded_rectangle(
        [left_x, 90, left_x + tw + pad_x * 2, 90 + th + pad_y * 2],
        radius=20, fill=(255, 184, 76),
    )
    d.text((left_x + pad_x, 90 + pad_y - 2), tag_text,
           font=f_tag, fill=(30, 24, 16))

    # main title
    f_title = font(96)
    title1 = "AI 空屋改造"
    title2 = "模板包"
    d.text((left_x, 160), title1, font=f_title, fill=(255, 255, 255))
    # accent for "模板包"
    title2_y = 270
    d.text((left_x, title2_y), title2, font=f_title, fill=(255, 200, 110))
    # underline accent
    t2w, _ = text_size(d, title2, f_title)
    d.rectangle([left_x, title2_y + 110, left_x + t2w, title2_y + 118],
                fill=(255, 184, 76))

    # subtitle
    f_sub = font(28)
    subtitle = "三種改造類型｜完整 SOP × Prompt × 發文腳本"
    d.text((left_x, 420), subtitle, font=f_sub, fill=(220, 220, 230))

    # feature chips
    chips = ["舊家具替換", "空間風格改造", "毛胚屋模擬"]
    f_chip = font(22)
    cx_pos = left_x
    cy_pos = 480
    for c in chips:
        cw, ch = text_size(d, c, f_chip)
        chip_w = cw + 28
        chip_h = ch + 22
        d.rounded_rectangle(
            [cx_pos, cy_pos, cx_pos + chip_w, cy_pos + chip_h],
            radius=chip_h // 2,
            outline=(255, 255, 255), width=2,
        )
        d.text((cx_pos + 14, cy_pos + (chip_h - ch) // 2 - 2),
               c, font=f_chip, fill=(255, 255, 255))
        cx_pos += chip_w + 12

    # bottom call-out
    f_foot = font(24)
    foot = "拍空屋 → 一鍵生成 → 直接發文 ｜ 含提案話術"
    d.text((left_x, 580), foot, font=f_foot, fill=(180, 200, 255))

    # tiny brand stripe
    d.rectangle([0, H - 8, W, H], fill=(255, 184, 76))

    return img


# ---------- THUMBNAIL 600x600 ----------
def build_thumbnail():
    W, H = 600, 600
    img = vertical_gradient((W, H), (16, 24, 48), (52, 30, 80))

    g1 = radial_glow((W, H), (120, 80), 260, (90, 140, 255), alpha=120)
    g2 = radial_glow((W, H), (W - 80, H - 80), 280, (255, 160, 100), alpha=130)
    img.paste(g1, (0, 0), g1)
    img.paste(g2, (0, 0), g2)

    d = ImageDraw.Draw(img)

    # before/after panel at top
    panel_w = 520
    panel_h = 230
    panel_x = (W - panel_w) // 2
    panel_y = 50
    ba = make_before_after(panel_w, panel_h)
    shadow = Image.new("RGBA", (panel_w + 60, panel_h + 60), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([30, 30, panel_w + 30, panel_h + 30],
                         radius=16, fill=(0, 0, 0, 140))
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    img.paste(shadow, (panel_x - 30, panel_y - 16), shadow)
    mask = Image.new("L", (panel_w, panel_h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, panel_w, panel_h], radius=16, fill=255)
    img.paste(ba, (panel_x, panel_y), mask)
    d.rounded_rectangle(
        [panel_x, panel_y, panel_x + panel_w, panel_y + panel_h],
        radius=16, outline=(255, 255, 255), width=3,
    )

    # eyebrow tag
    tag_text = "FOR 房仲"
    f_tag = font(22)
    tw, th = text_size(d, tag_text, f_tag)
    pad_x, pad_y = 16, 8
    tag_x = (W - (tw + pad_x * 2)) // 2
    tag_y = 310
    d.rounded_rectangle(
        [tag_x, tag_y, tag_x + tw + pad_x * 2, tag_y + th + pad_y * 2],
        radius=18, fill=(255, 184, 76),
    )
    d.text((tag_x + pad_x, tag_y + pad_y - 2), tag_text,
           font=f_tag, fill=(30, 24, 16))

    # title
    f_title = font(72)
    title1 = "AI 空屋改造"
    title2 = "模板包"
    t1w, _ = text_size(d, title1, f_title)
    t2w, _ = text_size(d, title2, f_title)
    d.text(((W - t1w) // 2, 365), title1, font=f_title, fill=(255, 255, 255))
    d.text(((W - t2w) // 2, 450), title2, font=f_title, fill=(255, 200, 110))
    # underline accent
    d.rectangle([(W - t2w) // 2, 538, (W - t2w) // 2 + t2w, 545],
                fill=(255, 184, 76))

    # bottom subtitle
    f_sub = font(20)
    sub = "三種類型 ｜ SOP × Prompt × 腳本"
    sw, _ = text_size(d, sub, f_sub)
    d.text(((W - sw) // 2, 560), sub, font=f_sub, fill=(210, 215, 235))

    # tiny brand stripe
    d.rectangle([0, H - 6, W, H], fill=(255, 184, 76))

    return img


def main():
    cover = build_cover()
    cover_path = os.path.join(OUT_DIR, "gumroad_cover_1280x720.png")
    cover.save(cover_path, "PNG", optimize=True)
    print("Saved", cover_path)

    thumb = build_thumbnail()
    thumb_path = os.path.join(OUT_DIR, "gumroad_thumbnail_600x600.png")
    thumb.save(thumb_path, "PNG", optimize=True)
    print("Saved", thumb_path)


if __name__ == "__main__":
    main()
