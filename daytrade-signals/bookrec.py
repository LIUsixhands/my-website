# -*- coding: utf-8 -*-
"""bookrec.py —— 五檔掛單記錄（只記錄，不影響任何訊號）。

10-22 使用者：「請想辦法可當預測，上網查」→「要，五檔掛單也開始記錄」。文獻上短線最有力的
預測因子是委買委賣的不平衡（Cont, Kukanov & Stoikov 2014：最佳一檔的 order flow imbalance
跟接下來的價格變動幾乎是直線關係）。分鐘 K 沒有掛單資料，只能從今天開始自己記，記一兩週再驗。

盯的那幾檔 + 首選，每一分鐘存一筆（label 跟分鐘 K 一樣是結束時間）：
  - 那一分鐘最後一刻的五檔（價、量）
  - 那一分鐘累計的 OFI（最佳一檔的買賣壓力變化，CKS 的定義）
  - 那一分鐘收到幾筆掛單更新
  - 10-23 加：那一分鐘的外盤／內盤張數，和其中「大單」（一筆 ≥ 300 萬元）的外盤／內盤張數
收盤後（以及盤中每 5 分鐘）寫 journal/book-YYYYMMDD.json。
"""
import json
import logging
import threading
from datetime import datetime, timedelta

import config

log = logging.getLogger("bookrec")

LEVELS = 5
SAVE_EVERY_SEC = 300
# 10-23 使用者：「當沖有需要參考主力的問題嗎」→ 盤中大單：「好」。一筆成交金額到這麼多算大單
# （台股常見的說法是 100 張或幾百萬；用金額，高價股、低價股才比得起來）。
BIG_AMOUNT = 3_000_000


def path_for(date: str):
    return config.JOURNAL_DIR / f"book-{date.replace('-', '')}.json"


def minute_label(t: datetime) -> str:
    """09:00:12 那一筆屬於 09:01 那一分鐘（跟分鐘 K 的 label 一樣是結束時間）。"""
    return (t.replace(second=0, microsecond=0) + timedelta(minutes=1)).strftime("%H:%M")


def ofi(prev, now) -> float:
    """最佳一檔的 order flow imbalance（Cont, Kukanov & Stoikov 2014）。
    prev / now = (買價, 買量, 賣價, 賣量)。正的 = 買方力量變強。"""
    pb0, qb0, pa0, qa0 = prev
    pb, qb, pa, qa = now
    return ((qb if pb >= pb0 else 0) - (qb0 if pb <= pb0 else 0)
            - (qa if pa <= pa0 else 0) + (qa0 if pa >= pa0 else 0))


def _levels(prices, volumes) -> list:
    out = []
    for p, v in list(zip(prices or [], volumes or []))[:LEVELS]:
        out.append([float(p), int(v)])
    return out


class BookRecorder:
    """on_bidask 回呼叫 record()；主迴圈叫 save_if_due()；收盤叫 save()。"""

    def __init__(self, codes, date: str | None = None, path=None):
        self.codes = {str(c) for c in codes}
        self.date = date or datetime.now().strftime("%Y-%m-%d")
        self.path = path
        self.rows: dict[str, dict[str, dict]] = {}     # 代號 → 分鐘 → 那一分鐘
        self.best: dict[str, tuple] = {}                # 代號 → 上一筆的最佳一檔
        self.lock = threading.Lock()
        self.last_save = None

    def record(self, bidask) -> None:
        """一筆五檔更新。試撮、零股、不在名單的不記；買賣任一邊是空的（漲跌停鎖死）不算 OFI。"""
        code = str(getattr(bidask, "code", ""))
        if code not in self.codes or getattr(bidask, "simtrade", 0) \
                or getattr(bidask, "intraday_odd", 0):
            return
        bid = _levels(bidask.bid_price, bidask.bid_volume)
        ask = _levels(bidask.ask_price, bidask.ask_volume)
        at = minute_label(bidask.datetime)
        with self.lock:
            row = self._row(code, at)
            row["bid"], row["ask"] = bid, ask
            row["n"] += 1
            if bid and ask and bid[0][0] > 0 and ask[0][0] > 0:
                now = (bid[0][0], bid[0][1], ask[0][0], ask[0][1])
                if code in self.best:
                    row["ofi"] += ofi(self.best[code], now)
                self.best[code] = now

    def _row(self, code: str, at: str) -> dict:
        return self.rows.setdefault(code, {}).setdefault(
            at, {"ofi": 0.0, "n": 0, "buy": 0, "sell": 0, "big_buy": 0, "big_sell": 0})

    def record_tick(self, tick) -> None:
        """一筆成交：外盤（tick_type 1）／內盤（2）張數，一筆金額 ≥ BIG_AMOUNT 的另外算大單。
        判不出方向的（0）、試撮、零股、不在名單的不記。"""
        code = str(getattr(tick, "code", ""))
        if code not in self.codes or getattr(tick, "simtrade", 0) or getattr(tick, "intraday_odd", 0):
            return
        lots = int(getattr(tick, "volume", 0) or 0)
        kind = int(getattr(tick, "tick_type", 0) or 0)
        if lots <= 0 or kind not in (1, 2):
            return
        side = "buy" if kind == 1 else "sell"
        big = float(getattr(tick, "close", 0) or 0) * lots * 1000 >= BIG_AMOUNT
        with self.lock:
            row = self._row(code, minute_label(tick.datetime))
            row[side] += lots
            if big:
                row["big_" + side] += lots

    def payload(self) -> dict:
        with self.lock:
            return {"date": self.date,
                    "codes": {c: [dict(at=k, **v) for k, v in sorted(m.items())]
                              for c, m in sorted(self.rows.items())}}

    def save(self, now: datetime | None = None):
        """寫檔。還沒收到任何掛單就不寫。回傳路徑。"""
        data = self.payload()
        if not data["codes"]:
            return None
        path = self.path or path_for(self.date)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        self.last_save = now or datetime.now()
        return path

    def save_if_due(self, now: datetime | None = None):
        now = now or datetime.now()
        if self.last_save and (now - self.last_save).total_seconds() < SAVE_EVERY_SEC:
            return None
        return self.save(now)
