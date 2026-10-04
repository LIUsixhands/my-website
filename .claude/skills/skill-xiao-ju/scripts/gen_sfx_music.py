"""步驟 5：音效＋配樂（ElevenLabs）
- 音效：episode.json 的 "sfx" 清單，每項 {name, prompt, dur, at(鏡頭 id), offset, vol}
- 配樂：episode.json 的 "music"，依 sections[].from 指定的鏡頭切段，長度自動對齊時間軸（composition_plan）
用法：python3 gen_sfx_music.py [sfx] [music]    已存在就跳過；配樂一支約 1,500 credits，不滿意才重生"""
import sys, json, requests
from common import ROOT, EP, key, dur
from timeline import build

S = ROOT / "sfx"
H = {"xi-api-key": key("ELEVENLABS_API_KEY")}


def sfx():
    for s in EP.get("sfx", []):
        out = S / f"{s['name']}.mp3"
        if out.exists():
            continue
        r = requests.post("https://api.elevenlabs.io/v1/sound-generation", headers=H, timeout=120,
                          json={"text": s["prompt"], "duration_seconds": s.get("dur", 2.0), "prompt_influence": 0.6})
        r.raise_for_status()
        out.write_bytes(r.content)
        print("sfx ok", s["name"])


def music():
    out = S / "bgm.mp3"
    if out.exists():
        print("bgm 已存在（要重生先刪 sfx/bgm.mp3）"); return
    tl = build(); t = {x["id"]: x for x in tl}; total = tl[-1]["end"]
    secs = EP["music"]["sections"]
    starts = [t[s["from"]]["start"] for s in secs] + [total]
    plan = {"positive_global_styles": EP["music"].get("global", []),
            "negative_global_styles": EP["music"].get("negative", ["vocals", "singing", "lyrics"]),
            "sections": [{"section_name": s["name"], "positive_local_styles": s["styles"], "negative_local_styles": [],
                          "duration_ms": int(round((starts[i + 1] - starts[i]) * 1000)), "lines": []} for i, s in enumerate(secs)]}
    bad = [s for s in plan["sections"] if s["duration_ms"] < 3000]
    if bad:
        sys.exit(f"❌ 配樂段落至少要 3 秒：{[s['section_name'] for s in bad]}，請合併段落")
    print(json.dumps([(s["section_name"], s["duration_ms"]) for s in plan["sections"]], ensure_ascii=False))
    r = requests.post("https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128", headers=H, timeout=600,
                      json={"composition_plan": plan, "model_id": "music_v1"})
    if r.status_code != 200:
        sys.exit(f"music {r.status_code} {r.text[:300]}")
    out.write_bytes(r.content)
    print(f"bgm ok {dur(out):.2f}s（片長 {total:.2f}s）")


which = set(sys.argv[1:]) or {"sfx", "music"}
if "sfx" in which: sfx()
if "music" in which: music()
