#!/usr/bin/env python3
"""用 HeyGen API 生成 AI 主播影片（文字 → 虛擬主播口播 mp4）。

流程：送出生成請求 → 輪詢狀態 → 完成後下載 mp4。

必填環境變數：
    HEYGEN_API_KEY        HeyGen 後台 Settings → API 取得（付費方案）
選填環境變數：
    HEYGEN_AVATAR_ID      現成主播角色 ID（用 list_heygen_assets.py 查）
    HEYGEN_TALKING_PHOTO_ID
                          自訂 Photo Avatar ID（用 upload_talking_photo.py 建立）。
                          有設定時優先於 HEYGEN_AVATAR_ID —— 這是讓虛擬人物用
                          「自己的臉」而不是跟別人共用現成主播的方式。
    HEYGEN_VOICE_ID       HeyGen 內建聲音 ID。⚠️ HeyGen 的中文聲音多為大陸腔，
                          台灣角色請改用 --minimax（Minimax 台灣女聲對嘴）。
    HEYGEN_WIDTH          預設 720
    HEYGEN_HEIGHT         預設 1280（9:16 直式；橫式可設 1280x720）

用法：
    # HeyGen 內建聲音（大陸腔，台灣角色不建議）
    python3 heygen_generate.py 腳本.txt out.mp4

    # 台灣腔：Minimax 產音檔 → 上傳 HeyGen → avatar 對嘴（推薦）
    python3 heygen_generate.py 腳本.txt out.mp4 --minimax

    # 已經有音檔了，直接用
    python3 heygen_generate.py 腳本.txt out.mp4 --audio voiceover.mp3
"""
import argparse
import json
import os
import subprocess
import sys
import time

try:
    import requests
except ImportError:
    print("❌ 缺少套件 requests。請確認 setup script 已安裝。")
    sys.exit(1)

API = "https://api.heygen.com"
UPLOAD = "https://upload.heygen.com/v1/asset"
API_KEY = os.getenv("HEYGEN_API_KEY")
AVATAR_ID = os.getenv("HEYGEN_AVATAR_ID")
TALKING_PHOTO_ID = os.getenv("HEYGEN_TALKING_PHOTO_ID")
VOICE_ID = os.getenv("HEYGEN_VOICE_ID")
WIDTH = int(os.getenv("HEYGEN_WIDTH", "720"))
HEIGHT = int(os.getenv("HEYGEN_HEIGHT", "1280"))


def headers():
    return {"X-Api-Key": API_KEY, "Content-Type": "application/json"}



def upload_audio(path):
    """把 mp3/wav 上傳到 HeyGen，取得 audio_asset_id。"""
    ext = os.path.splitext(path)[1].lower()
    mime = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}.get(ext)
    if not mime:
        sys.exit(f"❌ 不支援的音檔格式 {ext}（支援 mp3 / wav / m4a）")
    if not os.path.exists(path):
        sys.exit(f"❌ 找不到音檔：{path}")

    print(f"⬆️ 上傳音檔到 HeyGen（{os.path.getsize(path) // 1024} KB）…")
    with open(path, "rb") as f:
        r = requests.post(UPLOAD, headers={"X-Api-Key": API_KEY, "Content-Type": mime},
                          data=f.read(), timeout=180)
    if r.status_code != 200:
        print(f"❌ 音檔上傳失敗 HTTP {r.status_code}：{r.text[:500]}")
        sys.exit(1)
    try:
        payload = r.json()
    except ValueError:
        sys.exit(f"❌ 回應不是 JSON：{r.text[:400]}")

    data = payload.get("data") or {}
    asset_id = data.get("id") or data.get("asset_id")
    if not asset_id:
        print("⚠️ 上傳成功但找不到 asset id，完整回應如下（貼給我我幫你看）：")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:1200])
        sys.exit(1)
    print(f"✅ 音檔已上傳，asset_id = {asset_id}")
    return asset_id


def run_minimax(text, out_mp3):
    """呼叫同目錄的 minimax_tts.py 產台灣腔音檔。"""
    tts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "minimax_tts.py")
    if not os.path.exists(tts):
        sys.exit("❌ 找不到 minimax_tts.py（應與本檔同目錄）")
    print("🎙️ 交給 Minimax 產台灣腔配音…")
    rc = subprocess.call([sys.executable, tts, "--text", text, out_mp3])
    if rc != 0 or not os.path.exists(out_mp3):
        sys.exit("❌ Minimax 配音失敗，先解決配音再產影片。")
    return out_mp3


def character(photo_id=None):
    """Photo Avatar（自己的臉）優先；沒有才用現成主播。"""
    tp = photo_id or TALKING_PHOTO_ID
    if tp:
        return {"type": "talking_photo", "talking_photo_id": tp}
    return {"type": "avatar", "avatar_id": AVATAR_ID, "avatar_style": "normal"}


def submit(text, photo_id=None, audio_asset_id=None):
    if not audio_asset_id and not VOICE_ID:
        print("❌ 請設定 HEYGEN_VOICE_ID，或改用 --minimax / --audio 提供音檔。")
        sys.exit(1)
    if not (photo_id or TALKING_PHOTO_ID or AVATAR_ID):
        print("❌ 請設定 HEYGEN_TALKING_PHOTO_ID（自訂人物，用 upload_talking_photo.py 建立）"
              "或 HEYGEN_AVATAR_ID（現成主播）。")
        sys.exit(1)
    char = character(photo_id)
    kind = "自訂 Photo Avatar" if char["type"] == "talking_photo" else "現成主播"
    if audio_asset_id:
        voice = {"type": "audio", "audio_asset_id": audio_asset_id}
        print(f"🎭 使用{kind}｜🔊 外部音檔對嘴（台灣腔）")
    else:
        voice = {"type": "text", "input_text": text, "voice_id": VOICE_ID}
        print(f"🎭 使用{kind}｜🔊 HeyGen 內建聲音")
    body = {
        "video_inputs": [{"character": char, "voice": voice}],
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
    p = argparse.ArgumentParser()
    p.add_argument("script", nargs="?", help="腳本檔路徑")
    p.add_argument("--text", help="直接給文字（優先於 script）")
    p.add_argument("output", nargs="?", default="heygen_video.mp4")
    p.add_argument("--photo-id", help="這次改用指定的 Photo Avatar ID（蓋過環境變數）")
    p.add_argument("--minimax", action="store_true",
                   help="先用 Minimax 產台灣腔配音再對嘴（台灣角色建議一律加）")
    p.add_argument("--audio", help="直接指定現成音檔（mp3/wav/m4a），跳過 TTS")
    args = p.parse_args()

    # 金鑰檢查放在解析參數之後，這樣 --help 在沒設金鑰時也看得到
    if not API_KEY:
        sys.exit("❌ 找不到 HEYGEN_API_KEY，請在環境設定填入並存檔（新 session 才生效）。")

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

    audio_path = args.audio
    if args.minimax and not audio_path:
        audio_path = run_minimax(text, os.path.splitext(args.output)[0] + ".mp3")
    audio_asset_id = upload_audio(audio_path) if audio_path else None

    vid = submit(text, args.photo_id, audio_asset_id)
    wait_and_download(vid, os.path.join(os.getcwd(), args.output))


if __name__ == "__main__":
    main()
