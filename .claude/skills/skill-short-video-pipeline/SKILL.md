---
name: skill-short-video-pipeline
description: 用程式碼自動化生成 9:16 短影片的產線 — 把「選題→腳本→配音→畫面+字幕→ffmpeg 合成」串成一個指令，零 API 金鑰也能在 macOS 上跑出成片。當使用者想「用 code / 用程式做短影片」、要量產 Shorts/Reels/TikTok、要一個能現場 demo 的短影片自動化腳本、教學員「不用手機剪片」、或提到 make_short / 短影片產線 / 短影片自動化 / 龍蝦學院實戰訓練營第7堂時，主動觸發。也用於要把這條產線接真 API（OpenAI/ElevenLabs/文生圖）或排程量產的情境。觸發詞：短影片產線、code 做短影片、make_short、短影片自動化、量產 Shorts、零金鑰短影片。
---

# 短影片自動化產線（Code 版）

把一個主題，用程式碼跑成一支 9:16 直式短影片。核心精神：**你不是在做一支影片，是在養一台會自己生影片的機器** —— 一個指令、可量產、可排程，不靠手機手剪。

這是龍蝦學院實戰訓練營「第 7 堂：用 Code 做短影片」的實作產線。

## 何時用這個 skill

- 使用者想「用程式 / code 做短影片」「量產 Shorts」「教學員自動化做片」
- 要一個能在課堂**現場 demo**、不需任何付費金鑰就能跑出成片的腳本
- 要把這條產線**接上真 API**（LLM 生腳本、ElevenLabs 配音、文生圖）或**排程量產**

## 產線的 6 個環節

| 環節 | 函數 | 預設做法（零金鑰） | 升級成真 API |
|------|------|------------------|--------------|
| 1-2 腳本 | `get_scenes()` | 內建範例 / 讀 `scenes.json` | OpenAI 生分鏡 JSON |
| 3 配音 | `tts()` | macOS `say`（美佳・台灣中文） | ElevenLabs |
| 4 畫面+字幕 | `gen_image()` | Pillow 生品牌占位圖＋燒字幕 | Imagen / DALL·E 文生圖 |
| 5a 單鏡 | `make_clip()` | ffmpeg + Ken Burns 緩慢推近 | 同 |
| 5b 拼接 | `stitch()` | ffmpeg concat（重編碼）＋可選 BGM | 同 |

前一環節的輸出就是下一環節的輸入：腳本 JSON 餵給配音和生圖，圖＋音餵給 ffmpeg，成片餵給上傳。這就是「管線（pipeline）」。

## 怎麼跑（最短路徑）

腳本在 `scripts/make_short.py`。它的輸出與素材都讀寫**目前工作目錄（CWD）**，所以先 `cd` 到你要存放成品的資料夾再執行：

```bash
# 先確認環境（一次就好）
brew install ffmpeg
pip3 install pillow              # 配音用 macOS 內建 say，不用裝

# 在成品資料夾裡執行
cd ~/Desktop/我的短影片
python3 ~/.claude/skills/skill-short-video-pipeline/scripts/make_short.py "AI 如何讓小店營收翻倍"
```

跑完會自動開啟 `./final.mp4`（9:16、約 18 秒、含旁白＋字幕＋Ken Burns）。不給主題就用內建範例主題。

## 客製內容

- **換腳本**：在 CWD 放一個 `scenes.json`，程式會優先讀它。格式：
  ```json
  [
    {"narration": "你的店其實一直在漏錢", "visual": "夜晚的小店外觀"},
    {"narration": "AI 員工幫你 24 小時接單", "visual": "手機聊天介面"}
  ]
  ```
  `narration` 是旁白（拿去配音），`visual` 是畫面描述（拿去生圖）。
- **加背景音樂**：把一首**可商用**音樂放成 `./assets/bgm.mp3`，程式自動以 18% 音量混入。
- **接真 API**：`export OPENAI_API_KEY=...` 開啟 LLM 生腳本；`export ELEVEN_API_KEY=...` 開啟 ElevenLabs 配音；生圖把 `gen_image()` 內的占位邏輯換成你的文生圖 API 呼叫即可。

## 量產與排程（進階）

有了 `make_short()`，量產只是包一層迴圈，再用 macOS `launchd` / `cron` 排程：

```python
from make_short import make_short
for topic in ["主題1", "主題2", "主題3"]:
    make_short(topic)
```

這就是龍蝦學院「每晚自動上片」產線的雛形。

## 必守的硬規則（都已寫進程式碼，改動時別破壞）

這些是踩過雷換來的，是**硬規則**不是建議：

1. **中文字型必須用「繁體字面」** — macOS 的 `Songti.ttc` index 0 是 Songti **SC（簡體）**，會把「龍/蝦/學/數/員/機」等繁體字渲染成空白方塊。程式用 `find_font()` 自動挑 **Heiti TC（STHeiti Medium.ttc index 0）**，並逐字驗證可渲染。新增字型候選一定要帶正確的 ttc `index`。
2. **素材一律 9:16、鎖 1080×1920** — 生圖、合成都鎖死，否則畫面被拉變形。
3. **配樂只用可商用音源**（Musopen / filmmusic.io）— 用有版權的歌會被 YouTube Content ID 判侵權。
4. **concat 拼接必須重編碼** — 直接 stream copy 會讓字幕／時間軸對不上。程式已用 `libx264` 重編碼。
5. **長度抓 30–60 秒、Hook 放前 3 秒** — 腳本結構：Hook（勾住）→ 內容（一個重點）→ CTA（明確動作）。

## 品牌

成品畫面左上角會印「AI數字員工龍蝦學院」浮水印（金色）。後製建議再掛品牌片頭片尾（logo 在 `~/.claude/skills/skill-ai-lobster-brand/logo.png`）。對外發布請遵守品牌守則 skill `skill-ai-lobster-brand`。

## 相關
- 教材投影片：`~/Desktop/第一梯實戰訓練營/第7堂_製作短影片/`
- 數字人路線（露臉版）：skill `skill-jason-digital-human`
- 完整使用說明：見 `reference/README.md`
