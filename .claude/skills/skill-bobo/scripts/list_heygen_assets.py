#!/usr/bin/env python3
"""列出 HeyGen 可用的「主播角色」與「聲音」，方便挑 ID 設定。

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
    r = requests.get(f"{API}/v2/avatars", headers=headers(), timeout=60)
    avatars = r.json().get("data", {}).get("avatars", [])
    print(f"\n=== 主播角色(共 {len(avatars)} 個，顯示前 {limit}) ===")
    for a in avatars[:limit]:
        print(f"  avatar_id={a.get('avatar_id')} ｜ {a.get('avatar_name')}")


def main():
    if not API_KEY:
        print("❌ 找不到 HEYGEN_API_KEY。請在環境設定填入並存檔（新 session 才生效）。")
        sys.exit(1)
    all_voices = "--all-voices" in sys.argv
    list_voices(all_voices)
    list_avatars()
    print("\n挑好後，把 avatar_id 和 voice_id 設成環境變數 HEYGEN_AVATAR_ID / HEYGEN_VOICE_ID。")


if __name__ == "__main__":
    main()
