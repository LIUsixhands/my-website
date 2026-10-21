# -*- coding: utf-8 -*-
"""pickpulse.py —— 盤前首選開盤後的強弱監看（09:05～13:10）。

10-21 使用者：「盤前那一檔，9:00 推播後，我想繼續推播，直到 13 點 10 分結束」→「強弱續抱及出場，
我自己判斷，但你要給我判斷指標」→ 六個指標各給 1～10 分、平均分配一個名稱 →「一定要固定時間推嗎？
可否依強弱程度給我訊號」→ 強弱變兩級以上才推，60 分鐘沒推就補一則，13:10 總結。

只給數字，不講該抱該賣（出場由使用者自己判斷）。系統背後照樣記「首選本身」和「均線版」的規則成績。
六項一樣重 —— 哪一項比較重要現在沒有資料可以證明；每一次打分都存起來，11-09 拿來看
「分數高的時候，後面是不是真的比較常漲」，再調。

每根 5 分 K 收完打一次分（跟均線版同一把 5 分 K）：
  ① 價格 vs 均價線      低 1% → 1 分、平 → 5 分、高 1% → 10 分
  ② 價格 vs 5 分 K 20MA  同上
  ③ 5MA vs 20MA          ±0.5% 封頂
  ④ 量價（近 30 分鐘）    5 + 2.5 × 漲跌方向 × 量比（量比最多算 2 倍）
  ⑤ 外盤比例（近 30 分鐘） 30% → 1、50% → 5、70% → 10
  ⑥ 大盤（以 0050 代表）vs 開盤價  ±0.5% 封頂
缺資料的那一項不算進平均。
"""
import json
import logging
from datetime import datetime, time as dtime, timedelta

import config

log = logging.getLogger("pickpulse")

END_AT = dtime(13, 10)
WINDOW_MIN = 30          # ④⑤ 看最近幾分鐘
MIN_GAP_MIN = 10         # 兩則之間至少隔幾分鐘
HEARTBEAT_MIN = 60       # 這麼久沒推就補一則
STEP_TO_PUSH = 2         # 名稱變幾級才推

LEVELS = ((8.5, "強勢"), (7.5, "偏強"), (6.5, "稍強"), (5.5, "中性偏強"), (4.5, "中性"),
          (3.5, "中性偏弱"), (2.5, "稍弱"), (1.5, "偏弱"), (float("-inf"), "弱勢"))
ITEMS = ("vwap", "ma20", "ma_gap", "volume", "buy", "market")


def level(score: float) -> tuple[int, str]:
    """(級數 0＝弱勢 … 8＝強勢, 名稱)。"""
    for n, (floor, name) in enumerate(LEVELS):
        if score >= floor:
            return len(LEVELS) - 1 - n, name
    return 0, LEVELS[-1][1]


def lin(diff_pct: float, neg: float, pos: float) -> float:
    """差幾 % → 1～10 分：-neg% 以下 1 分、0 是 5 分、+pos% 以上 10 分，中間照比例。"""
    if diff_pct <= -neg:
        return 1.0
    if diff_pct >= pos:
        return 10.0
    return 5.0 + (4.0 * diff_pct / neg if diff_pct < 0 else 5.0 * diff_pct / pos)


def _pct(a, b) -> float | None:
    return (a - b) / b * 100 if a and b else None


def _hi_lo(d: float) -> str:
    return f"{'高' if d >= 0 else '低'} {abs(d):.1f}%"


def score_items(price, vwap, ma5, ma20, vol_ratio, direction, buy_pct, market_pct) -> dict:
    """{項目: (說明, 分數或 None)}。缺資料 → None，不算進平均。"""
    out = {}
    d = _pct(price, vwap)
    out["vwap"] = (f"均價線 {vwap:.2f}：{_hi_lo(d)}", lin(d, 1, 1)) if d is not None \
        else ("均價線：資料不足", None)
    d = _pct(price, ma20)
    out["ma20"] = (f"20MA {ma20:.2f}：{_hi_lo(d)}", lin(d, 1, 1)) if d is not None \
        else ("20MA：資料不足", None)
    d = _pct(ma5, ma20)
    out["ma_gap"] = (f"5MA 比 20MA {_hi_lo(d)}", lin(d, 0.5, 0.5)) if d is not None \
        else ("5MA／20MA：資料不足", None)
    if vol_ratio is None or direction is None:
        out["volume"] = ("量：資料不足", None)
    else:
        word = "上漲" if direction > 0 else "下跌" if direction < 0 else "持平"
        s = min(10.0, max(1.0, 5.0 + 2.5 * direction * min(vol_ratio, 2.0)))
        out["volume"] = (f"量 {vol_ratio:.1f} 倍、近 {WINDOW_MIN} 分鐘{word}", s)
    out["buy"] = (f"外盤 {buy_pct:.0f}%", lin(buy_pct - 50, 20, 20)) if buy_pct is not None \
        else ("外盤：資料不足", None)
    out["market"] = (f"大盤（以 0050 代表）{market_pct:+.1f}%", lin(market_pct, 0.5, 0.5)) \
        if market_pct is not None else ("大盤：資料抓不到", None)
    return out


def average(items: dict) -> float | None:
    vals = [s for _t, s in items.values() if s is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def path_for(date: str):
    return config.JOURNAL_DIR / f"pulse-{date.replace('-', '')}.json"


class Pulse:
    """首選的強弱監看。PickWatch 每根 5 分 K 收完叫 on_bar，主迴圈叫 on_clock（13:10 總結）。"""

    def __init__(self, sig: dict | None = None, market=None, date: str | None = None,
                 store=None):
        self.sig = sig
        self.market = market or (lambda: None)
        self.store = store           # store(date, code, history)：盤中才給（測試不寫檔）
        self.date = date or datetime.now().strftime("%Y-%m-%d")
        self.samples = []            # (時間, 價格, 總量, 外盤, 內盤)
        self.history = []            # 每一次打分
        self.pushed = None           # 上一次推的 {at, lv, score, label}
        self.summarized = False

    def start(self, sig: dict, st, now: datetime) -> None:
        """首選進場那一刻：記下起點（④⑤ 的「30 分鐘前」在開盤前 30 分鐘還不存在時用它）。"""
        self.sig = sig
        self.samples = [(now, float(sig["entry"]), 0, 0, 0)]

    def _window(self, now: datetime):
        ago = now - timedelta(minutes=WINDOW_MIN)
        base = None
        for s in self.samples:
            if s[0] <= ago:
                base = s
        return base or self.samples[0]

    def on_bar(self, st, done, now: datetime, status: str = "") -> list[str]:
        """一根 5 分 K 收完。done = (結束時間, 收盤, 5MA, 20MA, 往下穿過)。"""
        if not self.sig or not self.samples or now.time() > END_AT or not st.last_price:
            return []
        end, _close, ma5, ma20, _cross = done
        price = float(st.last_price)
        base = self._window(end)
        minutes = max(1.0, (end - base[0]).total_seconds() / 60)
        since_open = max(1.0, (end - self.samples[0][0]).total_seconds() / 60)
        vol = st.total_volume - base[2]
        avg = st.total_volume / since_open * minutes if st.total_volume else 0
        ratio = round(vol / avg, 2) if avg else None
        move = price - base[1]
        direction = (move > 0) - (move < 0)
        buys, sells = st.aggressive_buy - base[3], st.aggressive_sell - base[4]
        buy_pct = buys / (buys + sells) * 100 if buys + sells > 0 else None
        try:
            market = self.market()
        except Exception as e:
            log.warning("大盤抓不到（不影響盯盤）：%s", e)
            market = None
        items = score_items(price, st.vwap or None, ma5, ma20, ratio, direction, buy_pct, market)
        score = average(items)
        self.samples.append((end, price, st.total_volume, st.aggressive_buy, st.aggressive_sell))
        if score is None:
            return []
        lv, name = level(score)
        self.history.append({"at": end.strftime("%H:%M"), "price": price, "score": score,
                             "label": name, **{k: items[k][1] for k in ITEMS}})
        self._save()
        kind, before = None, self.pushed
        if before is None:
            kind = "start"
        else:
            gap = (now - before["at"]).total_seconds() / 60
            if abs(lv - before["lv"]) >= STEP_TO_PUSH and gap >= MIN_GAP_MIN:
                kind = "change"
            elif gap >= HEARTBEAT_MIN:
                kind = "quiet"
        if kind is None:
            return []
        self.pushed = {"at": now, "lv": lv, "score": score, "label": name}
        return [self._message(kind, st, items, score, name, before, end, status)]

    def _message(self, kind, st, items, score, name, before, at, status) -> str:
        sig = self.sig
        label = f"{sig['code']} {sig.get('name', '')}".split("・")[0].strip()
        price, entry, stop = float(st.last_price), float(sig["entry"]), float(sig["stop"])
        if kind == "start":
            head = [f"🌅 {label}・首選強弱｜{at:%H:%M}", f"開始：{name}（{score:.1f} 分）"]
        elif kind == "change":
            arrow = "↑" if score > before["score"] else "↓"
            head = [f"🌅 {label}・首選強弱變化｜{at:%H:%M}",
                    f"{before['label']} → {name} {arrow}（{before['score']:.1f} → {score:.1f} 分）"]
        else:
            head = [f"🌅 {label}・首選強弱｜{at:%H:%M}",
                    f"目前：{name}（{score:.1f} 分），{HEARTBEAT_MIN} 分鐘沒有明顯變化"]
        lines = head + ["────────────────",
                        f"現價 {price:.2f}｜進場 {entry:.2f}（{(price - entry) / entry * 100:+.2f}%）"]
        if st.day_high:
            lines.append(f"今天最高 {st.day_high:.2f}，已回落 {(price - st.day_high) / st.day_high * 100:+.1f}%")
        lines.append("────────────────")
        for n, k in enumerate(ITEMS):
            text, s = items[k]
            lines.append(f"{'①②③④⑤⑥'[n]} {text}" + (f"　{round(s)} 分" if s is not None else ""))
        lines += ["────────────────", f"平均 {score:.1f} 分：{name}（六項一樣重，未驗證）"]
        lines.append(f"停損 {stop:.2f}（還差 {(stop - price) / price * 100:+.1f}%）" if price > stop
                     else f"停損 {stop:.2f}（已經跌破）")
        if status:
            lines.append(status)
        return "\n".join(lines)

    def summary(self, st, now: datetime, status: str = "") -> list[str]:
        """13:10 總結一次。沒進場（或還沒打過分）就不推。"""
        if self.summarized or not self.sig or not st or not st.last_price:
            return []
        self.summarized = True
        sig = self.sig
        label = f"{sig['code']} {sig.get('name', '')}".split("・")[0].strip()
        price, entry = float(st.last_price), float(sig["entry"])
        lines = [f"🌅 {label}・首選今日總結｜{now:%H:%M}",
                 f"現價 {price:.2f}｜進場 {entry:.2f}（{(price - entry) / entry * 100:+.2f}%）",
                 f"開 {st.day_open or entry:.2f}｜高 {st.day_high:.2f}｜低 {st.day_low:.2f}",
                 "────────────────", "分數變化（每 30 分鐘一筆）："]
        marks = [h for h in self.history if h["at"].endswith((":00", ":30")) or h is self.history[0]]
        for h in marks or self.history:
            lines.append(f"{h['at']} {h['score']:.1f} {h['label']}")
        lines.append("────────────────")
        if status:
            lines.append(status)
        lines.append("13:25 還沒出場的會全部平倉。")
        return ["\n".join(lines)]

    def _save(self) -> None:
        if self.store is None:
            return
        try:
            self.store(self.date, self.sig.get("code"), self.history)
        except Exception as e:                      # 存不進去不可以影響盯盤
            log.warning("強弱紀錄寫不進去：%s", e)


def save_history(date: str, code, history: list, path=None) -> None:
    """每一次打分都存（journal/pulse-YYYYMMDD.json），11-09 拿來驗證分數有沒有用。"""
    path = path or path_for(date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": date, "code": code, "history": history},
                               ensure_ascii=False, indent=2), encoding="utf-8")


def market_change(broker, date: str | None = None) -> float | None:
    """大盤（以 0050 代表）現在比開盤價漲跌幾 %。抓不到回 None。"""
    import outcome as oc
    from broker import Broker
    date = date or datetime.now().strftime("%Y-%m-%d")
    bars = oc.day_bars_ohlcv(broker, Broker.MARKET_PROXY, date)
    if not bars or not bars[0][1]:
        return None
    return round((bars[-1][4] - bars[0][1]) / bars[0][1] * 100, 2)
