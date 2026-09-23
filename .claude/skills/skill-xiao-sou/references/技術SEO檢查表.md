# 技術 SEO 檢查表（seocheck.py 的 20 項對照）

> 修的順序：**必修（[X]）先修完，再處理建議（[!]）**。必修多半是「Google 看不懂你」，建議多半是「看得懂但不夠好」。

## A. 頁面身分（必修等級最高）

| 代碼 | 問題 | 為什麼要修 | 怎麼修 |
|:---|:---|:---|:---|
| `TITLE_MISSING` | 沒有 `<title>` | 搜尋結果沒有標題，等於沒有店招 | 一頁一句，主關鍵字放前面 |
| `TITLE_LONG` | 寬度 > 60 | 中文約 30 字就被切，重點跑到「…」後面 | 把品牌名縮到最後、砍形容詞 |
| `TITLE_SHORT` | 寬度 < 20 | 塞不下關鍵字，浪費最貴的版位 | 加上「做什麼 + 給誰 + 在哪」 |
| `TITLE_DUP` | 多頁同標題 | Google 不知道該給誰排名，互相稀釋 | 每頁一個獨立意圖 |
| `DESC_MISSING` | 沒有描述 | Google 自己從內文亂抓一段當摘要 | 寫 70-80 個中文字，含關鍵字與行動呼籲 |
| `DESC_LONG/SHORT` | 長度不對 | 尾巴被切或資訊不足 | 目標寬度 100-160（約 50-80 中文字） |
| `CANONICAL_MISSING` | 沒有 canonical | 同一頁被 `?fbclid=` 等參數重複索引，權重拆散 | 每頁指向自己的完整正式網址 |

## B. 分享與社群預覽

| 代碼 | 修法 |
|:---|:---|
| `OG_MISSING` / `OG_PARTIAL` | 補齊 `og:type / og:title / og:description / og:image / og:url / og:site_name`。**圖片必須是絕對網址**，建議 1200×630 |
| `TWITTER_MISSING` | 補 `twitter:card=summary_large_image` 與 title／description／image |

> OG 不直接影響排名，但直接影響「同一則連結貼到 LINE 群組有沒有人點」。這是流量。

## C. 結構化資料（拿複合式摘要的關鍵）

| 代碼 | 修法 |
|:---|:---|
| `LD_MISSING` | 依頁面性質加：活動頁→`Event`、課程頁→`Course`、店家→`LocalBusiness`、人物→`Person`、常見問題→`FAQPage`、影片→`VideoObject`、麵包屑→`BreadcrumbList` |
| `LD_INVALID` | JSON 格式錯，Google 整段忽略。用 `python3 -c "import json;json.load(open('x.json'))"` 驗 |

**鐵律**：schema 寫的東西，頁面上必須看得到。頁面沒有 FAQ 區塊就不能寫 FAQPage；沒有真實評論就不能寫 AggregateRating。這是 Google 明文的作弊判定，罰起來是整站。

驗證工具：Google 複合式搜尋結果測試（search.google.com/test/rich-results）、Schema Markup Validator。

## D. 內容結構

| 代碼 | 修法 |
|:---|:---|
| `H1_MISSING` / `H1_MULTI` | 一頁一個 h1，內容＝這頁最重要的那句話 |
| `H2_MISSING` | 用 h2 切段，每段回答一個問題。Google 靠這個抓「精選摘要」 |
| `THIN_CONTENT` | 正文 < 300 字很難排。銷售頁補 FAQ、案例、常見疑慮；工具頁補使用說明 |
| `IMG_ALT` | 每張有意義的圖都要 alt，寫「圖裡是什麼」而不是塞關鍵字 |
| `INTERNAL_LINKS` | 每頁至少 3 個站內連結。孤島頁（沒人連進去）等於不存在 |

## E. 基礎設定

| 代碼 | 修法 |
|:---|:---|
| `VIEWPORT_MISSING` | `<meta name="viewport" content="width=device-width, initial-scale=1">`。缺這行等於放棄手機排名 |
| `LANG_MISSING` / `LANG_ODD` | `<html lang="zh-TW">` |
| `NO_SITEMAP` | 產 sitemap.xml，並在 GSC 提交 |
| `NO_ROBOTS` | 產 robots.txt，並在最後一行寫 `Sitemap:` |

## F. Sixhands Studio特別加的兩項

| 代碼 | 說明 |
|:---|:---|
| `STALE_DATE` | title／description 寫著已經過去的場次日期（例：9 月了還掛 7/19）。搜尋結果掛過期資訊 = 直接勸退 |
| `RANDOM_DOMAIN` | 頁面寫死 `xxx-yyy-a1b2c3.netlify.app` 這種平台隨機網址。**能記住、能唸出口、能印在名片上的網域，本身就是 SEO 資產** |

## G. 掃描器抓不到、必須人工看的

1. **網站速度**：用 PageSpeed Insights 看 Core Web Vitals（LCP、INP、CLS）。首圖太大是最常見兇手。
2. **是否被索引**：Google 搜 `site:你的網域`。搜不到 = 前面做的全部無效，先去 GSC 要求索引。
3. **重複內容**：同一篇文章貼到多個平台，要指定 canonical 給原始出處。
4. **404 與轉址**：改檔名、換網域前先列轉址表（舊網址 → 新網址，301）。
5. **搜尋意圖對不對**：排上了卻沒人點、點了立刻跳出，通常是「這頁答的不是他想問的」。
