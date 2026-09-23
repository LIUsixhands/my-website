# -*- coding: utf-8 -*-
# 7/5 三場版海報（沿用 6/27 版型，日期改為 7 月三場 7/5、7/19、7/26）
from PIL import Image, ImageDraw, ImageFont
import os

PHOTO = "/Users/chenyunung/Desktop/講座報名網站_上線用/photos"
OUT = "/Users/chenyunung/Desktop/講座報名網站_上線用/廣告素材"
FB = "/System/Library/Fonts/STHeiti Medium.ttc"

def font(sz): return ImageFont.truetype(FB, sz)

GOLD = (245, 197, 66)
RED = (192, 57, 43)
WHITE = (255, 255, 255)

def fit_cover(im, w, h):
    iw, ih = im.size
    s = max(w/iw, h/ih)
    im = im.resize((int(iw*s), int(ih*s)), Image.LANCZOS)
    x = (im.width - w)//2; y = (im.height - h)//2
    return im.crop((x, y, x+w, y+h))

def grad_bottom(im, frac=0.62, top_dark=80):
    w, h = im.size
    ov = Image.new("L", (1, h), 0)
    start = int(h*(1-frac))
    for y in range(h):
        if y < start:
            ov.putpixel((0, y), top_dark)
        else:
            t = (y-start)/(h-start)
            ov.putpixel((0, y), int(top_dark + (255-top_dark)*(t**1.3)))
    ov = ov.resize((w, h))
    black = Image.new("RGB", (w, h), (8, 10, 16))
    return Image.composite(black, im, ov)

def draw_c(d, cx, y, txt, f, fill=WHITE, stroke=4, sc=(0,0,0)):
    bb = d.textbbox((0,0), txt, font=f, stroke_width=stroke)
    w = bb[2]-bb[0]
    d.text((cx-w/2, y), txt, font=f, fill=fill, stroke_width=stroke, stroke_fill=sc)
    return y + (bb[3]-bb[1]) + int(f.size*0.25)

def badge(d, cx, y, txt, f, pad=18, bg=RED, fg=WHITE):
    bb = d.textbbox((0,0), txt, font=f)
    w = bb[2]-bb[0]; h = bb[3]-bb[1]
    x0 = cx-w/2-pad; x1 = cx+w/2+pad
    d.rounded_rectangle([x0, y, x1, y+h+pad*1.3], radius=(h+pad)//2, fill=bg)
    d.text((cx-w/2, y+pad*0.55), txt, font=f, fill=fg)
    return y+h+pad*1.3

# ---------- 圖1: 1:1 痛點主圖 ----------
def ad1():
    W=H=1080
    base = fit_cover(Image.open(PHOTO+"/kaohsiung-03.jpg").convert("RGB"), W, H)
    base = grad_bottom(base, 0.66, 90)
    d = ImageDraw.Draw(base)
    badge(d, W/2, 70, "7/5、7/19、7/26 台北實體 · 限額 45 位", font(32))
    y = 470
    y = draw_c(d, W/2, y, "老闆，別再", font(112), fill=WHITE, stroke=6)
    y = draw_c(d, W/2, y, "花五萬請行銷了", font(112), fill=GOLD, stroke=6)
    y += 18
    y = draw_c(d, W/2, y, "讓一套 AI 當你 24 小時", font(46), stroke=4)
    y = draw_c(d, W/2, y, "不睡覺、不領薪水的行銷部", font(46), stroke=4)
    sub = "助哥手把手 3 小時實作　|　免費報名"
    bb = d.textbbox((0,0), sub, font=font(34)); sw = bb[2]-bb[0]
    d.text((W/2-sw/2, H-118), sub, font=font(34), fill=WHITE, stroke_width=3, stroke_fill=(0,0,0))
    base.save(OUT+"/ws705_ad1_痛點_1x1.jpg", quality=92)
    print("ad1 done")

# ---------- 圖2: 1:1 講師信任版 ----------
def ad2():
    W=H=1080
    base = fit_cover(Image.open(PHOTO+"/jason-new.jpg").convert("RGB"), W, H)
    base = grad_bottom(base, 0.58, 70)
    d = ImageDraw.Draw(base)
    badge(d, W/2, 60, "7 月台北三場 · AI 行銷實戰講座", font(34))
    y = 540
    y = draw_c(d, W/2, y, "一個人，用 AI 撐起", font(56), stroke=5)
    y = draw_c(d, W/2, y, "5 個 YouTube 頻道", font(64), fill=GOLD, stroke=5)
    y += 26
    y = draw_c(d, W/2, y, "他親自把這套「AI 行銷部」", font(42), stroke=4)
    y = draw_c(d, W/2, y, "建置 SOP 手把手教給你", font(42), stroke=4)
    badge(d, W/2, H-150, "免費報名 · 每場限額 45 位", font(40), bg=GOLD, fg=(20,20,20))
    base.save(OUT+"/ws705_ad2_講師_1x1.jpg", quality=92)
    print("ad2 done")

# ---------- 圖3: 9:16 限動版 ----------
def ad3():
    W, H = 1080, 1920
    base = fit_cover(Image.open(PHOTO+"/taichung-02.jpg").convert("RGB"), W, H)
    base = grad_bottom(base, 0.55, 110)
    d = ImageDraw.Draw(base)
    badge(d, W/2, 150, "7/5、7/19、7/26 台北 · 免費實體講座", font(36))
    y = 940
    y = draw_c(d, W/2, y, "別再請行銷了", font(120), fill=GOLD, stroke=7)
    y += 30
    y = draw_c(d, W/2, y, "讓 AI 當你 24 小時", font(56), stroke=5)
    y = draw_c(d, W/2, y, "不領薪水的行銷部", font(56), stroke=5)
    y += 50
    y = draw_c(d, W/2, y, "自動發文 · 自動做圖 · 自動回客訊", font(40), stroke=4)
    badge(d, W/2, H-300, "每場限額 45 位 · 立即報名 →", font(46), bg=RED, fg=WHITE)
    base.save(OUT+"/ws705_ad3_限動_9x16.jpg", quality=92)
    print("ad3 done")

ad1(); ad2(); ad3()
print("ALL DONE ->", OUT)
