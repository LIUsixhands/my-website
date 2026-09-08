# 測試片 01｜存款進度（主線第一支）

用途：驗證 Minimax 台灣腔 → HeyGen 小路對嘴 → 出片，整條產線通不通。
長度：約 33 秒（150 字，符合 voice.md 的 25–45 秒規格）

---

## 逐字稿（給 --minimax 吃的就是這段）

我月薪三萬六，存了十七個月。
先講結論：二十萬四。

我算給你看。
每個月固定存一萬二。
房租八千五，吃飯抓六千。
剩下的才是我的。

我想買的那種，大概八百萬。
自備款我抓兩成，一百六十萬。
所以我還差一百三十九萬六。

照這個速度，一百一十六個月。
將近十年。

所以我沒買。
但我每個月都會回來報一次數字。

---

## 數字驗算（小路的信用全靠這個，不能錯）

| 項目 | 算式 | 結果 |
|------|------|------|
| 已存 | 12,000 × 17 個月 | 204,000 ✅ |
| 目標自備款 | 8,000,000 × 20% | 1,600,000 ✅ |
| 還差 | 1,600,000 − 204,000 | 1,396,000 ✅ |
| 還要幾個月 | 1,396,000 ÷ 12,000 | 116.3 → 116 ✅ |
| 換算年數 | 116 ÷ 12 | 9.67 年 → 「將近十年」 ✅ |

## voice.md 自檢

- [x] 前 3 秒是完整鉤子（「我月薪三萬六，存了十七個月」）
- [x] 沒有「嗨大家好」
- [x] 平均句長 11 字
- [x] 用了口頭禪「先講結論」「我算給你看」，各 1 次（未超上限）
- [x] 數字全部講到個位數
- [x] 沒有禁用詞
- [x] 結尾用「所以我沒買」自嘲收
- [x] **沒有下任何房產專業判斷** —— 八百萬是「我想買的那種」，兩成是「我抓」，
      都是她個人的假設，不是市場宣稱。這條是合規紅線。

## 發佈時要附的揭露（說明欄第一段）

🤖 小路是 AI 生成的虛擬人物，不是真人。影像與文字由 AI 產生，
內容由 Sixhands Studio 企劃營運，房產專業內容由合作的執業房仲提供。

---

## 產片紀錄

| 日期 | 結果 |
|------|------|
| 2026-09-08 | ❌ 沒出片 —— HeyGen 與 Minimax 兩邊額度都是 0 |

當天查到的事實（充值後直接照這個跑，不用重查）：

- 小路的 Photo Avatar 存在，`talking_photo_id = 23942339949b4cba85c0f8d342392105`
- `HEYGEN_API_KEY` 有效；`/v2/user/remaining_quota` → `remaining_quota: 0`，
  送生成回 `HTTP 402 insufficient_credit`
- `MINIMAX_API_KEY` 有效且屬國際版（`api.minimax.io`），但餘額 0（`1008 insufficient balance`）；
  `api.minimaxi.com` / `api.minimax.chat` 回 `2049 invalid api key`，確定不是打錯區域
- 環境變數 `MINIMAX_GROUP_ID` 與這把金鑰不相符（`1004 token not match group`），應該移除

充值後的指令：

```bash
python3 .claude/skills/skill-bobo/scripts/heygen_generate.py \
    characters/xiaolu/drafts/test01_逐字稿.txt \
    xiaolu_test01.mp4 --minimax
```

Minimax 若還是沒額度，用 HeyGen 的 zh-TW 備援聲音先驗證對嘴（見 skill-bobo SKILL.md）：

```bash
HEYGEN_VOICE_ID=4158cf2ef85d4ccc856aacb1c47dbb0c \
  python3 .claude/skills/skill-bobo/scripts/heygen_generate.py \
    characters/xiaolu/drafts/test01_逐字稿.txt xiaolu_test01.mp4
```
