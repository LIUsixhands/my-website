# 短影片自動化產線 Demo 🦞
**AI數字員工龍蝦學院 ▎ 實戰訓練營 第 7 堂**

一個指令，把「選題 → 腳本 → 配音 → 畫面 → 合成」跑成一支 9:16 短影片。
**設計成「零 API 金鑰也能跑」**，方便上課現場 demo。

---

## 1. 安裝（一次就好）

```bash
brew install ffmpeg          # 影音引擎
pip3 install pillow          # 生圖/字幕
```

> 配音用 macOS 內建的 `say`（美佳・台灣中文），不用裝任何東西。

## 2. 跑起來

```bash
cd 短影片產線_demo
python3 make_short.py "AI 如何讓小店營收翻倍"
```

跑完會自動打開 `final.mp4`（9:16、約 18 秒、含旁白＋字幕＋Ken Burns 推近）。

不給主題就用內建範例：
```bash
python3 make_short.py
```

## 3. 產線的 6 個環節（對照課堂投影片）

| 環節 | 函數 | 預設做法（零金鑰） | 升級成真 API |
|------|------|------------------|--------------|
| 1-2 腳本 | `get_scenes()` | 內建範例 / 讀 `scenes.json` | OpenAI 生分鏡 JSON |
| 3 配音 | `tts()` | macOS `say` 美佳 | ElevenLabs |
| 4 畫面 | `gen_image()` | Pillow 品牌占位圖＋燒字幕 | Imagen / DALL·E 文生圖 |
| 5a 單鏡 | `make_clip()` | ffmpeg + Ken Burns | 同 |
| 5b 拼接 | `stitch()` | ffmpeg concat（重編碼） | 同 |

## 4. 自己改內容

**換腳本**：在資料夾放一個 `scenes.json`，程式會優先讀它：
```json
[
  {"narration": "你的店其實一直在漏錢", "visual": "夜晚的小店外觀"},
  {"narration": "AI 員工幫你 24 小時接單", "visual": "手機聊天介面"}
]
```

**加背景音樂**：把一首**可商用**音樂放成 `assets/bgm.mp3`，程式會自動以 18% 音量混進去。
（音源請用 Musopen / filmmusic.io，別用有版權的歌，會被 YouTube Content ID 抓。）

## 5. 接真 API（有金鑰時）

```bash
export OPENAI_API_KEY=sk-...     # 開啟 LLM 生腳本
export ELEVEN_API_KEY=...        # 開啟 ElevenLabs 配音
```
生圖只要把 `gen_image()` 裡的占位邏輯換成你的文生圖 API 呼叫即可。

## 6. 量產（課堂進階）

```python
from make_short import make_short
for topic in ["主題1", "主題2", "主題3"]:
    make_short(topic)
```
再用 macOS `launchd` 或 `cron` 排程，就是龍蝦學院「每晚自動上片」的產線雛形。

---

## 常見地雷
- **字幕變方塊** → 中文字型要用「繁體字面」（程式已自動挑 Heiti TC）。
- **畫面被拉變形** → 素材一律走 9:16，程式已鎖 1080×1920。
- **配樂侵權** → 只用可商用音源。
- **拼接後字幕/聲音跑掉** → concat 一定要重編碼（程式已處理）。

---
*Jason 教練 ▎ AI數字員工龍蝦學院*
