#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_short.py — 短影片自動化產線 Demo
AI數字員工龍蝦學院 ▎ 實戰訓練營 第 7 堂

一個指令，把「選題 → 腳本 → 配音 → 畫面 → 合成」跑成一支 9:16 短影片。

設計成「零 API 金鑰也能跑」，方便上課現場 demo：
  • 沒有 LLM 金鑰 → 用內建範例腳本（或讀 scenes.json）
  • 沒有 TTS 金鑰 → 用 macOS 內建 `say`（美佳 台灣中文）配音
  • 沒有生圖金鑰 → 用 Pillow 生品牌占位畫面
有金鑰時，把對應函數換成真的 API 即可（README 有說明）。

用法（在你想存放成品的資料夾裡執行）：
  python3 /path/to/make_short.py "AI 如何讓小店營收翻倍"
  python3 /path/to/make_short.py            # 用內建範例主題

輸出與素材都讀寫「目前工作目錄（CWD）」，不是腳本所在位置：
  • 成品：    ./final.mp4
  • 中間檔：  ./build/
  • 自訂腳本：./scenes.json（存在就優先讀）
  • 背景音樂：./assets/bgm.mp3（存在就自動混入）
"""
import os, sys, json, subprocess, textwrap

ROOT = os.getcwd()                       # 在哪裡執行，就把成品產在哪裡
WORK = os.path.join(ROOT, "build")
W, H, FPS = 1080, 1920, 25
BRAND = "AI數字員工龍蝦學院"
LOGO = "/Users/chenyunung/.claude/skills/skill-ai-lobster-brand/logo.png"

# 品牌色
NAVY=(22,31,51); NAVY2=(31,43,69); ORANGE=(232,85,45); GOLD=(242,177,60)
CREAM=(251,247,239); WHITE=(255,255,255)

# 中文字型自動偵測 — 必須是「繁體」字面，否則龍/蝦/學/數 等字會變空白。
# 每項 = (檔案路徑, ttc 內的字面 index)
FONT_CANDIDATES = [
    ("/System/Library/Fonts/PingFang.ttc", 0),           # PingFang TC（若存在最佳）
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),     # Heiti TC Medium（繁體、黑體）
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 2),# Songti TC Bold（繁體、宋體）
    ("/Library/Fonts/Arial Unicode.ttf", 0),
]
def find_font():
    from PIL import ImageFont
    for path, idx in FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            ImageFont.truetype(path, 40, index=idx)
            return (path, idx)
        except Exception:
            continue
    return None
FONT = find_font()   # (path, index) 或 None

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def sh(cmd):
    r = run(cmd)
    if r.returncode != 0:
        print("  ⚠️ 指令失敗：", " ".join(cmd[:3]), "...")
        print(r.stderr[-400:])
    return r

# ───────────────────────── 1) 腳本 ─────────────────────────
SAMPLE_SCENES = [
    {"narration": "你的店，其實一直在漏錢。",        "visual": "夜晚的小店外觀"},
    {"narration": "不是生意不好，是沒人幫你接住客人。", "visual": "店員忙到分身乏術"},
    {"narration": "AI 員工 24 小時自動回訊息、不漏單。", "visual": "手機上的聊天介面"},
    {"narration": "同樣的客流，營收可以多三成。",      "visual": "向上成長的曲線"},
    {"narration": "想知道怎麼做？留言「AI」我教你。",   "visual": "明亮的行動呼籲畫面"},
]

def get_scenes(topic):
    """Step 1-2：生成分鏡腳本 JSON。有 OPENAI_API_KEY 就用 LLM，否則用範例。"""
    if os.path.exists(os.path.join(ROOT, "scenes.json")):
        print("• 讀取 scenes.json")
        return json.load(open(os.path.join(ROOT, "scenes.json"), encoding="utf-8"))
    if os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            print("• 用 LLM 生成腳本…")
            client = OpenAI()
            prompt = (f"你是短影片編劇。把主題寫成 5 個分鏡，"
                      f"每鏡給 narration（旁白，繁體中文口語、少於25字）"
                      f"和 visual（畫面中文描述）。只回 JSON 陣列。主題：{topic}")
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"})
            data = json.loads(r.choices[0].message.content)
            scenes = data.get("scenes", data) if isinstance(data, dict) else data
            if scenes:
                return scenes
        except Exception as e:
            print("  ⚠️ LLM 失敗，改用範例腳本：", e)
    print("• 用內建範例腳本（無 OPENAI_API_KEY）")
    return SAMPLE_SCENES

# ───────────────────────── 2) 配音 ─────────────────────────
def tts(text, out_path):
    """Step 3：文字轉語音。有 ELEVEN key 用 ElevenLabs，否則用 macOS say。"""
    if os.getenv("ELEVEN_API_KEY"):
        try:
            from elevenlabs import generate, save, set_api_key
            set_api_key(os.getenv("ELEVEN_API_KEY"))
            audio = generate(text=text, voice="Rachel", model="eleven_multilingual_v2")
            save(audio, out_path)
            return out_path
        except Exception as e:
            print("  ⚠️ ElevenLabs 失敗，改用系統語音：", e)
    aiff = out_path.replace(".m4a", ".aiff")
    sh(["say", "-v", "Meijia", "-o", aiff, text])
    sh(["ffmpeg", "-y", "-i", aiff, "-c:a", "aac", "-b:a", "128k", out_path])
    if os.path.exists(aiff):
        os.remove(aiff)
    return out_path

def audio_dur(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 3.0

# ───────────────────────── 3) 畫面 ─────────────────────────
def gen_image(visual, narration, idx, out_path):
    """Step 4：生成 9:16 畫面 + 燒字幕。有生圖 key 換成 API，否則 PIL 占位。"""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    # 漸層背景
    for y in range(H):
        t = y / H
        r = int(NAVY[0] + (NAVY2[0]-NAVY[0]) * t)
        g = int(NAVY[1] + (NAVY2[1]-NAVY[1]) * t)
        b = int(NAVY[2] + (NAVY2[2]-NAVY[2]) * t)
        d.line([(0, y), (W, y)], fill=(r, g, b))
    # 橘色裝飾線
    d.rectangle([0, 980, W, 988], fill=ORANGE)

    def font(sz):
        try:
            return ImageFont.truetype(FONT[0], sz, index=FONT[1])
        except Exception:
            return ImageFont.load_default()

    # 品牌浮水印（左上）
    d.text((48, 48), BRAND, font=font(40), fill=GOLD)
    # 鏡次標
    d.text((48, 110), f"SHOT {idx+1}", font=font(34), fill=(150,160,180))

    # 中央視覺描述（占位用，接真圖時可移除）
    vis_lines = textwrap.wrap(visual, width=10)
    cy = 700
    for ln in vis_lines:
        bb = d.textbbox((0, 0), ln, font=font(70))
        d.text(((W - (bb[2]-bb[0]))//2, cy), ln, font=font(70), fill=WHITE)
        cy += 96

    # 底部字幕區
    sub = textwrap.wrap(narration, width=12)
    box_h = 90 + len(sub) * 92
    by = H - box_h - 180
    d.rectangle([60, by, W-60, by+box_h], fill=(0, 0, 0))
    ty = by + 40
    for ln in sub:
        bb = d.textbbox((0, 0), ln, font=font(64))
        d.text(((W - (bb[2]-bb[0]))//2, ty), ln, font=font(64), fill=WHITE)
        ty += 92

    img.save(out_path, quality=92)
    return out_path

# ───────────────────────── 4) 單鏡合成 ─────────────────────────
def make_clip(img_path, audio_path, out_path):
    """Step 5a：一張圖 + 一段配音 → 帶 Ken Burns 緩慢推近的小片段。"""
    dur = audio_dur(audio_path) + 0.4
    frames = int(dur * FPS)
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H},"
          f"zoompan=z='min(zoom+0.0006,1.12)':d={frames}:s={W}x{H}:fps={FPS}")
    sh(["ffmpeg", "-y", "-loop", "1", "-i", img_path, "-i", audio_path,
        "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-t", f"{dur:.2f}", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-r", str(FPS), out_path])
    return out_path

# ───────────────────────── 5) 拼接 ─────────────────────────
def stitch(clips, out_path):
    """Step 5b：把所有片段接起來（concat 必須重編碼，否則字幕/時間軸會壞）。"""
    listfile = os.path.join(WORK, "list.txt")
    with open(listfile, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    bgm = os.path.join(ROOT, "assets", "bgm.mp3")
    if os.path.exists(bgm):
        print("• 疊上背景音樂 assets/bgm.mp3")
        sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
            "-stream_loop", "-1", "-i", bgm,
            "-filter_complex",
            "[0:a]volume=1.0[a0];[1:a]volume=0.18[a1];[a0][a1]amix=inputs=2:duration=first[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", out_path])
    else:
        sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", out_path])
    return out_path

# ───────────────────────── 主流程 ─────────────────────────
def make_short(topic):
    os.makedirs(WORK, exist_ok=True)
    print(f"\n🦞 產線啟動：{topic}\n" + "─"*40)
    if not FONT:
        print("⚠️ 找不到中文字型，字幕可能變方塊。")

    scenes = get_scenes(topic)
    print(f"• 腳本完成：{len(scenes)} 個分鏡")

    clips = []
    for i, sc in enumerate(scenes):
        nar = sc.get("narration", "")
        vis = sc.get("visual", "")
        print(f"  [{i+1}/{len(scenes)}] {nar}")
        a = os.path.join(WORK, f"voice_{i}.m4a")
        img = os.path.join(WORK, f"shot_{i}.jpg")
        clip = os.path.join(WORK, f"clip_{i}.mp4")
        tts(nar, a)                       # 3 配音
        gen_image(vis, nar, i, img)       # 4 畫面 + 字幕
        make_clip(img, a, clip)           # 5a 單鏡合成
        clips.append(clip)

    out = os.path.join(ROOT, "final.mp4")
    stitch(clips, out)                    # 5b 拼接
    print("─"*40)
    if os.path.exists(out):
        print(f"✅ 完成：{out}")
        subprocess.run(["open", out])
    else:
        print("❌ 合成失敗，請看上面的 ffmpeg 錯誤訊息。")
    return out

if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "AI 如何讓小店營收翻倍"
    make_short(topic)
