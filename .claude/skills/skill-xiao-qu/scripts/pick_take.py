#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小曲 · 用本機 Whisper 挑 take（挑咬字，不是挑感覺）

把每個 take 轉回文字，跟歌詞逐句比對字元命中率，印出結果並推薦。
命中率低的句子＝唱糊了，**那幾句不要寫進字幕**。

用法：
    python3 pick_take.py mv.json
"""
import sys, json, re, pathlib

def norm(s):
    return re.sub(r"[^一-鿿]", "", s)

def hit(line, heard):
    a = norm(line)
    if not a:
        return 1.0
    return sum(1 for c in a if c in heard) / len(a)

def main():
    if len(sys.argv) < 2:
        sys.exit("用法：python3 pick_take.py mv.json")
    import whisper
    cfg_path = pathlib.Path(sys.argv[1]).resolve()
    root = cfg_path.parent
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    lines = [l.strip() for l in cfg.get("lyrics", "").splitlines()
             if l.strip() and not l.strip().startswith("[")]
    if not lines:
        sys.exit("❌ mv.json 缺 lyrics")

    takes = sorted((root / "audio").glob("take*.mp3"))
    if not takes:
        sys.exit("❌ audio/ 底下沒有 take*.mp3，先跑 gen_song.py")

    print("載入 Whisper large-v3-turbo（第一次會下載模型）…", flush=True)
    model = whisper.load_model("large-v3-turbo")

    best, best_score = None, -1
    for t in takes:
        print(f"\n=== {t.name} ===", flush=True)
        r = model.transcribe(str(t), language="zh",
                             initial_prompt="以下是繁體中文歌曲的歌詞。")
        heard = set(norm(r["text"]))
        (root / f"heard_{t.stem}.txt").write_text(r["text"], encoding="utf-8")
        scores = []
        for l in lines:
            s = hit(l, heard)
            scores.append(s)
            mark = "✅" if s >= 0.8 else ("⚠️" if s >= 0.55 else "❌")
            print(f"  {mark} {s*100:5.1f}%  {l}")
        avg = sum(scores) / len(scores)
        print(f"  → 平均命中 {avg*100:.1f}%")
        if avg > best_score:
            best, best_score = t, avg

    print(f"\n🏆 建議用 {best.name}（{best_score*100:.1f}%）")
    print("⚠️ 上面標 ❌ 的句子唱糊了 → 字幕不要寫那幾句，或重生一個 take。")
    print(f"\n👉 下一步：python3 align_subs.py {sys.argv[1]} --take {best.stem[-1]}")

if __name__ == "__main__":
    main()
