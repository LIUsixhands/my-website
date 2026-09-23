"""小劇共用設定：專案資料夾＝目前所在資料夾（先 cd 進去再跑各步驟）"""
import os, re, sys, json, time, subprocess
from pathlib import Path

ROOT = Path(os.environ.get("XJ_PROJECT") or Path.cwd()).resolve()
EPF = ROOT / "episode.json"
if not EPF.exists():
    sys.exit(f"❌ 找不到 {EPF}\n   先 cd 進短劇專案資料夾，或用 new_episode.py 建一個新專案。")
EP = json.loads(EPF.read_text(encoding="utf-8"))
FIX = EP.get("fixes", {})
IMG_MODEL = "gemini-3.1-flash-image-preview"
SKILL = Path(__file__).resolve().parent.parent

for d in ("refs", "frames", "audio", "clips", "sfx", "subs", "out"):
    (ROOT / d).mkdir(exist_ok=True)


def key(name):
    """金鑰：先看環境變數，再看 ~/.zshrc、~/.bash_profile（Mac 的 Bash 環境常讀不到 zshrc）"""
    if os.environ.get(name):
        return os.environ[name]
    for rc in (".zshrc", ".bash_profile", ".bashrc"):
        f = Path.home() / rc
        if f.exists():
            for line in f.read_text(errors="ignore").splitlines():
                m = re.match(rf'^\s*export {name}=(.*)$', line)
                if m:
                    return m.group(1).strip().strip('"').strip("'")
    sys.exit(f"❌ 沒有設定 {name}（見 安裝說明.md）")


def dur(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(f)]).decode())


def shots(ids=None):
    return [s for s in EP["shots"] if not ids or s["id"] in ids]


def gemini_image(prompt, out, refs=(), aspect="9:16", tries=3):
    from google import genai
    from google.genai import types
    out = Path(out)
    if out.exists():
        return out
    cl = genai.Client(api_key=key("GEMINI_API_KEY"))
    parts = []
    for r in refs:
        b = Path(r).read_bytes()
        parts.append(types.Part.from_bytes(data=b, mime_type="image/png" if b[:4] == b"\x89PNG" else "image/jpeg"))
    cfg = types.GenerateContentConfig(response_modalities=["IMAGE"], image_config=types.ImageConfig(aspect_ratio=aspect))
    for _ in range(tries):
        try:
            resp = cl.models.generate_content(model=IMG_MODEL, contents=parts + [prompt], config=cfg)
            for p in resp.candidates[0].content.parts:
                if getattr(p, "inline_data", None):
                    out.write_bytes(p.inline_data.data)
                    return out
            print("   （這次沒回圖，重試）")
        except Exception as e:
            print("   生圖重試：", str(e)[:160])
            time.sleep(4)
    raise RuntimeError(f"生圖失敗 {out.name}")
