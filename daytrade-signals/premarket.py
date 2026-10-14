# -*- coding: utf-8 -*-
"""premarket.py —— 08:45 盤前首選：候選池 20 檔裡挑一檔，09:00 開盤價買進。

10-13 使用者：「改為監測 20 檔，不用給 20 檔監測訊號，8:45 給這 20 檔其中一檔的
訊號，此訊號綜合研判，勝率最高的一檔。其他不變。」接著選了：
  - 20 檔只給首選用（盤中 v10 照舊盯前 10 檔 —— v10 的 20 天不用重來）
  - 09:00 開盤價買進
  - 透明加權分數
  - 出場照 v10（停損、先出一半＋移動停利、跌破開盤價、跌破均價線、量縮、13:25）

**「勝率最高」現在算不出來** —— 那要先有幾十筆紀錄證明哪些條件真的提高勝率。
所以這裡是一條寫明的公式，訊息上寫「盤前首選（未驗證）」，不寫勝率最高。
跟 v10 的突破訊號**分開記錄**（picks.csv）、不佔每日 3 個額度、不進風控閘門。
11-09 兩套放在一起比。

分數：候選池每一檔，四項各自排名（1 = 最好），名次加總，總分最低的那一檔：
  1. 量比                    越高越好（昨天的量是平常的幾倍）
  2. 近 5 日平均振幅         越高越好（當沖要有波動才有空間）
  3. 日線 RSI 離 60 多遠      越近越好（50～70 最好；太高是過熱，太低是弱勢）
  4. 昨收在昨天高低的哪裡     越接近高點越好（收在高點 = 收盤前還有人在買）
平手看量比，再平手看候選池裡的名次。缺資料的那一項排最後。

開盤價買進：跌回區間那一條不適用（沒有開盤區間）；「跌破開盤價」那一條等於
「那一分鐘收在進場價底下就出」，會比 v10 的突破訊號出得快。停損只用固定 3%
（沒有區間高，結構線不存在）。
"""
import csv
import logging
from datetime import datetime, time as dtime

import config

log = logging.getLogger("premarket")

PICK_AT = dtime(8, 45)          # 推播時間
ENTRY_AT = dtime(9, 0)          # 開盤價買進
RSI_SWEET = 60.0                # 日線 RSI 最好的位置（50～70 的中間）
LABEL = "盤前首選"
PICKS_FILE = config.BASE_DIR / "picks.csv"

FACTORS = (
    ("量比", "volume_ratio"),
    ("振幅", "amplitude"),
    ("RSI", "rsi_gap"),
    ("收盤位置", "close_pos"),
)
_HIGHER_BETTER = {"volume_ratio": True, "amplitude": True,
                  "rsi_gap": False, "close_pos": True}


def _num(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def features(row: dict) -> dict:
    """一檔候選的四個數字。算不出來的是 None。"""
    rsi = _num(row.get("daily_rsi"))
    hi, lo, close = _num(row.get("prev_high")), _num(row.get("prev_low")), _num(row.get("prev_close"))
    pos = None
    if hi is not None and lo is not None and close is not None and hi > lo:
        pos = round((close - lo) / (hi - lo) * 100, 1)
    return {
        "volume_ratio": _num(row.get("volume_ratio")),
        "amplitude": _num(row.get("avg_amplitude_pct")) or _num(row.get("amplitude_pct")),
        "rsi": rsi,
        "rsi_gap": abs(rsi - RSI_SWEET) if rsi is not None else None,
        "close_pos": pos,
    }


def _ranks(values: list, higher_better: bool) -> list[int]:
    """名次：1 = 最好；同分同名次；None 排最後（名次 = 總檔數）。"""
    n = len(values)
    out = []
    for v in values:
        if v is None:
            out.append(n)
        else:
            # 同分同名次：比它好的有幾個 + 1
            out.append(1 + sum(1 for x in values if x is not None and
                               (x > v if higher_better else x < v)))
    return out


def score(pool: list[dict]) -> list[dict]:
    """候選池每一檔的四項名次與總分，照總分排好（第一個就是首選）。"""
    feats = [features(r) for r in pool]
    ranks = {key: _ranks([f[key] for f in feats], _HIGHER_BETTER[key])
             for _, key in FACTORS}
    scored = []
    for i, (row, f) in enumerate(zip(pool, feats)):
        r = {key: ranks[key][i] for _, key in FACTORS}
        scored.append({"code": str(row["code"]), "name": row.get("name", ""),
                       "pool_rank": i + 1, "row": row, "features": f, "ranks": r,
                       "total": sum(r.values())})
    scored.sort(key=lambda s: (s["total"], -(s["features"]["volume_ratio"] or 0),
                               s["pool_rank"]))
    return scored


def choose(pool: list[dict], watched=()) -> dict | None:
    """寫進 watchlist.json 的 pick 欄位。候選池是空的就沒有首選。
    watched = 盤中 v10 也在盯的那幾檔代號（只是記下來，不影響選誰）。"""
    if not pool:
        return None
    ranked = score(pool)
    top = ranked[0]
    row = top["row"]
    return {
        "code": top["code"],
        "name": top["name"],
        "prev_close": float(row["prev_close"]),
        "amplitude_pct": _num(row.get("avg_amplitude_pct")) or _num(row.get("amplitude_pct")),
        "category": str(row.get("category", "") or ""),
        "pool_size": len(pool),
        "pool_rank": top["pool_rank"],
        "watched": top["code"] in {str(c) for c in watched},
        "features": top["features"],
        "ranks": top["ranks"],
        "total": top["total"],
        "runners_up": [{"code": s["code"], "name": s["name"], "total": s["total"]}
                       for s in ranked[1:3]],
    }


def _f(v, fmt):
    return "—" if v is None else format(v, fmt)


def format_pick(pick: dict | None, date: str) -> str:
    """08:45 推的那一則。"""
    if not pick:
        return (f"🌅 {date} {LABEL}\n────────────────\n"
                "今天候選池是空的，沒有首選。")
    f, r = pick["features"], pick["ranks"]
    label = f"{pick['code']} {pick.get('name', '')}".strip()
    half_pct = None
    amp = pick.get("amplitude_pct")
    if amp:
        lo, hi = config.SIGNAL["target_min_pct"], config.SIGNAL["target_max_pct"]
        half_pct = min(max(amp, lo), hi) * config.SIGNAL["exit_half_fraction"]
    others = "、".join(f"{s['code']} {s.get('name', '')}".strip() + f"（{s['total']}）"
                      for s in pick.get("runners_up", []))
    lines = [
        f"🌅 {date} {LABEL}（未驗證）",
        "────────────────",
        label,
        f"{ENTRY_AT:%H:%M} 開盤價買進，{_flatten_at():%H:%M} 前出場",
        f"昨收 {pick['prev_close']:.2f}｜量比 {_f(f['volume_ratio'], '.2f')}x"
        f"｜近 5 日振幅 {_f(f['amplitude'], '.1f')}%",
        f"日線 RSI {_f(f['rsi'], '.0f')}｜昨收在昨天高低的 {_f(f['close_pos'], '.0f')}% 位置",
        "────────────────",
        f"怎麼選的：候選池 {pick['pool_size']} 檔，四項各自排名後加總，總分最低的那一檔",
        f"量比第 {r['volume_ratio']}｜振幅第 {r['amplitude']}｜RSI 第 {r['rsi_gap']}"
        f"｜收盤位置第 {r['close_pos']} → 總分 {pick['total']}",
    ]
    if others:
        lines.append(f"次佳：{others}")
    lines += [
        "────────────────",
        f"停損：開盤價 -{config.SIGNAL['stop_loss_pct']:g}%"
        + (f"｜先出一半：開盤價 +{half_pct:.1f}%" if half_pct else ""),
        "其餘照 v10 出場。開盤後會再推一次實際價格。",
        "────────────────",
        "盤前就選的，沒有經過驗證；跟盤中突破訊號分開記錄，不佔每日 3 個額度。",
        "驗證期不下單。",
    ]
    return "\n".join(lines)


def wait_until(at: dtime, now=None, sleep=None, earliest: dtime = dtime(8, 0)) -> float:
    """排程 08:40 跑的選股通常 08:42 就跑完 —— 等到 08:45 再推首選。
    手動在別的時間跑（測試、晚開）不等。回傳等了幾秒。"""
    import time as _time
    now = now or datetime.now()
    if not (earliest <= now.time() < at):
        return 0.0
    wait = (datetime.combine(now.date(), at) - now).total_seconds()
    (sleep or _time.sleep)(wait)
    return wait


def _flatten_at():
    import outcome
    return outcome.FLATTEN_AT


def plan(pick: dict, entry: float, now: dtime | None = None) -> dict | None:
    """開盤價進場的停損、目標、張數、六條出場 —— 跟盤中訊號同一個函式。
    開盤就漲停（買不到）回 None。"""
    import signals
    st = signals.SymbolState(pick["code"], float(pick["prev_close"]), pick.get("name", ""))
    st.amplitude_pct = pick.get("amplitude_pct")
    st.day_open = entry
    p = signals._price_plan(st, entry, now or ENTRY_AT)
    if p is None:
        return None
    return dict(p, code=pick["code"], name=f"{pick.get('name', '')}・{LABEL}".lstrip("・"),
                or_high=None, pick=True)


def format_entry(sig: dict) -> str:
    """09:00 開盤之後推的那一則：實際的進場價、停損、張數。"""
    import signals
    label = f"{sig['code']} {sig.get('name', '')}".strip()
    plan_lines = signals._exit_plan_lines(sig)
    plan_lines = [l.replace(f"・跌破開盤價 {float(sig['entry']):.2f}",
                            f"・跌破開盤價 {float(sig['entry']):.2f}（＝進場價）")
                  for l in plan_lines]
    lines = [
        f"🌅 {label}｜{sig['time']}",
        "做多（盤前首選，開盤價買進）",
        f"進場：{sig['entry']:.2f}",
        f"張數：{sig['lots']} 張",
    ]
    if sig.get("oversized"):
        # 跟 v10 訊號同一句。10-14 中探針 200.50、停損 194.50：一張就 6,000 元。
        lines.append(f"⚠️ 一張的停損風險 {sig['risk_per_lot']:,} 元，"
                     f"超過上限 {config.RISK['per_trade_risk']:,} 元")
    lines += [
        "────────────────",
        *plan_lines,
        "────────────────",
        "跟盤中突破訊號分開記錄，不佔每日 3 個額度。",
        "驗證期不下單。",
    ]
    return "\n".join(lines)


def format_locked(pick: dict, price: float) -> str:
    label = f"{pick['code']} {pick.get('name', '')}".strip()
    return (f"🌅 {label}・{LABEL}\n────────────────\n"
            f"開盤 {price:.2f} 已經漲停，買不到 —— 今天首選不進場。")


class PickWatch:
    """盤中盯首選：開盤第一筆成交進場，之後照 v10 出場。

    自己一個 LiveTracker（不跟 v10 的訊號混在一起），結果寫回 state["pick"]。
    盤中重開：state 裡已經進場、還沒結束的，接著追；已經結束的不再追。
    """

    def __init__(self, pick: dict | None, state: dict, notify, save=None):
        import signals
        self.pick = pick
        self.state = state
        self.notify = notify
        self.save = save or (lambda: None)
        self.tracker = signals.LiveTracker(on_resolved=self._resolved, on_half=self._half)
        rec = state.get("pick") or {}
        if pick and rec.get("code") != pick["code"]:
            rec = {}
        self.rec = rec
        if pick and not rec:
            self.rec = {"code": pick["code"], "name": pick.get("name", "")}
            state["pick"] = self.rec
        sig = self.rec.get("sig")
        if sig and not self.rec.get("live_result"):
            self.tracker.track(sig)

    @property
    def code(self) -> str | None:
        return self.pick["code"] if self.pick else None

    @property
    def entered(self) -> bool:
        return bool(self.rec.get("sig")) or bool(self.rec.get("skipped"))

    def on_tick(self, st, now: datetime | None = None) -> list[str]:
        """st 是這一檔的 SymbolState（已經 update 過這一筆成交）。回傳要推的訊息。"""
        if not self.pick or not st.last_price:
            return []
        now = now or datetime.now()
        msgs = []
        if not self.entered:
            if now.time() < ENTRY_AT:
                return []
            entry = st.day_open or st.last_price
            sig = plan(self.pick, entry, now.time())
            if sig is None:
                self.rec["skipped"] = "開盤漲停，買不到"
                self.save()
                return [format_locked(self.pick, entry)]
            sig["time"] = now.strftime("%H:%M:%S")
            self.rec["sig"] = sig
            self.save()
            # 進場那一刻（訊號那一分鐘）不判出場，跟 v10 同一個約定
            self.tracker.track(sig, now=now)
            msgs.append(format_entry(sig))
            return msgs
        msgs += self.tracker.on_price(st.code, st.last_price, now=now, vwap=st.vwap,
                                      total_volume=st.total_volume)
        return msgs

    def flatten(self) -> list[str]:
        return self.tracker.flatten()

    def _resolved(self, o, price, verdict):
        self.rec.update(live_result=verdict, live_exit=round(float(price), 2),
                        live_at=datetime.now().strftime("%H:%M:%S"))
        self.save()

    def _half(self, o, price):
        self.rec["live_half"] = round(float(price), 2)
        self.save()


# ── 收盤後 ──────────────────────────────────────────────
PICK_FIELDS = ("date", "code", "name", "entry", "stop", "target", "lots", "half_at",
               "result", "exit_price", "exit_at", "half_exit", "r_multiple", "net_r",
               "gross_pct", "net_pct", "net_amount", "total", "rank_volume",
               "rank_amplitude", "rank_rsi", "rank_close_pos", "volume_ratio",
               "amplitude", "daily_rsi", "close_pos", "watched", "source")


# 盤中進場是開盤後第一筆成交（09:00:0x）。回推時用 09:00:01：walk_v10「進場那一分鐘
# 不判」才會跳過 09:00–09:01 那一根，跟盤中一致。寫 09:00:00 的話那一根會被拿去判
# 「跌破開盤價」—— 盤中不會判的那一分鐘。
REPLAY_ENTRY_TIME = "09:00:01"


def replay(pick: dict, full: list, date: str, sig: dict | None = None):
    """用當天分鐘 K（開高低收量）照同一套規則走一遍。回傳 (訊號, walk_v10 的結果)；
    沒有 K 棒、開盤漲停買不到、進場後沒有 K 棒 → None。whatif.py 也用這一個。"""
    import outcome as oc
    if not full:
        return None
    if not sig:
        sig = plan(pick, full[0][1])          # 第一根的開盤價 = 開盤價
        if sig is None:
            return None
        sig["time"] = REPLAY_ENTRY_TIME
    fired = datetime.strptime(f"{date} {sig['time']}", "%Y-%m-%d %H:%M:%S")
    walked = oc.walk_v10(full, sig, fired)
    if walked is None:
        return None
    return sig, walked


def resolve(broker, pick: dict, rec: dict | None, date: str) -> dict | None:
    """首選那一筆的結局。盤中有判過的以盤中為準（跟 v10 同一個原則）；
    沒有（監看沒開、中途掛掉）就用分鐘 K 照同一套規則回推。"""
    import exits
    import outcome as oc
    rec = rec or {}
    if rec.get("skipped"):
        return None
    sig = rec.get("sig")
    half = _num(rec.get("live_half"))
    if sig and rec.get("live_result") and rec.get("live_exit") is not None:
        result, exit_price, exit_at, source = (rec["live_result"], float(rec["live_exit"]),
                                               rec.get("live_at", ""), "盤中")
    else:
        replayed = replay(pick, oc.day_bars_ohlcv(broker, pick["code"], date), date, sig)
        if replayed is None:
            return None
        sig, (result, exit_price, _used, exit_at, half) = replayed
        source = "分鐘 K"
    entry, stop, lots = float(sig["entry"]), float(sig["stop"]), int(sig["lots"])
    pct, r = exits.blended(entry, stop, lots, half, exit_price)
    cost = config.round_trip_cost_pct()
    risk = entry - stop
    f, rk = pick.get("features", {}), pick.get("ranks", {})
    return {
        "date": date, "code": pick["code"], "name": pick.get("name", ""),
        "entry": entry, "stop": stop, "target": float(sig["target"]), "lots": lots,
        "half_at": float(sig["half_at"]), "result": result,
        "exit_price": round(float(exit_price), 2), "exit_at": exit_at,
        "half_exit": half, "r_multiple": round(r, 2),
        "net_r": round(r - cost / 100 * entry / risk, 2) if risk > 0 else round(r, 2),
        "gross_pct": round(pct, 3), "net_pct": round(pct - cost, 3),
        "net_amount": round((pct - cost) / 100 * entry * 1000 * lots),
        "total": pick.get("total"), "rank_volume": rk.get("volume_ratio"),
        "rank_amplitude": rk.get("amplitude"), "rank_rsi": rk.get("rsi_gap"),
        "rank_close_pos": rk.get("close_pos"), "volume_ratio": f.get("volume_ratio"),
        "amplitude": f.get("amplitude"), "daily_rsi": f.get("rsi"),
        "close_pos": f.get("close_pos"), "watched": pick.get("watched"),
        "source": source,
    }


def load(path=None) -> list[dict]:
    path = path or PICKS_FILE
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def append(row: dict, path=None) -> None:
    """同一天只留一筆（重跑 review 會蓋掉舊的）。"""
    path = path or PICKS_FILE
    rows = [r for r in load(path) if r.get("date") != row["date"]]
    rows.append({k: row.get(k) for k in PICK_FIELDS})
    rows.sort(key=lambda r: r["date"])
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=PICK_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in PICK_FIELDS})


def report_lines(today: dict | None, pick: dict | None, history: list[dict],
                 skipped: str = "") -> list[str]:
    """日報裡首選那一段。"""
    if not pick:
        return []
    import signals
    label = f"{pick['code']} {pick.get('name', '')}".strip()
    lines = ["────────────────", f"🌅 {LABEL}（分開記錄）"]
    if skipped:
        lines.append(f"{label}　{skipped}")
    elif today is None:
        lines.append(f"{label}　回推不出來（沒有分鐘 K）")
    else:
        mark = signals.RESOLUTION_MARK.get(today["result"], "")
        lines.append(f"{mark} {label}　{today['result']}")
        lines.append(f"　{float(today['r_multiple']):+.2f}R　"
                     f"{float(today['net_amount']):+,.0f} 元")
    rows = [r for r in history if _num(r.get("net_pct")) is not None]
    if rows:
        n = len(rows)
        wins = sum(1 for r in rows if float(r["net_pct"]) > 0)
        avg_r = sum(float(r["r_multiple"]) for r in rows) / n
        avg_net = sum(float(r["net_r"]) for r in rows) / n
        amount = sum(float(r["net_amount"]) for r in rows)
        lines += [f"首選累計 {n} 筆｜勝率 {wins / n * 100:.1f}%",
                  f"平均 {avg_r:+.2f}R（扣成本 {avg_net:+.2f}R）",
                  f"首選累計損益 {amount:+,.0f} 元"]
    return lines
