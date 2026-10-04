# Meta API 設定 SOP（FB 粉專 ＋ IG 商業帳號）

> ⚠️ **Meta 的介面、API 版本與權限名稱一直在改。**
> 這份是流程骨架與判斷點，實際欄位以當下的開發者後台為準。
> 卡住時先查 developers.facebook.com 的官方文件，**不要照記憶硬填**。

## 0. 誰做這件事（很重要）
**Token 由客戶／學員本人在自己的帳號下產生。** 小群不代登入、不代收驗證碼、不代保管密碼。
理由有二：一是帳號安全責任歸屬，二是合作結束時客戶要能自己收回權限。
產完 Token 由客戶貼進 `config.json`（權限 600，不進 git、不進交付文件、不截圖）。

## 1. 前置條件（缺一不可）
- [ ] 有一個 **Facebook 粉絲專頁**，客戶本人是管理員
- [ ] IG 帳號已切換為 **商業帳號或創作者帳號**（個人帳號無法用內容發佈 API）
- [ ] IG 帳號已在粉專設定裡 **連結到那個粉專**
- [ ] 有一個 Meta 開發者帳號（developers.facebook.com）

## 2. 建立應用程式
1. 開發者後台 → 建立應用程式 → 類型選 **「企業」**
2. 加入產品：**Facebook 登入**、**Instagram Graph API**（名稱依當前後台為準）
3. 記下 **應用程式編號** 與 **應用程式密鑰**

## 3. 需要的權限（Scope）
| 權限 | 做什麼 |
|:--|:--|
| `pages_show_list` | 列出可管理的粉專 |
| `pages_read_engagement` | 讀粉專資料與貼文 |
| `pages_manage_posts` | 發文、排程、刪文 |
| `instagram_basic` | 讀 IG 帳號基本資料 |
| `instagram_content_publish` | 發佈 IG 貼文與 Reels |
| `read_insights` | 讀洞察數據（要看成效才需要） |
| `business_management` | 帳號屬於企業管理平台時需要 |

⚠️ **上線前要送應用程式審查。** 未審查的應用程式只有「應用程式角色內的人」（管理員／開發人員／測試人員）
可以用，一般客戶帳號會失敗。若只服務單一客戶且客戶願意被加進應用程式角色，可以不送審。
**接案報價前先問清楚要哪一種**，送審是要寫用途說明與錄螢幕的，工時差很多。

## 4. 取得 Token（三段）
1. **短期使用者 Token** — 圖形 API 測試工具選好應用程式與權限 → 產生。有效期約 1–2 小時。
2. **長期使用者 Token** — 用短期換長期（約 60 天）：
   ```
   GET /oauth/access_token
       ?grant_type=fb_exchange_token
       &client_id=<應用程式編號>
       &client_secret=<應用程式密鑰>
       &fb_exchange_token=<短期Token>
   ```
3. **粉專 Token** — 拿長期使用者 Token 呼叫 `GET /me/accounts`，取回該粉專的 `access_token`。
   由長期使用者 Token 換來的粉專 Token **通常不會自動過期**，但改密碼、移除權限、Meta 政策變動都會失效。

驗證：
```bash
python3 socialpost.py auth 客戶代號
```
`auth` 會順便印出可管理的粉專與對應的 `ig_user_id`，直接填進 config。

## 5. IG 的兩個硬限制（一定要先跟客戶講）
1. **只吃公開網址**：`image_url` / `video_url` 必須是外網打得開的 https 網址，不能傳本機檔。
   → 要準備一個公開素材空間。可選：GitHub Pages、Netlify、任何自有網域的靜態空間。
   把網址前綴填進 config 的 `public_asset_base`。
   ⚠️ 有些雲端硬碟的「分享連結」不是直連檔案，Meta 抓不到，要用真正的直連網址。
2. **沒有原生排程 API**：FB 有 `scheduled_publish_time`，IG 沒有。
   小群的 IG「排程」是到點才呼叫 API，**那台電腦要開著**。做不到就誠實講，改人工發。

## 6. 額度
IG 內容發佈有 24 小時額度上限。查法：
```bash
python3 socialpost.py limit 客戶代號
```
快到頂就停手，硬送只會拿到錯誤碼還浪費一次。

## 7. 斷線時的排查順序
1. `python3 socialpost.py auth 客戶代號` → Token 死了沒
2. 錯誤訊息裡的 `code` / `error_subcode` 拿去查官方錯誤碼表
3. 客戶是不是換了密碼、把應用程式移除了、粉專管理員權限被收回
4. API 版本是不是被淘汰（config 的 `graph_version`）
5. 以上都不是 → 看官方變更紀錄，多半是政策改了

**永遠不要把「重新產一個 Token」當第一步。** 先查為什麼會斷，不然下個月照斷。
