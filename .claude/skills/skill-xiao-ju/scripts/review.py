"""步驟 7：成片審查（Gemini 3.1 Pro 看整支片＋聽混音）
用法：python3 review.py <成片.mp4>
⚠️ Gemini 看整支片時抓不到小面積的亂碼字（EP01 就漏了兩處），scan.py 的逐格總表才是主力，這裡是補充。"""
import sys, subprocess
from pathlib import Path
from google import genai
from google.genai import types
from common import ROOT, key

src = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted((ROOT / "out").glob("*.mp4"), key=lambda p: p.stat().st_mtime)[-1]
small = ROOT / "out" / "_review.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", "scale=540:960", "-c:v", "libx264", "-crf", "26",
                "-c:a", "aac", "-b:a", "128k", str(small)], check=True)
cl = genai.Client(api_key=key("GEMINI_API_KEY"))
q = ("這是一支 9:16 的 AI 生成短劇。請以短劇製作人的角度，用繁體中文條列精簡回答：\n"
     "①劇情看不看得懂（一句話複述）②角色長相在不同鏡頭是否一致（點名誰、第幾秒）③字幕與語音是否同步、有無錯字 "
     "④畫面瑕疵（變形、多手指、閃爍、物件突變、亂碼字或 logo，附秒數）⑤台詞有沒有被配樂或音效蓋過、結尾有沒有突然斷掉 "
     "⑥前 3 秒鉤子強不強 ⑦最該優先修的三件事")
for m in ("gemini-3.1-pro-preview", "gemini-2.5-flash"):
    try:
        r = cl.models.generate_content(model=m, contents=[types.Part.from_bytes(data=small.read_bytes(), mime_type="video/mp4"), q])
        print(f"[{m}]\n{r.text}"); break
    except Exception as e:
        print(m, "失敗：", str(e)[:150])
