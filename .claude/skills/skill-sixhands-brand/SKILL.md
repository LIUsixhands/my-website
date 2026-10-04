---
name: skill-sixhands-brand
description: Sixhands Studio 品牌識別模組 — 對外交付物掛品牌與 logo 的唯一規範來源。當任何員工 skill 寫「觸發 `skill-sixhands-brand`」、或使用者要求「加品牌」「加 logo」「掛品牌」「品牌色」「品牌規範」「CI」「浮水印」「片尾 logo」「頁尾聯絡資訊」「Sixhands 品牌」時，必須使用此 skill。提供：品牌名稱統一寫法、色票、字體、logo 檔（方形徽章／白色標誌／橫式全標）、影片角標與片尾規格、網頁頁尾與聯絡管道、AI 生成標示、以及「客戶自用交付物不掛 Sixhands 品牌」的判斷規則。
---

# Sixhands Studio 品牌識別（skill-sixhands-brand）

所有員工對外交付物（影片、海報、簡報、網頁、報告、月報）要掛品牌時，一律照這份做。員工 skill 裡寫「觸發 `skill-sixhands-brand`」就是指這裡。

## 1. 名稱統一寫法

| 場合 | 寫法 |
|---|---|
| 品牌主名 | **Sixhands Studio**（S 大寫、中間不加空格以外的符號） |
| 團隊全名 | **Sixhands Studio AI 數字員工** |
| 老闆稱呼 | **助哥**（CEO） |
| IP 定位語 | **不賣房子，賣判斷** |
| 本業 | 台中七期房地產仲介（住宅＋土地＋廠房） |

⚠️ 全網只用上面這幾種寫法，不要出現「六手工作室」「SixHands」「Six Hands」等變體 — 名稱一致，Google 與 AI 搜尋才認得是同一個品牌（見小搜 GEO 規則）。

## 2. 色票（與官網一致）

| Token | HEX | 用途 |
|---|---|---|
| forest | `#1F3A2E` | 主色：深森林綠，底色、標誌 |
| cream | `#F3EEE2` | 淺底、深底上的文字 |
| brass | `#B08D3F` | 強調色：黃銅金，標題、分隔線 |
| brass-lite | `#D8BC7E` | 深底上的強調文字 |
| ink | `#22271F` | 淺底上的內文 |
| muted | `#565C50` | 次要文字 |

影片／簡報若沿用舊模組的黑底金字（`INK #121216`、`GOLD #E8B74A`）可以，但新作品優先用上表。

## 3. 字體

- 中文標題：**Noto Serif TC**（700–900）
- 中文內文：**Noto Sans TC**（400–700）
- 英文品牌字：襯線粗體（網頁用 Noto Serif TC 的拉丁字；圖檔用 Liberation Serif Bold / Times 系列）
- 本機沒有 Noto 時（PIL 出圖）：中文用 `WenQuanYi Zen Hei` 或 `Microsoft JhengHei`

## 4. Logo 檔（本資料夾內）

| 檔案 | 內容 | 用在 |
|---|---|---|
| `logo.png` | 512×512 方形徽章（森林綠底＋米白六線標誌＋SIXHANDS） | 報告封面、社群頭像、各員工 `assets/logo.png` |
| `logo_white.png` | 透明底、米白標誌（無字） | 影片角標、深色背景浮水印 |
| `logo_full_white.png` | 透明底、米白全標（標誌＋Sixhands Studio＋副標） | 影片片尾、深色簡報封面 |
| `logo_full.png` | 透明底、森林綠全標 | 淺色背景：報告、海報、網頁頁首 |
| `logo_mark.svg` | 向量標誌（六條直線＋底線） | 網頁 favicon、可無限放大的場合 |

程式裡引用路徑一律用 `~/.claude/skills/skill-sixhands-brand/<檔名>`（Python 記得 `os.path.expanduser`）。

## 5. 各媒材規格

**影片（9:16 / 16:9）**
- 角標：`logo_white.png` 寬 120px（1080 寬基準），右上角，邊距 40px，不透明度 85%
- 片尾：`logo_full_white.png` 置中，停留 1.5–2 秒，森林綠或黑底
- AI 生成內容：畫面角落**一定要**加「AI 生成」標示（平台規範＋誠實揭露）

**海報／圖卡**
- 淺底用 `logo_full.png`，深底用 `logo_full_white.png`，放底部，高度約版面 6–8%
- 不要把 logo 疊在人臉或重要文字上

**簡報**
- 封面放全標；內頁只在右下角放 `logo_white.png` 或 `logo.png` 小圖

**網頁**
- 頁首：六線標誌＋「Sixhands Studio」＋小字「助哥 · 七期房地產」
- favicon：`logo_mark.svg`
- 頁尾版權：`© 2026 Sixhands Studio`

## 6. 標準聯絡管道（頁尾、片尾、名片通用）

| 管道 | 連結 |
|---|---|
| 官網 | https://sixhands-studio.netlify.app/ |
| 所有連結頁 | https://sixhands-studio.netlify.app/bio-links.html |
| LINE 官方帳號 | https://line.me/R/ti/p/@080akczk（@080akczk） |
| YouTube | ［待填：頻道網址］ |
| Facebook 粉專 | ［待填：粉專網址］ |
| Instagram | ［待填：IG 帳號］ |
| TikTok | ［待填：TikTok 帳號］ |

⚠️ 表格裡是「［待填］」的管道**不要**放進對外成品；只放已填好的。

## 7. 什麼時候「不」掛 Sixhands 品牌

- **交給客戶自用的成品**（客戶的 MV、客戶的網站、客戶的海報、學員企業的客服機器人）→ 用**客戶自己的品牌**，不掛 Sixhands logo。
- 只有「交給客戶看的報告／月報／提案」掛 Sixhands 品牌（表示這是我們的服務產出）。
- 客戶明確要求「Powered by Sixhands Studio」時，才在頁尾加一行小字。

## 8. 交付前檢查

- [ ] 名稱寫法正確（Sixhands Studio／助哥）
- [ ] logo 用對版本（深底白、淺底綠），沒有變形、沒有被裁切
- [ ] 顏色用色票，沒有自己調的近似色
- [ ] AI 生成內容有標示
- [ ] 聯絡管道只放已填好的，沒有「［待填］」字樣
- [ ] 客戶自用成品沒有誤掛 Sixhands logo
