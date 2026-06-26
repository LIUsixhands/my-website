---
name: skill-bobo
description: 播播 — HeyGen AI 主播影片製作 + 自動上架 YouTube。當使用者輸入「播播」、「叫播播」、「找播播」、「heygen」、「主播上片」、「主播影片」時，必須使用此 skill。把逐字稿交給 HeyGen 虛擬主播口播生成影片，再自動上傳到 YouTube。與「貓咪經濟學/cat」skill（火柴人手繪動畫風格）分屬不同產線，請依觸發詞分流：講「貓咪經濟學」走火柴人動畫；講「播播 / heygen」走主播影片。
---

# 播播 — HeyGen 主播影片 → YouTube 自動上片

## 簡介
此 skill 用 **HeyGen** 把逐字稿變成「AI 虛擬主播口播」影片，再用 YouTube API 自動上傳。
適合快速、量產的口播型科普/教學影片。

> 與 `skill-cat-economics`（火柴人貓咪動畫 + 旁白）是兩條不同產線：
> - 講「**貓咪經濟學 / cat**」→ 火柴人動畫
> - 講「**播播 / heygen**」→ 本 skill（主播影片）
> 逐字稿兩邊通用。

## 需要的環境變數
- `HEYGEN_API_KEY`：HeyGen 後台 Settings → API（付費方案才有）
- `HEYGEN_AVATAR_ID`、`HEYGEN_VOICE_ID`：用 `list_heygen_assets.py` 查後挑選
- YouTube 上傳：`YOUTUBE_CLIENT_ID`、`YOUTUBE_CLIENT_SECRET`、`YOUTUBE_REFRESH_TOKEN`（見 SETUP.md）

## 網路白名單（環境設定 → Custom）
需加入：
```
*.heygen.com
*.heygen.ai
```
（YouTube 走 `*.googleapis.com` / `accounts.google.com`，已在預設白名單）

## 工作流程（SOP）

### 步驟一：準備逐字稿
口語化純文字（同 cat skill 的逐字稿可直接拿來用）。HeyGen 單次約上限 1500 字，過長要分段。

### 步驟二：挑主播與聲音（第一次設定時）
```bash
python scripts/list_heygen_assets.py        # 列出中文聲音 + 主播角色
```
挑一個台灣/中文女聲與一個主播角色，把 ID 設成 `HEYGEN_VOICE_ID` / `HEYGEN_AVATAR_ID`。

### 步驟三：生成主播影片
```bash
python scripts/heygen_generate.py 腳本.txt heygen_video.mp4
```
會送出生成、輪詢狀態、完成後下載 mp4。

### 步驟四：自動上傳 YouTube
```bash
python scripts/youtube_upload.py heygen_video.mp4 \
  --title "標題" --description-file 簡介.txt \
  --tags "經濟學,科普" --privacy private
```
（OAuth 設定見 SETUP.md；未審核 app 上傳預設為私人，需手動改公開）

## 影片規格
- 直式 9:16 預設 720x1280（可用 `HEYGEN_WIDTH/HEIGHT` 改；橫式設 1280x720）
