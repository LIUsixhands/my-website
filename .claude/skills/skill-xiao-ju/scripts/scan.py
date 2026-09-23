"""步驟 5b（必跑）：逐格掃描。把每鏡「實際會用到的秒數」每 0.4 秒抽一格排成總表 out/scan_*.jpg
要人眼找：亂碼字／假字幕、品牌 logo（蘋果、微信…）、多手指、物件突然變形、多出來的人、臉走樣
會套用 episode.json 的 fixes（pick 換版、slow 只取前段），看到的就是成片會用的畫面"""
import subprocess
from PIL import Image, ImageDraw, ImageFont
from common import ROOT, FIX
from timeline import build

C, O = ROOT / "clips", ROOT / "out"
TW, TH, STEP, PER = 150, 267, 0.4, 5
PICK, SLOW = FIX.get("pick", {}), FIX.get("slow", {})
try:
    f = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 28)
except Exception:
    f = ImageFont.load_default()
rows = []
for x in build():
    name = PICK.get(x["id"], x["id"])
    used = x["dur"] * SLOW.get(x["id"], 1.0)   # 放慢的鏡頭只用到來源的前段
    n = max(1, int(used / STEP))
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(C / f"{name}.mp4"), "-t", f"{used:.2f}",
                                   "-vf", f"fps={1/STEP},scale={TW}:{TH}", "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    fr = [Image.frombytes("RGB", (TW, TH), raw[i:i + TW * TH * 3]) for i in range(0, len(raw) - TW * TH * 3 + 1, TW * TH * 3)]
    row = Image.new("RGB", (100 + TW * max(1, len(fr)), TH), "black")
    ImageDraw.Draw(row).text((8, 10), name, fill="yellow", font=f)
    for i, im in enumerate(fr):
        row.paste(im, (100 + i * TW, 0))
    rows.append(row)
for k in range(0, len(rows), PER):
    part = rows[k:k + PER]
    sheet = Image.new("RGB", (max(r.width for r in part), (TH + 6) * len(part)), "red")
    for i, r in enumerate(part):
        sheet.paste(r, (0, i * (TH + 6)))
    sheet.save(O / f"scan_{k // PER}.jpg", quality=82)
    print(O / f"scan_{k // PER}.jpg")
print("🔍 有問題的鏡頭三種修法：①換 OmniHuman 版（gen_video.py --omni sXX，再把 fixes.pick 設 sXX_omni）"
      "②字出在邊緣就裁掉（fixes.crop_top）③後段才壞就只取前段放慢（fixes.slow，0.6–0.8）；都不行就刪 clips/sXX.mp4 重生")
