# 小客 · LINE 24 小時自動客服（Windows 版）

**定位：答得出的秒回，答不出的轉真人。** 知識庫沒寫的絕不亂編；談錢、客訴、議價、個資一律交給真人。

一台放在家裡或店裡的 Windows 電腦就能跑，只用 Python 標準庫，不必 `pip install`。

```
客人傳 LINE ──► LINE 伺服器 ──► cloudflared 通道 ──► 你電腦上的小客（埠 8788）
                                                        │
                        ┌──── 有把握 ──── 自動回（全自動模式）／先給你審（審核模式）
                        └──── 沒把握／談錢／客訴／注入 ──► 推播給管理員，你回「1」或直接打字
```

---

## 一、先裝兩個東西（只做一次）

1. **Python 3.10 以上**：https://www.python.org/downloads/
   安裝第一個畫面**一定要勾「Add python.exe to PATH」**。
   Microsoft Store 版的 python 在開機排程裡跑不起來，請用官網版。
2. **cloudflared**（把家用電腦變成 LINE 打得到的 https 網址，免費）：
   開 PowerShell 打
   ```powershell
   winget install --id Cloudflare.cloudflared
   ```

> Windows 的命令是 `python`，沒有 `python3`（打了會說「不是內部或外部命令」）。

## 二、放程式

把整個 `xiaoke` 資料夾放到 **`C:\xiaoke`**。

⚠️ **不要放桌面、文件或任何 OneDrive 資料夾。** 同步中的檔案會被鎖住，服務看起來活著卻什麼都不做
（Mac 版就是放在 iCloud 桌面，死了一個月沒人發現）。安裝腳本偵測到 OneDrive 會直接拒絕。

## 三、填金鑰、開客服

在 `C:\xiaoke` 開 PowerShell（資料夾空白處按 Shift + 右鍵 →「在這裡開啟 PowerShell 視窗」）：

```powershell
copy .env.template .env
notepad .env                                          # 填 GEMINI_API_KEY
python tools\new_tenant.py sixhands --name "Sixhands Studio"
notepad tenants\sixhands\config.json                   # 填 channel_secret、channel_access_token
notepad tenants\sixhands\knowledge.md                  # 寫知識庫（格式見檔案裡的範本）
python server.py --check                              # 體檢，全部 [ OK ] 再往下
```

LINE 的兩串金鑰怎麼拿：LINE Developers → 你的 Channel →
Basic settings 的 **Channel secret**、Messaging API 分頁最下面的 **Channel access token**（按 Issue）。

## 四、設定開機自動跑

**推薦：開機就跑、不用登入**（Windows Update 半夜重開機也會自己起來）。
開始選單搜尋 PowerShell → 右鍵「**以系統管理員身分執行**」：

```powershell
cd C:\xiaoke
powershell -ExecutionPolicy Bypass -File windows\install_autostart.ps1 -AtStartup -NoSleep
```

沒有系統管理員權限的話，拿掉 `-AtStartup`，改成「登入 Windows 後自動跑」
（那就要設 Windows 自動登入，不然重開機後停在登入畫面，客服就沒了）。

| 參數 | 作用 |
|:--|:--|
| `-AtStartup` | 開機就啟動，不用登入（需系統管理員） |
| `-NoSleep` | 插電時不睡眠、不休眠。**電腦睡著＝客服下班**，24 小時一定要加 |

腳本會做：找 Python → 體檢 → 在「工作排程器」建立 `XiaokeLineBot`（當掉每分鐘自動重開）→ 啟動 → 15 秒後確認健康狀態。
看到 `[ OK ] 小客活著。對外網址：https://xxxx.trycloudflare.com` 就完成了，
**webhook 會自動註冊到 LINE，不用手動貼網址。**

| 要做什麼 | 指令 |
|:--|:--|
| 重啟（改了金鑰、加了新租戶） | `powershell -ExecutionPolicy Bypass -File windows\restart.ps1` |
| 移除開機自動跑 | `powershell -ExecutionPolicy Bypass -File windows\uninstall_autostart.ps1` |
| 看健康狀態 | 瀏覽器開 http://localhost:8788/health |
| 看 log | `notepad logs\xiaoke.log` |

知識庫 `knowledge.md` **改完存檔就生效，不用重啟**。

## 五、上線前必做

1. **LINE 官方帳號後台**（manager.line.biz）→ 設定 → 回應設定：
   Webhook **開**、自動回應訊息 **關**、加入好友的歡迎訊息 **關**（不關會跟小客搶著回）。
2. **配對管理員**：用你自己的 LINE，1 對 1 傳配對碼給官方帳號（`--check` 會印出來）。
   配對成功後會換一組新碼，舊碼外流也沒用。沒配對＝轉人工的訊息沒人收得到。
3. **先跑審核模式一週**（預設就是），每則草稿都先給你看，準了再在 LINE 打「全自動」。
4. **用另一個 LINE 帳號跑驗收 12 題**（含注入攻擊、合規誘導）。管理員帳號傳的訊息一律當指令，不能拿來測。

## 六、管理員在 LINE 上的指令

| 打什麼 | 做什麼 |
|:--|:--|
| `1` / `0` | 發送／略過最新一則 |
| `#3 1` / `#3 0` | 發送／略過第 3 則 |
| `#3 文字` | 用你打的字回第 3 則 |
| 直接打字 | 用你的版本回最新一則 |
| `清單`、`狀態`、`知識庫` | 看待處理、今日數字、【待補】還剩幾處 |
| `全自動` / `審核模式` | 切換模式 |

## 七、看成效

```powershell
python tools\report.py              # 全部租戶近 30 天
python tools\report.py sixhands 7    # 指定租戶近 7 天
```

- **自動化率 < 50%** → 照「轉人工的原因」補知識庫
- **擬稿失敗 > 0** → Gemini 金鑰或額度問題
- **疑似注入 > 0** → 有人在玩 AI，看 `tenants\<代號>\log.jsonl`
- **推播失敗 > 0** → 當月訊息額度用完（審核模式的草稿與轉人工通知都走推播，會吃額度）

## 排錯（依序查）

1. 工作排程器 →「工作排程器程式庫」找 `XiaokeLineBot`，看「上次執行結果」
2. http://localhost:8788/health 打不開 → 看 `logs\xiaoke.log`
3. health 的 `public_url` 是空的 → cloudflared 沒裝或被防毒擋，`python server.py --check`
4. `webhook` 顯示「註冊失敗」→ `channel_access_token` 填錯或過期
5. 客人說沒收到 → `log.jsonl` 找 `push_error`

## 關於快速通道

`trycloudflare.com` 快速通道免費、免註冊，但 Cloudflare 不保證它的穩定度，重開就換網址
（小客會自動重新註冊，所以不用管）。客戶多了之後，建議改成 Cloudflare 具名通道（固定網址），
把網址填進 `.env` 的 `PUBLIC_URL`，小客就不會自己開快速通道。

---

## 檔案

| 檔案 | 作用 |
|:--|:--|
| `server.py` | 主程式：收 webhook、開通道、註冊 webhook |
| `engine.py` | 判斷核心：注入、個資、強制轉人工、禁字、管理員指令（不碰網路，可離線測試） |
| `clients.py` | LINE 與 Gemini API |
| `tools/new_tenant.py` | 開新客服 |
| `tools/report.py` | 成效報表 |
| `windows/*.ps1` | 開機自動跑的安裝、重啟、移除 |
| `tenants/<代號>/` | 每個官方帳號的設定、知識庫、待處理、log（**含金鑰，不進 git**） |

```powershell
python test_xiaoke.py   # 離線測試（含驗收 12 題），不需金鑰與網路
```
