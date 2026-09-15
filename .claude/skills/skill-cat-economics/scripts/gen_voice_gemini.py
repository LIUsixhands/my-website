"""步驟三 配音 — 走 Google Gemini TTS（取代 MiniMax）。

為什麼不是 MiniMax：MiniMax 開發者平台會依地區把台灣使用者導到中國站，
註冊要中國手機號或微信，台灣帳號進不去。Gemini TTS 用的是步驟五生圖同一把
GOOGLE_API_KEY、同一個網域，不必再開一個帳號或多加一條網路白名單。

用法：
    python scripts/gen_voice_gemini.py --demo            # 先出 10-20 秒試聽
    python scripts/gen_voice_gemini.py                   # 確認音色後出全長
    python scripts/gen_voice_gemini.py --voice Aoede --style "冷靜、帶點嘲諷"

輸出 voiceover.mp3（--demo 則是 voiceover_demo.mp3），供步驟四產時間戳用。
"""
import argparse
import base64
import json
import os
import re
import struct
import subprocess
import sys
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SCRIPT = os.path.join(BASE_DIR, "cat_economics_script.txt")

MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

# 這個模型吃自然語言的語氣指示，是它取代 MiniMax 固定音色的關鍵：
# 音色本身換不回來，但語氣可以靠這句往「貓咪經濟學」的調性調。
DEFAULT_STYLE = "用台灣女生的口氣念，語速輕快，像在跟朋友聊八卦一樣帶點戲謔"
DEFAULT_VOICE = "Kore"

# 單次請求的文字上限沒有公告的硬數字，取保守值分段；分段點落在句末，
# 避免把一句話切兩半導致語調斷掉。
MAX_CHARS_PER_CHUNK = 1200
SENTENCE_END = "。！？!?\n"


def sanitize(text):
    """步驟三的輸入清洗：確保送出去的只有口播內容。

    腳本裡若殘留 [畫面：…]、(旁白) 或 Markdown 標題，TTS 會照字面念出來。
    """
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'（.*?）', '', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    return text.strip()


def split_chunks(text, limit=MAX_CHARS_PER_CHUNK):
    chunks, current = [], ""
    for char in text:
        current += char
        if len(current) >= limit and char in SENTENCE_END:
            chunks.append(current.strip())
            current = ""
    if current.strip():
        chunks.append(current.strip())
    return chunks


def synthesize(chunk, api_key, voice, style):
    payload = {
        "contents": [{"parts": [{"text": f"{style}：\n\n{chunk}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            },
        },
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.load(response)
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:500]
        sys.exit(f"Gemini TTS 回 HTTP {err.code}：{detail}\n"
                 f"  403/429 多半是這把 key 的免費額度不含 {MODEL}，或配額用完。")

    try:
        part = body["candidates"][0]["content"]["parts"][0]["inlineData"]
    except (KeyError, IndexError):
        sys.exit(f"回應裡沒有音訊，模型可能改了格式：{json.dumps(body)[:500]}")

    # mimeType 形如 audio/L16;codec=pcm;rate=24000 —— 取樣率要照它給的，寫死會變聲
    rate_match = re.search(r'rate=(\d+)', part.get("mimeType", ""))
    return base64.b64decode(part["data"]), int(rate_match.group(1)) if rate_match else 24000


def pcm_to_wav(pcm, rate, path, channels=1, sample_width=2):
    """模型回的是裸 PCM，沒有檔頭；補上 WAV 檔頭才餵得進 ffmpeg。"""
    byte_rate = rate * channels * sample_width
    header = b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVEfmt '
    header += struct.pack('<IHHIIHH', 16, 1, channels, rate, byte_rate,
                          channels * sample_width, sample_width * 8)
    header += b'data' + struct.pack('<I', len(pcm))
    with open(path, 'wb') as f:
        f.write(header + pcm)


def find_ffmpeg():
    from shutil import which
    exe = which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg
    except ImportError:
        sys.exit("找不到 ffmpeg。請安裝系統 ffmpeg，或 pip install imageio-ffmpeg")
    return imageio_ffmpeg.get_ffmpeg_exe()


def main():
    parser = argparse.ArgumentParser(description="貓咪經濟學配音（Gemini TTS）")
    parser.add_argument('--script', default=DEFAULT_SCRIPT, help="逐字稿路徑")
    parser.add_argument('--voice', default=DEFAULT_VOICE, help=f"聲音，預設 {DEFAULT_VOICE}")
    parser.add_argument('--style', default=DEFAULT_STYLE, help="語氣指示")
    parser.add_argument('--demo', action='store_true',
                        help="只念開頭 60 字出試聽檔，確認音色前必跑")
    parser.add_argument('--out', help="輸出 mp3 路徑")
    args = parser.parse_args()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        sys.exit("沒有 GOOGLE_API_KEY。請在環境設定裡填好後開新 session。")

    with open(args.script, encoding='utf-8') as f:
        text = sanitize(f.read())
    if not text:
        sys.exit(f"{args.script} 清洗後是空的")

    if args.demo:
        text = text[:60]
        out = args.out or os.path.join(BASE_DIR, "voiceover_demo.mp3")
        print(f"[試聽模式] 只念前 60 字：{text}")
    else:
        out = args.out or os.path.join(BASE_DIR, "voiceover.mp3")
        if len(text) < 100:
            print(f"警告：腳本只有 {len(text)} 字，確認一下是不是餵錯檔案。")

    chunks = split_chunks(text)
    print(f"[1/3] 送出 {len(chunks)} 段 / 共 {len(text)} 字，voice={args.voice}")

    pcm, rate = b"", 24000
    for i, chunk in enumerate(chunks, 1):
        audio, rate = synthesize(chunk, api_key, args.voice, args.style)
        pcm += audio
        print(f"      {i}/{len(chunks)} 完成（{len(audio)} bytes @ {rate}Hz）")

    wav_path = out + ".wav"
    pcm_to_wav(pcm, rate, wav_path)
    print(f"[2/3] PCM → WAV：{len(pcm)} bytes，約 {len(pcm) / (rate * 2):.1f} 秒")

    result = subprocess.run([find_ffmpeg(), '-y', '-i', wav_path, '-codec:a', 'libmp3lame',
                             '-q:a', '2', out], capture_output=True, text=True)
    os.remove(wav_path)
    if result.returncode != 0:
        print(result.stderr[-1500:], file=sys.stderr)
        sys.exit("轉 mp3 失敗")
    print(f"[3/3] 完成：{out}（{os.path.getsize(out) / 1024:.0f} KB）")


if __name__ == '__main__':
    main()
