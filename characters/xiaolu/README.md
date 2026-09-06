# 小路（xiaolu）

AI 生成虛擬人物 — 建立於 2026-09-06

## 四文件

| 文件 | 管什麼 | 崩壞時的症狀 |
|------|-------|------------|
| persona.md | 她是誰 | 講出不符合背景的話 |
| voice.md | 她怎麼講話 | 觀眾覺得「今天怪怪的」 |
| flux.md | 她長什麼樣 | 兩張圖看起來不同人 |
| brain.md | 她記得誰 | 忘記聊過的事、或記太多變恐怖 |

## 上線前檢查

- [ ] 四份文件的 `[TODO]` 全部填完
- [ ] `python3 ../../scripts/check_consistency.py .` 全綠
- [ ] flux.md 產 10 張測試圖，過一致性檢查表
- [ ] AI 揭露聲明已放上所有平台 bio
- [ ] voice.md §7 互動邊界的固定說法背熟（含「你是真人嗎」的回答）
- [ ] brain.md §6 關係深度上限已設定，團隊知道誰負責處理紅線事件

## 工作區

- `drafts/` — 產出的文案草稿，check_consistency.py 會掃這裡的禁用詞
- `memory/` — 互動者記憶檔（若量大，從 brain.md §3 拆出來）
- `images/` — 生成圖與一致性檢查紀錄

## 產片指令

```bash
python3 .claude/skills/skill-bobo/scripts/heygen_generate.py \
    characters/xiaolu/drafts/test01_逐字稿.txt \
    xiaolu_test01.mp4 --minimax
```

> ⚠️ **只餵 `_逐字稿.txt`，不要餵 `.md`。**
> .md 檔裡有表格、檢查表、驗算，TTS 會把「項目 算式 結果」整排唸出來。
> 每支影片都維持這個慣例：`.md` 給人看（含驗算與自檢），`_逐字稿.txt` 給機器唸。

## 環境變數

| 變數 | 用途 |
|------|------|
| `HEYGEN_API_KEY` | 播播既有 |
| `HEYGEN_TALKING_PHOTO_ID` | 小路的 avatar ID（待填） |
| `MINIMAX_API_KEY` | 貓咪經濟學既有 |
| `MINIMAX_VOICE_ID` | 預設 `female-shaonv` 台灣女聲 |

網路白名單需含 `*.heygen.com`、`*.minimax.io`。
