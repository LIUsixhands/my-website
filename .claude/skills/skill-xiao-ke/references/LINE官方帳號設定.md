# 客戶要做的事：拿到 LINE 憑證（可直接整份轉給客戶）

> 這份給客戶自己照做，約 10 分鐘。做完把**兩串代碼**回傳即可，其他我們處理。

## Step 1：有一個 LINE 官方帳號

沒有的話到 https://tw.linebiz.com/service/account-solutions/line-official-account/ 免費申請。
（已經有官方帳號的直接跳 Step 2）

## Step 2：開通 Messaging API

1. 進 **LINE Official Account Manager**（manager.line.biz）→ 選你的帳號
2. 右上「設定」→ 左側「**Messaging API**」→ 點「**啟用 Messaging API**」
3. 依指示建立／選擇一個 Provider（公司名稱即可）→ 完成

## Step 3：拿兩串代碼

進 **LINE Developers**（developers.line.biz/console）→ 選剛剛的 Channel：

| 要拿的東西 | 在哪 |
|:---|:---|
| **Channel secret** | 「Basic settings」分頁，往下找 Channel secret |
| **Channel access token** | 「Messaging API」分頁最下方，點 **Issue**（選 long-lived）|

⚠️ 這兩串等同你帳號的鑰匙，只傳給負責建置的人，不要貼在公開群組。

## Step 4：關掉會打架的官方設定（很重要）

回 **LINE Official Account Manager** → 設定 → **回應設定**：

| 項目 | 要設成 |
|:---|:---|
| 聊天 | **開啟** |
| Webhook | **開啟** |
| 自動回應訊息 | **關閉** ← 不關會跟 AI 客服搶著回罐頭訊息 |
| 加入好友的歡迎訊息 | **關閉**（改由 AI 客服發，內容可客製） |

## Step 5：等我們通知配對

我們建好後會給你一組**配對碼**。
用你自己的 LINE 加自家官方帳號為好友 → 1 對 1 傳那組配對碼 →
你就成為這個帳號的「客服管理員」，AI 沒把握的問題會即時推播給你，你回「1」就發出。
