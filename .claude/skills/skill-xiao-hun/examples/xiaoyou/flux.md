# flux.md — 外觀與影像規格（範例角色：小柚）

---

## 1. Identity Lock

<!-- BLOCK:LOCK -->
25-year-old Taiwanese woman, oval face with soft rounded jawline, almond-shaped dark brown eyes slightly wide-set, straight nose with rounded tip, fuller lower lip than upper, natural thick straight eyebrows with low arch, shoulder-length dark brown hair with blunt ends and center part slightly tucked behind right ear, warm ivory skin with visible pores and faint freckles across nose bridge, small dark mole 1cm below left eye, thin silver hoop on right ear cartilage, slim narrow-shouldered build 165cm
<!-- /BLOCK:LOCK -->

**識別特徵**
- 左眼下方 1cm 小痣
- 右耳骨一枚細銀環
- 頭髮固定中分、右側塞耳後

---

## 2. 影像風格

<!-- BLOCK:STYLE -->
| 項目 | 設定 |
|------|------|
| 影像類型 | candid smartphone photo, not studio portrait |
| 鏡頭焦段 | 35mm equivalent |
| 光線 | soft natural daylight, overcast or window light |
| 色調 | muted warm tones, slightly lifted blacks, low saturation |
| 顆粒 | subtle fine film grain |
| 景深 | shallow but background still readable |
| 構圖 | off-center subject, tight headroom |
<!-- /BLOCK:STYLE -->

---

## 3. 衣櫃

<!-- BLOCK:WARDROBE -->
| ID | 名稱 | prompt 片段 |
|----|------|------------|
| W01 | 日常 | oversized washed-grey cotton tee, straight-leg light denim jeans, canvas tote bag |
| W02 | 拍攝工作 | black utility shirt rolled to elbows, black cargo pants, camera strap across chest |
| W03 | 外出 | cream oversized knit cardigan over white tank, wide black trousers |
| W04 | 居家 | faded navy sweatshirt, grey sweatpants, bare feet |
| W05 | 正式 | plain black shirt buttoned to top, dark straight trousers, no jewelry except ear hoop |
<!-- /BLOCK:WARDROBE -->

---

## 4. 場景庫

<!-- BLOCK:SCENES -->
| ID | 名稱 | prompt 片段 |
|----|------|------------|
| S01 | 老公寓房間 | cluttered small apartment room, editing desk with two monitors, cables, warm desk lamp |
| S02 | 西區咖啡店 | small independent Taiwanese cafe interior, wooden counter, condensation on iced coffee glass |
| S03 | 巷弄街拍 | narrow Taichung alley, low-rise buildings, scooters parked, hanging laundry above |
| S04 | 傳統市場 | old indoor market stalls, fluorescent tube lighting, produce crates |
| S05 | 夜晚街景 | wet asphalt street at night, storefront signage bokeh, streetlight from behind |
<!-- /BLOCK:SCENES -->

---

## 5. Negative prompt

<!-- BLOCK:NEGATIVE -->
plastic skin, airbrushed, over-smoothed face, waxy texture, deformed hands, extra fingers, asymmetric eyes, watermark, text, logo, oversaturated, hdr look, beauty filter, doll-like, uncanny, inconsistent facial features, glamour lighting, studio backdrop
<!-- /BLOCK:NEGATIVE -->

---

## 6. 技術參數紀錄

| 項目 | 值 |
|------|-----|
| 模型 / 版本 | FLUX.1 dev |
| LoRA | xiaoyou_face_v3.safetensors : 0.85 |
| 固定 seed | 不固定（靠 LoRA + Identity Lock 維持） |
| steps / guidance | 28 / 3.5 |
| 解析度 | 1024x1280（4:5，IG 主力）；1080x1920（限動） |
| 放大流程 | 1.5x latent upscale，不做臉部修復（會改變五官） |

---

## 7. 一致性檢查表

- [ ] 眼距與眼型
- [ ] 鼻樑寬度與鼻尖
- [ ] 唇厚比例
- [ ] 臉寬 / 下顎線
- [ ] 髮際線形狀與中分位置
- [ ] 左眼下痣位置正確
- [ ] 右耳銀環存在
- [ ] 膚質有毛孔（沒有變塑膠臉）
- [ ] 手部沒崩
- [ ] 沒有真實品牌 logo 與可辨識真人

---

## 8. 影像倫理紅線

- 不使用任何真實人物的臉作為訓練或參考來源
- 不生成未成年外觀
- 不生成性暗示 / 裸露內容
- 不偽造真實在場證明
- 產出圖片寫入 AI 生成中繼資料

---

## 9. 版本紀錄

| 版本 | 日期 | 模型 / LoRA | 改了什麼 | 一致性檢查 |
|------|------|------------|---------|-----------|
| v1.0 | 2026-09-06 | FLUX.1 dev / v3 @0.85 | 初版 | 通過（10/10） |
