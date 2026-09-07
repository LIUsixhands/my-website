# flux.md — 外觀與影像規格

> 目標只有一個：**任何人把她的第 1 張圖和第 500 張圖並排，會說「這是同一個人」**。
> 做法是把「不可變特徵」抽成 Identity Lock，每張圖的 prompt 都必須原封不動帶上。

---

## 1. Identity Lock（不可變，每次生成必帶）

> 規則：這段文字**一個字都不能改**。要改造型改 §3 的衣櫃，不要動這裡。
> 越具體越鎖得住。「漂亮女生」鎖不住，「左眼下方 1cm 一顆小痣」鎖得住。

<!-- BLOCK:LOCK -->
[TODO 用英文寫，8–12 個特徵，依序涵蓋：
族裔與年齡 / 臉型 / 眼睛（形狀＋顏色＋眼距） / 鼻型 / 唇形 / 眉形 / 髮色髮質髮長 / 膚色與質地 / 一個獨特識別特徵（痣、疤、虎牙、耳骨釘） / 體型與身高感]

範例格式（請整段替換）：
25-year-old Taiwanese woman, oval face with soft jawline, almond-shaped dark brown eyes with slightly wide-set spacing, straight nose with rounded tip, full lower lip, natural thick straight eyebrows, shoulder-length dark brown hair with blunt ends and center part, warm ivory skin with visible fine texture and light freckles across nose bridge, small mole 1cm below left eye, slim build 165cm
<!-- /BLOCK:LOCK -->

**識別特徵（人眼一致性判斷靠這個，務必獨特且固定）**
- [TODO 例：左眼下方小痣]
- [TODO 例：右耳骨一枚細銀環]
- [TODO 例：笑起來左邊有單邊酒窩]

---

## 2. 影像風格（決定「一看就是她的照片」）

<!-- BLOCK:STYLE -->
| 項目 | 設定 |
|------|------|
| 影像類型 | [TODO 例：candid smartphone photo，不要 studio portrait] |
| 鏡頭焦段 | [TODO 例：35mm] |
| 光線 | [TODO 例：soft natural window light, overcast] |
| 色調 | [TODO 例：muted warm tones, slightly lifted blacks] |
| 顆粒 / 質地 | [TODO 例：subtle film grain] |
| 景深 | [TODO 例：shallow but not blurred out] |
| 構圖習慣 | [TODO 例：off-center, headroom tight] |
<!-- /BLOCK:STYLE -->

---

## 3. 衣櫃（Wardrobe，每套給編號，重複穿才像真人）

> 真人不會每張照片都換新衣服。同一套衣服在不同場景出現，是**最便宜的真實感**。

<!-- BLOCK:WARDROBE -->
| ID | 名稱 | prompt 片段 |
|----|------|------------|
| W01 | [TODO 日常] | [TODO 例：oversized cream knit sweater, straight-leg jeans] |
| W02 | [TODO 工作] | [TODO] |
| W03 | [TODO 外出] | [TODO] |
| W04 | [TODO 居家] | [TODO] |
| W05 | [TODO 正式] | [TODO] |
<!-- /BLOCK:WARDROBE -->

---

## 4. 場景庫（Scenes）

<!-- BLOCK:SCENES -->
| ID | 名稱 | prompt 片段 |
|----|------|------------|
| S01 | [TODO 家中] | [TODO] |
| S02 | [TODO 咖啡店] | [TODO] |
| S03 | [TODO 街上] | [TODO] |
| S04 | [TODO 工作場所] | [TODO] |
| S05 | [TODO 夜晚] | [TODO] |
<!-- /BLOCK:SCENES -->

---

## 5. Negative prompt（固定不變）

<!-- BLOCK:NEGATIVE -->
plastic skin, airbrushed, over-smoothed face, waxy texture, deformed hands, extra fingers, asymmetric eyes, watermark, text, logo, oversaturated, hdr look, beauty filter, doll-like, uncanny, inconsistent facial features
<!-- /BLOCK:NEGATIVE -->

---

## 6. 技術參數紀錄（換模型＝換臉，務必記錄）

| 項目 | 值 |
|------|-----|
| 模型 / 版本 | [TODO 例：FLUX.1 dev] |
| LoRA / 角色訓練檔 | [TODO 檔名＋權重，例：char_v3.safetensors : 0.85] |
| 固定 seed | [TODO 或註明「不固定，靠 LoRA + Lock 維持」] |
| steps / guidance | [TODO] |
| 解析度 | [TODO 例：1024x1280（4:5，IG 主力）] |
| 放大流程 | [TODO] |

> **鐵則**：模型版本或 LoRA 權重一改，等於整容。改動前先產 10 張測試圖過 §7 檢查表。

---

## 7. 一致性檢查表（每批圖抽 3 張逐項比對）

- [ ] 眼距與眼型
- [ ] 鼻樑寬度與鼻尖
- [ ] 唇厚比例（上唇 : 下唇）
- [ ] 臉寬 / 下顎線
- [ ] 髮際線形狀
- [ ] 識別特徵（痣／耳環／酒窩）位置正確
- [ ] 膚質質感一致（沒有突然變成塑膠臉）
- [ ] 身形比例一致
- [ ] 手部沒有崩壞
- [ ] 沒有出現真實品牌 logo 與可辨識真人

**任一項不過 → 整批重生，不要只挑好的用。** 混用不一致的圖是人設崩壞最快的路徑。

---

## 8. 影像倫理紅線（不可協商）

- 不使用任何真實人物的臉作為訓練或參考來源（不做 deepfake、不換臉）
- 不生成未成年外觀
- 不生成性暗示 / 裸露內容
- 不偽造「與真實地點的真實在場證明」（如假造某活動現場合照）
- 產出圖片建議寫入 C2PA / 標註 AI 生成中繼資料

---

## 9. 版本紀錄

| 版本 | 日期 | 模型 / LoRA | 改了什麼 | 一致性檢查 |
|------|------|------------|---------|-----------|
| v1.0 | [TODO] | [TODO] | 初版 | 通過 / 未過 |
