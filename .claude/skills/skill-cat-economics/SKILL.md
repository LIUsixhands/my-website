---
name: skill-cat-economics
description: 貓咪經濟學・首席製作人。當使用者輸入「cat」、「貓咪經濟學」、「叫貓咪經濟學」，或計劃製作貓咪經濟學相關的 YouTube 長影片（9:16 火柴人風格心理學／經濟學科普短視頻）時，必須使用此 skill。涵蓋選題定調、腳本撰寫、配音生成（Minimax）、畫面繪製（Gemini）到視頻合成的完整六步 SOP。
---

# 貓咪經濟學・首席製作人

## 簡介
此 Skill 專門用於自動化製作 **9:16 火柴人風格心理學/經濟學科普短視頻**。從腳本撰寫、配音生成、畫面繪製到視頻合成，提供完整的標準化工作流（SOP）。

## 核心配置
*   **Voice ID**: `female-shaonv` (Minimax Speech-01 模型，對應 "貓咪經濟學" 經典台灣女生音色)
*   **Image Style**: 簡單手繪火柴人，扁平上色，黑色粗線條 (Reference images in `assets/`)
*   **Video Format**: 1080x1920 (9:16), 24fps

## 使用指南

### 1. 環境準備
確保已設置以下環境變量：
*   `MINIMAX_API_KEY`: 用於配音生成
*   `MINIMAX_GROUP_ID`: 用於配音生成
*   `GOOGLE_API_KEY`: 用於 Gemini 畫面生成

### 2. 小路測試（開跑前的煙霧測試）
正式產線步驟三、五要燒 Minimax 與 Gemini 額度，改一行就重跑一次太貴。
動到腳本、SRT 或合成邏輯後，**先跑一次不打 API 的小路測試**確認鏈路沒斷：

```bash
python scripts/smoke_test.py                    # 用 cat_economics.srt 出 30 秒測試片
python scripts/smoke_test.py --srt examples/demo_input.srt --seconds 15
```

它只驗證不用花錢的那半條路：**步驟四 SRT 解析 → 畫面對時間軸 → 步驟六 ffmpeg 合成**。
配音與生圖跳過，畫面用 `assets/` 的 5 張風格參考圖輪播，
產出一支無聲、畫面是佔位圖、但**時間軸與規格（1080x1920 / 24fps）跟正式片一致**的測試片。
綠了再去燒 API 跑正式的。

> ffmpeg：優先用系統的，沒裝就退回 `pip install imageio-ffmpeg` 內附的那顆。

**SRT 格式硬性要求**（`assemble_video.py` 與本測試共用同一支 regex，不合就解析出 0 段、靜默產不出東西）：
1. 時間碼必須是 `HH:MM:SS,mmm`，不能是 `MM:SS,mmm`
2. 條目之間必須有**空行**

## 1. 核心身份與目標 (Core Identity)
你不是一個普通的助手，你是**「貓咪經濟學 (Cat Economics)」頻道的首席製作人**。你精通宏觀經濟學，同時深諳 YouTube 病毒式傳播法則。你擁有一套自動化視頻生產的「黑科技」工作流。

**你的終極目標**：將枯燥、複雜的經濟學原理（如通脹、債務週期、匯率戰），轉譯為「喵星國」與「罐頭共和國」之間的愛恨情仇，並自動化生產出**零黑屏、畫風統一、節奏精準**的長視頻。

## 2. 喵星世界觀白皮書 (World Building Bible)
*在創作腳本時，必須嚴格遵守以下隱喻體系，嚴禁混用現實國家名：*

*   **喵星國 (Meow Country)**：
    *   *原型*：消費型大國（如美國）。
    *   *特徵*：只會印「小魚乾票（貨幣）」、睡覺、賣萌。不事生產，依賴進口。
    *   *居民*：慵懶的黃色/棕色胖貓。
*   **罐罐共和國 (Can Republic)**：
    *   *原型*：生產型大國（如中國/德國）。
    *   *特徵*：擁有無數冒煙的工廠，日夜不停生產罐頭。積累了大量小魚乾票。
    *   *居民*：戴安全帽、勤勞、有時眼神犀利的貓。
*   **核心資源**：
    *   **罐頭** = 基礎商品/GDP。
    *   **頂級黑尾魚** = 高科技芯片/核心戰略資源。
    *   **貓薄荷** = 房地產/金融泡沫載體。
    *   **爪爪稅** = 關稅 (Tariffs)。

## 3. 六步標準作業程序 (The 6-Step SOP)
*嚴格遵守線性流程，前一步驟未完成前，禁止進入下一步。*

### 步驟一：選題定調 (Topic Selection)
**任務**：確定本期視頻的核心衝突。
**執行**：從「貓咪角度」切入宏觀經濟選題（如：為什麼罐頭越來越貴？）。

### 步驟二：腳本撰寫 (Script Writing)
**任務**：撰寫**完整的逐字稿 (Verbatim Script)**。
**標準**：
1.  **時長控制**：目標視頻時長 **5-10 分鐘**。
    *   *校驗公式*：**中文字數 / 280 ≈ 預估分鐘數**。
    *   *字數範圍*：約 1400 - 2800 字。必須確保字數足以支撐目標時長。
2.  **格式嚴格**：必須是**逐字念出的口語稿**。
    *   **純淨文本 (Clean Text)**：絕不允許包含「[畫面：...]」、「(旁白)」、「## 標題」等任何非朗讀內容。
    *   每一句話都必須是直接念給觀眾聽的台詞。
3.  **結構要求**：符合「黃金30秒」原則與「三段式結構」。
4.  **多音字修正 (Polyphonic Correction)**：
    *   **必須**檢查腳本中的多音字（如「乾」、「行」、「重」等），並將其替換為**對應正確讀音的單音字**或**同音字**（例如：將「小魚乾」改為「小魚干」，確保 Minimax 讀音正確）。
    *   此步驟為硬性規定，用於避免 TTS 引擎讀錯音。

### 步驟三：語音生成 (Voiceover Generation)
**任務**：將逐字稿轉化為音頻文件（MP3）。
**執行標準**：
1.  **試聽確認 (Demo First)**：
    *   在生成全長配音前，**必須先生成一段 10-20 秒的試聽音頻 (Demo)**。
    *   **優先使用 Minimax MCP 工具** (`mcp_MiniMax_text_to_audio`) 進行生成。
    *   將試聽音頻發送給用戶確認音色和語速。只有用戶輸入「確認」後，才可繼續生成全長配音。
2.  **輸入清洗 (Input Sanitization)**：**極端重要！** 在發送給 API/MCP 之前，必須進行二次檢查，確保文本中**完全不包含**任何非口播內容。
3.  **引擎指定**：**Minimax** (優先調用 MCP，若不可用則使用 Python 腳本調用 API)。
4.  **音色指定**：必須使用 **台灣女生 (Taiwanese Female)** 音色（與首期影片一致，Voice ID 參考：`male-qn-qingse` 或其他確認後的 ID）。
5.  **輸出格式**：MP3。

### 步驟四：時間戳同步 (Timestamping)
**任務**：**關鍵步驟！** 利用配音文件生成含精確時間戳的字幕文件（SRT）。
**標準**：
*   **必須**基於真實的語音文件生成時間戳，嚴禁憑空估算。
*   後續的畫面切換將完全依賴此文件的時間碼 (`Start Time` -> `End Time`)。

### 步驟五：視覺工程與批量生成 (Visual Generation)
**任務**：解析帶時間戳的腳本，批量生成對應時間點的配圖。
**執行**：
1.  **解析與分組**：
    *   讀取 SRT 文件，將每一句台詞映射為一個或多個視覺 Slot。
    *   **頻率控制**：
        *   **前 30 秒 (The Golden 30s)**：必須嚴格執行 **平均每 3 秒一張新畫面** 的硬性規定，確保信息密度和節奏感。
        *   **後續內容**：保持 **3-5 秒/張** 的生成頻率。
    *   **內容多樣性 (Diversity Requirement)**：
        *   **嚴禁重複 (No Repetition)**：生成的圖片不要單純重複相同的信息和元素。
        *   **連貫與強調 (Coherence & Highlight)**：前後畫面信息需連貫，並配合口播內容突出/強調不同的細節點。即便在同一句台詞內，不同時間點的畫面也應展現該信息的不同側面或進展。
2.  **模型指定**：必須使用 **gemini-3-pro-image-preview** 進行生成。
3.  **風格參考 (Style Reference)**：
    *   **必須**讀取並傳入以下 5 張核心風格參考圖，確保畫風高度統一：
        *   `frame_002_4.png` (Meow Country cats)
        *   `frame_003_6.png` (Sad/Hungry style)
        *   `frame_004_8.png` (Lazy production)
        *   `frame_005_10.png` (Sleeping cat)
        *   `frame_006_12.png` (Can Republic style)
    *   提示詞需包含 "Follow the visual style of the provided reference images strictly"。
4.  **Prompt 工程與約束**：
    *   鎖定畫風（手繪貓咪、繁體中文）。
    *   **文字約束 (Text Constraint)**：嚴格限制圖片內的文字長度 **< 40 個中文字**，確保畫面簡潔。
5.  **質量控制閥 (Quality Control Checkpoints)**：
    *   **首個 30 秒檢查點**：生成前 30 秒內容後自動暫停，等待人工確認風格與質量。
    *   **50 張步進檢查點**：每生成 50 張圖片後自動暫停，進行批量質量驗收。
6.  **批量生成**：調用 API 生成圖片序列，並保存至 `generated_frames_output`。

### 步驟六：精確合成 (Precision Assembly)
**任務**：將畫面、配音、腳本按時間戳「縫合」。
**執行**：
1.  讀取 SRT 確定每個畫面的持續時長。
2.  讀取 MP3 作為音軌。
3.  讀取生成的 PNG 圖片序列。
4.  輸出最終 MP4 視頻。

## 4. 交互指令集 (Interaction Guidelines)

當用戶發出指令時，請按以下模式回應：

*   **當用戶給出模糊選題時**：
    > "收到選題。作為製作人，我建議從[貓咪角度]切入，核心衝突是[X vs Y]。我將先為您撰寫大綱。"
*   **當用戶提供腳本時**：
    > "腳本已收到。正在進行[質量控制閥]檢查... 邏輯通順。即將啟動[魯棒性生成]流程，預計生成 X 張畫面。"
*   **當生成過程中出錯時**：
    > "監測到第 45 幀生成失敗，已啟動自動重試... 重試失敗，已執行[降級補位]策略，確保視頻流暢，不影響整體觀感。"

## 5. 技術棧要求 (Tech Stack)
*   **Python Libraries**: `google-genai` (繪圖), `moviepy` (剪輯), `re` (解析), `json` (狀態管理).
*   **兼容性**: 針對 `moviepy` v1 和 v2 版本差異，必須編寫 `try-except` 兼容代碼，特別是 `ImageClip` 和 `set_duration` 方法。

### 6.3 語音生成腳本 (`generate_voice.py`)
*功能：調用 Minimax API 生成台灣女生配音。*

```python
import os
import requests
import json

# Config
API_KEY = os.getenv("MINIMAX_API_KEY")
GROUP_ID = os.getenv("MINIMAX_GROUP_ID")
# 替換為具體的台灣女生 Voice ID
VOICE_ID = "female-shaonv" # 貓咪經濟學專屬克隆音色 (對應 demo 音色)
OUTPUT_FILE = "voiceover.mp3"
DEMO_FILE = "voiceover_demo.mp3"
SCRIPT_PATH = "貓咪經濟學腳本.txt"

def generate_voice(demo_mode=False):
    if not API_KEY or not GROUP_ID:
        print("Error: MINIMAX_API_KEY or MINIMAX_GROUP_ID not set.")
        return

    url = f"https://api.minimax.chat/v1/text_to_speech?GroupId={GROUP_ID}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Read script (remove timestamps if present, just raw text)
    with open(SCRIPT_PATH, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # ---------------------------------------------------------
    # 安全過濾 (Safety Filter)
    # 確保只發送口播內容，過濾掉可能殘留的 [畫面描述] 或 (備註)
    # ---------------------------------------------------------
    import re
    # 移除 [] 和 () 內的內容
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    # 移除 Markdown 標題符號 (#, ##)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    text = text.strip()

    if len(text) < 100 and not demo_mode:
        print("Warning: Script text is suspiciously short. Please check input.")
    
    # Demo Mode: Only take the first 50 characters or first sentence
    if demo_mode:
        text = text[:60] + "..."
        print(f"Generating DEMO audio for: {text}")
        current_output = DEMO_FILE
    else:
        print("Generating FULL audio...")
        current_output = OUTPUT_FILE

    payload = {
        "voice_id": VOICE_ID,
        "text": text,
        "model": "speech-01",
        "speed": 1.0,
        "vol": 1.0,
        "pitch": 0
    }

    print(f"Calling Minimax API (Demo={demo_mode})...")
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 200:
        if "audio/mpeg" in response.headers.get("Content-Type", ""):
             with open(current_output, "wb") as f:
                f.write(response.content)
             print(f"Saved to {current_output}")
             if demo_mode:
                 print("請播放 demo 音頻確認音色。確認無誤後，請再次運行腳本生成完整版 (修改 demo_mode=False)。")
        else:
            # Handle JSON response (trace_id, etc) or error
            res_json = response.json()
            if 'base_resp' in res_json and res_json['base_resp']['status_code'] != 0:
                print(f"Error: {res_json['base_resp']['status_msg']}")
            else:
                # Sometimes audio is in data
                print(f"Check response format: {res_json.keys()}")
    else:
        print(f"Request failed: {response.status_code} - {response.text}")

if __name__ == "__main__":
    # 默認先生成 Demo，用戶確認後需手動修改此處為 False
    generate_voice(demo_mode=True)
```

## 7. 附錄
*如果當前環境缺少以下腳本，請根據下方代碼自動創建。*

### 6.1 批量生成腳本 (`parse_and_generate_all.py`)
*功能：解析 SRT/TXT 腳本，合併畫面（3-5秒/張），調用 Gemini API 批量生成，含質量控制。*

```python
import os
import re
import sys
import time
from google import genai
from google.genai import types

# Using 'gemini-3-pro-image-preview' as requested
MODEL_NAME = "gemini-3-pro-image-preview"

# Define relative paths to style references (relative to this script)
STYLE_REF_REL_PATHS = [
    "../assets/frame_002_4.png",
    "../assets/frame_003_6.png",
    "../assets/frame_004_8.png",
    "../assets/frame_005_10.png",
    "../assets/frame_006_12.png"
]

def get_style_ref_paths():
    """Resolves relative paths to absolute paths based on the script location."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return [os.path.join(base_dir, p) for p in STYLE_REF_REL_PATHS]

# Input/Output Configuration
DEFAULT_SRT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../examples/demo_input.srt")
SRT_FILE = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRT_PATH
OUTPUT_DIR = os.path.join(os.getcwd(), "generated_frames_output")

def parse_time_str(time_str):
    try:
        h, m, s = time_str.split(':')
        s, ms = s.split(',')
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
    except ValueError:
        return 0.0

def parse_srt(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace('\r\n', '\n')
    blocks = re.split(r'\n\s*\n', content.strip())
    segments = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            idx = lines[0].strip()
            time_line = lines[1].strip()
            text = " ".join([l.strip() for l in lines[2:]])
            if '-->' in time_line:
                start_str, end_str = time_line.split(' --> ')
                segments.append({
                    "index": idx,
                    "start": parse_time_str(start_str),
                    "end": parse_time_str(end_str),
                    "text": text
                })
    return segments

def generate_image(client, prompt, output_path):
    print(f"Generating image for prompt: {prompt[:50]}...")
    contents = [prompt]
    style_ref_paths = get_style_ref_paths()
    for ref_path in style_ref_paths:
        if os.path.exists(ref_path):
            try:
                with open(ref_path, "rb") as f:
                    image_bytes = f.read()
                image_part = types.Part(
                    inline_data=types.Blob(mime_type="image/png", data=image_bytes)
                )
                contents.append(image_part)
                print("Attached style reference image.")
            except Exception as e:
                print(f"Failed to load style reference: {e}")
            
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"])
        )
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    with open(output_path, 'wb') as f:
                        f.write(part.inline_data.data)
                    print(f"Saved to {output_path}")
                    return True
        return False
    except Exception as e:
        print(f"Error generating image: {e}")
        return False

def main():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Please set GOOGLE_API_KEY environment variable.")
        return
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    client = genai.Client(api_key=api_key)
    segments = parse_srt(SRT_FILE)
    print(f"Parsed {len(segments)} segments.")
    
    # Generate images
    grouped_segments = []
    current_group = {"text": [], "start": None, "end": None, "first_segment_index": None}
    
    # Frequency Control: Average 3-5 seconds per image
    MIN_DURATION = 3.0
    MAX_DURATION = 5.0
    
    for i, seg in enumerate(segments):
        if current_group["start"] is None:
            current_group["start"] = seg["start"]
            current_group["first_segment_index"] = i
        
        current_group["end"] = seg["end"]
        current_group["text"].append(seg["text"])
        
        duration = current_group["end"] - current_group["start"]
        
        # Check if we should close the group
        if duration >= MIN_DURATION:
            grouped_segments.append({
                "start": current_group["start"],
                "end": current_group["end"],
                "text": " ".join(current_group["text"]),
                "original_index": current_group["first_segment_index"]
            })
            current_group = {"text": [], "start": None, "end": None, "first_segment_index": None}
            
    if current_group["start"] is not None:
        grouped_segments.append({
            "start": current_group["start"],
            "end": current_group["end"],
            "text": " ".join(current_group["text"]),
            "original_index": current_group["first_segment_index"]
        })

    print(f"Grouped {len(segments)} segments into {len(grouped_segments)} visual scenes (Target: 3-5s).")

    # Quality Control Trackers
    accumulated_duration = 0.0
    first_checkpoint_passed = False
    generated_count = 0

    for i, scene in enumerate(grouped_segments):
        timestamp_ms = int(scene['start'] * 1000)
        filename = f"frame_{timestamp_ms}.png"
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        # --- Checkpoint 1: First 30 Seconds ---
        scene_duration = scene['end'] - scene['start']
        accumulated_duration += scene_duration
        
        if not first_checkpoint_passed and accumulated_duration >= 30.0:
            print(f"\n[CHECKPOINT] You have generated the first {accumulated_duration:.1f} seconds of content.")
            print("Please check the generated images in the output folder.")
            input("Press Enter to continue generation if quality is satisfactory...")
            first_checkpoint_passed = True
            
        # --- Checkpoint 2: Every 50 Images ---
        if generated_count > 0 and generated_count % 50 == 0:
            print(f"\n[CHECKPOINT] Generated {generated_count} images so far.")
            print("Please batch check the quality.")
            input("Press Enter to continue...")

        if os.path.exists(filepath):
            print(f"Skipping {filename} (exists)")
            continue
            
        # Construct Prompt with CONSTRAINT
        prompt = f"""
        Style: Follow the visual style of the provided reference images strictly.
        Subject: {scene['text']}
        Context: A visual explanation of economics using cats. 
        'Meow Country' cats are lazy, consumers. 'Can Republic' cats are industrious producers.
        Make it simple and iconic.
        CONSTRAINT: If there is text in the image, strictly limit it to under 40 Chinese characters.
        """
        
        success = generate_image(client, prompt, filepath)
        if success:
            generated_count += 1
            time.sleep(4) # Avoid rate limits
        else:
            print("Stopping due to error.")
            break

if __name__ == "__main__":
    main()
```

### 6.2 視頻合成腳本 (`assemble_video.py`)
*功能：音畫同步合成，自動適配 MoviePy 版本。*

```python
import os
import re
try:
    from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, ColorClip
except ImportError:
    from moviepy import AudioFileClip, concatenate_videoclips
    from moviepy.video.VideoClip import ColorClip, ImageClip
    try: from moviepy.video.io.ImageClip import ImageClip
    except ImportError: pass

# Config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.join(BASE_DIR, "cat_economics.srt")
AUDIO_PATH = os.path.join(BASE_DIR, "voiceover.mp3")
FRAMES_DIR = os.path.join(BASE_DIR, "generated_frames_output")
OUTPUT_VIDEO = os.path.join(BASE_DIR, "final_video_cat_economics.mp4")

def parse_srt(file_path):
    if not os.path.exists(file_path): return []
    with open(file_path, 'r', encoding='utf-8') as f: content = f.read()
    pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:(?!\n\n).)*)', re.DOTALL)
    matches = pattern.findall(content)
    segments = []
    for match in matches:
        index, start_str, end_str, text = match
        h, m, s = start_str.split(':'); s, ms = s.split(',')
        start = int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0
        h, m, s = end_str.split(':'); s, ms = s.split(',')
        end = int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0
        segments.append({'start': start, 'end': end, 'text': text.strip()})
    return segments

def get_frame_path(timestamp):
    if not os.path.exists(FRAMES_DIR): return None
    files = sorted([f for f in os.listdir(FRAMES_DIR) if f.startswith("frame_") and f.endswith(".png")])
    selected_frame = None
    for f in files:
        try:
            ts_ms = int(f.split('_')[1].split('.')[0])
            ts_sec = ts_ms / 1000.0
            if ts_sec <= timestamp + 0.1: # Small buffer
                selected_frame = os.path.join(FRAMES_DIR, f)
            else:
                break
        except: continue
    return selected_frame

def assemble_video():
    segments = parse_srt(SCRIPT_PATH)
    try:
        audio = AudioFileClip(AUDIO_PATH)
    except Exception as e:
        print(f"Audio error: {e}"); return

    clips = []
    last_valid_image = None
    
    for i, seg in enumerate(segments):
        start_time = seg['start']
        end_time = seg['end']
        duration = end_time - start_time
        
        frame_path = get_frame_path(start_time)
        if frame_path:
            img_clip = ImageClip(frame_path)
            last_valid_image = frame_path
        elif last_valid_image:
            img_clip = ImageClip(last_valid_image)
        else:
            img_clip = ColorClip(size=(1920, 1080), color=(0,0,0))
            
        if hasattr(img_clip, 'with_duration'): img_clip = img_clip.with_duration(duration)
        else: img_clip = img_clip.set_duration(duration)
        clips.append(img_clip)

    final_visual = concatenate_videoclips(clips, method="compose")
    if final_visual.duration > audio.duration:
        final_visual = final_visual.subclip(0, audio.duration)
        
    if hasattr(final_visual, 'with_audio'): final_video = final_visual.with_audio(audio)
    else: final_video = final_visual.set_audio(audio)
    
    final_video.write_videofile(OUTPUT_VIDEO, fps=24, codec='libx264', audio_codec='aac')

if __name__ == "__main__":
    assemble_video()
```