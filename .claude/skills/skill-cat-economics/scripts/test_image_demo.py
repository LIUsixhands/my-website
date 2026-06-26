#!/usr/bin/env python3
"""測試用：驗證 GOOGLE_API_KEY 與 Gemini 畫面生成是否正常。

只產生 2 張測試圖、不需 SRT、不會中途暫停。
自動套用 assets/ 的風格參考圖；若設定的模型不可用會自動改用可用的影像模型。

用法：
    python .claude/skills/skill-cat-economics/scripts/test_image_demo.py
輸出：
    ./generated_frames_output/test_*.png
"""
import os
import sys

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("❌ 缺少套件 google-genai。請確認 setup script 已執行：pip install google-genai")
    sys.exit(1)

# 優先使用 skill 指定的模型，失敗時依序嘗試這些備援影像模型
PREFERRED_MODEL = "gemini-3-pro-image-preview"
FALLBACK_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-2.5-flash-image-preview",
    "gemini-2.0-flash-preview-image-generation",
    "gemini-2.0-flash-exp",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "..", "assets")
STYLE_REFS = [
    "frame_002_4.png",
    "frame_003_6.png",
    "frame_004_8.png",
    "frame_005_10.png",
    "frame_006_12.png",
]
OUTPUT_DIR = os.path.join(os.getcwd(), "generated_frames_output")

# 兩個測試畫面（取自喵星世界觀）
TEST_PROMPTS = [
    "一隻又胖又慵懶的黃色貓咪躺在沙發上曬太陽，旁邊散落著印有小魚圖案的鈔票。簡單手繪火柴人風格，扁平上色，黑色粗線條。",
    "一隻戴著黃色安全帽、勤勞的貓咪站在冒煙的罐頭工廠前，神情認真。簡單手繪火柴人風格，扁平上色，黑色粗線條。",
]


def load_style_parts():
    parts = []
    for name in STYLE_REFS:
        path = os.path.join(ASSETS_DIR, name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                parts.append(types.Part(inline_data=types.Blob(mime_type="image/png", data=f.read())))
    print(f"已載入 {len(parts)} 張風格參考圖")
    return parts


def try_generate(client, model, prompt, style_parts, out_path):
    contents = [prompt] + style_parts
    resp = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    if resp.candidates and resp.candidates[0].content and resp.candidates[0].content.parts:
        for part in resp.candidates[0].content.parts:
            if getattr(part, "inline_data", None):
                with open(out_path, "wb") as f:
                    f.write(part.inline_data.data)
                return True
    return False


def main():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("❌ 找不到 GOOGLE_API_KEY 環境變數。請確認已在環境設定填入並存檔，且這是新開的 session。")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    client = genai.Client(api_key=api_key)
    style_parts = load_style_parts()

    # 決定要用哪個模型：先試指定的，不行就試備援
    candidates = [PREFERRED_MODEL] + FALLBACK_MODELS
    working_model = None
    last_err = None

    for i, prompt in enumerate(TEST_PROMPTS, 1):
        out_path = os.path.join(OUTPUT_DIR, f"test_{i}.png")
        done = False
        models_to_try = [working_model] if working_model else candidates
        for model in models_to_try:
            try:
                print(f"嘗試用模型 {model} 生成第 {i} 張…")
                if try_generate(client, model, prompt, style_parts, out_path):
                    print(f"✅ 已存檔：{out_path}（模型：{model}）")
                    working_model = model
                    done = True
                    break
                else:
                    print(f"   {model} 沒有回傳影像，換下一個。")
            except Exception as e:
                last_err = e
                print(f"   {model} 失敗：{e}")
        if not done:
            print(f"❌ 第 {i} 張生成失敗。最後錯誤：{last_err}")

    print("\n完成。請查看資料夾：", OUTPUT_DIR)


if __name__ == "__main__":
    main()
