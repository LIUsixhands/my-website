# -*- coding: utf-8 -*-
"""產生 30:00 → 00:00 倒數待機影片（PIL 逐幀渲染 → 管線進 ffmpeg）。

為什麼用 PIL：homebrew 的 ffmpeg 沒有 drawtext filter（缺 libfreetype），
無法直接燒字，所以改用 PIL 畫每一幀再 pipe raw RGB24 給 ffmpeg 編碼。

產完後配免版權音樂（incompetech / Kevin MacLeod，CC-BY，避 Content ID）：
  ffmpeg -y -i countdown30_silent.mp4 -stream_loop -1 -i music.mp3 \
    -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 128k -ac 2 -t 1801 \
    -af "volume=0.85,afade=t=out:st=1797:d=4" countdown30.mp4
另存第一幀 30:00 當投影片 poster_frame_image。

用法：python make_countdown.py [輸出路徑] [分鐘數]
"""
import sys
import subprocess
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
BG = (18, 18, 22)        # INK 0x121216
GOLD = (232, 183, 74)    # 0xE8B74A
MIN = int(sys.argv[2]) if len(sys.argv) > 2 else 30
TOTAL = MIN * 60
OUT = sys.argv[1] if len(sys.argv) > 1 else "countdown_silent.mp4"
POSTER = OUT.rsplit(".", 1)[0] + "_poster.png"

big = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 360)


def render(sec):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    txt = f"{sec // 60:02d}:{sec % 60:02d}"
    bb = d.textbbox((0, 0), txt, font=big)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text(((W - tw) / 2 - bb[0], (H - th) / 2 - bb[1]), txt, font=big, fill=GOLD)
    return img


proc = subprocess.Popen(
    ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
     "-s", f"{W}x{H}", "-r", "1", "-i", "-",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "10",
     "-preset", "medium", "-crf", "28", OUT],
    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

for sec in range(TOTAL, -1, -1):
    img = render(sec)
    if sec == TOTAL:
        img.save(POSTER)
    proc.stdin.write(img.tobytes())

proc.stdin.close()
proc.wait()
print("countdown video:", OUT)
print("poster:", POSTER)
