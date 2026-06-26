# YouTube 自動上傳設定教學

讓影片做好後自動上傳到你的 YouTube 頻道。比 API 金鑰麻煩一點，因為上傳影片
需要 **OAuth 授權**（你要親自同意「讓這支程式管理我的 YouTube」）。

> ⚠️ 重要限制：未經 Google 審核的程式，透過 API 上傳的影片**會是「私人」**。
> 所以一開始是「自動上傳成私人 → 你到後台手動按公開」。要全自動公開需送 Google 審核（流程長）。

設定完成後，需要三個環境變數：
`YOUTUBE_CLIENT_ID`、`YOUTUBE_CLIENT_SECRET`、`YOUTUBE_REFRESH_TOKEN`

---

## 步驟 1：在 Google Cloud 建立 OAuth 用戶端

1. 開 https://console.cloud.google.com/ ，選一個專案（可沿用 Gemini 那個）
2. 搜尋並啟用 **YouTube Data API v3**（API 與服務 → 啟用 API）
3. 左側 **API 與服務 → OAuth 同意畫面**：
   - User Type 選 **External（外部）**，填必要欄位，儲存
   - 「測試使用者(Test users)」加入**你自己的 Gmail**（很重要，否則授權會被擋）
   - Scopes 可不加（程式會自己要 youtube.upload）
4. 左側 **憑證 → 建立憑證 → OAuth 用戶端 ID**：
   - 應用程式類型選 **桌面應用程式(Desktop app)**
   - 建立後**下載 JSON**（檔名通常 client_secret_xxxx.json），裡面有 client_id 與 client_secret

---

## 步驟 2：取得 Refresh Token（二選一）

### 方法 A：用 OAuth Playground（不用寫程式，推薦）
1. 開 https://developers.google.com/oauthplayground/
2. 右上角齒輪 ⚙️ → 勾 **Use your own OAuth credentials**，填入步驟 1 的 client_id / client_secret
3. 左側「Input your own scopes」貼上：
   ```
   https://www.googleapis.com/auth/youtube.upload
   ```
   按 **Authorize APIs** → 用你的 Google 帳號登入並同意
4. 按 **Exchange authorization code for tokens**
5. 畫面會出現 **Refresh token**（rt- 或 1// 開頭）→ 複製保存

> 注意：OAuth Playground 的重新導向網址 `https://developers.google.com/oauthplayground`
> 要加到步驟 1 OAuth 用戶端的「已授權的重新導向 URI」。

### 方法 B：在自己電腦跑小工具
```bash
pip install google-auth-oauthlib
python scripts/youtube_get_refresh_token.py client_secret_xxxx.json
```
會開瀏覽器授權，結束後印出三個值（含 refresh token）。

---

## 步驟 3：把三個值填進雲端環境變數
在 claude.ai/code 環境設定 → Environment variables 加：
```
YOUTUBE_CLIENT_ID=（你的 client id）
YOUTUBE_CLIENT_SECRET=（你的 client secret）
YOUTUBE_REFRESH_TOKEN=（剛拿到的 refresh token）
```
按 Save changes。

> 網路白名單不用再加：上傳走 `*.googleapis.com`、`accounts.google.com`，都在預設白名單內。

---

## 步驟 4：上傳（有影片之後）
```bash
python scripts/youtube_upload.py final_video_cat_economics.mp4 \
  --title "為什麼罐頭越來越貴?爪爪稅大戰｜貓咪經濟學" \
  --description-file youtube_description.txt \
  --tags "貓咪經濟學,關稅,經濟學,通貨膨脹" \
  --privacy private
```
上傳完成會印出影片網址；確認無誤後到 YouTube 後台改「公開」。

---

## 配額提醒
上傳一支影片約耗 1600 配額；YouTube API 預設每日 10000 配額（約 6 支/日），個人用足夠。
