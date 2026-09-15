# 雲端環境設定（讓步驟三~六可自動執行）

步驟三~六（配音 / 字幕 / 畫面 / 合成）需要 API 金鑰、套件與網路白名單。
在 claude.ai/code 的「環境設定」對話框完成以下三項，之後每個雲端 session 啟動就會自動就緒。

> 環境變數改了要**開新 session** 才吃得到 —— 變數是容器啟動時載入的。

## 1. 環境變數（Environment variables）

**必要，一把就夠：**

| 變數 | 來源 | 用途 |
| --- | --- | --- |
| `GOOGLE_API_KEY` | Google AI Studio（aistudio.google.com）→ API keys | 配音（步驟三）＋ 畫面生成（步驟五） |

**選用 —— 只有在你有 Minimax 帳號時才需要：**

| 變數 | 來源 |
| --- | --- |
| `MINIMAX_API_KEY` | Minimax 國際站 → API 金鑰 |
| `MINIMAX_GROUP_ID` | Minimax 國際站 → 帳戶 GroupID |

> Minimax 開發者平台會依地區把台灣使用者導向中國站（需中國手機號或微信），
> 台灣帳號通常註冊不了，所以配音預設走 Gemini TTS。
> `scripts/gen_taiwan_speech.py` 仍保留，有帳號的人可直接用。

注意：目前無專用密鑰庫，環境變數對可編輯該環境者皆可見，請使用個人金鑰。

## 2. 網路存取（Network access）
- **Google Gemini**：預設 Trusted 白名單已含 `*.googleapis.com`，**無需額外設定**。
  配音與生圖都走 `generativelanguage.googleapis.com`，所以預設環境就能出片。
- **Minimax（僅在你要用它時）**：選 **Custom**，勾「Also include default list of
  common package managers」，Allowed domains 加入 `gen_taiwan_speech.py` 實際打的網域：
    ```
    api.minimax.io
    api-uw.minimax.io
    ```

## 3. Setup script（自動裝套件）
貼入環境設定的 Setup script 欄位：
```bash
#!/bin/bash
pip install -r .claude/skills/skill-cat-economics/requirements.txt || true
apt-get update && apt-get install -y ffmpeg || true
```
ffmpeg 用於合成影片。若 apt 裝不起來，`requirements.txt` 裡的 `imageio-ffmpeg`
會提供備援二進位，`smoke_test.py` 與 `gen_voice_gemini.py` 都會自動退回用它。

## 驗證
設定完成後在新 session 執行：
```bash
echo "$GOOGLE_API_KEY" | sed 's/./*/g'   # 確認有值（遮罩顯示）
cd .claude/skills/skill-cat-economics
python3 scripts/smoke_test.py --seconds 6   # 不打 API，確認合成鏈路沒斷
```

## 出片流程（依序執行）

先跑一次不花錢的煙霧測試，綠了再燒 API：
```bash
python scripts/smoke_test.py               # 小路測試：SRT→時間軸→合成，無聲佔位片
```

正式出片：
1. `python scripts/gen_voice_gemini.py --demo`  # 先出試聽，**確認音色後才繼續**
2. `python scripts/gen_voice_gemini.py`         # 全長配音 → voiceover.mp3
3. `python scripts/generate_srt.py`             # 依真實音檔產時間戳 SRT
4. `python scripts/parse_and_generate_all.py`   # 批量畫面（前30秒/每50張會暫停驗收）
5. `python scripts/assemble_video.py`           # 合成最終 MP4

想在真畫面出來前先聽聽聲音配上節奏對不對：
```bash
python scripts/smoke_test.py --audio voiceover.mp3   # 佔位圖 + 真配音
```
