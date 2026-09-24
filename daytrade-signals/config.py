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
    "lookback_days": 5,             # 量能均值回看天數
    "max_kbar_queries": 60,         # 只對前 N 名打 kbars —— API 有流量上限，超過會被停用一分鐘
    "kbar_sleep_sec": 0.3,          # 每次 kbars 之間的間隔
}

# ── ② 盤中訊號規則 ────────────────────────────────────
SIGNAL = {
    "or_start": "09:00:00",         # 開盤區間起
    "or_end": "09:15:00",           # 開盤區間迄（ORB 用）
    "entry_window_end": "12:30:00", # 這時間之後不發新訊號（尾盤流動性與回補風險）
    "breakout_buffer_pct": 0.10,    # 突破要超過區間高點多少 % 才算數（防假突破）
    "volume_surge_ratio": 1.8,      # 突破當下 5 分鐘量能速率 / 前段量能速率
    "require_above_vwap": True,     # 多單需站上均價線；空單需跌破
    "max_signals_per_symbol": 1,    # 同一檔一天只發一次，杜絕凹單
    "stop_loss_pct": 1.5,           # 建議停損（%）
    "reward_risk": 1.5,             # 目標 = 1.5R
    "allow_short": False,           # 先賣後買 v1 未實作（券源、軋空風險）
    "backfill_opening_range": True, # 09:15 後才啟動時，用分鐘 K 補算開盤區間
    "market_close": "13:30:00",     # 收工時間
}

# ── ③ 風控閘門（最重要的一層，不要調鬆）──────────────────
RISK = {
    "max_signals_per_day": 5,       # 一天最多推播幾個訊號
    "max_trades_per_day": 4,        # 一天最多做幾筆
    "max_daily_loss": 8000,         # 當日實現虧損達此數字 → 系統停止發訊號（元）
    "max_consecutive_losses": 3,    # 連續虧損筆數 → 當日停手
    "per_trade_risk": 2000,         # 單筆可承受虧損（元）→ 用來反推張數
    "halt_when_pnl_unknown": True,  # 損益查不到 → 直接關閘（模擬模式不適用，見 README）
    "poll_interval_sec": 300,       # 沒有訊號時，每隔多久主動查一次損益（API 有流量上限）
}

# ── ④ 成本模型（用來驗證期望值）──────────────────────────
COST = {
    "fee_rate": 0.001425,           # 券商手續費率
    "fee_discount": 0.20,           # 你的折讓（2 折 = 0.20，務必填真實值）
    "tax_rate": 0.0015,             # 當沖證交稅減半（0.3% → 0.15%）
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


def round_trip_cost_pct() -> float:
    """來回一趟的成本（%）。策略期望值必須先跨過這條線。"""
    fee = COST["fee_rate"] * COST["fee_discount"] * 2
    return (fee + COST["tax_rate"]) * 100


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
    if s["reward_risk"] <= 0:
        errs.append("SIGNAL.reward_risk 必須 > 0")
    if s["breakout_buffer_pct"] < 0:
        errs.append("SIGNAL.breakout_buffer_pct 不可為負")
    if s["volume_surge_ratio"] < 1:
        errs.append("SIGNAL.volume_surge_ratio < 1 等於不要求量增")
    if s["max_signals_per_symbol"] < 1:
        errs.append("SIGNAL.max_signals_per_symbol 必須 >= 1")
    if not s["or_start"] < s["or_end"] <= s["entry_window_end"] <= s["market_close"]:
        errs.append("時間順序必須是 or_start < or_end <= entry_window_end <= market_close")
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
    if r["per_trade_risk"] * r["max_trades_per_day"] < r["max_daily_loss"]:
        errs.append(
            f"紅線互相矛盾：單筆風險 {r['per_trade_risk']:,} × 最多 {r['max_trades_per_day']} 筆 "
            f"= {r['per_trade_risk'] * r['max_trades_per_day']:,} 元，"
            f"還沒到日虧上限 {r['max_daily_loss']:,} 元，日虧這條線形同虛設。")

    c = SCREEN
    if c["min_price"] >= c["max_price"]:
        errs.append("SCREEN.min_price 必須小於 max_price")
    if c["max_universe"] < 1:
        errs.append("SCREEN.max_universe 必須 >= 1")
    if c["lookback_days"] < 1:
        errs.append("SCREEN.lookback_days 必須 >= 1")

    return errs
