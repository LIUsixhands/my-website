# 播播 skill 設定教學（HeyGen → YouTube）

## 1. HeyGen API 金鑰
1. 登入 HeyGen → 右上角 Settings（設定）→ 找 **API** 或 **Subscriptions → API Token**
2. 複製 API Key
3. 到 claude.ai/code 環境設定 → Environment variables 加：
   ```
   HEYGEN_API_KEY=（你的 HeyGen API Key）
   ```

## 2. 網路白名單
環境設定 → Network access → Custom → Allowed domains 加上：
```
*.heygen.com
*.heygen.ai
```
（保留「Also include default list of common package managers」勾選）

## 3. 挑主播與聲音
開新 session 執行：
```bash
python .claude/skills/skill-bobo/scripts/list_heygen_assets.py
```
從清單挑一個台灣/中文女聲與主播角色，把 ID 加進環境變數：
```
HEYGEN_VOICE_ID=（挑到的 voice_id）
HEYGEN_AVATAR_ID=（挑到的 avatar_id）
```

## 4. YouTube 自動上傳
與貓咪經濟學 skill 共用同一套 YouTube 設定，照
`.claude/skills/skill-cat-economics/YOUTUBE_SETUP.md` 設定這三個：
```
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REFRESH_TOKEN=
```

## 5. 跑整條流程
```bash
# 生成主播影片
python .claude/skills/skill-bobo/scripts/heygen_generate.py \
  .claude/skills/skill-cat-economics/貓咪經濟學腳本.txt heygen_video.mp4

# 自動上傳（預設私人，確認後手動公開）
python .claude/skills/skill-bobo/scripts/youtube_upload.py heygen_video.mp4 \
  --title "為什麼罐頭越來越貴?爪爪稅大戰" --privacy private
```

## 驗證
```bash
python3 -c "import requests, googleapiclient; print('deps ok')"
echo "$HEYGEN_API_KEY" | sed 's/./*/g'   # 確認有值（遮罩）
```
