"""開一個新短劇專案：python3 new_episode.py <專案資料夾> [--style anime|real] [--brand sixhands|none]
會複製劇本範本 episode.json（範例是代銷 EP01《穿藍白拖的客人》），再依你的劇本改。"""
import sys, json, shutil
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    sys.exit(__doc__)
dst = Path(args[0]).expanduser().resolve()
if (dst / "episode.json").exists():
    sys.exit(f"❌ {dst} 已經有 episode.json，不覆蓋")
dst.mkdir(parents=True, exist_ok=True)
for d in ("refs", "frames", "audio", "clips", "sfx", "subs", "out"):
    (dst / d).mkdir(exist_ok=True)
ep = json.loads((SKILL / "templates" / "episode_template.json").read_text(encoding="utf-8"))
styles = json.loads((SKILL / "templates" / "style_presets.json").read_text(encoding="utf-8"))
style = sys.argv[sys.argv.index("--style") + 1] if "--style" in sys.argv else "anime"
ep["style"] = styles[style]
brand = sys.argv[sys.argv.index("--brand") + 1] if "--brand" in sys.argv else "none"
if brand == "none":
    ep["brand"] = {"logo": "", "logo_end": "", "line": ""}
(dst / "episode.json").write_text(json.dumps(ep, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"✅ 新專案：{dst}\n   畫風：{style}｜品牌：{brand}\n   下一步：改 episode.json 的劇本，再 cd 進去跑 gen_refs.py")
