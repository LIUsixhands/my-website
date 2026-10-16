# -*- coding: utf-8 -*-
"""preopen.py —— 開盤前試撮，候選池 20 檔全部記下來（只記錄，不影響任何規則）。

10-16 使用者看到開盤突破研究用「今天開盤前 5 分鐘的量」挑股票，問盤前首選能不能也
這樣挑。08:45 選股時今天還沒開盤 —— 那個量還不存在。開盤前唯一看得到「今天熱不熱」
的是試撮：08:30～09:00 交易所一直試算「現在開盤會成交在哪、成交多少」。

使用者選「兩個都做」：這一支只負責把試撮記下來。歷史試撮查不到，回測不了，
只能從今天開始存；11-09 拿這十幾天回答「試撮量大的，開盤後是不是比較好」。

signals.py 本來就有記試撮方向（SymbolState.record_simtrade），但只記盯的那 10 檔、
而且只記價格方向。這裡記整個候選池（盯的 + 沒盯的），價格和量都記。

**試撮不是成交**：數字可以在 09:00 前抽單改掉，有人會故意掛假單。所以只記錄、
不當條件 —— 跟 10-08 記試撮方向是同一個約定。
"""
import json
from datetime import datetime, time as dtime

import config

OPEN_AT = dtime(9, 0)


def path_for(date: str):
    return config.JOURNAL_DIR / f"preopen-{date.replace('-', '')}.json"


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v


class PreOpenRecorder:
    """收 09:00 以前的試撮 tick。pool = 盤前存檔的列（code、name、prev_close…）。"""

    def __init__(self, pool: list[dict], watched=(), date: str | None = None):
        self.date = date or datetime.now().strftime("%Y-%m-%d")
        self.watched = {str(c) for c in watched}
        self.rows = {}
        for r in pool:
            code = str(r["code"])
            self.rows[code] = {"code": code, "name": r.get("name", ""),
                               "prev_close": _num(r.get("prev_close")),
                               "watched": code in self.watched,
                               "first_price": None, "first_at": "", "last_price": None,
                               "last_at": "", "volume": None, "total_volume": None,
                               "ups": 0, "downs": 0, "n": 0}
        self.saved = False

    @property
    def codes(self) -> list[str]:
        return list(self.rows)

    def record(self, tick) -> bool:
        """記一筆試撮。不是池子裡的、09:00 以後的（收盤集合競價也是試撮）、沒有價格的都不收。"""
        row = self.rows.get(str(getattr(tick, "code", "")))
        if row is None or not getattr(tick, "simtrade", 0):
            return False
        dt = getattr(tick, "datetime", None)
        ts = dt.time() if hasattr(dt, "time") else None
        if ts is None or ts >= OPEN_AT:
            return False
        price = _num(getattr(tick, "close", None))
        if not price or price <= 0:
            return False
        if row["first_price"] is None:
            row["first_price"], row["first_at"] = price, ts.strftime("%H:%M:%S")
        elif price > row["last_price"]:
            row["ups"] += 1
        elif price < row["last_price"]:
            row["downs"] += 1
        row["last_price"], row["last_at"] = price, ts.strftime("%H:%M:%S")
        row["volume"] = _num(getattr(tick, "volume", None))
        row["total_volume"] = _num(getattr(tick, "total_volume", None))
        row["n"] += 1
        return True

    def snapshot(self) -> dict:
        items = []
        for r in self.rows.values():
            item = dict(r)
            pc, last = r["prev_close"], r["last_price"]
            item["gap_pct"] = round((last - pc) / pc * 100, 3) if pc and last else None
            items.append(item)
        return {"date": self.date, "saved_at": datetime.now().isoformat(timespec="seconds"),
                "items": items}

    def save(self, path=None):
        """寫一次就好（第一筆真正成交進來、或主迴圈 09:01 備援）。壞掉不可以影響盯盤。"""
        if self.saved:
            return None
        self.saved = True
        path = path or path_for(self.date)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path


def load(date: str, path=None) -> dict | None:
    path = path or path_for(date)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
