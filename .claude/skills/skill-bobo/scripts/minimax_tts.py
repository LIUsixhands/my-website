#!/usr/bin/env python3
"""Minimax T2A v2 配音（台灣女聲），供 HeyGen 對嘴使用。

為什麼需要這支：HeyGen 內建的中文聲音多為大陸腔，台灣觀眾一秒出戲。
改用 Minimax 產台灣腔音檔，再讓 HeyGen 的 avatar 對嘴。

環境變數（與 skill-cat-economics 共用同一組）：
    MINIMAX_API_KEY    (必填)
    MINIMAX_GROUP_ID   (選填) 國際版多半不需要
    MINIMAX_VOICE_ID   (選填) 預設 female-shaonv（台灣女生音色）
    MINIMAX_MODEL      (選填) 預設 speech-02-hd
    MINIMAX_API_HOST   (選填) 預設 https://api.minimax.io
    MINIMAX_SPEED      (選填) 預設 1.0；短影音可調 1.05~1.15

用法：
    python3 minimax_tts.py 腳本.txt voiceover.mp3
    python3 minimax_tts.py --text "先講結論。" demo.mp3

註：skill-cat-economics/scripts/gen_taiwan_speech.py 是同一套 API 的另一份實作，
   服務它自己的動畫產線。兩邊刻意不互相 import，避免跨 skill 耦合。
"""
import argparse
import os
import re
import sys

try:
    import requests
except ImportError:
    sys.exit("❌ 缺少套件 requests。請確認 setup script 已執行。")

API_KEY = os.getenv("MINIMAX_API_KEY")
GROUP_ID = os.getenv("MINIMAX_GROUP_ID")
VOICE_ID = os.getenv("MINIMAX_VOICE_ID", "female-shaonv")
MODEL = os.getenv("MINIMAX_MODEL", "speech-02-hd")
API_HOST = os.getenv("MINIMAX_API_HOST", "https://api.minimax.io")
SPEED = float(os.getenv("MINIMAX_SPEED", "1.0"))


def sanitize(text):
    """移除非口播內容：[畫面]、(旁白)、（備註）、# 標題、字幕標記。"""
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"（.*?）", "", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    return re.sub(r"\n{2,}", "\n", text).strip()


def _attempt(url, payload, headers):
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
    except Exception as e:
        return None, f"連線失敗：{e}（網路被擋的話，白名單要加 *.minimax.io）"
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}：{resp.text[:300]}"
    try:
        data = resp.json()
    except Exception:
        return None, f"回應不是 JSON：{resp.text[:200]}"
    base = data.get("base_resp") or {}
    code = base.get("status_code")
    if code not in (0, None):
        return None, f"Minimax 錯誤 {code} - {base.get('status_msg')}"
    audio_hex = (data.get("data") or {}).get("audio")
    if not audio_hex:
        return None, f"回應沒有音檔：{str(data)[:200]}"
    try:
        return bytes.fromhex(audio_hex), None
    except ValueError:
        return None, "音檔解碼失敗（非 hex）"


def synthesize(text, output_file):
    """產生 mp3，成功回傳路徑，失敗回傳 None。"""
    if not API_KEY:
        print("❌ 找不到 MINIMAX_API_KEY，請在環境設定填入並存檔（新 session 才生效）。")
        return None

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "text": text,
        "stream": False,
        "voice_setting": {"voice_id": VOICE_ID, "speed": SPEED, "vol": 1.0, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
    }

    # 國際版多半「不帶 GroupId」即可；帶錯的 GroupId 會出現 1004。依序試。
    base_url = f"{API_HOST}/v1/t2a_v2"
    variants = [("不帶 GroupId", base_url)]
    if GROUP_ID:
        variants.append((f"帶 GroupId={GROUP_ID}", f"{base_url}?GroupId={GROUP_ID}"))

    print(f"🎙️ Minimax｜模型 {MODEL}｜音色 {VOICE_ID}｜語速 {SPEED}｜{len(text)} 字")
    errors = []
    for label, url in variants:
        audio, err = _attempt(url, payload, headers)
        if audio:
            with open(output_file, "wb") as f:
                f.write(audio)
            print(f"✅ 配音完成（{label}）：{output_file}（{len(audio)//1024} KB）")
            return output_file
        print(f"   ✗ {label}：{err}")
        errors.append(f"{label}: {err}")

    print("❌ 全部寫法都失敗：")
    for e in errors:
        print("   -", e)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script", nargs="?", help="腳本檔路徑")
    ap.add_argument("output", nargs="?", default="voiceover.mp3")
    ap.add_argument("--text", help="直接給文字（優先於 script）")
    a = ap.parse_args()

    if a.text:
        text = sanitize(a.text)
    elif a.script and os.path.exists(a.script):
        with open(a.script, encoding="utf-8") as f:
            text = sanitize(f.read())
    else:
        sys.exit("❌ 請提供腳本檔或 --text。")

    if not text:
        sys.exit("❌ 清乾淨之後沒有可唸的內容（整篇都是 [畫面] 之類的標記？）")

    sys.exit(0 if synthesize(text, os.path.join(os.getcwd(), a.output)) else 1)


if __name__ == "__main__":
    main()
