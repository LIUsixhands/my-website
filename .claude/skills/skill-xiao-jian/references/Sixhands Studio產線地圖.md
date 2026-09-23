# Sixhands Studio產線地圖（小健專用）

## 會產生大量中間檔的專案

| 專案 | 路徑 | 中間檔資料夾 | 成品在哪 |
|---|---|---|---|
| The Frozen Archives | `~/Desktop/TheFrozenArchives頻道/episodes/EPxx/` | `tmp_v1` `tmp_v2` `tmp_shorts` `tmp_thumb` | **`final/`** |
| Lively English Stories | `~/Desktop/Lively English Stories頻道/EPxx_*/` | `tmp` `nostatic_tmp` `once*_tmp` | 專案根 `final.mp4` |
| 貓咪經濟學 | `~/貓咪經濟學/`（**本機碟，不是桌面**） | 依集數 | 依集數 |
| 各類 MV 專案 | `~/{專案名}_MV/`（本機碟） | `tmp` | 專案根 |

🚨 **貓咪經濟學在 `~/貓咪經濟學/`，不在桌面。** 別搞混。

## 已知的空間大戶（2026-09-15 盤點）
```
43G  ~/Desktop          ← 在 iCloud 上，長期隱患
39G  ~/Library          ← 其中 13G 是 Claude 沙箱 VM（不可刪）
7.8G ~/貓咪經濟學
3.1G ~/Downloads
```
家目錄根層另有十幾個已交付的 MV 專案資料夾，加總約 6GB
（財富冥想、二泉映月、0821 短影片 A/B、講座開場片加長版、TCELL1、音樂MV工作區…）。
**這些是成品案，裡面混著原始素材，要一個一個確認，小健不自動處理。**

## launchd 排程清單（`~/Library/LaunchAgents/`）
啟用中的 `com.sixhands.*` / `com.poetic.*` 系列涵蓋：
每日發片（貓咪經濟學 20:00、油畫詩境 21:00）、留言自動回覆 22:00、
TFA drip 產線、小客 LINE 客服、小搜 blog。

⚠️ **停用中的 plist 會留成 `.plist.disabled` 或 `.bak_日期`** —— 那些不算啟用，別誤報。

## 檢查排程時要注意
1. `RunAtLoad` 是否為 0（見踩雷速查）
2. 路徑是否在 iCloud 同步區
3. `ProgramArguments` 指到的檔案是否還存在（改過資料夾名稱會斷）
4. **上一集做完沒換 plist** → 新集 0 進度但 log 很漂亮（TFA drip 的經典死法）
