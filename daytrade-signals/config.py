"""
config.py — 所有參數集中在這裡。
原則：交易規則只能在「開盤前」改。盤中改這個檔案 = 破壞系統。
"""
import math
import os
import sys
from pathlib import Path

# ── 路徑 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
JOURNAL_DIR = BASE_DIR / "journal"          # 每日覆盤 Markdown
STATE_FILE = BASE_DIR / "state.json"        # 當日風控狀態（跨程式共用）
WATCHLIST_FILE = BASE_DIR / "watchlist.json"  # 盤前選股結果
ENV_FILE = BASE_DIR / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    """把 .env 讀進 os.environ。已存在的環境變數優先，不覆寫。

    標準庫不會自動讀 .env。少了這一步，API_KEY 永遠是空字串，
    而且要等到 broker 登入時才炸開 —— 那時你已經在盤中了。
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, val = line.partition("=")
        if not sep:
            continue
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]                 # 去掉成對引號
        if key:
            os.environ.setdefault(key, val)


load_env()


# ── 終端機編碼 ────────────────────────────────────────
def enable_console_fallback() -> None:
    """印不出來的字元換成替代字，而不是讓程式當掉。

    Windows 繁中環境的主控台預設是 cp950，印 ✅ 這類符號會直接
    UnicodeEncodeError —— 體檢報告第一行就掛掉，而且錯誤訊息
    看起來像程式壞了，其實只是終端機編碼。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:          # 被導向到 StringIO 之類的物件
            continue
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):    # pragma: no cover - 取決於終端機
            pass


def console_can_encode(text: str) -> bool:
    """這個終端機印得出這些字元嗎？"""
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        text.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def symbol(preferred: str, fallback: str) -> str:
    """終端機印得出就用 preferred，否則退回純 ASCII 的 fallback。

    狀態符號（✅⚠️❌）本身就是資訊，退成「?」會讓體檢報告讀不懂，
    所以這裡換成 [ OK ] / [WARN] / [FAIL] 而不是交給 errors='replace'。
    """
    return preferred if console_can_encode(preferred) else fallback


# 推播訊息裡的符號，印不出來時換成看得懂的字（不影響送出去的內容）
CONSOLE_FALLBACKS = (
    ("\u26a0\ufe0f", "[注意]"),
    ("\u26a0", "[注意]"),
    ("\U0001f4cc", "[訊號]"),
    ("\U0001f4cb", "[名單]"),
    ("\U0001f4ca", "[覆盤]"),
    ("\u2705", "[OK]"),
    ("\U0001f6d1", "[停損]"),
    ("\u23f9", "[平倉]"),
    ("\u274c", "[FAIL]"),
)


def console_text(text: str) -> str:
    """要印在終端機上的版本；送去 Telegram 的原文不經過這裡。

    cp950 印不出 \U0001f4cc，errors='replace' 會把它變成「?」——
    盤中訊號的第一行於是只剩一個問號，看不出那是訊號還是警告。
    手機收到的仍是原本的符號，這裡只換終端機顯示。
    """
    if console_can_encode(text):
        return text
    for wide, plain in CONSOLE_FALLBACKS:
        text = text.replace(wide, plain)
    return text


# 教學訊息裡的直譯器名稱：Windows 沒有 python3 這個命令
PY_CMD = "python" if os.name == "nt" else "python3"

enable_console_fallback()

# ── 永豐 Shioaji 金鑰（放 .env，不要寫死在程式裡）────────
API_KEY = os.getenv("SHIOAJI_API_KEY", "")
SECRET_KEY = os.getenv("SHIOAJI_SECRET_KEY", "")
SIMULATION = os.getenv("SHIOAJI_SIMULATION", "1") == "1"  # 預設模擬，正式跑再改 0

# ── 電子憑證（只有真錢模式需要）────────────────────────
# 下單與「帳務查詢」都要憑證。本系統不下單，但風控的日虧上限與連敗停手
# 建立在 list_profit_loss 上 —— 沒有憑證就查不到損益，閘門會直接關閘停手。
CA_PATH = os.getenv("SHIOAJI_CA_PATH", "")        # e-Leader 下載的 .pfx 路徑
CA_PASSWD = os.getenv("SHIOAJI_CA_PASSWD", "")    # 憑證密碼（多半是身分證字號）
PERSON_ID = os.getenv("SHIOAJI_PERSON_ID", "")    # 身分證字號

# ── 推播（Line Notify 已停止服務，改用 Telegram）────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── ① 盤前選股條件 ────────────────────────────────────
SCREEN = {
    "min_prev_volume_lots": 5000,   # 前一日成交量下限（張）— 流動性，出得掉才是重點
    "min_price": 20.0,              # 太便宜跳動級距佔比高，成本吃掉利潤
    "max_price": 300.0,             # 太貴單筆風險過大
    "min_amplitude_pct": 3.0,       # 前一日振幅下限（高-低)/收盤
    "max_universe": 20,             # 最多留幾檔進盤中監看
    "require_day_trade": True,      # 只留可現股當沖（Shioaji contract.day_trade）
    # 處置股剔除。**這不是偏好，是 v4 之下的可執行性問題。**
    #
    # 處置股是分盤撮合 —— 5 分鐘或 20 分鐘才撮合一次。而 v4 的進場窗口只有
    # 09:02–09:05 三分鐘：20 分鐘分盤的標的在那三分鐘內**一次都不會撮合**，
    # 5 分鐘分盤最多撮合一次，「突破」這個概念根本不存在。發出去的訊號你
    # 物理上做不到，卻佔掉 20 檔監看、甚至 3 個訊號名額的其中一個。
    #
    # 原本只靠 contract.day_trade，而 broker.is_day_tradable 的註解寫著
    # 「處置股／全額交割**通常**會是 No」—— 「通常」兩個字就是沒把握。
    # 合約物件上其實有 disposition_level / trading_suspended，直接看它們，
    # 不要靠推測。
    "skip_disposition": True,       # disposition_level > 0 或暫停交易 → 不收
    "lookback_days": 5,             # 量能均值回看天數
    "max_kbar_queries": 60,         # 只對前 N 名打 kbars —— API 有流量上限，超過會被停用一分鐘
    "kbar_sleep_sec": 0.3,          # 每次 kbars 之間的間隔
}

# ── ② 盤中訊號規則 ────────────────────────────────────
# 規則版本。**改任何會影響「發不發訊號／發什麼價位」的參數，就要往上加一號。**
#
# 為什麼需要它：20 天的驗證期裡一定會改東西 —— 而我之前的做法是「為了資料
# 純淨，所以什麼都不改」，那會變成無限迴圈：第 20 天改完又要再 20 天驗證。
#
# 正確的做法不是不改，是**記下來是哪一版產生的**，然後分開算。
# 09-29 把 1.5R 改成 2.5R 時就已經造成這個問題了，當時只靠我記得。
#
# v1  2026-09-24  1.5R / 單筆 2,000
# v2  2026-09-29  2.5R / 單筆 3,000
# v3  2026-10-02  停損加上結構線（區間高下方），停損不再飄到突破點之上
# v4  2026-10-02  **策略改版，不是調參數。** 使用者定的四條原則：
#                 1. 09:00-09:05 出買入訊號（開盤區間縮成 09:00-09:02）
#                 2. 09:30 發「時間到」賣出訊號，未達停損的由下單者自己決定
#                 3. 目標回到 1.5R
#                 4. 一天只發三個訊號
#                 依據：前五天 25 筆，訊號全部發在 09:17 之後，而當日漲幅
#                 幾乎都在 09:15 前就走完。10-02 五筆全停損，其中金山電
#                 走到 1.67R（1.5R 的目標打得到，2.5R 打不到）才回頭。
# v5  2026-10-05  **只動倉位大小，四條原則不變。** per_trade_risk 3,000 → 4,000。
#                 理由：v4 把當日筆數從 4 改成 3，但單筆風險沒跟著動，於是
#                 3,000 × 3 = 9,000，日虧上限有 3,000 元永遠用不到。改成
#                 4,000 × 3 = 12,000，三條紅線重新對齊（v2 時代本來就是對齊的）。
#                 為什麼要換版本號：R 倍數不受倉位影響，但**金額**會。10-05 之前
#                 的 26 筆是用 3,000 算的，之後是 4,000 —— 累計元直接相加等於
#                 拿兩把尺量出來的數字相加。analyse.py 的「〇、規則版本」那一節
#                 會把兩段分開，R 可以跨版本看，元不行。
# v6  2026-10-07  **策略改版：當沖改成「最多抱兩天」。** 使用者定的三條：
#                 1. 停損 3%（結構線那條照留，取較寬的）
#                 2. 目標 = 進場價 +8%，不再用 R 倍數
#                 3. 當天沒碰停損就可以留倉，隔天賣；隔天 13:25 還沒結束就平倉
#                 理由（使用者原話）：「當天 8% 較難，兩天較容易」。進場價通常
#                 已經比昨收高 3–6%，當天漲停只有 +10%，+8% 第一天常常物理上
#                 到不了；第二天漲停線從第一天收盤重算，才有空間。
#                 代價要記著：留倉有跳空風險（隔天開盤直接穿過停損，跌停是 -10%，
#                 等於 3.3R），留倉證交稅是 0.3% 不是 0.15%。
#                 批次前三檔照舊用量能倍數排序 ——「勝率最高的前三檔」要等資料夠了
#                 再定義，現在沒有任何數字支持哪一種排法。
# v7  2026-10-07  **只動進場窗口，v6 的停損／目標／抱兩天不變。** 使用者定的兩條：
#                 1. 進場窗口從 09:02–09:05 延長到 09:30。09:02–09:05 突破的那批
#                    照舊收集、09:05 按量能排序發出；09:05 之後突破的一出現就發，
#                    直到湊滿 3 個或 09:30 截止。
#                 2. 取消 09:30「時間到」提醒 —— 那是當沖時代的規則，跟抱兩天
#                    互相打架（09:29 發的訊號，09:30 就叫你考慮走）。
#                 依據：10-07（v6 第一天）20 檔沒有一檔在 09:02–09:05 同時通過
#                 突破、均價線、量能；whynot 10-05／10-06 也是「沒突破」佔 13–14/20
#                 —— 瓶頸是窗口太短，不是名單或濾網。
#                 代價：09:05 之後的訊號是先到先發，而且越晚發的越可能已經追高；
#                 訊號上的「已追高 +x%」就是看這個的。
# v8  2026-10-07  **只動停利目標，其餘照 v7。** 使用者問：「訊號出來，你沒辦法依個股
#                 判斷停利目標嗎？」—— 每檔都 +8% 沒有意義：平常一天動 2% 的股票要
#                 8% 很難，平常動 7% 的 8% 可能還不夠。改成**這一檔近 5 日平均日振幅**，
#                 夾在 3%～10% 之間（3% = 停損距離，再低賺賠比就小於 1；10% = 一天的
#                 漲跌幅上限）。前三檔排序與篩選照舊不動 —— 使用者選「資料夠了再加」。
# v9  2026-10-08  **只加一道進場條件，其餘照 v8。** 使用者：「開盤回落前日收盤價
#                 或開盤近前日收盤價有往上的判斷，再出訊號」。條件是下面兩個
#                 有一個成立就算（± 範圍使用者選 1%）：
#                 1. 開盤價在昨收 ±1% 以內 —— 沒有大跳空
#                 2. 進場前的當日最低點在昨收 ±1% 以內 —— 開高之後曾回到昨收附近
#                 「往上」不另外判：開盤區間突破本身就是往上。
#                 代價要記著：v6 的註解寫過，進場價通常已經比昨收高 3–6%，
#                 這道條件會把跳空開高、一路往上的那種擋掉，訊號會變少。
#                 v8 只跑了 10-08 一天就換掉；v9 從 10-09 起重新算 20 天。
RULESET = "v9"

SIGNAL = {
    "or_start": "09:00:00",         # 開盤區間起
    "or_end": "09:02:00",           # 開盤區間迄（ORB 用）
    "entry_window_end": "09:30:00", # 這時間之後不發新訊號（v7 起 09:30）
    # 09:02-09:05 突破的不是「誰先突破誰先發」，是全部收集起來，
    # 09:05:00 一次發出、按當下量能倍數排序取前 N 檔。
    #
    # 理由：09:05 之前沒有任何資訊可以排序，先來後到等於看哪一檔的報價封包
    # 先到 —— 那是隨機的。開盤頭三分鐘的先後只剩雜訊。
    #
    # 09:05 之後（v7）一出現就發，直到湊滿 max_signals_per_day 或 entry_window_end。
    # 那時候先後已經是真的先後了 —— 晚十分鐘突破，跟晚兩秒收到封包不是同一件事。
    "signal_batch_at": "09:05:00",  # 收集到這個時間，然後一次發出
    # 「時間到」提醒的時間。None = 不發（v7 起）。
    #
    # v4 的規則是 09:30 提醒「沒碰停損的要不要走」。v6 改成抱兩天之後它就跟
    # 規則打架，v7 把進場窗口延到 09:30 之後更是直接撞在一起。要恢復就填時間，
    # 但必須晚於 entry_window_end。
    "exit_signal_at": None,
    "breakout_buffer_pct": 0.10,    # 突破要超過區間高點多少 % 才算數（防假突破）
    "volume_surge_ratio": 1.8,      # 突破當下的量能速率 / 基準量能速率
    # 量能倍數的取樣視窗。**這三個必須跟著進場窗口一起縮**，否則整條規則無聲失效。
    #
    # v3 以前寫死在 signals.py：近期 300 秒、基準至少橫跨 240 秒。那是為
    # 「15 分鐘區間 + 三小時進場窗口」設計的。v4 把窗口壓到 09:00–09:05，
    # 總共只有 300 秒 —— 近期視窗一口氣吃掉全部樣本，「基準」那一組是空的，
    # volume_surge() 回傳 0.0，於是**任何訊號都不成立，整天掛零而且不報錯**。
    # 下面的 validate() 會擋住這種組合。
    "volume_recent_sec": 60,        # 「現在」的量能取樣長度
    "volume_min_recent_span_sec": 30,   # 近期樣本至少橫跨多久才算得出速率
    "volume_min_base_span_sec": 60,     # 基準樣本至少橫跨多久，否則基準不可信
    "require_above_vwap": True,     # 多單需站上均價線；空單需跌破
    # v9：開盤價、或進場前的當日最低點，至少有一個要在昨收 ± 這麼多 % 以內。
    # None = 不判（v8 以前）。昨收不知道的那一檔判不出來，就不發 —— 跟均價線
    # 拿不到時一樣，不可以讓一條「以為開著」的規則無聲放行。
    "near_prev_close_pct": 1.0,
    "max_signals_per_symbol": 1,    # 同一檔一天只發一次，杜絕凹單
    "stop_loss_pct": 3.0,           # 進場價往下這麼多 %（兩條停損的其中一條；v6 起 3%）
    # 停損另外有一條結構線：區間高點下方這麼多 %。
    #
    # 原本只有 stop_loss_pct（進場價往下固定 %），而它和開盤區間完全無關。
    # 後果是：訊號發得越晚、進場價飄得越高，停損就跟著往上飄 —— 飄到突破點
    # **之上**。2026-10-02 美亞：區間高 26.70、進場 27.25、停損 26.85。
    # 那檔只要回測一下突破點（最正常不過的動作）就被掃出場，而突破在技術上
    # 根本還沒失敗。
    #
    # 「跌回區間 = 突破失敗」才是這套策略自己的前提。停損在突破點之上，
    # 等於「突破還好好的，但我先出場了」—— 那不是參數調不好，是實作沒做到
    # 它宣稱的事。
    #
    # 兩條取**較寬**的那一條（較低的停損價）。進場貼近突破點時固定 % 本來就
    # 比較低，這條不會生效；只有在追高之後才會接手，而且接手的方式是
    # 自動加大風險、減少張數 —— 系統自己踩煞車，不需要一條武斷的「不准追」。
    "stop_below_or_high_pct": 0.2,  # 區間高點往下這麼多 %（結構線）
    "reward_risk": 1.5,             # 目標 = 1.5R（v4 從 2.5R 調回）；target_pct 有設時不用
    # v8：目標 = 進場價往上「這一檔近 5 日平均日振幅」%，夾在下面這兩個數字之間。
    # 振幅由 screener.py 算好寫進 watchlist.json（avg_amplitude_pct；算不出來
    # 就用昨天一天的 amplitude_pct）。設成 False 就退回固定的 target_pct。
    "target_from_amplitude": True,
    "target_min_pct": 3.0,          # 下限：等於停損距離，再低賺得比賠得少
    "target_max_pct": 10.0,         # 上限：一天的漲跌幅上限
    # 固定 % 目標（v6/v7 是 8%）。target_from_amplitude 關掉、或這一檔完全沒有
    # 振幅資料時用它；設成 None 就再退回上面的 reward_risk。
    #
    # 只抱一天（max_hold_days=1）時目標會貼齊當天漲停 —— 超過漲停的價位當天
    # 不存在。抱兩天時**不貼齊**：今天到不了，明天的漲停線是從今天收盤重算的。
    "target_pct": 8.0,
    # 最多抱幾個交易日。1 = 當沖（13:25 平倉）；2 = 當天沒結束就留倉，
    # 隔天 13:25 還沒碰停損或目標就平倉。
    "max_hold_days": 2,
    "allow_short": False,           # 先賣後買 v1 未實作（券源、軋空風險）
    "backfill_opening_range": True, # 09:15 後才啟動時，用分鐘 K 補算開盤區間
    "market_close": "13:30:00",     # 收工時間
}

# ── ③ 風控閘門（最重要的一層，不要調鬆）──────────────────
RISK = {
    "max_signals_per_day": 3,       # 一天最多推播幾個訊號
    "max_trades_per_day": 3,        # 一天最多做幾筆
    "max_daily_loss": 12000,        # 當日實現虧損達此數字 → 系統停止發訊號（元）
    "max_consecutive_losses": 3,    # 連續虧損筆數 → 當日停手
    "per_trade_risk": 4000,         # 單筆可承受虧損（元）→ 用來反推張數
    "halt_when_pnl_unknown": True,  # 損益查不到 → 直接關閘（模擬模式不適用，見 README）
    "poll_interval_sec": 300,       # 沒有訊號時，每隔多久主動查一次損益（API 有流量上限）
}

# ── ④ 成本模型（用來驗證期望值）──────────────────────────
COST = {
    "fee_rate": 0.001425,           # 券商手續費率
    "fee_discount": 0.20,           # 你的折讓（2 折 = 0.20，務必填真實值）
    "tax_rate": 0.0015,             # 當沖證交稅減半（0.3% → 0.15%）
    # 留倉過夜就不是當沖，證交稅回到全額。來回成本從 0.207% 變 0.357%。
    "tax_rate_overnight": 0.003,
    "min_fee": 1,                   # 最低手續費
}


# ── ⑤ 台股升降單位（檔位）────────────────────────────
# 停損與目標價必須落在合法檔位上。算出 99.48 這種價位，你照著下單會被退單
# 或被自動修價 —— 真正的停損位置就不是你以為的那個了。
TICK_TABLE = ((10.0, 0.01), (50.0, 0.05), (100.0, 0.1), (500.0, 0.5), (1000.0, 1.0))
TICK_ABOVE_1000 = 5.0


def tick_size(price: float) -> float:
    """該價位的最小升降單位。"""
    for upper, tick in TICK_TABLE:
        if price < upper:
            return tick
    return TICK_ABOVE_1000


def round_to_tick(price: float, mode: str = "nearest") -> float:
    """把價格對齊到合法檔位。mode: up / down / nearest。"""
    tick = tick_size(price)
    q = price / tick
    if mode == "up":
        n = math.ceil(q - 1e-9)
    elif mode == "down":
        n = math.floor(q + 1e-9)
    else:
        n = math.floor(q + 0.5)
    return round(n * tick, 2)


# 台股單日漲跌幅上限。停損與目標都不可以落在這兩條線之外 ——
# 那不是「比較難成交」，那是一張永遠不會成交的委託。
PRICE_LIMIT_PCT = 10.0


def limit_up(prev_close: float) -> float | None:
    """當日漲停價。往**下**取合法檔位：漲停價不可以超過漲幅上限。"""
    if not prev_close or prev_close <= 0:
        return None
    return round_to_tick(prev_close * (1 + PRICE_LIMIT_PCT / 100), "down")


def near_prev_close(prev_close: float, day_open: float | None, low_so_far: float | None,
                    band_pct: float) -> str | None:
    """v9 的進場條件：開盤價或目前為止的當日最低點，有沒有一個落在昨收 ± band_pct %。

    回傳依據 —— NEAR_BY_OPEN（開盤就在附近）／NEAR_BY_PULLBACK（開高後回到附近）；
    都不成立、或昨收不知道就回 None。開盤價優先：兩個都成立時講開盤那一個。
    0 或 None 代表那個價位不知道，不算成立。
    """
    if not prev_close or prev_close <= 0:
        return None
    lo, hi = prev_close * (1 - band_pct / 100), prev_close * (1 + band_pct / 100)
    # 檔位價跟乘出來的邊界比，差一點浮點誤差就會把剛好在邊上的那一檔擋掉。
    eps = 1e-9 * prev_close
    near = lambda p: bool(p) and lo - eps <= p <= hi + eps
    if near(day_open):
        return NEAR_BY_OPEN
    if near(low_so_far):
        return NEAR_BY_PULLBACK
    return None


NEAR_BY_OPEN = "開盤"
NEAR_BY_PULLBACK = "回落"


def limit_down(prev_close: float) -> float | None:
    """當日跌停價。往**上**取合法檔位。"""
    if not prev_close or prev_close <= 0:
        return None
    return round_to_tick(prev_close * (1 - PRICE_LIMIT_PCT / 100), "up")


def round_trip_cost_pct(overnight: bool = False) -> float:
    """來回一趟的成本（%）。策略期望值必須先跨過這條線。

    overnight=True：隔天才賣，不是當沖，證交稅是全額。
    """
    fee = COST["fee_rate"] * COST["fee_discount"] * 2
    tax = COST["tax_rate_overnight"] if overnight else COST["tax_rate"]
    return (fee + tax) * 100


def push_enabled() -> bool:
    """推播該不該真的送出去。

    2026-09-29：使用者跑一次 `python test_daytrade.py`，手機收到 5 則「今日停手」，
    其中一則寫著「原因：測試」。RiskGate._close() 直接呼叫 notify()，而使用者的機器
    上 .env 有金鑰、requests 也裝了 —— 測試就真的把訊息推到他手機。CI 兩樣都沒有，
    所以這個洞從來沒在 CI 裡露出來。

    測試與 dryrun 一律不推：它們的「訊號」是假的，混進真的推播裡會讓你分不出來
    哪一則該當真。DAYTRADE_NO_PUSH 讓 dryrun.py 與任何腳本能明確關掉。
    """
    if os.environ.get("DAYTRADE_NO_PUSH"):
        return False
    # 保險絲：就算未來有人新增測試檔忘了設環境變數，也推不出去。
    if "unittest" in sys.modules or "pytest" in sys.modules:
        return False
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def _seconds(hhmmss: str) -> int:
    h, m, sec = (int(x) for x in hhmmss.split(":"))
    return h * 3600 + m * 60 + sec


def validate() -> list[str]:
    """開盤前自我檢查。回傳錯誤訊息，空清單才可以上線。

    參數打錯不會讓程式崩掉，它會安靜地算出錯的停損與張數 —— 那比崩掉更貴。
    """
    errs: list[str] = []

    if not 0 < COST["fee_discount"] <= 1:
        errs.append("COST.fee_discount 要在 0~1 之間（2 折 = 0.20）")
    if COST["fee_rate"] <= 0 or COST["tax_rate"] < 0:
        errs.append("COST.fee_rate / tax_rate 不可為負")

    s = SIGNAL
    if s["stop_loss_pct"] <= 0:
        errs.append("SIGNAL.stop_loss_pct 必須 > 0，否則停損等於進場價")
    if s.get("target_pct") is None:
        if s["reward_risk"] <= 0:
            errs.append("SIGNAL.reward_risk 必須 > 0")
    elif s["target_pct"] <= 0:
        errs.append("SIGNAL.target_pct 必須 > 0（不要用目標就設成 None，退回 reward_risk）")
    if s.get("target_from_amplitude"):
        lo, hi = s.get("target_min_pct", 0), s.get("target_max_pct", 0)
        if not 0 < lo <= hi:
            errs.append("SIGNAL.target_min_pct / target_max_pct 必須 0 < 下限 <= 上限")
    if s.get("max_hold_days", 1) not in (1, 2):
        errs.append("SIGNAL.max_hold_days 只能是 1（當沖）或 2（最多抱到隔天）—— "
                    "三天以上的追蹤沒有實作")
    if COST.get("tax_rate_overnight", 0) < COST["tax_rate"]:
        errs.append("COST.tax_rate_overnight 不可以低於當沖稅率 tax_rate")
    if s.get("near_prev_close_pct") is not None and not 0 < s["near_prev_close_pct"] < PRICE_LIMIT_PCT:
        errs.append("SIGNAL.near_prev_close_pct 必須介於 0 和漲跌幅上限之間（不要這條就設成 None）")
    if s["breakout_buffer_pct"] < 0:
        errs.append("SIGNAL.breakout_buffer_pct 不可為負")
    if s["volume_surge_ratio"] < 1:
        errs.append("SIGNAL.volume_surge_ratio < 1 等於不要求量增")
    if s["max_signals_per_symbol"] < 1:
        errs.append("SIGNAL.max_signals_per_symbol 必須 >= 1")
    if not s["or_start"] < s["or_end"] <= s["entry_window_end"] <= s["market_close"]:
        errs.append("時間順序必須是 or_start < or_end <= entry_window_end <= market_close")
    if not s["or_end"] <= s["signal_batch_at"] <= s["entry_window_end"]:
        errs.append("SIGNAL.signal_batch_at 必須落在 or_end 與 entry_window_end 之間 —— "
                    "在區間鎖定之前發不出訊號，在進場窗口關掉之後發也沒有意義")
    if (s.get("exit_signal_at") is not None
            and not s["entry_window_end"] < s["exit_signal_at"] < s["market_close"]):
        errs.append("SIGNAL.exit_signal_at 必須晚於 entry_window_end、早於 market_close"
                    "（不要提醒就設成 None）")
    # 量能倍數要算得出來，開盤到發訊號那一刻必須容得下「基準 + 現在」兩段取樣。
    # 容不下的話 volume_surge() 一律回 0.0，於是**整天發不出任何訊號，而且不報錯**。
    # v4 把進場窗口從三小時壓到三分鐘時就踩到了：原本寫死的 300 秒近期視窗
    # 一口氣吃掉全部樣本，基準那一組是空的。那種失效在畫面上和「今天沒行情」
    # 一模一樣，所以要在啟動時就擋下來。
    need = s["volume_recent_sec"] + s["volume_min_base_span_sec"]
    have = _seconds(s["signal_batch_at"]) - _seconds(s["or_start"])
    if have < need:
        errs.append(
            f"量能取樣放不進進場窗口：{s['or_start']} 到 {s['signal_batch_at']} 只有 "
            f"{have} 秒，而基準 {s['volume_min_base_span_sec']} 秒 + 現在 "
            f"{s['volume_recent_sec']} 秒要 {need} 秒。這樣 volume_surge() 一律是 "
            f"0.0，整天一個訊號都發不出來而且不會報錯。")
    if s["allow_short"]:
        errs.append("SIGNAL.allow_short=True 但 v1 沒有實作空方訊號，"
                    "打開它只會讓你以為系統在看空單。要做空請先實作 evaluate() 的空方分支。")

    r = RISK
    if s["stop_loss_pct"] > 0 and r["per_trade_risk"] <= 0:
        errs.append("RISK.per_trade_risk 必須 > 0，它是反推張數的分子")
    if r["max_signals_per_day"] < 1 or r["max_trades_per_day"] < 1:
        errs.append("RISK.max_signals_per_day / max_trades_per_day 必須 >= 1")
    if r["max_daily_loss"] <= 0:
        errs.append("RISK.max_daily_loss 必須 > 0（它是絕對值，程式會自己加負號）")
    if r["max_consecutive_losses"] < 1:
        errs.append("RISK.max_consecutive_losses 必須 >= 1")
    if r["poll_interval_sec"] < 30:
        errs.append("RISK.poll_interval_sec 太短會撞到 Shioaji 流量上限（建議 >= 60）")

    c = SCREEN
    if c["min_price"] >= c["max_price"]:
        errs.append("SCREEN.min_price 必須小於 max_price")
    if c["max_universe"] < 1:
        errs.append("SCREEN.max_universe 必須 >= 1")
    if c["lookback_days"] < 1:
        errs.append("SCREEN.lookback_days 必須 >= 1")

    return errs


def warnings() -> list[str]:
    """不致命、但你應該知道的設定互動。印出來，不擋啟動。

    紅線那條原本是**錯誤**，寫的是「日虧上限形同虛設」。那個算式錯了：
    它假設每一筆都剛好賠 per_trade_risk，但 signals.py 的 oversized 路徑
    （連一張都超過上限時，仍然給 1 張並標記）讓單筆風險可以超過上限。
    以 stop_loss_pct=1.5%、per_trade_risk=3,000 來說，股價超過 200 元的
    訊號每一筆都會超標 —— 三筆都抽到高價股就可能賠超過 3 × 3,000。
    那正是日虧上限唯一會出手的時候，所以它不是虛設，不該擋住啟動。
    """
    w, r, s = [], RISK, SIGNAL
    if r["per_trade_risk"] * r["max_trades_per_day"] < r["max_daily_loss"]:
        cap = r["per_trade_risk"] / 1000 / (s["stop_loss_pct"] / 100) if s["stop_loss_pct"] else 0
        w.append(
            f"單筆風險 {r['per_trade_risk']:,} × 最多 {r['max_trades_per_day']} 筆 "
            f"= {r['per_trade_risk'] * r['max_trades_per_day']:,} 元，低於日虧上限 "
            f"{r['max_daily_loss']:,} 元。一般情況下日虧上限不會觸發；但股價高於約 "
            f"{cap:,.0f} 元的訊號單筆風險會超標（強制 1 張），那時日虧上限就是"
            f"唯一的煞車。確認這是你要的。")
    # 價格死區：一張的風險就超過單筆上限的股票，照樣選得進來。
    # 系統減不了碼（最小單位就是一張 1,000 股），只能標 ⚠️ 超額 —— 也就是
    # 把一個你自己定的規則，變成每次都要臨場重新決定一次的事。
    if s["stop_loss_pct"] > 0:
        oversized_from = r["per_trade_risk"] / 1000 / (s["stop_loss_pct"] / 100)
        if SCREEN["max_price"] > oversized_from:
            w.append(
                f"選股價格上限 {SCREEN['max_price']:,.0f} 元，但股價超過約 "
                f"{oversized_from:,.0f} 元時，一張的停損風險就超過單筆上限 "
                f"{r['per_trade_risk']:,} 元（最小單位一張，減不了碼）。"
                f"也就是 {oversized_from:,.0f}–{SCREEN['max_price']:,.0f} 元之間的"
                f"訊號每一筆都會標超額，要不要做變成你臨場決定。"
                f"要消掉這個區間：max_price 調到 {oversized_from:,.0f} 以下，"
                f"或 per_trade_risk 調高。")
    if r["max_consecutive_losses"] >= r["max_signals_per_day"]:
        w.append(
            f"連敗停手 {r['max_consecutive_losses']} 筆 >= 當日訊號上限 "
            f"{r['max_signals_per_day']} 個 —— 要連輸 {r['max_consecutive_losses']} 筆，"
            f"得先發滿 {r['max_signals_per_day']} 個訊號，那時當日額度已經用完了，所以連敗停手"
            f"**在當日永遠不會出手**。它現在只是一個紀錄欄位。")
    return w
