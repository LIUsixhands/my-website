# flux.md — 外觀與影像規格（小路 · Midjourney）

> 檔名沿用 `flux.md`（系統固定的欄位名），但本角色用 **Midjourney** 生圖，參數已全部改成 MJ 語法。

---

## ⚠️ 先做這件事：建立角色參考圖（--cref）

Midjourney 鎖臉靠 `--cref`。你**現在還沒有參考圖**，所以流程分兩階段：

**階段一（只做一次）**
1. 用下面 §1 的 Identity Lock ＋ `--ar 9:16 --style raw` 跑 4 次，共 16 張
2. 從裡面挑**一張正面、光線平、表情自然**的當「基準臉」
3. 把那張圖上傳（IG 私帳、Imgur、Google Drive 公開連結都行），複製圖片網址
4. 把網址填到下面的「基準圖 URL」欄

**階段二（之後每一張圖）**
在 prompt 最後加上：`--cref <基準圖網址> --cw <數值>`

| 情境 | --cw 數值 | 原因 |
|------|----------|------|
| 同一套衣服、換場景 | `--cw 100` | 臉＋髮型＋衣服全鎖 |
| 換衣服、只要臉一樣 | `--cw 0` ～ `--cw 30` | 只鎖臉，衣服才換得掉 |

**基準圖 URL**：`（階段一做完後填這裡）`

---

## 1. Identity Lock

<!-- BLOCK:LOCK -->
24-year-old Taiwanese woman, round face with soft cheeks, slightly downturned monolid eyes with dark brown irises, small rounded nose, thin upper lip with defined cupid's bow, straight low-set eyebrows, black shoulder-blade-length hair usually in a low messy ponytail with loose strands at temples, warm light skin with faint acne marks on left cheek, small mole on right side of chin, thin build 160cm, no makeup or minimal makeup
<!-- /BLOCK:LOCK -->

**識別特徵**
- 右下巴一顆小痣
- 左臉頰淡淡的痘疤（**不要修掉**，這是真實感來源）
- 低馬尾，鬢角有幾根散落的頭髮

> **為什麼要留痘疤**：TikTok 受眾對「完美臉」極度敏感，一眼認出是 AI。瑕疵是這個角色最重要的資產。

---

## 2. 影像風格

<!-- BLOCK:STYLE -->
| 項目 | 設定 |
|------|------|
| 影像類型 | candid iPhone photo, slightly imperfect framing |
| 光線 | available light only, no flash, sometimes slightly underexposed |
| 色調 | neutral to slightly cool, low saturation |
| 質地 | visible skin texture, mild digital noise |
| 景深 | mostly deep focus like a phone camera |
| 構圖 | handheld, slight tilt, subject not perfectly centered |
| Midjourney 參數 | --ar 9:16 --style raw --v 7 |
<!-- /BLOCK:STYLE -->

> 若你的帳號還在 v6.1，把 `--v 7` 改成 `--v 6.1`。

---

## 3. 衣櫃

> 只有 5 套，而且要**重複穿**。真人不會每支影片換新衣服。

<!-- BLOCK:WARDROBE -->
| ID | 名稱 | prompt 片段 |
|----|------|------------|
| W01 | 上班（最常出現） | plain white short-sleeve shirt, black wide-leg trousers, small crossbody bag |
| W02 | 下班拍片 | oversized grey hoodie, black jeans, white sneakers |
| W03 | 週末看屋 | beige linen shirt over white tee, straight jeans, canvas tote |
| W04 | 居家記帳 | faded pink cotton tee, grey shorts, hair in low bun |
| W05 | 騎車 | dark green windbreaker, black jeans, helmet in hand |
<!-- /BLOCK:WARDROBE -->

---

## 4. 場景庫

<!-- BLOCK:SCENES -->
| ID | 名稱 | prompt 片段 |
|----|------|------------|
| S01 | 租的套房 | small 5-ping studio apartment, single window, IKEA folding table, clothes rack, air conditioner unit |
| S02 | 一中商圈街上 | busy Taiwanese night market street, food stalls, scooters, neon signage |
| S03 | 老公寓樓梯間 | narrow tiled apartment stairwell, mailboxes, fluorescent tube light |
| S04 | 空屋看屋現場 | empty unfurnished apartment, bare walls, afternoon light through balcony door |
| S05 | 便利商店 | Taiwanese convenience store interior at night, fluorescent lighting, drink fridge |
| S06 | 機車上／路邊 | roadside in Taichung, parked scooter, low-rise buildings, overcast sky |
<!-- /BLOCK:SCENES -->

---

## 5. Negative（Midjourney 寫成 `--no`）

<!-- BLOCK:NEGATIVE -->
plastic skin, airbrushed, flawless complexion, heavy makeup, beauty filter, doll-like, glamour lighting, studio backdrop, deformed hands, extra fingers, watermark, text, logo, oversaturated, model pose
<!-- /BLOCK:NEGATIVE -->

用法：把上面整串接在 prompt 最後，寫成 `--no plastic skin, airbrushed, ...`

---

## 6. 技術參數紀錄

| 項目 | 值 |
|------|-----|
| 工具 | Midjourney |
| 版本 | v7（帳號若為 v6.1 則用 v6.1） |
| 一致性機制 | `--cref` 角色參考圖 ＋ Identity Lock 文字 |
| 基準圖 URL | （待填） |
| 風格參考 | `--sref`（可選，選定後填這裡固定住整體調性） |
| 比例 | `--ar 9:16`（TikTok 全螢幕） |
| 風格化 | `--style raw`（越低越像真實照片） |

> **鐵則**：基準圖一旦選定就不能換。換基準圖 = 換臉，老觀眾會發現。

---

## 7. 一致性檢查表（每批抽 3 張比對基準圖）

- [ ] 臉型圓度
- [ ] 眼型（單眼皮、微下垂）
- [ ] 鼻子大小
- [ ] 嘴唇厚度
- [ ] 髮型（低馬尾＋鬢角散髮）
- [ ] 右下巴痣位置
- [ ] 左臉痘疤還在（沒被修掉）
- [ ] 皮膚有質感（不是塑膠臉）
- [ ] 手部沒崩
- [ ] 沒有真實品牌 logo、沒有可辨識的真人

**任一項不過 → 整批重生，不要挑圖。**

---

## 8. 影像倫理紅線

- 不使用任何真實人物的臉作為參考來源（`--cref` 只能餵自己生成的圖）
- 不生成未成年外觀
- 不生成性暗示 / 裸露內容
- 不偽造真實在場證明（例：假造在某建案現場的合照）
- 不拍到可辨識的真實門牌、車牌、住戶

---

## 9. 版本紀錄

| 版本 | 日期 | 工具 | 改了什麼 | 一致性檢查 |
|------|------|------|---------|-----------|
| v1.0 | 2026-09-06 | Midjourney v7 | 初版，基準圖待建立 | 待做 |
