#!/usr/bin/env python3
"""產生並驗證助哥的 QR Code 素材。

用法：python3 .claude/scripts/make_qr.py
需要：pip install segno opencv-python-headless

產出到 .claude/assets/qr/：PNG（數位）、SVG（印刷）、@2x（看板）、-mono（單色）。
每一張都會用 cv2 在多種縮放下驗證解碼，確保印小了也掃得到。
"""
import os, sys
try:
    import segno, cv2
except ImportError:
    sys.exit("請先執行：pip install segno opencv-python-headless")

OUT = ".claude/assets/qr"
FOREST = "#1F3A2E"          # 品牌森綠
ITEMS = [
    ("sixhands-tw",   "https://sixhands.tw",                     "網站"),
    ("line-sixhands", "https://line.me/R/ti/p/@080akczk",        "LINE 官方帳號"),
]

os.makedirs(OUT, exist_ok=True)
det = cv2.QRCodeDetector()
fail = False

for name, data, label in ITEMS:
    q = segno.make(data, error="h")          # H = 最高容錯，預留疊 logo 的空間
    q.save(f"{OUT}/{name}.png",      scale=16, border=4, dark=FOREST,   light="white")
    q.save(f"{OUT}/{name}.svg",      scale=16, border=4, dark=FOREST,   light="white")
    q.save(f"{OUT}/{name}@2x.png",   scale=40, border=4, dark=FOREST,   light="white")
    q.save(f"{OUT}/{name}-mono.svg", scale=16, border=4, dark="#000000", light="white")

    img = cv2.imread(f"{OUT}/{name}.png")
    results = []
    for s in (1.0, 0.5, 0.3, 0.2):           # 模擬印小後的可讀性
        small = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        text, _, _ = det.detectAndDecode(small)
        ok = (text == data)
        results.append((s, ok))
        if not ok:
            fail = True
    print(f"{label:14s} 版本{q.version}  " +
          " ".join(f"{int(s*100)}%{'OK' if ok else 'FAIL'}" for s, ok in results))
    print(f"               {data}")

sys.exit(1 if fail else 0)
