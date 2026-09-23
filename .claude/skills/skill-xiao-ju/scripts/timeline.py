"""時間軸：對白鏡頭長度＝該句音檔長度；其他鏡頭長度＝episode.json 的 dur"""
import sys
from common import ROOT, EP, dur


def build():
    t, out = 0.0, []
    for sh in EP["shots"]:
        if sh["type"] == "talk":
            f = ROOT / "audio" / f"{sh['id']}.mp3"
            if not f.exists():
                sys.exit(f"⏳ 還沒配音：找不到 audio/{sh['id']}.mp3（先跑 gen_audio.py）")
            d = dur(f)
        else:
            d = sh["dur"]
        out.append({"id": sh["id"], "type": sh["type"], "start": round(t, 3), "dur": round(d, 3), "end": round(t + d, 3)})
        t += d
    return out


if __name__ == "__main__":
    tl = build()
    for x in tl:
        print(f"{x['id']}  {x['type']:5s}  {x['start']:6.2f} → {x['end']:6.2f}  ({x['dur']:.2f}s)")
    print(f"總長 {tl[-1]['end']:.2f} 秒")
