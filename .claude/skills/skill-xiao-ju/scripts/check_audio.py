"""步驟 3b：Gemini 逐句核對配音（漏字、多字、把 [標籤] 念出來、語氣、口音、雜音）
用法：python3 check_audio.py [s01 ...]
⚠️ Gemini 的口音判斷不穩，同一個聲音會一下說台灣一下說大陸；以「漏字／念錯字」為準。"""
import sys
from google import genai
from google.genai import types
from common import ROOT, EP, key, shots

cl = genai.Client(api_key=key("GEMINI_API_KEY"))
for sh in shots(set(sys.argv[1:])):
    ln = sh.get("line") or sh.get("vo")
    f = ROOT / "audio" / f"{sh['id']}.mp3"
    if not ln or not f.exists():
        continue
    q = (f"這是一段短劇台詞配音。預期台詞（方括號是情緒指示，不應被念出）：{ln['text']}\n"
         "請用繁體中文回答一行：①逐字聽寫 ②有無漏字／多字／念錯字／把方括號念出來 ③語氣是否符合情緒指示 ④有無雜音怪聲。精簡。")
    r = cl.models.generate_content(model="gemini-2.5-flash", contents=[types.Part.from_bytes(data=f.read_bytes(), mime_type="audio/mpeg"), q])
    print(sh["id"], "→", r.text.strip().replace("\n", " "))
