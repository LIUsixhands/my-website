"""步驟 2：每一鏡的首幀（帶角色定裝圖＋場景圖當參考）
- kf（首尾幀）鏡頭另外生尾幀 sXX_end.png：用 end_img 描述，並把首幀也當參考，鎖住同一個構圖與光線
用法：python3 gen_frames.py [s01 s02 ...]   （不給就全部；已存在的跳過）
跑完會輸出 out/frames_sheet.jpg 總表，目視檢查。"""
import sys
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from common import ROOT, EP, gemini_image, shots

R, F = ROOT / "refs", ROOT / "frames"
only = set(sys.argv[1:])


def frame(sh):
    if sh["type"] == "hold":   # 定格鏡頭沿用上一鏡最後一格，不用生圖
        return
    cs = EP["characters"]
    who = " ".join(f"Character {i+1} (see reference sheet {i+1}): {cs[c]['desc']}." for i, c in enumerate(sh["chars"]))
    rule = ("Only the characters described appear clearly; background people are small and blurred. "
            "No text, no signage, no brand logos on any object.")
    refs = [R / f"{c}.png" for c in sh["chars"]] + [R / "location.png"]
    prompt = (f"{EP['style']} Use the attached character reference sheets to keep every character's face, hair, age and outfit EXACTLY the same. "
              f"The last attached image is the location reference: keep the same interior. {who} Scene: {sh['img']} {rule}")
    first = gemini_image(prompt, F / f"{sh['id']}.png", refs=refs)
    if sh["type"] == "kf":
        prompt = (f"{EP['style']} Use the attached character reference sheets to keep every character's face, hair, age and outfit EXACTLY the same. "
                  "The last attached image is the FIRST FRAME of this same shot: keep the exact same camera angle, framing, lens, lighting, "
                  f"background and props, only the action changes. {who} Scene (end of the shot): {sh['end_img']} {rule}")
        gemini_image(prompt, F / f"{sh['id']}_end.png", refs=refs[:-1] + [first])
    print("ok", sh["id"])


with ThreadPoolExecutor(6) as ex:
    for f in [ex.submit(frame, sh) for sh in shots(only)]:
        f.result()

fs = [f for s in EP["shots"] for f in (F / f"{s['id']}.png", F / f"{s['id']}_end.png") if f.exists()]
cols = 7
sheet = Image.new("RGB", (256 * cols, 455 * ((len(fs) + cols - 1) // cols)), "white")
for i, f in enumerate(fs):
    sheet.paste(Image.open(f).convert("RGB").resize((256, 455)), ((i % cols) * 256, (i // cols) * 455))
sheet.save(ROOT / "out" / "frames_sheet.jpg", quality=85)
print("👀 下一步：看 out/frames_sheet.jpg ── 對白鏡頭臉要夠大、不要出現多餘的人、物品上不能有品牌 logo")
