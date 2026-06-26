# 雲端環境設定（讓步驟三~六可自動執行）

步驟三~六（配音 / 字幕 / 畫面 / 合成）需要 API 金鑰、套件與網路白名單。
在 claude.ai/code 的「環境設定」對話框完成以下三項，之後每個雲端 session 啟動就會自動就緒。

## 1. 環境變數（Environment variables）
| 變數 | 來源 |
| --- | --- |
| `GOOGLE_API_KEY` | Google AI Studio（aistudio.google.com）→ Get API key |
| `MINIMAX_API_KEY` | Minimax 平台 → API 金鑰 |
| `MINIMAX_GROUP_ID` | Minimax 平台 → 帳戶 GroupID |

注意：目前無專用密鑰庫，環境變數對可編輯該環境者皆可見，請使用個人金鑰。

## 2. 網路存取（Network access）
- Google Gemini：預設 Trusted 白名單已含 `*.googleapis.com`，無需額外設定。
- Minimax：`api.minimax.chat` 不在預設白名單，會被擋。
  - 選 **Custom**，勾「Also include default list of common package managers」。
  - Allowed domains 加入：
    ```
    api.minimax.chat
    api.minimaxi.com
    ```

## 3. Setup script（自動裝套件）
貼入環境設定的 Setup script 欄位：
```bash
#!/bin/bash
pip install -r .claude/skills/skill-cat-economics/requirements.txt || true
apt-get update && apt-get install -y ffmpeg || true
```
ffmpeg 為 moviepy 合成影片所需；PyPI 與 Ubuntu apt 皆在預設白名單內。

## 驗證
設定完成後在新 session 執行：
```bash
python3 -c "import requests, google.genai, moviepy; print('deps ok')"
ffmpeg -version | head -1
echo "$GOOGLE_API_KEY" | sed 's/./*/g'   # 確認有值（遮罩顯示）
```

## 出片流程（依序執行）
1. `python scripts/gen_taiwan_speech.py`  # 先出 10-20 秒試聽，確認音色
2. `python scripts/generate_srt.py`        # 依真實音檔產時間戳 SRT
3. `python scripts/parse_and_generate_all.py`  # 批量畫面（前30秒/每50張會暫停驗收）
4. `python scripts/assemble_video.py`      # 合成最終 MP4
