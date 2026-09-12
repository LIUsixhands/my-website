#!/usr/bin/env python3
"""列出 HeyGen 可用的角色與聲音，方便挑 ID 設定。

會列出兩種角色：
  ⭐ 你自己的 Photo Avatar（talking_photos）—— 虛擬人物 IP 要用這個
     臉只有你有，用 HeyGen 網頁 Avatar → Create a virtual character 建立
  現成主播（avatars）—— 臉與其他 HeyGen 用戶共用

不要從網址列抄 ID：那串是網頁用的，且人眼容易把 0/O、1/l 看錯。
用本工具查出來的才是 API 要的 ID。

預設只列出中文/台灣相關的聲音，方便找台灣女聲。

用法：
    python list_heygen_assets.py            # 列中文聲音 + 前 20 個主播
    python list_heygen_assets.py --all-voices   # 列全部聲音
"""
import os
import sys

try:
    import requests
except ImportError:
    print("❌ 缺少套件 requests。")
    sys.exit(1)

API = "https://api.heygen.com"
API_KEY = os.getenv("HEYGEN_API_KEY")


def headers():
    return {"X-Api-Key": API_KEY}


def list_voices(all_voices=False):
    r = requests.get(f"{API}/v2/voices", headers=headers(), timeout=60)
    voices = r.json().get("data", {}).get("voices", [])
    print(f"\n=== 聲音(共 {len(voices)} 個){'' if all_voices else '，只顯示中文相關'} ===")
    count = 0
    for v in voices:
        lang = (v.get("language") or "").lower()
        name = v.get("name") or ""
        is_zh = "chinese" in lang or "mandarin" in lang or "taiwan" in lang or "中文" in name
        if all_voices or is_zh:
            gender = v.get("gender", "")
            print(f"  voice_id={v.get('voice_id')} ｜ {name} ｜ {v.get('language')} ｜ {gender}")
            count += 1
    if count == 0:
        print("  （沒找到中文聲音，試試 --all-voices 看全部）")


def list_avatars(limit=20):
    """/v2/avatars 同時回傳現成主播(avatars)與自訂 Photo Avatar(talking_photos)。"""
    r = requests.get(f"{API}/v2/avatars", headers=headers(), timeout=180)
    data = r.json().get("data", {}) or {}

    # 自訂 Photo Avatar 先列 —— 虛擬人物 IP 要用的是這個，不是共用的現成主播
    photos = data.get("talking_photos", []) or []
    print(f"\n=== ⭐ 你自己的 Photo Avatar(共 {len(photos)} 個) ===")
    if photos:
        for t in photos:
            name = t.get("talking_photo_name") or "(未命名)"
            print(f"  HEYGEN_TALKING_PHOTO_ID={t.get('talking_photo_id')} ｜ {name}")
    else:
        print("  （沒有。用 HeyGen 網頁 Avatar → Create a virtual character 建立）")

    avatars = data.get("avatars", []) or []
    print(f"\n=== 現成主播(共 {len(avatars)} 個，顯示前 {limit}；臉與其他用戶共用) ===")
    for a in avatars[:limit]:
        print(f"  HEYGEN_AVATAR_ID={a.get('avatar_id')} ｜ {a.get('avatar_name')}")


def main():
    if not API_KEY:
        print("❌ 找不到 HEYGEN_API_KEY。請在環境設定填入並存檔（新 session 才生效）。")
        sys.exit(1)
    all_voices = "--all-voices" in sys.argv
    list_voices(all_voices)
    list_avatars()
    print("\n把上面印出來的整行（例如 HEYGEN_TALKING_PHOTO_ID=xxx）設進環境設定即可。")
    print("台灣角色的聲音建議走 Minimax（見 SKILL.md），不用設 HEYGEN_VOICE_ID。")


if __name__ == "__main__":
    main()
