#!/usr/bin/env python3
"""Minimax 國際版 (t2a_v2) 配音生成。

讀取逐字稿 → 呼叫 Minimax T2A v2 → 輸出 mp3。
支援台灣女生音色，可用環境變數覆寫設定。

環境變數：
    MINIMAX_API_KEY    (必填) sk- 開頭的金鑰
    MINIMAX_GROUP_ID   (必填) 帳號 UID / GroupId
    MINIMAX_VOICE_ID   (選填) 預設 female-shaonv（貓咪經濟學經典台灣女生音色）
    MINIMAX_MODEL      (選填) 預設 speech-02-hd
    MINIMAX_API_HOST   (選填) 預設 https://api.minimax.io（西美可改 https://api-uw.minimax.io）

用法：
    python gen_taiwan_speech.py            # 讀腳本全文 → voiceover.mp3
    python gen_taiwan_speech.py --demo     # 只唸前一句 → voiceover_demo.mp3（試聽用）
    python gen_taiwan_speech.py <腳本路徑> [輸出.mp3]
"""
import os
import re
import sys

try:
    import requests
except ImportError:
    print("❌ 缺少套件 requests。請確認 setup script 已執行：pip install requests")
    sys.exit(1)

API_KEY = os.getenv("MINIMAX_API_KEY")
GROUP_ID = os.getenv("MINIMAX_GROUP_ID")
VOICE_ID = os.getenv("MINIMAX_VOICE_ID", "female-shaonv")
MODEL = os.getenv("MINIMAX_MODEL", "speech-02-hd")
API_HOST = os.getenv("MINIMAX_API_HOST", "https://api.minimax.io")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCRIPT = os.path.join(BASE_DIR, "..", "貓咪經濟學腳本.txt")


def sanitize(text):
    """移除非口播內容（[畫面]、(旁白)、# 標題），確保 TTS 只唸台詞。"""
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"（.*?）", "", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    return text.strip()


def first_sentence(text):
    for sep in ["。", "！", "？", "\n"]:
        if sep in text:
            return text.split(sep)[0] + sep
    return text[:60]


def synthesize(text, output_file):
    if not API_KEY or not GROUP_ID:
        print("❌ 找不到 MINIMAX_API_KEY 或 MINIMAX_GROUP_ID。請確認環境設定已填入並存檔，且這是新開的 session。")
        return False

    url = f"{API_HOST}/v1/t2a_v2?GroupId={GROUP_ID}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": VOICE_ID,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }

    print(f"🎙️ 模型 {MODEL}｜音色 {VOICE_ID}｜字數 {len(text)}")
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
    except Exception as e:
        print(f"❌ 連線失敗：{e}")
        print("   （若是網路被擋，請確認環境網路白名單已加入 *.minimax.io）")
        return False

    if resp.status_code != 200:
        print(f"❌ HTTP {resp.status_code}：{resp.text[:500]}")
        return False

    try:
        data = resp.json()
    except Exception:
        print(f"❌ 回應不是 JSON：{resp.text[:300]}")
        return False

    base = data.get("base_resp", {})
    if base.get("status_code") not in (0, None):
        print(f"❌ Minimax 回報錯誤：{base.get('status_code')} - {base.get('status_msg')}")
        print(f"   完整回應：{str(data)[:400]}")
        return False

    audio_hex = (data.get("data") or {}).get("audio")
    if not audio_hex:
        print(f"❌ 回應沒有音檔內容：{str(data)[:400]}")
        return False

    try:
        audio_bytes = bytes.fromhex(audio_hex)
    except ValueError:
        print("❌ 音檔解碼失敗（非 hex 格式）。")
        return False

    with open(output_file, "wb") as f:
        f.write(audio_bytes)
    print(f"✅ 配音完成：{output_file}（{len(audio_bytes)//1024} KB）")
    return True


def main():
    args = [a for a in sys.argv[1:]]
    demo = "--demo" in args
    args = [a for a in args if a != "--demo"]

    script_path = args[0] if args else DEFAULT_SCRIPT
    if not os.path.exists(script_path):
        print(f"⚠️ 找不到腳本 {script_path}，改用測試句。")
        text = "歡迎來到貓咪經濟學，今天我們聊聊爪爪稅大戰。"
        out = args[1] if len(args) > 1 else "voiceover_demo.mp3"
    else:
        with open(script_path, "r", encoding="utf-8") as f:
            text = sanitize(f.read())
        if demo:
            text = first_sentence(text)
            out = args[1] if len(args) > 1 else "voiceover_demo.mp3"
            print("（試聽模式：只唸第一句）")
        else:
            out = args[1] if len(args) > 1 else "voiceover.mp3"

    synthesize(text, os.path.join(os.getcwd(), out))


if __name__ == "__main__":
    main()
