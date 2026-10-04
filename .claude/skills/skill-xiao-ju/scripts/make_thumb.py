"""步驟 8.5：做封面縮圖（1080×1920，上下兩張臉＋中間紅帶鉤子）
素材直接從 clips/ 抽幀，所以縮圖裡的人一定跟片中同一個人。
設定寫在 episode.json 的 thumb：
  "thumb": {
    "hook": "我沒有說要換人",              # 紅帶大字（自動縮到放得下）
    "top":    {"shot": "s02", "t": 1.2, "crop": 0.30,
               "bubble": ["我馬上換人，", "讓她走"]},   # 第 2 行會是紅字；不要對話框就拿掉
    "bottom": {"shot": "s06", "t": 0.8, "crop": 0.25},  # crop＝從畫面上緣幾成的位置開始裁
    "tag": "穿藍白拖的客人｜第2集"
  }
用法：python3 make_thumb.py [--out 縮圖.jpg]
"""
import subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw
from common import ROOT, EP
from compose import W, H, SANS_B, SERIF, font, fit_font

TH = EP.get("thumb")
if not TH:
    sys.exit("❌ episode.json 沒有 thumb 設定（用法看這支檔案開頭）")

BAND_Y, BAND_H = 880, 172          # 紅帶位置與高度
RED = (196, 18, 32)
outname = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else f"縮圖_EP{EP['ep']:02d}.jpg"
OUT = ROOT / "out" / outname
TMP = ROOT / "out" / "_thumb_tmp"; TMP.mkdir(parents=True, exist_ok=True)


def grab(spec, box_h):
    """從 clip 抽一幀，裁成 W×box_h
    zoom＝先放大幾倍（臉太小就調大，1.3 左右），crop＝取垂直哪一段（0 最上、1 最下）"""
    src = ROOT / "clips" / f"{spec['shot']}.mp4"
    if not src.exists():
        sys.exit(f"❌ 找不到 {src}")
    jpg = TMP / f"{spec['shot']}.jpg"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(spec.get("t", 0.6)),
                    "-i", str(src), "-frames:v", "1", str(jpg)], check=True)
    im = Image.open(jpg).convert("RGB")
    zw = round(W * spec.get("zoom", 1.0))
    im = im.resize((zw, round(im.height * zw / im.width)), Image.LANCZOS)
    left = round((im.width - W) * spec.get("x", 0.5))      # 放大後水平取哪一段
    top = round((im.height - box_h) * spec.get("crop", 0.25))
    return im.crop((left, max(0, top), left + W, max(0, top) + box_h))


def rounded(d, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


def stroked(d, xy, txt, f, fill, stroke=(0, 0, 0), w=0, anchor="la"):
    d.text(xy, txt, font=f, fill=fill, anchor=anchor, stroke_width=w, stroke_fill=stroke)


img = Image.new("RGB", (W, H), (0, 0, 0))
img.paste(grab(TH["top"], BAND_Y), (0, 0))
img.paste(grab(TH["bottom"], H - (BAND_Y + BAND_H)), (0, BAND_Y + BAND_H))
d = ImageDraw.Draw(img)

# 中間紅帶＋鉤子
d.rectangle((0, BAND_Y, W, BAND_Y + BAND_H), fill=RED)
hook = TH["hook"]
stroked(d, (W // 2, BAND_Y + BAND_H // 2), hook, fit_font(hook, SERIF, 128, W - 90, 72),
        (255, 255, 255), (120, 8, 18), 3, "mm")

# 上格對話框（白底圓角＋指向人物的尖角，第 2 行紅字）
bub = TH["top"].get("bubble")
if bub:
    f = font(SANS_B, 58)
    tw = max(d.textlength(l, font=f) for l in bub)
    bw, bh = round(tw) + 72, 58 * len(bub) + 54
    bx, by = 44, BAND_Y - bh - 96
    rounded(d, (bx, by, bx + bw, by + bh), 28, (255, 255, 255))
    d.polygon([(bx + bw - 130, by + bh - 6), (bx + bw - 40, by + bh - 6), (bx + bw + 46, by + bh + 74)],
              fill=(255, 255, 255))
    for i, line in enumerate(bub):
        d.text((bx + 36, by + 26 + i * 58), line, font=f, fill=RED if i else (24, 24, 26))

# 右上 AI 標示
f = font(SANS_B, 42)
tw = round(d.textlength("AI 生成內容", font=f))
rounded(d, (W - tw - 86, 34, W - 34, 108), 26, (18, 18, 20))
d.text((W - tw - 60, 50), "AI 生成內容", font=f, fill=(255, 255, 255))

# 左下劇名標籤
tag = TH.get("tag") or f"{EP['title']}｜第{EP['ep']}集"
f = fit_font(tag, SANS_B, 50, W - 320)
tw = round(d.textlength(tag, font=f))
rounded(d, (44, H - 128, 44 + tw + 60, H - 44), 22, (255, 255, 255))
d.text((74, H - 116), tag, font=f, fill=RED)

# 右下 logo
logo = EP.get("brand", {}).get("logo", "")
if logo and Path(logo).expanduser().exists():
    lg = Image.open(Path(logo).expanduser()).convert("RGBA")
    lg = lg.resize((150, round(lg.height * 150 / lg.width)), Image.LANCZOS)
    img.paste(lg, (W - 194, H - 44 - lg.height), lg)

img.save(OUT, quality=92)
print(f"✅ {OUT}  {OUT.stat().st_size // 1024} KB（YouTube 上限 2MB）")
