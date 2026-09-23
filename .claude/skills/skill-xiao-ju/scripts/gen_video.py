"""步驟 4：影片生成（fal.ai）
- 對白鏡頭（talk）→ Kling AI Avatar v2 對嘴（實測不輸 OmniHuman、價格 1/3，預設用它）
- 其他鏡頭（anim / card）→ Hailuo-02 圖生影片 6 秒（後半常亂演，合成時只取前段）
用法：python3 gen_video.py [s01 ...] [--omni s06,s09]
  --omni：另外用 OmniHuman 生指定鏡頭的對照版（檔名 sXX_omni.mp4），Kling 版出包時可換
成品已存在就跳過；request_id 記在 clips/_jobs.json，程式中斷可從 fal 後台撈回。"""
import os, sys, json, threading, requests
from concurrent.futures import ThreadPoolExecutor
from common import ROOT, EP, key, shots

os.environ["FAL_KEY"] = key("FAL_KEY")
import fal_client

F, A, C = ROOT / "frames", ROOT / "audio", ROOT / "clips"
JOBS = C / "_jobs.json"
lock = threading.Lock()
argv = sys.argv[1:]
OMNI_IDS = set()
if "--omni" in argv:
    i = argv.index("--omni")
    OMNI_IDS = set(argv[i + 1].split(","))
    argv = argv[:i] + argv[i + 2:]
only = set(a for a in argv if not a.startswith("--"))
KLING = "fal-ai/kling-video/ai-avatar/v2/standard"
OMNI = "fal-ai/bytedance/omnihuman/v1.5"
HAILUO = "fal-ai/minimax/hailuo-02/standard/image-to-video"


def run(name, ep, make_args):
    out = C / f"{name}.mp4"
    if out.exists():
        print("skip", name); return
    args = make_args()  # 需要時才上傳素材
    h = fal_client.submit(ep, arguments=args)
    with lock:
        d = json.loads(JOBS.read_text()) if JOBS.exists() else {}
        d[name] = {"endpoint": ep, "request_id": h.request_id}
        JOBS.write_text(json.dumps(d, indent=1))
    print("submitted", name, flush=True)
    res = fal_client.result(ep, h.request_id)
    out.write_bytes(requests.get(res["video"]["url"], timeout=300).content)
    print("done", name, flush=True)


def tasks():
    for sh in shots(only):
        sid = sh["id"]
        img = lambda sid=sid: fal_client.upload_file(str(F / f"{sid}.png"))
        aud = lambda sid=sid: fal_client.upload_file(str(A / f"{sid}.mp3"))
        if sh["type"] == "talk":
            yield sid, KLING, lambda sh=sh, img=img, aud=aud: {"image_url": img(), "audio_url": aud(), "prompt": sh.get("prompt", ".")}
            if sid in OMNI_IDS:
                yield f"{sid}_omni", OMNI, lambda sh=sh, img=img, aud=aud: {"image_url": img(), "audio_url": aud(), "prompt": sh.get("prompt", ""), "resolution": "1080p"}
        else:
            motion = sh.get("motion", "Subtle cinematic movement, slow push-in.")
            yield sid, HAILUO, lambda img=img, motion=motion: {"prompt": motion + " Keep the character's face and outfit unchanged. No text, no subtitles, no logos.",
                                                              "image_url": img(), "duration": "6", "prompt_optimizer": False}


with ThreadPoolExecutor(16) as ex:
    fs = [ex.submit(run, *t) for t in tasks()]
    err = 0
    for f in fs:
        try:
            f.result()
        except Exception as e:
            err += 1; print("❌", e, flush=True)
print("ALL DONE, errors:", err)
print("🔍 下一步：跑 scan.py 逐格掃描（影片模型會自己生出亂碼字、假字幕、品牌 logo、物件變形）")
