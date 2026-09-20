"""
broker.py — 永豐 Shioaji 連線封裝。
注意事項（官方限制）：
  * 每 24 小時必須重新登入一次，否則會安靜地失效。
  * snapshots 一次最多 500 檔，且 API 有流量上限，超過會被停用一分鐘。
  * 行情資料只需登入；下單／帳務需要電子憑證。本系統只讀行情與帳務，不下單。
"""
import logging
import time
from datetime import datetime, timedelta

import config

# shioaji 是專有套件，測試環境不一定裝得起來。
# 這裡容許缺席，讓純邏輯（訊號、風控、稽核）可以離線測試；
# 真的要連線時才在 Broker.__init__ 擋下來。
try:
    import shioaji as sj
except ImportError:              # pragma: no cover - 取決於環境
    sj = None

log = logging.getLogger(__name__)


class Broker:
    def __init__(self, api=None):
        """api 可注入，用來離線測試這些封裝對 Shioaji 回傳格式的假設。

        注入時不登入 —— 測試不該打網路。正式使用一律不帶參數。
        """
        self._pnl_warned = False
        self._trades_warned = False
        if api is not None:
            self.api = api
            self._login_at = datetime.now()
            return
        if sj is None:
            raise RuntimeError(
                "未安裝 shioaji。請執行 pip install -r requirements.txt。"
                "（離線跑測試不需要它，但盤前／盤中／盤後三支程式都需要。）")
        self.api = sj.Shioaji(simulation=config.SIMULATION)
        self._login_at = None
        self.login()

    # ── 連線 ────────────────────────────────────────
    def login(self):
        if not config.API_KEY or not config.SECRET_KEY:
            raise RuntimeError(
                "缺少 SHIOAJI_API_KEY / SHIOAJI_SECRET_KEY。"
                f"請確認 {config.ENV_FILE.name} 存在且已填入金鑰"
                "（cp .env.template .env），或已 export 這兩個環境變數。")
        self.api.login(api_key=config.API_KEY, secret_key=config.SECRET_KEY)
        self._login_at = datetime.now()
        log.info("Shioaji 登入完成（simulation=%s）", config.SIMULATION)
        self.activate_ca()

    def activate_ca(self) -> bool | None:
        """啟用電子憑證。回傳 True/False，模擬模式或未設定則回傳 None。

        帳務查詢要憑證，而風控的日虧上限與連敗停手都建立在帳務上。
        真錢模式沒有憑證 → 查不到損益 → 閘門在第一個訊號就關閘停手。
        與其讓你盤中才發現，不如在登入時就講清楚。
        """
        if config.SIMULATION:
            return None
        if not config.CA_PATH:
            log.warning(
                "真錢模式但沒有設定 SHIOAJI_CA_PATH，帳務查詢會失敗 —— "
                "風控查不到損益會直接關閘停手。請在 .env 補上憑證設定。")
            return None
        try:
            ok = self.api.activate_ca(
                ca_path=config.CA_PATH,
                ca_passwd=config.CA_PASSWD,
                person_id=config.PERSON_ID,
            )
        except Exception as e:
            raise RuntimeError(
                f"電子憑證啟用失敗：{e}。請確認 SHIOAJI_CA_PATH 指向 e-Leader 下載的 "
                f".pfx、密碼與身分證字號正確。") from e
        if ok is False:
            raise RuntimeError(
                "電子憑證啟用被拒（activate_ca 回傳 False）。憑證可能已過期，"
                "或與這個帳號不符 —— 請在 e-Leader 重新下載。")
        log.info("電子憑證已啟用")
        return True

    def ensure_session(self):
        """超過 20 小時就重登，避免撞到 24 小時上限。"""
        if self._login_at is None or datetime.now() - self._login_at > timedelta(hours=20):
            log.warning("session 接近過期，重新登入")
            try:
                self.api.logout()
            except Exception:
                pass
            self.login()

    # ── 商品檔 ──────────────────────────────────────
    def _stocks_root(self):
        """shioaji 1.7 起 api.Contracts 已棄用（會噴 DeprecationWarning），
        改用 api.contracts。保留舊路徑以相容更早的版本。"""
        new = getattr(self.api, "contracts", None)
        if new is not None and hasattr(new, "Stocks"):
            return new.Stocks
        return self.api.Contracts.Stocks

    def stock(self, code: str):
        return self._stocks_root()[code]

    def all_stocks(self):
        """上市 + 上櫃全部股票合約。"""
        root = self._stocks_root()
        out = []
        for exch in ("TSE", "OTC"):
            group = getattr(root, exch, None)
            if group:
                out.extend(list(group))
        return out

    @staticmethod
    def day_trade_flag(contract) -> str:
        """contract.day_trade 的值（Yes / No / OnlyBuy / 未知）。"""
        dt = getattr(contract, "day_trade", None)
        if dt is None:
            return "未知"
        name = str(dt).rsplit(".", 1)[-1]
        return name if name in ("Yes", "No", "OnlyBuy") else "未知"

    def is_day_tradable(self, contract, allow_short: bool | None = None) -> bool:
        """可現股當沖？處置股／全額交割通常會是 No。

        `OnlyBuy` 是「只能先買後賣」。v1 只做多（`allow_short=False`），
        所以 OnlyBuy 完全可用 —— 原本只認 Yes 會把這一票合格標的默默篩掉。
        要做空時 OnlyBuy 就不能收，因為先賣後買在這些標的上不被允許。

        認不出來的值一律當成不可當沖（fail closed）：寧可少看幾檔，
        也不要對一檔不能當沖的股票發訊號。
        """
        if allow_short is None:
            allow_short = config.SIGNAL["allow_short"]
        flag = self.day_trade_flag(contract)
        return flag == "Yes" or (flag == "OnlyBuy" and not allow_short)

    # ── 行情 ────────────────────────────────────────
    def snapshots(self, contracts):
        """一次最多 500 檔，自動分批。"""
        out = []
        for i in range(0, len(contracts), 500):
            out.extend(self.api.snapshots(contracts[i:i + 500]))
        return out

    def kbars(self, code: str, start: str, end: str):
        return self.api.kbars(self.stock(code), start=start, end=end)

    def opening_range(self, code: str, or_start: str, or_end: str, date: str | None = None):
        """用分鐘 K 補算開盤區間高低，回傳 (high, low)；補不到回傳 None。

        signals.py 若在 09:15 之後才啟動（睡過頭、程式重開），tick 已經流過去了，
        沒有這個函式就永遠鎖不到區間 —— 整天不會發任何訊號，而且不會報錯。
        """
        date = date or datetime.now().strftime("%Y-%m-%d")
        try:
            kb = self.kbars(code, date, date)
        except Exception as e:
            log.warning("%s 開盤區間補算失敗：%s", code, e)
            return None

        highs, lows = [], []
        ts_list = list(getattr(kb, "ts", []) or [])
        hi_list = list(getattr(kb, "High", []) or [])
        lo_list = list(getattr(kb, "Low", []) or [])
        for ts, hi, lo in zip(ts_list, hi_list, lo_list):
            t = _bar_time(ts)
            # 分鐘 K 的 ts 為該分鐘的起點，故取 [or_start, or_end) 半開區間。
            if t is None or not (or_start <= t.strftime("%H:%M:%S") < or_end):
                continue
            highs.append(float(hi))
            lows.append(float(lo))

        if not highs:
            log.warning("%s 在 %s~%s 沒有分鐘 K，無法補算開盤區間", code, or_start, or_end)
            return None
        return max(highs), min(lows)

    def short_sources(self, codes):
        """借券／券源查詢，先賣後買才需要。回傳 {code: 可用張數}"""
        contracts = [self.stock(c) for c in codes]
        try:
            res = self.api.short_stock_sources(contracts)
            return {r.code: getattr(r, "short_stock_source", 0) for r in res}
        except Exception as e:
            log.warning("券源查詢失敗：%s", e)
            return {}

    # ── 帳務（風控閘門用）──────────────────────────────
    def realized_pnl_rows_today(self) -> list[float] | None:
        """當日每筆已實現損益，依 API 回傳順序。

        查不到回傳 **None，不是 0**。兩者差很多：
        0 代表「今天確實沒賺沒賠」，None 代表「不知道」。
        把不知道當成 0，日虧上限與連敗停手兩條線會同時失效 ——
        系統會在你已經虧掉三萬的那天繼續發訊號。呼叫端必須分開處理。
        """
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            acct = self.api.stock_account
            rows = self.api.list_profit_loss(acct, begin_date=today, end_date=today)
            return [float(getattr(r, "pnl", 0) or 0) for r in rows]
        except Exception as e:
            if not self._pnl_warned:
                log.warning("損益查詢失敗（風控將視為『未知』）：%s", e)
                self._pnl_warned = True
            return None

    def realized_pnl_today(self) -> float | None:
        """當日已實現損益合計。查不到回傳 None。"""
        rows = self.realized_pnl_rows_today()
        return None if rows is None else float(sum(rows))

    def trades_today(self) -> list | None:
        """當日成交明細。查不到回傳 None，不是空清單。

        實測金鑰權限不足時這裡會 401（Token doesn't have permission）。
        回傳 [] 會讓「當日交易筆數上限」這條紅線永遠不觸發 ——
        又是一條你以為開著、其實沒作用的規則。
        """
        try:
            self.api.update_status(self.api.stock_account)
            return [t for t in self.api.list_trades()]
        except Exception as e:
            if not self._trades_warned:
                log.warning("成交查詢失敗（風控將視為『未知』）：%s", e)
                self._trades_warned = True
            return None


def _bar_time(ts):
    """把 kbars 的 ts 轉成 datetime。ts 可能是 datetime、秒或奈秒 epoch。"""
    if isinstance(ts, datetime):
        return ts
    try:
        v = float(ts)
    except (TypeError, ValueError):
        return None
    # 1e11 以上視為毫秒／微秒／奈秒，逐級降到秒
    while v > 1e11:
        v /= 1000.0
    try:
        return datetime.fromtimestamp(v)
    except (OverflowError, OSError, ValueError):
        return None


def throttle(seconds: float):
    """打 API 之間的間隔。Shioaji 超流量會把你停用一分鐘，盤前 08:30 停一分鐘很貴。"""
    if seconds > 0:
        time.sleep(seconds)
