#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小曲 · 成片驗收（抽幀拼圖 + 音畫長度）

程式抓不到「缺字變空白」「字幕壓到臉」「角落有違禁物」這類問題，
所以這支的產物是**給你用眼睛看的**一張拼圖。沒看過就不算做完。

用法：
    python3 check_frames.py out/final.mp4
    python3 check_frames.py out/final.mp4 --n 24
"""
import sys, subprocess, pathlib, math
from PIL import Image

def main():
    if len(sys.argv) < 2:
        sys.exit("用法：python3 check_frames.py out/final.mp4 [--n 幀數]")
    mp4 = pathlib.Path(sys.argv[1]).resolve()
    if not mp4.exists():
        sys.exit(f"❌ 找不到 {mp4}")
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 20

    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                           "stream=codec_type,duration:format=duration",
                           "-of", "default=nw=1", str(mp4)],
                          capture_output=True, text=True).stdout
    print(info)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(mp4)],
                               capture_output=True, text=True).stdout.strip())

    out = mp4.parent.parent / "check"
    out.mkdir(exist_ok=True)
    for f in out.glob("f*.jpg"):
        f.unlink()

    ims = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        p = out / f"f{i:02d}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
                        "-i", str(mp4), "-frames:v", "1", "-q:v", "3", str(p)], check=True)
        ims.append((t, Image.open(p).convert("RGB")))

    cols = 5
    rows = math.ceil(n / cols)
    tw_, th_ = 360, int(360 * ims[0][1].height / ims[0][1].width)
    sheet = Image.new("RGB", (cols * tw_, rows * th_), (20, 20, 22))
    for i, (t, im) in enumerate(ims):
        sheet.paste(im.resize((tw_, th_), Image.LANCZOS), ((i % cols) * tw_, (i // cols) * th_))
    sp = out / "contact_sheet.jpg"
    sheet.save(sp, quality=92)

    print(f"\n✅ 抽幀拼圖：{sp}")
    print(f"   總長 {dur:.2f}s，抽 {n} 幀\n")
    print("用眼睛逐格檢查（程式抓不到這些）：")
    for c in ["中文有沒有變空白／豆腐格（缺字）",
              "字幕有沒有切邊、壓到人臉、超出安全區",
              "有沒有違禁畫面（刀械、槍、菸酒、他人肖像、競品 logo）— 每個裁切鏡位都要重看",
              "尾卡的電話／LINE／地址逐字對客戶原文",
              "人臉、產品有沒有被 Ken Burns 推到裁掉",
              "AI 生圖有沒有翻車（手指、文字亂碼、人種漂走）"]:
        print(f"   [ ] {c}")

if __name__ == "__main__":
    main()
