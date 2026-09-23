#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小曲 · 字幕對時（讓字幕貼著人聲，不是貼著猜測）

拿選定的 take 跑 Whisper 逐段時間戳，配上歌詞原文產 subs.json。
🚨 產出**一定要人工修**：唱糊的句子刪掉、時間明顯早／晚的拉齊。
   字幕文字一律用歌詞原文，不用 Whisper 聽到的字（聽錯會直接印在畫面上）。

用法：
    python3 align_subs.py mv.json --take 2
"""
import sys, json, pathlib, re

def main():
    if len(sys.argv) < 2:
        sys.exit("用法：python3 align_subs.py mv.json --take 2")
    import whisper
    cfg_path = pathlib.Path(sys.argv[1]).resolve()
    root = cfg_path.parent
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    n = sys.argv[sys.argv.index("--take") + 1] if "--take" in sys.argv else "1"
    audio = root / "audio" / f"take{n}.mp3"
    if not audio.exists():
        sys.exit(f"❌ 找不到 {audio}")

    lines = [l.strip() for l in cfg.get("lyrics", "").splitlines()
             if l.strip() and not l.strip().startswith("[")]

    print("載入 Whisper large-v3-turbo…", flush=True)
    model = whisper.load_model("large-v3-turbo")
    r = model.transcribe(str(audio), language="zh", word_timestamps=True,
                         initial_prompt="以下是繁體中文歌曲的歌詞。")

    segs = [s for s in r["segments"] if re.search(r"[一-鿿]", s["text"])]
    subs = []
    for i, s in enumerate(segs):
        text = lines[i] if i < len(lines) else s["text"].strip()
        subs.append({"t0": round(s["start"], 2), "t1": round(s["end"], 2), "text": text,
                     "_heard": s["text"].strip()})

    p = root / "subs.json"
    p.write_text(json.dumps(subs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n✅ {p}（{len(subs)} 句）")
    print("每一句都印在下面，_heard 是 Whisper 真的聽到的，跟 text 差太多就代表對錯行：\n")
    for s in subs:
        print(f"  {s['t0']:6.2f}-{s['t1']:6.2f}  {s['text']}")
        if s["_heard"][:4] not in s["text"]:
            print(f"                    ⚠️ 聽到的是：{s['_heard']}")
    print("\n👉 手動修完 subs.json，再跑：python3 build_mv.py mv.json")

if __name__ == "__main__":
    main()
