# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

FONT = "/System/Library/AssetsV2/com_apple_MobileAsset_Font7/3419f2a427639ad8c8e139149a287865a90fa17e.asset/AssetData/PingFang.ttc"
TC_R, TC_M, TC_B = 2, 6, 10          # PingFang TC Regular / Medium / Semibold
def f(sz, idx=TC_M): return ImageFont.truetype(FONT, sz, index=idx)

W, H = 1080, 1350
BG    = (14, 14, 16)
GOLD  = (212, 175, 55)
RED   = (198, 54, 42)
WHITE = (245, 245, 245)
GREY  = (150, 150, 155)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# 頂部金線
d.rectangle([0, 0, W, 8], fill=GOLD)

# logo
logo = Image.open(Path.home()/".claude/skills/skill-xiao-bu/assets/logo.png").convert("RGBA")
logo.thumbnail((150, 150), Image.LANCZOS)
img.paste(logo, (int(W/2 - logo.width/2), 62), logo)

y = 62 + logo.height + 22
def center(text, yy, font, fill):
    w = d.textbbox((0,0), text, font=font)[2]
    d.text(((W-w)/2, yy), text, font=font, fill=fill)
    return yy

center("Sixhands Studio AI數字員工", y, f(30, TC_R), GREY); y += 54

# 主標
center("小簿", y, f(132, TC_B), WHITE); y += 162
center("Xiao Bu ／ 生意帳專員", y, f(34, TC_R), GOLD); y += 66

d.line([(150, y), (W-150, y)], fill=(60,60,66), width=2); y += 48

# 三個問題
center("我只回答老闆的三個問題", y, f(38, TC_M), GREY); y += 72

qs = [("1", "這個月到底賺不賺？", "連你的真實時薪一起算給你看"),
      ("2", "現金還能撐幾個月？", "低於 3 個月，該砍的不是行銷預算"),
      ("3", "該不該漲價？", "少掉幾 % 客人以內，你還是賺更多")]
for n, q, sub in qs:
    d.ellipse([132, y+6, 132+52, y+58], fill=RED)
    nb = d.textbbox((0,0), n, font=f(30, TC_B))
    d.text((132+26-nb[2]/2, y+16), n, font=f(30, TC_B), fill=WHITE)
    d.text((212, y), q, font=f(46, TC_B), fill=WHITE)
    d.text((212, y+62), sub, font=f(28, TC_R), fill=GREY)
    y += 120

y += 14
d.line([(150, y), (W-150, y)], fill=(60,60,66), width=2); y += 38

# 紅線
d.rectangle([132, y+4, 138, y+96], fill=RED)
d.text((162, y), "只做內部管理帳。不代理報稅、不出簽證財報、", font=f(29, TC_R), fill=(200,200,205))
d.text((162, y+42), "不設計節稅方案 —— 那是記帳士與會計師的法定業務。", font=f(29, TC_R), fill=(200,200,205))
y += 108

BANNER_TOP = H - 92
quote_f = f(33, TC_M)
qh = d.textbbox((0, 0), "帳", font=quote_f)[3]
assert y + qh < BANNER_TOP - 16, f"金句會被底部橫幅蓋到：y={y} 底線={BANNER_TOP}"
center("帳的價值不在漂亮，在你敢照著它做決定。", y, quote_f, GOLD)

# 底
d.rectangle([0, H-92, W, H], fill=(22,22,25))
center("叫一聲「小簿」，我就上工", H-64, f(31, TC_M), WHITE)
d.rectangle([0, H-6, W, H], fill=GOLD)

out = Path.home()/"Desktop/小簿_介紹卡.png"
img.save(out, "PNG")
print("✅", out, img.size)
