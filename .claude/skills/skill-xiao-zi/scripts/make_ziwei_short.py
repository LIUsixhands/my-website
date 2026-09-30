#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_ziwei_short.py — 紫微斗數宣傳影片產線（9:16 直式短片）
Sixhands Studio AI數字員工 🦞 ▎AI 員工「小紫」主產線

一個指令，把 scenes.json（分鏡腳本）跑成一支帶配音、字幕、命盤視覺的成片。

用法（在你要存成品的資料夾裡執行）：
    python3 /path/to/make_ziwei_short.py                 # 讀 ./scenes.json，沒有就用內建範例
    python3 /path/to/make_ziwei_short.py my_scenes.json
    python3 /path/to/make_ziwei_short.py my_scenes.json --169   # 改成 16:9 橫式

讀寫都在「目前工作目錄」：
    ./scenes.json      分鏡腳本（必備；沒有就用內建範例）
    ./chart.json       命盤資料（選用；type=chart 的鏡頭會用它，沒有就用示範盤）
    ./assets/bgm.mp3   背景音樂（選用，存在就自動混入）
    ./build/           中間檔
    ./final.mp4        成品

scenes.json 格式（陣列）：
[
  {"narration": "旁白（繁中口語，一句 12-20 字最好唸）",
   "type": "text",              # text | chart | image
   "big": "畫面大字（≤9 字）",   # type=text 用
   "highlight": "夫妻宮",        # type=chart 用，讓某一宮發光
   "image": "photos/a.jpg"      # type=image 用
  }, ...
]

配音優先序：ELEVEN_API_KEY → macOS 內建 say（Meijia 台灣中文）
"""
import os, sys, json, subprocess, shutil, textwrap

ROOT = os.getcwd()
WORK = os.path.join(ROOT, "build")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FPS = 25
VERTICAL = "--169" not in sys.argv
W, H = (1080, 1920) if VERTICAL else (1920, 1080)

BRAND = "Sixhands Studio AI數字員工"
LOGO = os.path.join(HERE, "..", "assets", "logo.png")

# 紫金色系（與 gen_chart.py 同一套）
BG_TOP    = (26, 11, 46)
BG_BOTTOM = (45, 27, 78)
GOLD      = (212, 175, 55)
HL        = (255, 214, 102)
CREAM     = (245, 240, 228)
PURPLE_LT = (176, 142, 232)

SUB_Y_RATIO = 0.64 if VERTICAL else 0.80   # 直式壓在 62-65%（避開手機介面），橫式沉到底部
KEN_BURNS   = 1.10          # 推近倍率
OVERSCAN    = 1.14          # 背景層放大倍率（要 > KEN_BURNS 才有推近空間）

FONT_CANDIDATES = [
    ("/System/Library/Fonts/PingFang.ttc", 0),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 2),   # Songti TC Bold（繁體）
    ("/Library/Fonts/Arial Unicode.ttf", 0),
]

def find_font():
    from PIL import ImageFont
    for path, idx in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                ImageFont.truetype(path, 40, index=idx)
                return (path, idx)
            except Exception:
                continue
    return None

FONT = find_font()

def font(sz):
    from PIL import ImageFont
    if not FONT:
        return ImageFont.load_default()
    return ImageFont.truetype(FONT[0], sz, index=FONT[1])

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def sh(cmd):
    r = run(cmd)
    if r.returncode != 0:
        print("  ⚠️ 指令失敗：", " ".join(cmd[:4]), "…")
        print("  ", r.stderr.strip()[-400:])
    return r

# ────────────────────── 內建範例腳本 ──────────────────────
SAMPLE = [
    {"type": "text",  "big": "你不是不努力",
     "narration": "你不是不努力，你只是一直在跟自己的個性打架。"},
    {"type": "chart", "highlight": "命宮",
     "narration": "紫微斗數把一個人拆成十二個宮位，命宮講的是你天生的反應方式。"},
    {"type": "chart", "highlight": "官祿宮",
     "narration": "官祿宮講你適合怎麼工作，不是講你會不會發財。"},
    {"type": "text",  "big": "看懂，才有得選",
     "narration": "看懂自己的盤，不是為了認命，是為了知道哪一條路你走起來比較不費力。"},
    {"type": "text",  "big": "免費解盤直播",
     "narration": "這禮拜四晚上八點，我開一場免費直播，帶你看自己的命宮。留言「命盤」我把連結給你。"},
]

def load_scenes():
    for name in (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".json") else None,
                 "scenes.json"):
        if name and os.path.exists(os.path.join(ROOT, name)):
            print(f"• 讀取分鏡：{name}")
            return json.load(open(os.path.join(ROOT, name), encoding="utf-8"))
    print("• 用內建範例分鏡（要用自己的，請放 scenes.json）")
    return SAMPLE

# ────────────────────── 配音 ──────────────────────
def tts(text, out_path):
    key = os.getenv("ELEVEN_API_KEY") or os.getenv("ELEVENLABS_API_KEY")
    if key:
        try:
            import urllib.request
            voice = os.getenv("ELEVEN_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
            req = urllib.request.Request(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                data=json.dumps({"text": text,
                                 "model_id": "eleven_multilingual_v2",
                                 "voice_settings": {"stability": 0.45,
                                                    "similarity_boost": 0.75}}).encode(),
                headers={"xi-api-key": key, "Content-Type": "application/json"})
            mp3 = out_path.replace(".m4a", ".mp3")
            with urllib.request.urlopen(req, timeout=90) as r, open(mp3, "wb") as f:
                f.write(r.read())
            sh(["ffmpeg", "-y", "-i", mp3, "-c:a", "aac", "-b:a", "160k",
                "-ar", "44100", "-ac", "2", out_path])
            if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                return out_path
        except Exception as e:
            print("  ⚠️ ElevenLabs 失敗，改用系統語音：", e)
    if shutil.which("say"):                       # macOS 內建語音
        aiff = out_path.replace(".m4a", ".aiff")
        sh(["say", "-v", "Meijia", "-r", "185", "-o", aiff, text])
        sh(["ffmpeg", "-y", "-i", aiff, "-c:a", "aac", "-b:a", "160k",
            "-ar", "44100", "-ac", "2", out_path])
        if os.path.exists(aiff):
            os.remove(aiff)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return out_path

    if sys.platform.startswith("win"):            # Windows 內建語音
        try:
            wav = out_path.replace(".m4a", ".wav")
            ps = ("Add-Type -AssemblyName System.Speech;"
                  "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                  f"$s.SetOutputToWaveFile('{wav}');$s.Speak('{text}');$s.Dispose()")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, timeout=120)
            if os.path.exists(wav):
                sh(["ffmpeg", "-y", "-i", wav, "-c:a", "aac", "-b:a", "160k",
                    "-ar", "44100", "-ac", "2", out_path])
                os.remove(wav)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                    return out_path
        except Exception as e:
            print("  ⚠️ Windows 語音失敗：", e)

    # 最後手段：產等長靜音，先把片子做出來，之後自己配音蓋上去
    dur = max(1.8, len(text) / 5.2)               # 中文口播約每秒 5 字
    print(f"  ⚠️ 找不到可用的語音引擎，本鏡用 {dur:.1f} 秒靜音代替。")
    sh(["ffmpeg", "-y", "-f", "lavfi", "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", f"{dur:.2f}", "-c:a", "aac", "-b:a", "160k", out_path])
    return out_path

def audio_dur(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 3.0

# ────────────────────── 背景層 ──────────────────────
def bg_canvas():
    """放大版底圖（含漸層 + 星點），供 Ken Burns 推近裁切。"""
    from PIL import Image, ImageDraw
    import random
    bw, bh = int(W * OVERSCAN), int(H * OVERSCAN)
    img = Image.new("RGB", (bw, bh), BG_TOP)
    d = ImageDraw.Draw(img, "RGBA")
    for y in range(bh):
        t = y / bh
        d.line([(0, y), (bw, y)],
               fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    rnd = random.Random(20260823)
    for _ in range(320):
        x, y = rnd.randint(0, bw), rnd.randint(0, bh)
        r = rnd.choice([1, 1, 2, 2, 3])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rnd.randint(50, 190)))
    return img

def fit_cover(im, box_w, box_h):
    """等比放大後置中裁切，填滿指定尺寸（不變形、不留黑邊）。"""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(im).convert("RGB")     # 手機照片必做，否則會躺平
    s = max(box_w / im.width, box_h / im.height)
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    x = (im.width - box_w) // 2
    y = (im.height - box_h) // 2
    return im.crop((x, y, x + box_w, y + box_h))

PUNC = "，。！？、；：）」』～…"          # 這些字不可以出現在行首

def wrap_cjk(s, per_line):
    """中文斷行：行寬平均、標點不落行首、不留單字孤行。"""
    import math
    s = (s or "").strip()
    if not s:
        return [""]
    if len(s) <= per_line:
        return [s]
    n = math.ceil(len(s) / per_line)
    target = math.ceil(len(s) / n)          # 平均行寬，避免最後一行只剩一兩個字
    lines, i = [], 0
    while i < len(s):
        end = min(i + target, len(s))
        while end < len(s) and s[end] in PUNC:   # 標點跟著上一行走
            end += 1
        if 0 < len(s) - end <= 1:                # 尾巴只剩 1 字就併進來
            end = len(s)
        lines.append(s[i:end])
        i = end
    return lines

def split_big(s, per_line):
    """畫面大字：有標點就在標點處分行，讀起來才有停頓感。"""
    s = (s or "").strip()
    for p in ("，", "、", "。", "？", "！"):
        if p in s[:-1]:
            head, _, tail = s.partition(p)
            return [head + p, tail]
    return wrap_cjk(s, per_line)

def render_bg(scene, idx):
    """畫一鏡的背景層（不含字幕、不含 logo — 那兩層固定不動）。"""
    from PIL import Image, ImageDraw
    img = bg_canvas()
    bw, bh = img.size
    d = ImageDraw.Draw(img, "RGBA")
    t = scene.get("type", "text")

    if t == "image" and scene.get("image"):
        path = scene["image"] if os.path.isabs(scene["image"]) else os.path.join(ROOT, scene["image"])
        if os.path.exists(path):
            img = fit_cover(Image.open(path), bw, bh)
            d = ImageDraw.Draw(img, "RGBA")
            d.rectangle([0, 0, bw, bh], fill=(26, 11, 46, 90))       # 壓一層紫，統一調性
        else:
            print(f"  ⚠️ 找不到圖片 {scene['image']}，改用大字卡")
            t = "text"

    if t == "chart":
        import gen_chart
        cj = os.path.join(ROOT, "chart.json")
        data = json.load(open(cj, encoding="utf-8")) if os.path.exists(cj) else gen_chart.DEMO
        tmp = os.path.join(WORK, f"chart_{idx}.png")
        gen_chart.render(data, tmp, scene.get("highlight"))
        # 盤面是正方形：尺寸要同時受寬與高限制，否則 16:9 會撐出畫面被字幕吃掉
        side = int(min(bw * 0.84, bh * 0.62))
        chart = Image.open(tmp).resize((side, side), Image.LANCZOS)
        img.paste(chart, ((bw - side) // 2, int(bh * 0.12)))
        if scene.get("highlight"):
            d = ImageDraw.Draw(img, "RGBA")
            bb = d.textbbox((0, 0), scene["highlight"], font=font(64))
            d.text(((bw - (bb[2] - bb[0])) / 2, int(bh * 0.045)),
                   scene["highlight"], font=font(64), fill=HL)

    if t == "text":
        big = scene.get("big") or scene.get("narration", "")[:9]
        lines = split_big(big, 6)
        fsz = 130 if len(lines) <= 2 else 104
        total = len(lines) * (fsz + 26)
        y = bh * 0.37 - total / 2
        for ln in lines:
            bb = d.textbbox((0, 0), ln, font=font(fsz))
            x = (bw - (bb[2] - bb[0])) / 2
            d.text((x + 4, y + 5), ln, font=font(fsz), fill=(0, 0, 0, 140))   # 陰影
            d.text((x, y), ln, font=font(fsz), fill=HL)
            y += fsz + 26
        d.rectangle([bw * 0.5 - 90, y + 24, bw * 0.5 + 90, y + 30], fill=GOLD)

    return img

def paste_overlay(frame, scene):
    """字幕 + 品牌層（固定不動，不參與推近）。"""
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(frame, "RGBA")
    nar = scene.get("narration", "")
    if nar:
        per = 13 if VERTICAL else 22
        lines = wrap_cjk(nar, per)
        fsz = 60 if VERTICAL else 54
        pad = 26
        box_h = len(lines) * (fsz + 18) + pad * 2
        top = int(H * SUB_Y_RATIO)
        d.rectangle([W * 0.055, top, W * 0.945, top + box_h], fill=(12, 5, 26, 205))
        d.rectangle([W * 0.055, top, W * 0.055 + 8, top + box_h], fill=GOLD)
        y = top + pad
        for ln in lines:
            bb = d.textbbox((0, 0), ln, font=font(fsz))
            d.text(((W - (bb[2] - bb[0])) / 2, y), ln, font=font(fsz), fill=CREAM)
            y += fsz + 18
    # 品牌浮水印
    if os.path.exists(LOGO):
        lg = Image.open(LOGO).convert("RGBA")
        s = int(W * 0.10)
        lg = lg.resize((s, s), Image.LANCZOS)
        frame.paste(lg, (W - s - 40, 44), lg)
    d.text((44, 52), BRAND, font=font(34), fill=(212, 175, 55, 210))
    return frame

def make_clip(scene, idx, audio_path, out_path):
    """PIL 逐幀 Ken Burns（不用 ffmpeg zoompan：它配 -loop 1 會爆幀，且會裁邊）。"""
    from PIL import Image
    dur = audio_dur(audio_path) + 0.35
    n = max(2, int(dur * FPS))
    base = render_bg(scene, idx)
    bw, bh = base.size
    fdir = os.path.join(WORK, f"f{idx}")
    shutil.rmtree(fdir, ignore_errors=True)
    os.makedirs(fdir, exist_ok=True)

    for i in range(n):
        t = i / (n - 1)
        z = 1.0 + (KEN_BURNS - 1.0) * t          # 由 1.00 緩慢推到 1.10
        cw, ch = int(W * OVERSCAN / z), int(H * OVERSCAN / z)
        cw, ch = min(cw, bw), min(ch, bh)
        x, y = (bw - cw) // 2, (bh - ch) // 2
        fr = base.crop((x, y, x + cw, y + ch)).resize((W, H), Image.LANCZOS)
        paste_overlay(fr, scene).save(os.path.join(fdir, f"{i:04d}.jpg"), quality=90)

    sh(["ffmpeg", "-y", "-framerate", str(FPS), "-i", os.path.join(fdir, "%04d.jpg"),
        "-i", audio_path, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-ar", "44100", "-ac", "2", "-shortest", out_path])
    shutil.rmtree(fdir, ignore_errors=True)
    return out_path

def outro_clip(out_path, seconds=2.6):
    """品牌尾卡（每支片都掛，符合Sixhands Studio品牌守則）。"""
    from PIL import Image, ImageDraw
    img = bg_canvas().resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(img, "RGBA")
    if os.path.exists(LOGO):
        lg = Image.open(LOGO).convert("RGBA")
        s = int(W * 0.30)
        lg = lg.resize((s, s), Image.LANCZOS)
        img.paste(lg, ((W - s) // 2, int(H * 0.30)), lg)
    bb = d.textbbox((0, 0), BRAND, font=font(64))
    d.text(((W - (bb[2] - bb[0])) / 2, int(H * 0.30) + int(W * 0.30) + 50),
           BRAND, font=font(64), fill=GOLD)
    p = os.path.join(WORK, "outro.jpg")
    img.save(p, quality=92)
    sh(["ffmpeg", "-y", "-loop", "1", "-i", p, "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(seconds), "-c:v", "libx264", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-r", str(FPS), out_path])
    return out_path

def stitch(clips, out_path):
    lst = os.path.join(WORK, "list.txt")
    with open(lst, "w") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
    bgm = os.path.join(ROOT, "assets", "bgm.mp3")
    if os.path.exists(bgm):
        print("• 混入背景音樂 assets/bgm.mp3")
        sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
            "-stream_loop", "-1", "-i", bgm, "-filter_complex",
            "[0:a]volume=1.0[a0];[1:a]volume=0.16[a1];[a0][a1]amix=inputs=2:duration=first[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-ar", "44100", "-ac", "2", "-shortest", out_path])
    else:
        sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2", out_path])
    return out_path

def main():
    os.makedirs(WORK, exist_ok=True)
    scenes = load_scenes()
    print(f"\n🔮 小紫產線啟動｜{'9:16 直式' if VERTICAL else '16:9 橫式'}｜{len(scenes)} 個分鏡\n" + "─" * 46)
    if not FONT:
        print("⚠️ 找不到繁體字型，字幕可能空白。")
    clips = []
    for i, sc in enumerate(scenes):
        print(f"  [{i+1}/{len(scenes)}] {sc.get('narration','')[:24]}…")
        a = os.path.join(WORK, f"voice_{i}.m4a")
        c = os.path.join(WORK, f"clip_{i}.mp4")
        tts(sc.get("narration", ""), a)
        make_clip(sc, i, a, c)
        clips.append(c)
    clips.append(outro_clip(os.path.join(WORK, "clip_outro.mp4")))
    out = os.path.join(ROOT, "final.mp4")
    stitch(clips, out)
    print("─" * 46)
    if os.path.exists(out):
        print(f"✅ 完成：{out}（{audio_dur(out):.1f} 秒）")
    else:
        print("❌ 合成失敗，請看上面的 ffmpeg 訊息。")

if __name__ == "__main__":
    main()
