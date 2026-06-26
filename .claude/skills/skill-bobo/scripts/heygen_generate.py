#!/usr/bin/env python3
"""用 HeyGen API 生成 AI 主播影片（文字 → 虛擬主播口播 mp4）。

流程：送出生成請求 → 輪詢狀態 → 完成後下載 mp4。

必填環境變數：
    HEYGEN_API_KEY        HeyGen 後台 Settings → API 取得（付費方案）
選填環境變數：
    HEYGEN_AVATAR_ID      主播角色 ID（用 list_heygen_assets.py 查）
    HEYGEN_VOICE_ID       聲音 ID（挑中文/台灣女聲）
    HEYGEN_WIDTH          預設 720
    HEYGEN_HEIGHT         預設 1280（9:16 直式；橫式可設 1280x720）

用法：
    python heygen_generate.py 腳本.txt [輸出.mp4]
    python heygen_generate.py --text "直接給一段文字"
"""
import argparse
import os
import sys
import time

try:
    import requests
except ImportError:
    print("❌ 缺少套件 requests。請確認 setup script 已安裝。")
    sys.exit(1)

API = "https://api.heygen.com"
API_KEY = os.getenv("HEYGEN_API_KEY")
AVATAR_ID = os.getenv("HEYGEN_AVATAR_ID")
VOICE_ID = os.getenv("HEYGEN_VOICE_ID")
WIDTH = int(os.getenv("HEYGEN_WIDTH", "720"))
HEIGHT = int(os.getenv("HEYGEN_HEIGHT", "1280"))


def headers():
    return {"X-Api-Key": API_KEY, "Content-Type": "application/json"}


def submit(text):
    if not (AVATAR_ID and VOICE_ID):
        print("❌ 請先設定 HEYGEN_AVATAR_ID 與 HEYGEN_VOICE_ID（用 list_heygen_assets.py 查）。")
        sys.exit(1)
    body = {
        "video_inputs": [
            {
                "character": {"type": "avatar", "avatar_id": AVATAR_ID, "avatar_style": "normal"},
                "voice": {"type": "text", "input_text": text, "voice_id": VOICE_ID},
            }
        ],
        "dimension": {"width": WIDTH, "height": HEIGHT},
    }
    r = requests.post(f"{API}/v2/video/generate", headers=headers(), json=body, timeout=60)
    if r.status_code != 200:
        print(f"❌ 送出失敗 HTTP {r.status_code}：{r.text[:400]}")
        sys.exit(1)
    data = r.json()
    if data.get("error"):
        print(f"❌ HeyGen 回報錯誤：{data['error']}")
        sys.exit(1)
    vid = data["data"]["video_id"]
    print(f"✅ 已送出生成，video_id = {vid}")
    return vid


def wait_and_download(video_id, output):
    print("⏳ 生成中（通常數十秒到幾分鐘）…")
    while True:
        r = requests.get(f"{API}/v1/video_status.get?video_id={video_id}", headers=headers(), timeout=60)
        d = r.json().get("data", {})
        status = d.get("status")
        if status == "completed":
            url = d.get("video_url")
            print("⬇️ 完成，下載中…")
            vid_data = requests.get(url, timeout=300)
            with open(output, "wb") as f:
                f.write(vid_data.content)
            print(f"✅ 影片已存：{output}（{len(vid_data.content)//1024} KB）")
            return True
        if status == "failed":
            print(f"❌ 生成失敗：{d.get('error')}")
            return False
        print(f"   狀態：{status}…")
        time.sleep(15)


def main():
    if not API_KEY:
        print("❌ 找不到 HEYGEN_API_KEY，請在環境設定填入並存檔（新 session 才生效）。")
        sys.exit(1)
    p = argparse.ArgumentParser()
    p.add_argument("script", nargs="?", help="腳本檔路徑")
    p.add_argument("--text", help="直接給文字（優先於 script）")
    p.add_argument("output", nargs="?", default="heygen_video.mp4")
    args = p.parse_args()

    if args.text:
        text = args.text
    elif args.script and os.path.exists(args.script):
        with open(args.script, encoding="utf-8") as f:
            text = f.read().strip()
    else:
        print("❌ 請提供腳本檔或 --text。")
        sys.exit(1)

    if len(text) > 1500:
        print(f"⚠️ 文字 {len(text)} 字，HeyGen 單次上限約 1500 字，可能需分段。先嘗試送出…")

    vid = submit(text)
    wait_and_download(vid, os.path.join(os.getcwd(), args.output))


if __name__ == "__main__":
    main()
