#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小曲 · ElevenLabs 生歌（一次生 2 個 take）

🚫 音樂只准從這裡來。不准去 pixabay／YouTube／任何網站抓歌，
   也不准丟連結叫客戶自己下載素材。

用法：
    export ELEVENLABS_API_KEY=...
    python3 gen_song.py mv.json
    python3 gen_song.py mv.json --takes 3

mv.json 需要有：
    "lyrics": "[Verse]\n...",
    "song_prompt": "曲風描述（英文寫，咬字要求也寫在裡面）",
    "song_ms": 55000
"""
import os, sys, json, pathlib, requests

def main():
    if len(sys.argv) < 2:
        sys.exit("用法：python3 gen_song.py mv.json [--takes N]")
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("❌ ELEVENLABS_API_KEY 沒設。寫在 ~/.zshrc 裡，然後 source ~/.zshrc")

    cfg_path = pathlib.Path(sys.argv[1]).resolve()
    root = cfg_path.parent
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    takes = int(sys.argv[sys.argv.index("--takes") + 1]) if "--takes" in sys.argv else 2

    lyrics = cfg.get("lyrics", "").strip()
    if not lyrics:
        sys.exit("❌ mv.json 缺 lyrics")
    for bad in ("保證", "第一名", "最便宜", "唯一", "療效", "根治"):
        if bad in lyrics:
            sys.exit(f"❌ 歌詞出現紅線字「{bad}」→ 先改歌詞（見 references/合規紅線.md）")

    style = cfg.get("song_prompt", "").strip()
    if not style:
        sys.exit("❌ mv.json 缺 song_prompt（曲風描述）")

    prompt = (f"{style}\n\n"
              "CRITICAL: articulate every Chinese syllable slowly and very distinctly, "
              "never slur or rush. No English vocals, no rap unless requested, no heavy autotune.\n\n"
              f"Sing exactly these Traditional Chinese lyrics, nothing else:\n{lyrics}")

    out = root / "audio"
    out.mkdir(exist_ok=True)
    ms = int(cfg.get("song_ms", 55000))

    ok = 0
    for i in range(1, takes + 1):
        print(f"--- take {i} 生成中（約 1-3 分鐘）---", flush=True)
        r = requests.post("https://api.elevenlabs.io/v1/music",
                          headers={"xi-api-key": key, "Content-Type": "application/json"},
                          params={"output_format": "mp3_44100_192"},
                          json={"prompt": prompt, "music_length_ms": ms, "model_id": "music_v2"},
                          timeout=900)
        if r.status_code != 200:
            print(f"  ❌ take {i} 失敗 {r.status_code}: {r.text[:300]}", flush=True)
            continue
        p = out / f"take{i}.mp3"
        p.write_bytes(r.content)
        ok += 1
        print(f"  ✅ {p}  ({len(r.content)/1024:.0f} KB)", flush=True)

    if not ok:
        sys.exit("❌ 一個 take 都沒生出來")
    print("\n👉 下一步：python3 pick_take.py mv.json   （用機器挑咬字，不要用感覺挑）")

if __name__ == "__main__":
    main()
