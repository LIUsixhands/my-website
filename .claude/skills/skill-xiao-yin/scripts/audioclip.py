#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小音（Xiao Yin）— 音檔批次處理引擎  audioclip.py
Sixhands Studio AI數字員工 / 學員專屬垂直員工

零第三方依賴（標準庫）＋ ffmpeg / ffprobe。
Whisper 為「選配」：有裝就能自動辨識片頭導語；沒裝則退化成純靜音偵測並要求人工確認。

指令一覽（12 個）：
  init                  建立工作區與設定檔
  probe   <路徑...>     掃描音檔規格（時長／取樣率／聲道／位元率）
  scan    <路徑...>     偵測片頭切點，只報告不動檔  ← 批次前一定先跑這個
  trim    <路徑...>     去片頭（自動偵測導語＋音樂）
  trimtail<路徑...>     去片尾（自動偵測結尾導語／音樂）
  cut     <檔> --start S --end E    手動切一段
  split   <檔>          依長靜音自動分題，切成多個小檔
  gap     <檔> --seconds N          統一題目之間的作答留白
  level   <路徑...>     音量統一（EBU R128 loudnorm）
  convert <路徑...> --to mp3|m4a|wav
  transcript <路徑...>  產出逐字稿（需 Whisper）
  report                列出工作區歷次處理紀錄
"""

import argparse, json, os, re, shutil, subprocess, sys, time

# ─────────────────────────── 基本設定 ───────────────────────────

WORKSPACE = os.path.expanduser("~/AI員工_小音")   # 本機碟，不可放桌面 iCloud
AUDIO_EXT = (".m4a", ".mp3", ".wav", ".aac", ".mp4", ".mov", ".flac", ".ogg")

# 片頭導語的中文特徵詞（聽力／課程／廣播教材通用）
INTRO_PAT = re.compile(
    r"(現在開始|以下是|接下來是|請聽|聽力測驗|聽力作業|听力作业|聽力練習|"
    r"第[一二三四五六七八九十\d]+部分|第[一二三四五六七八九十\d]+課|"
    r"習作|作業|作业|問答|问答|看圖|看图|辨義|辨义|短文聽解|簡短對話|測驗開始|本課)"
)
# 結尾導語特徵詞
OUTRO_PAT = re.compile(
    r"(測驗結束|作業結束|練習結束|本課結束|到此結束|以上|謝謝(聆聽|收聽|觀看)|结束)"
)
# Whisper 對純音樂／雜訊常見的幻覺句（視同片頭，不是內容）
HALLU_PAT = re.compile(
    r"(字幕|志願者|志愿者|請不吝|请不吝|點贊|点赞|訂閱|订阅|明鏡|明镜|"
    r"轉發|转发|打賞|打赏|雙擊|双击|更多精彩|MING PAO|Amara)"
)

DEFAULT_CFG = {
    "pad": 0.30,              # 內容前保留的空白秒數
    "silence_noise": "-35dB", # 靜音判定門檻
    "silence_dur": 0.40,      # 靜音最短長度
    "whisper_model": "large-v3-turbo",
    "head_scan_seconds": 60,  # 片頭只辨識前 N 秒
    "tail_scan_seconds": 45,
    "split_min_gap": 3.0,     # split 用：多長的靜音算「換一題」
    "loudness_lufs": -16.0,
}

# ─────────────────────────── 小工具 ───────────────────────────

def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def need_ffmpeg():
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            die(f"找不到 {exe}。請先安裝：brew install ffmpeg")

def die(msg, code=1):
    print(f"✗ {msg}")
    sys.exit(code)

def cfg_path():
    return os.path.join(WORKSPACE, "config.json")

def load_cfg():
    c = dict(DEFAULT_CFG)
    p = cfg_path()
    if os.path.exists(p):
        try:
            c.update(json.load(open(p, encoding="utf-8")))
        except Exception as e:
            print(f"⚠️  設定檔讀取失敗，改用預設值：{e}")
    return c

def duration(path):
    r = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", path])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0

def probe_one(path):
    r = sh(["ffprobe", "-v", "error", "-show_entries",
            "format=duration,bit_rate:stream=codec_name,sample_rate,channels",
            "-of", "json", path])
    try:
        j = json.loads(r.stdout)
    except Exception:
        return None
    st = (j.get("streams") or [{}])[0]
    fm = j.get("format") or {}
    return {
        "codec": st.get("codec_name"),
        "sample_rate": st.get("sample_rate"),
        "channels": st.get("channels"),
        "duration": float(fm.get("duration", 0) or 0),
        "bit_rate": int(fm.get("bit_rate", 0) or 0),
    }

def silences(path, noise, dur):
    """回傳 [(start, end), ...]"""
    r = sh(["ffmpeg", "-hide_banner", "-i", path, "-af",
            f"silencedetect=noise={noise}:d={dur}", "-f", "null", "-"])
    out, start = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start: ([-\d.]+)", line)
        if m:
            start = float(m.group(1))
        m = re.search(r"silence_end: ([-\d.]+)", line)
        if m and start is not None:
            out.append((start, float(m.group(1))))
            start = None
    return out

_MODEL = None
def whisper_model(name):
    """回傳 model 或 None（沒裝 whisper 就 None，不中斷流程）"""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        import whisper
    except ImportError:
        return None
    _MODEL = whisper.load_model(name)
    return _MODEL

def transcribe_range(path, cfg, start=0.0, secs=60):
    m = whisper_model(cfg["whisper_model"])
    if m is None:
        return None
    tmp = os.path.join(WORKSPACE, ".tmp_seg.wav")
    os.makedirs(WORKSPACE, exist_ok=True)
    sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", path,
        "-t", str(secs), "-ar", "16000", "-ac", "1", tmp])
    r = m.transcribe(tmp, language="zh", word_timestamps=True,
                     initial_prompt="以下是繁體中文的教學錄音。")
    segs = r["segments"]
    for s in segs:                      # 位移回原檔時間軸
        s["start"] += start
        s["end"] += start
    return segs

def collect(paths):
    files = []
    for p in paths:
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                if os.path.basename(root) in ("output", "備份"):
                    continue
                for n in sorted(names):
                    if n.lower().endswith(AUDIO_EXT) and not n.startswith("._"):
                        files.append(os.path.join(root, n))
        elif os.path.isfile(p):
            files.append(p)
        else:
            print(f"⚠️  找不到：{p}")
    return files

def outdir_for(files, explicit=None):
    if explicit:
        d = os.path.expanduser(explicit)
    else:
        d = os.path.join(os.path.dirname(os.path.abspath(files[0])), "output")
    os.makedirs(d, exist_ok=True)
    return d

def ffcut(src, dst, ss=None, to=None):
    """優先無損 stream copy；失敗才重新編碼（避免不必要的音質損失）"""
    base = ["ffmpeg", "-v", "error", "-y"]
    if ss is not None:
        base += ["-ss", f"{ss:.3f}"]
    base += ["-i", src]
    if to is not None:
        base += ["-t", f"{to:.3f}"]
    r = sh(base + ["-c", "copy", "-movflags", "+faststart", dst])
    if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 1024:
        return True, "無損"
    r = sh(base + ["-c:a", "aac", "-b:a", "64k", dst])
    return (r.returncode == 0), ("重編碼" if r.returncode == 0 else f"失敗：{r.stderr[:150]}")

def log_run(action, rows):
    os.makedirs(WORKSPACE, exist_ok=True)
    p = os.path.join(WORKSPACE, "處理紀錄.jsonl")
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "action": action, "items": rows},
                           ensure_ascii=False) + "\n")

# ─────────────────────── 核心：片頭／片尾偵測 ───────────────────────

def find_head_cut(path, cfg):
    """回傳 dict(cut, intro, content_at, method, confident)"""
    sils = silences(path, cfg["silence_noise"], cfg["silence_dur"])
    segs = transcribe_range(path, cfg, 0.0, cfg["head_scan_seconds"])

    if segs is None:                     # 沒有 Whisper → 純靜音啟發式
        if not sils:
            return {"cut": 0.0, "intro": "", "content_at": 0.0,
                    "method": "silence-only", "confident": False}
        a, b = sils[0]
        return {"cut": max(0.0, b - cfg["pad"]), "intro": f"（未辨識，0~{a:.2f}s）",
                "content_at": b, "method": "silence-only", "confident": False}

    intro_end, intro_txt, first_content = 0.0, [], None
    for s in segs:
        t = s["text"].strip()
        if HALLU_PAT.search(t):                       # 音樂／雜訊段
            intro_end = max(intro_end, s["end"]); intro_txt.append("[音樂片頭]"); continue
        if INTRO_PAT.search(t) and not re.search(r"[A-Za-z]{3}", t):
            intro_end = max(intro_end, s["end"]); intro_txt.append(t); continue
        first_content = s
        break

    if first_content is None:
        return {"cut": None, "intro": " ".join(intro_txt), "content_at": None,
                "method": "whisper", "confident": False}

    # Whisper 的時間戳會往前漂 0.5~1s，用「片頭結束後第一段靜音的結束點」對齊真正的語音起點
    cand = first_content["start"]
    for a, b in sils:
        if a >= intro_end - 0.5:
            cand = b
            break
    return {"cut": max(0.0, cand - cfg["pad"]), "intro": " ".join(intro_txt) or "（無片頭）",
            "content_at": cand, "method": "whisper", "confident": bool(intro_txt)}

def find_tail_cut(path, cfg):
    dur = duration(path)
    win = min(cfg["tail_scan_seconds"], dur)
    segs = transcribe_range(path, cfg, max(0.0, dur - win), win)
    if segs is None:
        return {"end": dur, "outro": "", "confident": False}
    end = dur
    outro = []
    for s in reversed(segs):
        t = s["text"].strip()
        if OUTRO_PAT.search(t) or HALLU_PAT.search(t):
            end = min(end, s["start"]); outro.insert(0, t)
        else:
            break
    return {"end": end, "outro": " ".join(outro), "confident": bool(outro)}

# ─────────────────────────── 各指令 ───────────────────────────

def cmd_init(a, cfg):
    os.makedirs(WORKSPACE, exist_ok=True)
    for sub in ("待處理", "output", "備份"):
        os.makedirs(os.path.join(WORKSPACE, sub), exist_ok=True)
    if not os.path.exists(cfg_path()):
        json.dump(DEFAULT_CFG, open(cfg_path(), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    print(f"✓ 工作區就緒：{WORKSPACE}")
    print(f"  設定檔：{cfg_path()}")
    print(f"  Whisper：{'已安裝' if whisper_model(cfg['whisper_model']) else '未安裝（可用，但片頭需人工確認）'}")

def cmd_probe(a, cfg):
    files = collect(a.paths)
    if not files: die("找不到音檔")
    for f in files:
        i = probe_one(f)
        if not i:
            print(f"✗ {os.path.basename(f)}  無法讀取"); continue
        print(f"{os.path.basename(f)}\n    {i['codec']} / {i['sample_rate']}Hz / "
              f"{i['channels']}ch / {i['bit_rate']//1000}kbps / {i['duration']:.1f}s")

def _scan_rows(files, cfg):
    rows = []
    for f in files:
        try:
            h = find_head_cut(f, cfg)
        except Exception as e:
            print(f"✗ {os.path.basename(f)}  錯誤：{e}"); continue
        dur = duration(f)
        name = os.path.basename(f)
        if h["cut"] is None:
            print(f"⚠️  {name}\n    整段都像片頭，需人工確認，已跳過")
            rows.append({"file": name, "cut": None, "note": "需人工確認"}); continue
        flag = "" if h["confident"] else "  ⚠️ 低信心，請人工聽過"
        print(f"✓ {name}{flag}\n    片頭：{h['intro']}\n"
              f"    切掉 0 ~ {h['cut']:.2f}s（內容起點 {h['content_at']:.2f}s，{h['method']}）"
              f" → 剩 {dur - h['cut']:.1f}s")
        rows.append({"file": name, "path": f, "cut": round(h["cut"], 3),
                     "intro": h["intro"], "old": round(dur, 2),
                     "new": round(dur - h["cut"], 2), "confident": h["confident"]})
    return rows

def cmd_scan(a, cfg):
    files = collect(a.paths)
    if not files: die("找不到音檔")
    rows = _scan_rows(files, cfg)
    low = [r for r in rows if r.get("cut") is not None and not r.get("confident")]
    print(f"\n共 {len(rows)} 檔；低信心 {len(low)} 檔。")
    print("確認無誤後改用 trim 實際切檔（原檔不動，輸出到 output/）。")

def cmd_trim(a, cfg):
    files = collect(a.paths)
    if not files: die("找不到音檔")
    rows = _scan_rows(files, cfg)
    od = outdir_for(files, a.outdir)
    done = 0
    for r in rows:
        if r.get("cut") is None:
            continue
        if not r["confident"] and not a.force:
            print(f"    ⏭  {r['file']} 低信心，未切（要照切請加 --force）"); continue
        dst = os.path.join(od, r["file"])
        ok, how = ffcut(r["path"], dst, ss=r["cut"])
        r["ok"], r["how"] = ok, how
        if ok: done += 1
        else: print(f"    ✗ {r['file']} 切檔失敗：{how}")
    log_run("trim", rows)
    print(f"\n完成 {done}/{len(rows)} → {od}")

def cmd_trimtail(a, cfg):
    files = collect(a.paths)
    if not files: die("找不到音檔")
    od = outdir_for(files, a.outdir)
    rows = []
    for f in files:
        t = find_tail_cut(f, cfg)
        name = os.path.basename(f)
        dur = duration(f)
        if not t["confident"]:
            print(f"⏭  {name}  沒偵測到結尾導語，未動"); continue
        print(f"✓ {name}\n    片尾：{t['outro']}\n    保留 0 ~ {t['end']:.2f}s（原 {dur:.1f}s）")
        dst = os.path.join(od, name)
        ok, how = ffcut(f, dst, to=t["end"])
        rows.append({"file": name, "end": round(t["end"], 3), "ok": ok, "how": how})
    log_run("trimtail", rows)
    print(f"\n→ {od}")

def cmd_cut(a, cfg):
    f = os.path.expanduser(a.file)
    if not os.path.isfile(f): die(f"找不到檔案：{f}")
    od = outdir_for([f], a.outdir)
    dur = duration(f)
    end = a.end if a.end is not None else dur
    if end <= a.start: die("--end 必須大於 --start")
    dst = os.path.join(od, os.path.basename(f))
    ok, how = ffcut(f, dst, ss=a.start, to=end - a.start)
    print(f"{'✓' if ok else '✗'} {os.path.basename(f)}  {a.start:.2f}~{end:.2f}s（{how}）→ {dst}")
    log_run("cut", [{"file": os.path.basename(f), "start": a.start, "end": end, "ok": ok}])

def cmd_split(a, cfg):
    f = os.path.expanduser(a.file)
    if not os.path.isfile(f): die(f"找不到檔案：{f}")
    gap = a.min_gap or cfg["split_min_gap"]
    sils = silences(f, cfg["silence_noise"], gap)
    dur = duration(f)
    marks = [0.0] + [(s + e) / 2 for s, e in sils if e - s >= gap] + [dur]
    marks = sorted(set(round(m, 3) for m in marks))
    segs = [(marks[i], marks[i + 1]) for i in range(len(marks) - 1)
            if marks[i + 1] - marks[i] >= 1.0]
    if len(segs) <= 1:
        die(f"只切出 {len(segs)} 段 — 試著把 --min-gap 調小（目前 {gap}s）")
    od = outdir_for([f], a.outdir)
    stem, ext = os.path.splitext(os.path.basename(f))
    rows = []
    for i, (s, e) in enumerate(segs, 1):
        dst = os.path.join(od, f"{stem}_{i:02d}{ext}")
        ok, how = ffcut(f, dst, ss=s, to=e - s)
        print(f"  {'✓' if ok else '✗'} {i:02d}  {s:6.2f}~{e:6.2f}s  ({e-s:5.1f}s)  {how}")
        rows.append({"seg": i, "start": s, "end": e, "ok": ok})
    log_run("split", rows)
    print(f"\n切成 {len(segs)} 段 → {od}")

def cmd_gap(a, cfg):
    """把題目之間的長靜音統一成 N 秒（作答時間）"""
    f = os.path.expanduser(a.file)
    if not os.path.isfile(f): die(f"找不到檔案：{f}")
    target = a.seconds
    thresh = a.min_gap or cfg["split_min_gap"]
    sils = [(s, e) for s, e in silences(f, cfg["silence_noise"], thresh) if e - s >= thresh]
    if not sils:
        die(f"找不到長度 ≥ {thresh}s 的停頓")
    dur = duration(f)
    od = outdir_for([f], a.outdir)
    work = os.path.join(WORKSPACE, "_gap_parts")
    shutil.rmtree(work, ignore_errors=True); os.makedirs(work, exist_ok=True)

    parts, prev = [], 0.0
    sr = probe_one(f)["sample_rate"] or "16000"
    for i, (s, e) in enumerate(sils):
        seg = os.path.join(work, f"p{i:03d}.wav")
        sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{prev:.3f}", "-i", f,
            "-t", f"{s - prev:.3f}", "-ar", sr, "-ac", "1", seg])
        parts.append(seg)
        sil = os.path.join(work, f"s{i:03d}.wav")
        sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
            f"anullsrc=r={sr}:cl=mono", "-t", f"{target:.3f}", sil])  # 取樣率與人聲一致，否則整段會變速
        parts.append(sil)
        prev = e
    if dur - prev > 0.05:
        seg = os.path.join(work, "pEND.wav")
        sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{prev:.3f}", "-i", f,
            "-ar", sr, "-ac", "1", seg])
        parts.append(seg)

    lst = os.path.join(work, "list.txt")
    with open(lst, "w", encoding="utf-8") as fp:
        for p in parts:
            fp.write(f"file '{p}'\n")
    dst = os.path.join(od, os.path.basename(f))
    r = sh(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
            "-c:a", "aac", "-b:a", "64k", dst])
    shutil.rmtree(work, ignore_errors=True)
    if r.returncode != 0:
        die(f"合併失敗：{r.stderr[:200]}")
    print(f"✓ {os.path.basename(f)}  {len(sils)} 處停頓統一成 {target}s  "
          f"（{dur:.1f}s → {duration(dst):.1f}s）→ {dst}")
    log_run("gap", [{"file": os.path.basename(f), "gaps": len(sils), "seconds": target}])

def cmd_level(a, cfg):
    files = collect(a.paths)
    if not files: die("找不到音檔")
    od = outdir_for(files, a.outdir)
    rows = []
    for f in files:
        dst = os.path.join(od, os.path.basename(f))
        r = sh(["ffmpeg", "-v", "error", "-y", "-i", f, "-af",
                f"loudnorm=I={cfg['loudness_lufs']}:TP=-1.5:LRA=11",
                "-c:a", "aac", "-b:a", "64k", dst])
        ok = r.returncode == 0
        print(f"{'✓' if ok else '✗'} {os.path.basename(f)}  → {cfg['loudness_lufs']} LUFS")
        rows.append({"file": os.path.basename(f), "ok": ok})
    log_run("level", rows)
    print(f"\n→ {od}")

def cmd_convert(a, cfg):
    files = collect(a.paths)
    if not files: die("找不到音檔")
    od = outdir_for(files, a.outdir)
    enc = {"mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
           "m4a": ["-c:a", "aac", "-b:a", "128k"],
           "wav": ["-c:a", "pcm_s16le"]}[a.to]
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]
        dst = os.path.join(od, f"{stem}.{a.to}")
        r = sh(["ffmpeg", "-v", "error", "-y", "-i", f] + enc + [dst])
        print(f"{'✓' if r.returncode == 0 else '✗'} {stem}.{a.to}")
    print(f"\n→ {od}")

def cmd_transcript(a, cfg):
    if whisper_model(cfg["whisper_model"]) is None:
        die("未安裝 Whisper：pip3 install -U openai-whisper")
    files = collect(a.paths)
    if not files: die("找不到音檔")
    od = outdir_for(files, a.outdir)
    for f in files:
        segs = transcribe_range(f, cfg, 0.0, duration(f) + 1)
        stem = os.path.splitext(os.path.basename(f))[0]
        dst = os.path.join(od, f"{stem}.txt")
        with open(dst, "w", encoding="utf-8") as fp:
            for s in segs:
                fp.write(f"[{s['start']:7.2f} - {s['end']:7.2f}] {s['text'].strip()}\n")
        print(f"✓ {stem}.txt（{len(segs)} 句）")
    print(f"\n→ {od}")

def cmd_report(a, cfg):
    p = os.path.join(WORKSPACE, "處理紀錄.jsonl")
    if not os.path.exists(p):
        die("還沒有任何處理紀錄，先跑 trim／split 等指令")
    for line in open(p, encoding="utf-8"):
        try:
            j = json.loads(line)
        except Exception:
            continue
        ok = sum(1 for i in j["items"] if i.get("ok") is not False)
        print(f"{j['time']}  {j['action']:10s}  {len(j['items'])} 項（成功 {ok}）")

# ─────────────────────────── CLI ───────────────────────────

def main():
    ap = argparse.ArgumentParser(prog="audioclip.py", description="小音 — 音檔批次處理引擎")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_paths(p):
        p.add_argument("paths", nargs="+", help="檔案或資料夾")
        p.add_argument("--outdir", default=None)

    add_paths(sub.add_parser("probe",  help="掃描音檔規格"))
    add_paths(sub.add_parser("scan",   help="偵測片頭切點（不動檔）"))
    p = sub.add_parser("trim", help="去片頭"); add_paths(p)
    p.add_argument("--force", action="store_true", help="低信心也照切")
    add_paths(sub.add_parser("trimtail", help="去片尾"))
    add_paths(sub.add_parser("level",  help="音量統一"))
    add_paths(sub.add_parser("transcript", help="產出逐字稿"))
    p = sub.add_parser("convert", help="轉檔"); add_paths(p)
    p.add_argument("--to", choices=["mp3", "m4a", "wav"], required=True)

    p = sub.add_parser("cut", help="手動切一段")
    p.add_argument("file"); p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--end", type=float, default=None); p.add_argument("--outdir", default=None)

    p = sub.add_parser("split", help="依長靜音自動分題")
    p.add_argument("file"); p.add_argument("--min-gap", type=float, default=None)
    p.add_argument("--outdir", default=None)

    p = sub.add_parser("gap", help="統一題目間留白")
    p.add_argument("file"); p.add_argument("--seconds", type=float, required=True)
    p.add_argument("--min-gap", type=float, default=None); p.add_argument("--outdir", default=None)

    sub.add_parser("init",   help="建立工作區")
    sub.add_parser("report", help="處理紀錄")

    a = ap.parse_args()
    if a.cmd != "init":
        need_ffmpeg()
    cfg = load_cfg()
    globals()[f"cmd_{a.cmd}"](a, cfg)

if __name__ == "__main__":
    main()
