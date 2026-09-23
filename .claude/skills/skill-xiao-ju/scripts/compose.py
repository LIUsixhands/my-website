"""步驟 6：合成成片（1080×1920／30fps）
- 對白鏡頭用自己的音檔（不用對嘴模型輸出的音軌），配樂自動閃避台詞（sidechain），整體 -14 LUFS
- 字幕／片名／角色字卡／AI 標示／品牌 logo／片尾下集預告，全部 PIL 畫好疊上去（不需要 libass）
- 讀 episode.json 的 fixes：pick（換版本）、crop_top（裁掉底部亂碼）、slow（只取前段再放慢）
用法：python3 compose.py [--out 檔名.mp4]"""
import re, sys, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from common import ROOT, EP, FIX, dur
from timeline import build

W, H, FPS = 1080, 1920, 30
C, A, S, O = ROOT / "clips", ROOT / "audio", ROOT / "sfx", ROOT / "subs"
SEG = ROOT / "out" / "seg"; SEG.mkdir(parents=True, exist_ok=True)
GOLD = (236, 200, 120)
PICK, CROP_TOP, SLOW = FIX.get("pick", {}), FIX.get("crop_top", {}), FIX.get("slow", {})
VO_OFFSET = EP.get("vo_offset", 0.2)
BRAND = EP.get("brand", {})
outname = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else f"{EP['title']}_EP{EP['ep']:02d}.mp4"


def find_font(cands):
    for p, idx in cands:
        if Path(p).exists():
            return p, idx
    sys.exit("❌ 找不到中文字型（Mac 內建蘋方／宋體；Windows 用微軟正黑）")


import glob
_pf = glob.glob("/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/PingFang.ttc")
SANS_B = find_font([(p, 10) for p in _pf] + [("/System/Library/Fonts/STHeiti Medium.ttc", 0), ("C:/Windows/Fonts/msjhbd.ttc", 0)])
SANS_M = find_font([(p, 6) for p in _pf] + [("/System/Library/Fonts/STHeiti Medium.ttc", 0), ("C:/Windows/Fonts/msjh.ttc", 0)])
SERIF = find_font([("/System/Library/Fonts/Supplemental/Songti.ttc", 2), ("C:/Windows/Fonts/mingliub.ttc", 0)] + [SANS_B])


def font(spec, size):
    return ImageFont.truetype(spec[0], size, index=spec[1])


def fit_font(txt, spec, size, max_w, min_size=34):
    """字太長會被畫面切掉 → 自動縮到放得下（EP02 第1鏡與片尾預告踩過）"""
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while size > min_size and d.textlength(txt, font=font(spec, size)) > max_w:
        size -= 2
    return font(spec, size)


def sh_run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-2500:]); sys.exit(f"ffmpeg 失敗 rc={r.returncode}")


def segments(tl):
    files = []
    for x in tl:
        src = C / f"{PICK.get(x['id'], x['id'])}.mp4"
        out = SEG / f"{x['id']}.mp4"
        pre = ""
        if x["id"] in CROP_TOP:
            z = CROP_TOP[x["id"]]; pre += f"crop=iw*{z}:ih*{z}:(iw-iw*{z})/2:0,"
        if x["id"] in SLOW:
            pre += f"setpts=PTS/{SLOW[x['id']]},"
        vf = (pre + f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},setsar=1,fps={FPS},"
              f"tpad=stop_mode=clone:stop_duration=2,trim=duration={x['dur']:.3f},setpts=PTS-STARTPTS,format=yuv420p")
        sh_run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-an", "-vf", vf, "-c:v", "libx264", "-crf", "16", "-preset", "fast", str(out)])
        files.append(out)
    lst = SEG / "list.txt"
    lst.write_text("".join(f"file '{f}'\n" for f in files))
    base = ROOT / "out" / "base.mp4"
    sh_run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(base)])
    return base


def speech_spans(f):
    total = dur(f)
    log = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(f), "-af", "silencedetect=noise=-32dB:d=0.12", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    st = [float(v) for v in re.findall(r"silence_start: ([-\d.]+)", log)]
    en = [float(v) for v in re.findall(r"silence_end: ([\d.]+)", log)]
    if len(en) < len(st): en.append(total)
    sil = [(max(0, s), e) for s, e in zip(st, en)]
    head = sil[0][1] if sil and sil[0][0] <= 0.02 else 0.0
    tail = sil[-1][0] if sil and sil[-1][1] >= total - 0.02 else total
    return head, tail, [((s + e) / 2) for s, e in sil if s > head + 0.05 and e < tail - 0.05]


def sub_times(sid, chunks):
    """字幕切段：用台詞中的停頓當切點，找不到停頓就按字數比例"""
    head, tail, inner = speech_spans(A / f"{sid}.mp3")
    if len(chunks) == 1:
        return [(head, tail)]
    lens = [len(re.sub(r"[，。？！…—、\s]", "", c)) or 1 for c in chunks]
    tot, acc, bounds = sum(lens), 0, []
    for L in lens[:-1]:
        acc += L
        target = head + (tail - head) * acc / tot
        cands = [p for p in inner if not bounds or p > bounds[-1]]
        b = min(cands, key=lambda p: abs(p - target)) if cands else target
        bounds.append(b if abs(b - target) <= 0.9 else target)
    edges = [head] + bounds + [tail]
    return list(zip(edges[:-1], edges[1:]))


def text_img(txt, f, fill, stroke=6, stroke_fill=(0, 0, 0), shadow=True):
    d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    x0, y0, x1, y1 = d.textbbox((0, 0), txt, font=f, stroke_width=stroke)
    pad = 24
    im = Image.new("RGBA", (x1 - x0 + pad * 2, y1 - y0 + pad * 2), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((pad - x0 + 4, pad - y0 + 6), txt, font=f, fill=(0, 0, 0, 170), stroke_width=stroke, stroke_fill=(0, 0, 0, 170))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(6)))
    ImageDraw.Draw(im).text((pad - x0, pad - y0), txt, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    return im


def overlays(tl):
    ov = []  # (png, x, y, t0, t1)
    t = {x["id"]: x for x in tl}
    first, last = tl[0], tl[-1]
    sub_size = 64
    for sh in EP["shots"]:
        if "subs" not in sh:
            continue
        off = t[sh["id"]]["start"] + (VO_OFFSET if sh["type"] != "talk" else 0)
        for k, ((a, b), txt) in enumerate(zip(sub_times(sh["id"], sh["subs"]), sh["subs"])):
            im = text_img(txt, fit_font(txt, SANS_B, sub_size, W - 90), (255, 255, 255), stroke=7)
            p = O / f"sub_{sh['id']}_{k}.png"; im.save(p)
            ov.append((p, (W - im.width) // 2, 1330 - im.height // 2, off + a, off + b + 0.08))
    # 片名（第一鏡）
    title = text_img(EP["title"], font(SERIF, 118), GOLD, stroke=8, stroke_fill=(40, 20, 0))
    ep_tag = text_img(f"第 {EP['ep']} 集", font(SANS_B, 44), (255, 255, 255), stroke=5)
    card = Image.new("RGBA", (max(title.width, ep_tag.width), title.height + ep_tag.height - 20), (0, 0, 0, 0))
    card.alpha_composite(title, ((card.width - title.width) // 2, 0))
    card.alpha_composite(ep_tag, ((card.width - ep_tag.width) // 2, title.height - 20))
    p = O / "title.png"; card.save(p)
    ov.append((p, (W - card.width) // 2, 250, 0.3, first["end"] - 0.1))
    # 角色字卡
    for sh in EP["shots"]:
        if "label" not in sh:
            continue
        name, desc = sh["label"]
        n_im, d_im = text_img(name, font(SANS_B, 70), (255, 255, 255), stroke=5), text_img(desc, font(SANS_M, 40), GOLD, stroke=4)
        im = Image.new("RGBA", (max(n_im.width, d_im.width) + 30, n_im.height + d_im.height - 10), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle([4, 26, 13, im.height - 26], fill=GOLD + (255,))
        im.alpha_composite(n_im, (22, 0)); im.alpha_composite(d_im, (22, n_im.height - 22))
        p = O / f"label_{sh['id']}.png"; im.save(p)
        s0 = t[sh["id"]]["start"]
        ov.append((p, 56, 1040, s0 + 0.25, min(s0 + 3.2, t[sh["id"]]["end"])))
    # 角標：品牌 logo（有設才放）＋ AI 生成內容（一定放）
    if BRAND.get("logo") and Path(BRAND["logo"]).expanduser().exists():
        logo = Image.open(Path(BRAND["logo"]).expanduser()).convert("RGBA")
        logo = logo.resize((120, int(120 * logo.height / logo.width)), Image.LANCZOS)
        logo.putalpha(logo.getchannel("A").point(lambda v: int(v * 0.85)))
        p = O / "logo_corner.png"; logo.save(p)
        ov.append((p, 44, 64, 0, last["start"]))
    ai = text_img("AI 生成內容", font(SANS_M, 30), (255, 255, 255, 230), stroke=3, shadow=False)
    p = O / "ai_tag.png"; ai.save(p)
    ov.append((p, W - ai.width - 36, 80, 0, last["end"]))
    # 片尾（最後一鏡）：下集預告＋品牌
    endc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        grad.putpixel((0, y), int(215 * max(0, (y - 700) / (H - 700)) ** 0.8))
    endc.putalpha(grad.resize((W, H)))
    if EP.get("next"):
        nx = text_img("下集", font(SANS_B, 46), (30, 20, 0), stroke=0, shadow=False)
        pill = Image.new("RGBA", (nx.width + 30, nx.height + 2), (0, 0, 0, 0))
        ImageDraw.Draw(pill).rounded_rectangle([0, 0, pill.width - 1, pill.height - 1], radius=pill.height // 2, fill=GOLD + (255,))
        pill.alpha_composite(nx, (15, 1))
        endc.alpha_composite(pill, ((W - pill.width) // 2, 1080))
        qtxt = EP["next"].split("｜")[-1]
        q = text_img(qtxt, fit_font(qtxt, SERIF, 84, W - 110), (255, 255, 255), stroke=6)
        endc.alpha_composite(q, ((W - q.width) // 2, 1180))
    if BRAND.get("logo_end") and Path(BRAND["logo_end"]).expanduser().exists():
        fl = Image.open(Path(BRAND["logo_end"]).expanduser()).convert("RGBA")
        fl = fl.resize((230, int(230 * fl.height / fl.width)), Image.LANCZOS)
        endc.alpha_composite(fl, ((W - fl.width) // 2, 1390))
    if BRAND.get("line"):
        b = text_img(BRAND["line"], font(SANS_M, 34), (230, 230, 230), stroke=3, shadow=False)
        endc.alpha_composite(b, ((W - b.width) // 2, 1650))
    p = O / "endcard.png"; endc.save(p)
    ov.append((p, 0, 0, last["start"] + 0.15, last["end"] + 1))
    return ov


def audio_graph(tl, n_in):
    t = {x["id"]: x for x in tl}
    total = tl[-1]["end"]
    ins, fl, dl, fx = [], [], [], []
    idx = n_in
    for sh in EP["shots"]:
        if not (sh.get("line") or sh.get("vo")):
            continue
        ms = int((t[sh["id"]]["start"] + (VO_OFFSET if sh["type"] != "talk" else 0)) * 1000)
        ins += ["-i", str(A / f"{sh['id']}.mp3")]
        fl.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms}[d{idx}]"); dl.append(f"[d{idx}]"); idx += 1
    for s in EP.get("sfx", []):
        f = S / f"{s['name']}.mp3"
        if not f.exists():
            continue
        ms = int(max(0, t[s["at"]]["start"] + s.get("offset", 0)) * 1000)
        ins += ["-i", str(f)]
        fl.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={s.get('vol', 0.8)},adelay={ms}|{ms}[f{idx}]"); fx.append(f"[f{idx}]"); idx += 1
    has_bgm = (S / "bgm.mp3").exists()
    # 台詞軌先補滿片長：sidechaincompress 會在 key 結束時一起截斷配樂（EP01 踩過）
    fl.append(f"{''.join(dl)}amix=inputs={len(dl)}:normalize=0:dropout_transition=0,apad=whole_dur={total:.3f},asplit[dlg][key]")
    mix = ["[dlg]"]
    if has_bgm:
        ins += ["-i", str(S / "bgm.mp3")]
        fl.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={EP.get('music', {}).get('volume', 0.34)}[bg0]")
        fl.append("[bg0][key]sidechaincompress=threshold=0.015:ratio=10:attack=20:release=400:makeup=1[bgd]")
        mix.append("[bgd]")
    else:
        fl.append("[key]anullsink")
    if fx:
        fl.append(f"{''.join(fx)}amix=inputs={len(fx)}:normalize=0[fx]"); mix.append("[fx]")
    fl.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:dropout_transition=0,loudnorm=I=-14:TP=-1.5:LRA=11,"
              f"aresample=48000,afade=t=out:st={total - 0.6:.3f}:d=0.6[aout]")
    return ins, fl


def main():
    tl = build()
    base = segments(tl)
    ov = overlays(tl)
    ins = ["-i", str(base)]
    for p, *_ in ov:
        ins += ["-loop", "1", "-i", str(p)]
    fl, last = [], "[0:v]"
    for i, (p, x, y, t0, t1) in enumerate(ov, 1):
        fl.append(f"{last}[{i}:v]overlay={x}:{y}:enable='between(t,{t0:.3f},{t1:.3f})':shortest=1[v{i}]")
        last = f"[v{i}]"
    ains, afl = audio_graph(tl, len(ov) + 1)
    total = tl[-1]["end"]
    out = ROOT / "out" / outname
    sh_run(["ffmpeg", "-y", "-loglevel", "error", *ins, *ains, "-filter_complex", ";".join(fl + afl),
            "-map", last, "-map", "[aout]", "-t", f"{total:.3f}", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    print("✅", out, f"{total:.2f}s")
    print("🎬 下一步：review.py 讓 Gemini 看整支片，再自己抽幾格看字幕和片尾")


if __name__ == "__main__":
    main()
