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
*.minimax.io
```
（YouTube 走 `*.googleapis.com` / `accounts.google.com`，已在預設白名單）

## 工作流程（SOP）

### 步驟一：準備逐字稿
口語化純文字（同 cat skill 的逐字稿可直接拿來用）。HeyGen 單次約上限 1500 字，過長要分段。

### 步驟二：挑聲音與「誰來講」（第一次設定時）
```bash
python scripts/list_heygen_assets.py        # 列出中文聲音 + 現成主播角色
```
挑一個台灣/中文女聲，設成 `HEYGEN_VOICE_ID`。

**「誰來講」有兩條路：**

| | 現成主播 | **自訂 Photo Avatar** |
|---|---|---|
| 設定 | `HEYGEN_AVATAR_ID` | `HEYGEN_TALKING_PHOTO_ID` |
| 臉 | 跟其他 HeyGen 用戶共用 | 只有你有 |
| 適合 | 純知識口播、不建立人物 IP | **虛擬人物 IP（小魂的角色）** |

兩個都設時，**Photo Avatar 優先**。

**建立自訂 Photo Avatar：**
```bash
python scripts/upload_talking_photo.py 小路_基準臉.png
```
會印出 `talking_photo_id`，設成 `HEYGEN_TALKING_PHOTO_ID` 即可。

> ⚠️ 只能上傳你有權使用的臉：AI 生成的虛擬人物、或你自己。
> 別人的照片、名人、網路抓的圖都不行 —— 違反 HeyGen 條款，也違法。

> **與小魂的接法**：`skill-xiao-hun` 產出角色的 `flux.md`（外觀規格）→ 用 Gemini 之類的工具
> 生出基準臉 → 上傳成 Photo Avatar → 這條產線就有了固定的臉。
> 角色的語氣則由 `voice.md` 決定，寫逐字稿時要照著走。

### 步驟三：生成主播影片

**台灣角色請一律加 `--minimax`：**
```bash
python3 scripts/heygen_generate.py 腳本.txt heygen_video.mp4 --minimax
```

一個指令跑完三件事：Minimax 產台灣腔配音 → 上傳 HeyGen → avatar 對嘴 → 下載 mp4。

> ⚠️ **為什麼不用 HeyGen 內建中文聲音**：它們幾乎都是大陸腔。
> 台灣觀眾對「垃圾（ㄌㄚ ㄐㄧ vs ㄌㄜˋ ㄙㄜˋ）」「和（ㄏㄜˊ vs ㄏㄢˋ）」極度敏感，
> 一秒出戲，比臉不像還傷。配音對了才值得做這條產線。

其他寫法：
```bash
python3 scripts/heygen_generate.py 腳本.txt out.mp4                    # HeyGen 內建聲音
python3 scripts/heygen_generate.py 腳本.txt out.mp4 --audio 我的配音.mp3  # 用現成音檔
python3 scripts/minimax_tts.py 腳本.txt voiceover.mp3                  # 只產配音不產片
```

**Minimax 環境變數**（與 `skill-cat-economics` 共用同一組）：
`MINIMAX_API_KEY`、`MINIMAX_VOICE_ID`（預設 `female-shaonv` 台灣女聲）、
`MINIMAX_SPEED`（短影音可調 1.05~1.15）。

### 步驟四：自動上傳 YouTube
```bash
python scripts/youtube_upload.py heygen_video.mp4 \
  --title "標題" --description-file 簡介.txt \
  --tags "經濟學,科普" --privacy private
```
（OAuth 設定見 SETUP.md；未審核 app 上傳預設為私人，需手動改公開）

## 影片規格
- 直式 9:16 預設 720x1280（可用 `HEYGEN_WIDTH/HEIGHT` 改；橫式設 1280x720）
