# -*- coding: utf-8 -*-
"""exits.py —— v10 的六條出場規則。盤中（signals.LiveTracker 看 tick）與收盤回推
（outcome.resolve 看分鐘 K）共用**同一份**判斷，兩邊算出來的才對得起來。

使用者 10-08 貼的六條，選「直接改成新規則（v10）」，四個數字也是使用者選的：

  1. 進場理由消失就出：跌回開盤區間高點以下、或跌破均價線（各留 0.2% 緩衝）。
     **那一分鐘收在線下才算**（10-08 晚，使用者選「現在就改」）：開盤後半小時
     上下震盪，單一筆擦過去就出的話，跳空開高的股票幾乎每一筆都會在幾分鐘內
     被洗掉。出場價 = 那一分鐘的收盤價
  2. 虧損達到設定金額就出：硬停損。張數本來就是用單筆 4,000 元反推的
  3. 漲到目標的一半先出一半；剩下的從最高點回落 1.5% 出，不低於成本
     （只有 1 張分不了：整張改移動停利）
  4. 跌破當日開盤價就出（進場前就定好，寫在訊號上）—— 同樣「那一分鐘收在下面才算」
  5. 量能萎縮就出：拿**進場後的前 10 分鐘**當基準（10-08 晚改；原本拿進場前的
     平均量，裡面有開盤爆量，基準偏高、太容易「不到一半」）。進場 20 分鐘後開始判：
     最近 10 分鐘的量不到基準的一半，而且這 10 分鐘價格上下不到 1%
  6. 13:25 全部平倉，不留倉

碰到就出的：停損、先出一半、移動停利（tick 一到就判）。
收盤才算的：開盤價、跌回區間、均價線（每一分鐘結束時用那一分鐘的收盤判）。
同一分鐘裡好幾條都成立：停損 → 先出一半 → 移動停利 → 開盤價 → 跌回區間 →
均價線 → 量縮。

盤中 tick 與收盤分鐘 K 的「一分鐘」要對得起來：訊號那一刻所在的那一分鐘不判
（分鐘 K 那一根裡有訊號前的成交），從下一個完整的一分鐘開始。

分鐘 K 一根裡看不出先後，所以同一根先碰到「先出一半」的，那一根不再拿來判
移動停利 —— 不知道低點是在高點之前還是之後，兩邊都不假設。
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import config

# 出場原因。舊的「停損／目標／收盤平倉」在 outcome.py，這裡沿用同樣的字。
STOP = "停損"
FLAT = "收盤平倉"
BELOW_OPEN = "跌破開盤價"
BACK_IN_RANGE = "跌回區間"
BELOW_VWAP = "跌破均價線"
TRAIL = "移動停利"
VOLUME_DRY = "量縮"
HALF = "先出一半"

V10 = 10        # 訊號上記 exit_rules = 10，表示這一筆照 v10 的六條出場


def plan_fields(entry: float, stop: float, target: float, *, day_open: float | None,
                total_volume: int | None, minutes_since_open: float | None) -> dict:
    """發訊號時要一起記在訊號上的出場計畫。記在訊號上、不是收盤時再去看 config ——
    隔天拿新版程式回推舊訊號，也要照**當時**的規則走。"""
    cfg = config.SIGNAL
    half_at = config.round_to_tick(entry + (target - entry) * cfg["exit_half_fraction"], "up")
    return {
        "exit_rules": V10,
        "key_level": day_open or None,
        "half_at": half_at,
        "trail_pct": cfg["exit_trail_pct"],
        "reason_buffer_pct": cfg["exit_reason_buffer_pct"],
        "vol_window_min": cfg["exit_vol_window_min"],
        "vol_ratio": cfg["exit_vol_ratio"],
        "flat_pct": cfg["exit_flat_pct"],
        "confirm": "minute_close",                # 理由消失那幾條：一分鐘收盤確認
        "vol_base": "after_entry",                # 量縮基準：進場後前 N 分鐘
        "entry_cum_volume": total_volume or None,  # 量縮從進場那一刻開始算
    }


def below(line: float) -> float:
    """嚴格低於 line 的第一個合法檔位 —— 「跌破」那條線時，真的會成交到的價格。"""
    p = config.round_to_tick(line, "down")
    if p >= line - 1e-9:
        p = round(p - config.tick_size(p - 1e-6), 2)
    return p


def uses_v10(sig: dict) -> bool:
    try:
        return int(sig.get("exit_rules") or 0) >= V10
    except (TypeError, ValueError):
        return False


def _num(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


@dataclass
class Position:
    entry: float
    stop: float
    target: float
    lots: int
    half_at: float
    entered: datetime
    key_level: float | None = None
    or_high: float | None = None
    trail_pct: float = 1.5
    reason_buffer_pct: float = 0.2
    vol_window_min: float = 10
    vol_ratio: float = 0.5
    flat_pct: float = 1.0
    base_per_min: float | None = None    # 進場後前 N 分鐘的每分鐘量；到時間才算得出來
    entry_cum: float | None = None       # 進場那一刻的累計量
    # 走的過程
    half_done: bool = False
    half_price: float | None = None
    half_time: datetime | None = None
    peak: float = 0.0
    done: bool = False
    samples: list = field(default_factory=list)    # (時間, 累計量, 高, 低)
    # 正在走的那一分鐘：(那一分鐘的起點, 最後一筆價, 當時的均價線)
    bucket: tuple | None = None

    @classmethod
    def from_signal(cls, sig: dict, entered: datetime) -> "Position":
        entry = float(sig["entry"])
        return cls(
            entry=entry, stop=float(sig["stop"]), target=float(sig["target"]),
            lots=int(_num(sig.get("lots")) or 0), half_at=float(sig["half_at"]),
            entered=entered, key_level=_num(sig.get("key_level")),
            or_high=_num(sig.get("or_high")),
            trail_pct=float(sig.get("trail_pct") or 1.5),
            reason_buffer_pct=float(sig.get("reason_buffer_pct") or 0.0),
            vol_window_min=float(sig.get("vol_window_min") or 10),
            vol_ratio=float(sig.get("vol_ratio") or 0.5),
            flat_pct=float(sig.get("flat_pct") or 1.0),
            entry_cum=_num(sig.get("entry_cum_volume")),
            peak=entry)

    # ── 可以分批嗎 ────────────────────────────────
    @property
    def half_lots(self) -> int:
        """先出幾張。1 張分不了 → 0（整張改移動停利）。"""
        return self.lots // 2 if self.lots >= 2 else 0

    @property
    def trailing(self) -> bool:
        return self.half_done

    def trail_line(self) -> float:
        """最高點回落 trail_pct 的那個價位，往下取合法檔位（回落「到」1.5% 才算，
        第一個成交得到的價位在它下面）；不低於成本。"""
        line = config.round_to_tick(self.peak * (1 - self.trail_pct / 100), "down")
        return max(self.entry, line)

    def range_line(self) -> float | None:
        if not self.or_high:
            return None
        return self.or_high * (1 - self.reason_buffer_pct / 100)

    def vwap_line(self, vwap: float | None) -> float | None:
        if not vwap:
            return None
        return vwap * (1 - self.reason_buffer_pct / 100)

    # ── 一步 ──────────────────────────────────────
    def _reason_gone(self, close: float, vwap: float | None):
        """一分鐘收盤時，進場理由還在嗎。不在 → (原因, 出場價 = 那一分鐘的收盤)。"""
        if self.key_level and close < self.key_level:
            return BELOW_OPEN, close
        line = self.range_line()
        if line is not None and close < line:
            return BACK_IN_RANGE, close
        line = self.vwap_line(vwap)
        if line is not None and close < line:
            return BELOW_VWAP, close
        return None

    def step(self, now: datetime, high: float, low: float, last: float,
             vwap: float | None = None, cum_volume: float | None = None,
             bar: bool = False) -> list[tuple]:
        """往前走一步。

        bar=False：一筆 tick（high = low = last）。理由消失那幾條要等這一分鐘結束 ——
        下一分鐘的第一筆 tick 進來時，拿上一分鐘的最後一筆價（＝收盤）判。
        bar=True ：一根已經收完的分鐘 K（高低收），那一根的收盤直接判。

        回傳事件清單：("half", 價格) 與／或 ("exit", 原因, 價格)。出場之後不再有事件。
        """
        if self.done:
            return []
        events = []

        def out(reason, price):
            self.done = True
            events.append(("exit", reason, round(price, 2)))
            return events

        # 上一分鐘收完了嗎（tick 模式）。訊號那一分鐘（起點早於進場）不判。
        if not bar:
            minute = now.replace(second=0, microsecond=0)
            if self.bucket and minute > self.bucket[0]:
                start, close, v = self.bucket
                self.bucket = None
                if start >= self.entered:
                    gone = self._reason_gone(close, v)
                    if gone:
                        return out(*gone)
            self.bucket = (minute, last, vwap if vwap else (self.bucket[2] if self.bucket else None))

        # 碰到就出
        if low <= self.stop:
            return out(STOP, self.stop)
        just_halved = False
        if not self.half_done and high >= self.half_at:
            self.half_done, self.half_price, self.half_time = True, self.half_at, now
            self.peak = max(self.peak, self.half_at)
            events.append(("half", self.half_at))
            just_halved = True
        elif self.trailing:
            line = self.trail_line()
            if low <= line:
                return out(TRAIL, line)
        if self.trailing and not just_halved:
            self.peak = max(self.peak, high)

        # 分鐘 K 模式：這一根的收盤
        if bar:
            gone = self._reason_gone(last, vwap)
            if gone:
                return out(*gone)

        # 量縮（要有量的資料才判）
        if cum_volume is not None:
            if self.entry_cum is None:
                self.entry_cum = float(cum_volume)
            window = timedelta(minutes=self.vol_window_min)
            if self.base_per_min is None and now - self.entered >= window:
                self.base_per_min = max(0.0, (float(cum_volume) - self.entry_cum)
                                        / self.vol_window_min)
            self.samples.append((now, float(cum_volume), high, low))
            cutoff = now - window
            # 只留窗口內的，加上窗口起點之前的最後一筆（當作起點的累計量）
            older = [x for x in self.samples if x[0] <= cutoff]
            recent = [x for x in self.samples if x[0] > cutoff]
            self.samples = older[-1:] + recent
            if self.base_per_min and older and now - self.entered >= 2 * window:
                volume = self.samples[-1][1] - older[-1][1]
                # 價格範圍含窗口起點那一筆：報價稀疏時，起點的價格就是「10 分鐘前在哪」
                hi = max(x[2] for x in self.samples)
                lo = min(x[3] for x in self.samples)
                flat = (hi - lo) / self.entry * 100 <= self.flat_pct
                if volume < self.vol_ratio * self.base_per_min * self.vol_window_min and flat:
                    return out(VOLUME_DRY, last)
        return events

    def flatten(self, last: float) -> list[tuple]:
        if self.done:
            return []
        self.done = True
        return [("exit", FLAT, round(last, 2))]


def blended(entry: float, stop: float, lots: int, half_price: float | None,
            exit_price: float, half_lots: int | None = None) -> tuple[float, float]:
    """兩段出場合起來的 (報酬 %, R)。沒有先出一半就是單一段。

    權重用張數：5 張先出 2 張、剩 3 張。張數不知道（舊紀錄）就各算一半。
    """
    risk = entry - stop
    if half_price is None:
        pct = (exit_price - entry) / entry * 100
        return pct, ((exit_price - entry) / risk if risk > 0 else 0.0)
    if lots and lots >= 2:
        h = half_lots if half_lots is not None else lots // 2
        w_half = h / lots
    elif lots == 1:
        w_half = 0.0             # 1 張分不了，「先出一半」那一刻沒有賣
    else:
        w_half = 0.5
    avg = w_half * half_price + (1 - w_half) * exit_price
    pct = (avg - entry) / entry * 100
    return pct, ((avg - entry) / risk if risk > 0 else 0.0)
