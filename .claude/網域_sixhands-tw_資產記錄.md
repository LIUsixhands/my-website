# 網域資產記錄：sixhands.tw

> ## ✅ 2026-10-05 18:21 已上線
> `https://sixhands.tw` 正常載入、憑證有效（瀏覽器顯示鎖頭）。
> 全程未觸發任何 Netlify 建置，在額度凍結期間完成。
>
> **總耗時：2026-10-04 19:46 下單 → 2026-10-05 18:21 上線，約 22.5 小時。**

> 建立 2026-10-04。網域是公司資產，**過期被別人註冊走就拿不回來**。
> 這份檔案是三年後找不到資料時的唯一依據。

---

## 基本資料

| 項目 | 值 |
|:--|:--|
| 網域 | **sixhands.tw** |
| 註冊商 | **網路中文**（net-chinese.com.tw） |
| 註冊商帳號 | `sixhands` |
| 註冊人 Email | `sixhands2001@gmail.com`（TWNIC 驗證信與到期通知都寄這裡） |
| 訂單編號 | **1603479** |
| 下單日 | 2026-10-04 |
| 年限 | **3 年** |
| 金額 | TWD 2,160（約 720／年，一個月 60 元） |
| 付款方式 | 匯款（國泰世華 信義分行 013） |
| 發票 | 個人電子發票，手機條碼載具 `/25Z4PXP` |
| **假設到期日** | **2029-10-04** ⚠️ 見下方校正事項 |

> ⚠️ **到期日是推算值。** 10/4（週日）匯款，網路中文 10/5 起上班對帳，
> 實際註冊生效日可能是 10/5 或 10/6，到期日隨之位移。
> **取得後台顯示的實際到期日後，必須回來校正本檔與三則行事曆提醒。**

## 為什麼不在 Netlify 買

**Netlify 不販售 `.tw`**（2025-11-13 changelog 列的是 .place／.be／.pl／.dk／.co.uk）。
`.tw` 必須向 TWNIC 認證的註冊商購買，再把 DNS 指向 Netlify。
助哥原本的指示「在 Netlify 買就好，不用搬來搬去」因此無法執行，已於 2026-10-04 說明並改向網路中文購買。
**網域留在註冊商，只是 DNS 指向 Netlify，沒有「搬來搬去」的問題。**

---

## 📅 已建立的行事曆提醒（Google Calendar，sixhands2001@gmail.com）

| 日期 | 標題 | 用途 |
|:--|:--|:--|
| 2026-10-05 15:00 | 確認 sixhands.tw 匯款入帳 ＋ TWNIC 驗證信 | 近期四項確認（見下） |
| 2029-07-03（全天） | ⏳ 到期前 3 個月：決定續約或轉移 | 要轉註冊商得趁早，到期前 60 天內通常不能轉 |
| 2029-09-04（全天） | 🔔 **續約繳費（到期前 1 個月）** | ⭐ 主提醒 |
| 2029-09-27（全天） | 🚨 最後確認：續約了嗎？（到期前 1 週） | 最後防線 |

三則續約提醒皆設 popup ＋ email 雙通道。

---

## ✅ 2026-10-05 要確認的四件事

1. **訂單狀態** — 網路中文會員中心，是否已從「未付款」變「已付款」
   （週日匯款，週一上班才對帳。若未更新，找「匯款通知／匯款回報」或回信附轉帳後五碼）
2. **TWNIC 聯絡資料驗證信** — 到 Gmail 找出來點連結。**沒點會被停用**，且容易被當廣告忽略
3. **記下實際到期日** — 回來校正本檔與三則提醒
4. **DNS 設定畫面截圖** — 進「商標網域管理」→ sixhands.tw → DNS 設定，
   **先不要自己填**，各家欄位名稱寫法不同，截圖給 Claude 再逐格確認

⏰ 訂單有效期限 **2026-10-09 10:00**，逾期訂單失效、域名釋出。

---

## 🎯 DNS 設定 — ✅ 已於 2026-10-05 完成

路徑：域名總覽 → `sixhands.tw` 那列的橘色「代」→ **DNS紀錄設定** 分頁

| 序號 | 記錄類型 | 主機名稱/別名 | IP/域名 |
|:--|:--|:--|:--|
| 1st | **A** | **（留空）** | `75.2.60.5` |
| 2nd | **CNAME** | `www` | `sixhands-studio.netlify.app` |

存檔後畫面顯示「✅ DNS紀錄設定成功」。

### ⚠️ 這家的介面有一個坑，下次別再踩

**「主機名稱/別名」欄位後面已經自動接上 `.sixhands.tw`。**
所以那格只填**子網域的部分**：

- 根網域（`sixhands.tw` 本身）→ **留空**，**不是填 `@`**
  （填 `@` 會變成 `@.sixhands.tw`，錯的）
- `www` → 填 `www`，系統自動組成 `www.sixhands.tw`

> 🩸 我（Claude）一開始憑常識說「填 `@`」，是錯的。
> **看過實際畫面才下指示**，不要憑其他註冊商的慣例假設。

### DNS 主機設定（另一個分頁，不要動）

```
◉ DNS代管：使用網路中文DNS主機   ← 保持這個
   cns1.net-chinese.com.tw  34.81.16.85
   cns2.net-chinese.com.tw  104.199.229.182
```

DNS 代管**已包含在域名費用內，沒有另外收費**，所以不需要改用 Cloudflare。

### 生效時間 — ✅ 已生效

| 時間（台灣） | 狀態 |
|:--|:--|
| 10-05 10:24 存檔 | SERVFAIL／NoNameservers（尚未生效） |
| **10-05 13:55 複查** | ✅ **已生效** |

```
sixhands.tw      A     -> 75.2.60.5                     ✅
www.sixhands.tw  CNAME -> sixhands-studio.netlify.app.   ✅
```

**實際約 3.5 小時**，遠快於網頁明載的 12–24 小時。
（頁面另註「部分域名 DNS 更新須由管理局審核」——本次未遇到。）

> 📌 存檔後當下查不到是正常的。SERVFAIL／NoNameservers 代表「還沒生效」，不是「填錯」。
> 判斷方式：拿一個已知正常的網域（如 `net-chinese.com.tw`）當對照組，
> 它解析得出來就代表查詢管道正常，問題純粹是時間。

> ⛔ **另一處自我更正**：我曾說「可以直接問網路中文的 DNS 主機，幾分鐘就知道對不對」。
> **做不到。** 這個執行環境的 DNS 查詢全被導向同一個解析器，無法繞過遞迴鏈直接問權威伺服器。
> 所以我看到的跟全世界看到的一樣，**沒有捷徑，只能等**。

---

## ✅ Netlify 端 — 2026-10-05 18:19 完成

```
Production domains
  sixhands-studio.netlify.app   Netlify subdomain
  sixhands.tw                   ★ Primary domain
  www.sixhands.tw               Redirects automatically to primary domain
```

**加完 `sixhands.tw` 後 Netlify 自動建立 `www` 並設定轉址，不需手動加第二個。**

### 操作路徑（下次或換站時照走）

```
Netlify → Projects → sixhands-studio → Domain management
  → Add a domain ⌄
     ⛔ Buy a new domain              ← 不是這個（這是買新網域）
     ✅ Add a domain you already own  ← 是這個
  → 輸入 sixhands.tw → Verify → Add domain
  → 往下捲到 HTTPS / SSL/TLS certificate
```

> 🩸 **踩過的坑**：Domain management 頁面上的「**Find a new domain**」（網址含 `/buy-domain`）
> 是**賣你新網域**的頁面，不是加入既有網域。助哥第一次點進去就是那裡。
> 分辨方式看網址：`/domain-management` 才對，`/domain-management/buy-domain` 是買。

### SSL 憑證

| 時間 | 狀態 |
|:--|:--|
| 加完網域當下 | ❌ `We could not provision a Let's Encrypt certificate` |
| 按 **Verify DNS configuration** | ✅ `DNS verification was successful` |
| 按 **Provision certificate** | ⚙️ `Waiting on DNS propagation`（自動進行中） |

**第一次失敗是正常的時間差**，不是設定錯誤——當下已獨立驗證 DNS 全部正確：

```
sixhands.tw      A     -> 75.2.60.5                     ✅
www.sixhands.tw  CNAME -> sixhands-studio.netlify.app.  ✅ (解析到 Netlify IP)
CAA                    -> 無                             ✅ 沒有紀錄阻擋發憑證
NS                     -> cns1/cns2.net-chinese.com.tw  ✅
```

→ 處理方式：按「Verify DNS configuration」重試即可。進入 `Waiting on DNS propagation`
後 Netlify 會自動完成，**不需要再按任何按鈕**。

⛔ **不要按「Provide your own certificate」**——那是要自己花錢買憑證，Netlify 的 Let's Encrypt 免費且自動續期。

> ⚠️ **Claude 無法驗證憑證結果。** 本執行環境的 egress proxy 擋住 `sixhands.tw`、
> `netlify.app`、`app.netlify.com`、`crt.sh`（憑證透明度查詢站），全部回 403。
> **最後一哩只能由助哥用瀏覽器開 `sixhands.tw` 看有沒有鎖頭。**

> ✅ **全程不需要建置**，在 2026-10-26 額度凍結期間順利完成。
> 真正要等 10/26 的是「全站 349 處網址改寫」那批。

---

## 🔁 網域上線時必須同步更改的地方

**漏掉任何一項，等於白換。**

| # | 位置 | 現況 |
|:--|:--|:--|
| 1 | 全站 HTML 349 處（canonical／og:url／JSON-LD url、@id、mainEntityOfPage）＋ sitemap.xml，共 57 檔 | `sixhands-studio.netlify.app` |
| 2 | **Google 商家檔案「網站」欄位** | `https://sixhands-studio.netlify.app/` |
| 3 | Search Console 新增並驗證新網域資源、重送 sitemap | — |
| 4 | FB／LINE／YouTube／591 簡介欄 | — |
| 5 | 舊網址 **一頁對一頁 301**（`_redirects` 或 `netlify.toml`），**不可全導首頁** | — |
| 6 | 名片、QR Code、看板、委託書 | 印出去就改不了，換域名後才重印 |
| 7 | **Claude 知識庫**（`.claude/` 文件、員工 references、商辦網頁產生器） | ✅ **2026-10-06 已改**，規則寫進 `助哥與Claude的工作約定.md` |
| 8 | 根目錄文件（連結總表、LINE OA 內容包、換新對話框必讀） | ⏸ 併入 #1 那批，10/26 處理 |

→ 排在 `部署凍結與待辦_2026-10.md` 第 1 項，等 2026-10-26 額度重置後一次處理。

---

## 🩸 為什麼要這麼小心

網域過期釋出後被他人註冊，**拿不回來**。屆時失效的不只是網站：

名片上的網址、QR Code、Google 商家檔案的連結、Search Console 的全部歷史、
所有外部連結、以及好不容易累積的搜尋信任——**全部歸零**。

「網站打不開」那天才發現，就已經來不及了。
