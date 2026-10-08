"""
outcome.py — 用分鐘 K 回推每個訊號的結局。

訊號發出後程式就不再追蹤那檔（一檔一天只發一次），所以「後來到底怎麼了」
從來沒有被記下來。驗證期跑 20 天、每天只存下「發了什麼訊號」，
最後會拿到一疊沒有結果的紀錄 —— 勝率、賺賠比、扣完成本的淨值，一個都算不出來。

這支程式補上那一段：收盤後回頭看分鐘 K，從發訊號的下一根開始往後走，
看停損與目標哪一個先被碰到。都沒碰到就以收盤平倉計（當沖不留倉）。

三個刻意選擇的保守假設，每一個都寧可低估這套系統：

1. **同一根 K 同時觸及停損與目標 → 判停損。** 分鐘 K 只有開高低收，
   看不出那一分鐘內哪個先到。往壞處算。
2. **成交價就是訊號上的進場價與出場價。** 真實交易有滑價，實際成績
   只會比這裡差，不會更好。
3. **平倉時間卡在 13:25**，不是 13:30 —— 尾盤集合競價那五分鐘不保證出得掉。
"""
import csv
import logging
import pathlib
from dataclasses import dataclass, asdict
from datetime import datetime, time as dtime, timedelta

import config
import exits

log = logging.getLogger("outcome")

STOP = "停損"
TARGET = "目標"
FLAT = "收盤平倉"
# v6：第一天收盤時還沒碰停損也沒到目標 —— 留倉過夜，結局要等明天。
# 這不是結局，所以**不寫進 outcomes.csv**、不進勝率；日報上另外列。
CARRY = "留倉中"

# 當沖平倉的最後時點。13:25 之後進尾盤集合競價，不保證出得掉。
FLATTEN_AT = dtime(13, 25)
# 收盤。留倉過夜的那一筆，第一天要看到這一根為止 —— 你沒有在 13:25 走，
# 尾盤集合競價那一下碰到停損，就是碰到了。
SESSION_CLOSE = dtime(13, 30)

OUTCOME_FILE = config.BASE_DIR / "outcomes.csv"

# 一根分鐘 K 涵蓋的時間長度。用來排掉「包著訊號那一刻」的那一根。
BAR_SPAN = timedelta(minutes=1)

# 看「訊號後多久之內買得到」用的窗口。人從收到推播、開 App、輸入到送出，
# 現實上就是這幾分鐘 —— 窗口開太大等於假設你反應得比實際快。
FILL_WINDOW_BARS = 5

# 台股一張 = 1000 股。signals.py 算單筆風險時用的是同一個數字。
SHARES_PER_LOT = 1000
FIELDS = ("date", "code", "time", "entry", "stop", "target", "lots",
          "result", "exit_price", "r_multiple", "gross_pct", "net_pct", "bars",
          "or_high", "vwap", "volume_surge", "extension_pct", "vwap_gap_pct",
          "mae_pct", "mfe_pct", "target_after_stop", "low_5m_pct",
          "fill_low_pct", "rank", "category", "mkt_open_pct", "mkt_day_pct",
          "exit_at", "ruleset", "exit_0930", "r_0930", "bid_ask_ratio",
          "mkt_signal_pct", "exit_date", "close_pos_pct", "vs_vwap_pct", "volume_x",
          "open_gap_pct", "low_gap_pct", "half_exit")


@dataclass
class Outcome:
    date: str
    code: str
    time: str
    entry: float
    stop: float
    target: float
    lots: int
    result: str
    exit_price: float
    r_multiple: float     # 以「進場到停損」為 1R
    gross_pct: float      # 未扣成本的報酬率
    net_pct: float        # 扣掉來回成本後
    bars: int             # 從進場到出場經過幾根分鐘 K
    # 以下是發訊號當下的現場條件。它們不影響任何判定，純粹是為了讓 20 天之後
    # 回答得了「什麼樣的訊號比較會成功」—— 沒留下來的話，那些問題就永遠問不了。
    or_high: float | None = None        # 開盤區間高點
    vwap: float | None = None           # 當時的均價線
    volume_surge: float | None = None   # 當時的量能倍數
    extension_pct: float | None = None  # 進場價比區間高點高出幾 %（追高的程度）
    vwap_gap_pct: float | None = None   # 進場價比均價線高出幾 %
    # 進場之後整天（到 13:25）的極端值，不管中途有沒有出場。
    # 用來回答「停損該多緊、目標該多遠」—— 只看出場價的話，這兩個問題永遠問不了。
    mae_pct: float | None = None        # 最大不利偏移：進場後最低點離進場價幾 %
    mfe_pct: float | None = None        # 最大有利偏移：進場後最高點離進場價幾 %
    target_after_stop: bool | None = None   # 停損出場後，當天還是碰到目標了嗎
    # 訊號後第 1~5 分鐘的最低價離進場價幾 %。<= 0 表示「限價掛訊號價買得到」。
    # 人從收到訊號到送出委託正好就落在這個窗口裡，所以它直接回答「我追得上嗎」。
    low_5m_pct: float | None = None
    # 同一題，但是用盤中 tick 量的（signals.py 的 FillProbe 寫回 state.json）。
    # low_5m_pct 用分鐘 K，看不到訊號後的頭 60 秒；急拉的訊號正好都在那 60 秒
    # 內跑掉，所以分鐘 K 版本對這幾筆會偏悲觀。兩欄並存，20 天後互相對照。
    fill_low_pct: float | None = None
    rank: int = 0                 # 盤前選股名次（1 = 量比最高），0 = 未知
    category: str = ""            # 產業類別代碼 —— 「輪動題材」的客觀代理
    # 當日大盤（0050 代理）。這套系統只做多，多方突破在綠盤日結構上逆風，
    # 不分開看等於把兩種完全不同的日子平均在一起。
    #
    # mkt_open_pct 是 09:15 的大盤。這裡原本寫著「它在任何訊號發出之前就已知，
    # 所以它是唯一有資格變成規則的那個」—— v1–v3 訊號全部發在 09:17 之後，
    # 那時是對的；v4 起 09:05 就發完，它變成事後十分鐘的資訊。是不是事前，
    # 要逐筆看訊號時間，analyse.by_market() 就是這樣判的。
    mkt_open_pct: float | None = None     # 09:15 時的大盤漲跌 %
    mkt_day_pct: float | None = None      # 當日收盤的大盤漲跌 %
    # v4 原則二：09:30 發「時間到」訊號，未達停損的由下單者自己決定走不走。
    # 系統不替人平倉，所以上面那幾欄（result / exit_price / r_multiple）照舊是
    # 「照停損目標走到底、13:25 平倉」的機械結果 —— 也就是**續抱**的那個版本。
    #
    # 下面這兩欄記的是「09:30 就走」的版本。兩個並存、互不覆蓋，是因為
    # 「09:30 就走是不是比較好」這一題需要對照組，而現在就把後半天砍掉的話，
    # 20 天後只會有一個數字，沒有東西可以比。
    #
    # 已經在 09:30 之前碰到停損或目標的那幾筆是 None —— 那不是「沒走」，
    # 是那時候已經沒有部位了。空白代表不適用，不是 0。
    exit_0930: float | None = None        # 09:30 當下的價位
    r_0930: float | None = None           # 同一刻換算成幾 R
    # 開盤區間內的外盤成交 ÷ 內盤成交。量能倍數只數量的大小，分不出方向 ——
    # 量放大但內盤居多，是有人在出貨給你。tick 沒帶 tick_type 時留空，
    # 空白代表「判不出來」，不是「剛好打平」。
    bid_ask_ratio: float | None = None
    # 決策當下的大盤：量測時間跟著 config.SIGNAL["signal_batch_at"] 走。
    # 這才是 v4 之後唯一「訊號發出前就已知」的大盤數字。舊列沒有這一欄 —— 留空。
    mkt_signal_pct: float | None = None
    # 出場時間 "HH:MM:SS"。風控閘門看的是**已實現**損益，而一筆要出場了才算實現 ——
    # 沒有這一欄就答不出「這一筆發訊號的時候，前面幾筆已經結束了幾筆」，
    # 於是「照規則今天真的會做到哪幾筆」只能用「前 N 筆」粗估，而那會算錯。
    exit_at: str = ""
    # 產生這一筆的規則版本。沒有它，改過規則之後的資料就只能整批丟掉 ——
    # 而「為了資料純淨所以什麼都不改」會變成無限迴圈。
    ruleset: str = ""
    # v6 起可以抱到隔天。出場那天的日期；空白 = 當天就出場（當沖）。
    # 有值時 exit_at 是**那一天**的時間，成本用留倉稅率算。
    exit_date: str = ""
    # 13:25 還沒結束（可能留倉）那一刻的樣子，signals.close_snapshot() 記的。
    # 只有那幾筆有值；當天就結束的留空 —— 空白不是 0。大盤用上面的 mkt_day_pct。
    close_pos_pct: float | None = None    # 收在當日最低～最高之間的哪裡（0～100）
    vs_vwap_pct: float | None = None      # 現價比均價線高幾 %
    volume_x: float | None = None         # 今天量是平常一天的幾倍
    # v9 的進場條件看的兩個數字（signals.evaluate() 記在訊號上）。v8 以前沒有。
    open_gap_pct: float | None = None     # 開盤價比昨收高幾 %
    low_gap_pct: float | None = None      # 發訊號前的當日最低比昨收高幾 %
    # v10「先出一半」的價位。有值表示分兩段出場，報酬與 R 是兩段合起來的；
    # result / exit_price 是剩下那一段的出場原因與價位。
    half_exit: float | None = None

    @property
    def overnight(self) -> bool:
        return bool(self.exit_date) and self.exit_date != self.date

    @property
    def is_win(self) -> bool:
        return self.net_pct > 0

    @property
    def net_amount(self) -> float:
        """扣掉成本後的損益金額（元）。

        用 net_pct 乘上部位金額，而不是另外去算一次手續費與證交稅 —— 這樣訊息上
        的百分比和金額一定對得起來。兩邊各算各的，遲早會差幾十塊而讓人懷疑哪個
        才是對的。代價是成本以進場金額為基準估算，誤差在十位數，不影響判斷。
        """
        return self.net_pct / 100 * self.entry * SHARES_PER_LOT * self.lots


def _num(value) -> float | None:
    """舊的訊號紀錄沒有這些欄位，缺了就留空，不要塞 0 冒充真實數字。"""
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _pct_above(price: float, base: float | None) -> float | None:
    """price 比 base 高出幾 %。base 缺或為 0 就沒有意義，回 None。"""
    if not base:
        return None
    return round((price - base) / base * 100, 3)


def _parse_signal_time(sig: dict, date: str) -> datetime | None:
    raw = str(sig.get("time", "")).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(raw, fmt).time()
            return datetime.combine(datetime.strptime(date, "%Y-%m-%d").date(), t)
        except ValueError:
            continue
    log.warning("訊號時間格式看不懂：%r", raw)
    return None


def bars_after(broker, code: str, date: str, after: datetime,
               until: dtime = FLATTEN_AT) -> list[tuple]:
    """回傳 (時間, 高, 低, 收) 的清單，只留**完全在訊號之後**、13:25 之前的 K 棒。

    K 棒的時間戳是該分鐘的**結束**時間（實機驗證過：09:00~09:01 那根標 09:01）。
    所以「label > 訊號時間」的第一根，涵蓋的是訊號發出**前**的那幾十秒。
    以前的版本留著那一根，還以為只是「略偏保守」——

    那是錯的，而且錯得剛好會毀掉這個策略的統計。突破訊號依定義發在股價剛越過
    開盤區間高點的那一刻，而停損就設在區間高點下方一點。那一根 K 棒裡，訊號
    發出前的每一筆成交都還在區間高點之下 —— 低點幾乎必然掃到停損。
    2026-09-24 五個訊號有四個被判成「第一根就停損」，實際上合晶當天從 119 一路
    走到目標 121.50 還收在 120.50。不是市場的事，是尺量錯了。

    所以只收「起點不早於訊號時間」的 K 棒，也就是 label >= 訊號時間 + 1 分鐘。
    代價是訊號後最多 60 秒內的價格看不到 —— 那段空白對停損和目標一視同仁，
    不偏向任何一邊；而且盤中的即時追蹤（signals.py 的 LiveTracker）看的是 tick，
    正好補上這一段。
    """
    from broker import _bar_time
    try:
        kb = broker.kbars(code, date, date)
    except Exception as e:
        log.warning("%s 分鐘 K 取得失敗：%s", code, e)
        return []
    ts = list(getattr(kb, "ts", []) or [])
    highs = list(getattr(kb, "High", []) or [])
    lows = list(getattr(kb, "Low", []) or [])
    closes = list(getattr(kb, "Close", []) or [])
    if not (len(ts) == len(highs) == len(lows) == len(closes)):
        log.warning("%s 分鐘 K 欄位長度不一致，跳過", code)
        return []

    # K 棒 label 是該分鐘的結束時間，所以 label 為 T 的那根涵蓋 (T-1分, T]。
    # 要「整根都在訊號之後」，就是 T - 1分 >= 訊號時間。
    first_ok = after + BAR_SPAN
    out = []
    for raw, h, l, c in zip(ts, highs, lows, closes):
        t = _bar_time(raw)
        if t is None or t < first_ok or t.time() > until:
            continue
        out.append((t, float(h), float(l), float(c)))
    out.sort(key=lambda r: r[0])
    return out


def next_session_bars(broker, code: str, date: str,
                      through: str) -> tuple[str, list[tuple]]:
    """date 之後、through（含）之前的**第一個**交易日的分鐘 K。

    回傳 (那一天, [(時間, 開, 高, 低, 收), ...])，只留到 13:25。找不到就回 ("", [])。

    「隔天」不能用日曆加一天：週五的隔天是週一，遇到連假更遠。拿 date+1 到
    through 這一段的 K 棒，第一根出現的那天就是下一個交易日。

    這裡要「開」：留倉最大的風險是跳空。隔天一開盤就在停損之下，你賣到的是
    開盤價，不是停損價 —— 用停損價記，等於把跳空的損失從帳上抹掉。
    """
    from broker import _bar_time
    start = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    if start > through:
        return "", []
    try:
        kb = broker.kbars(code, start, through)
    except Exception as e:
        log.warning("%s 隔日分鐘 K 取得失敗：%s", code, e)
        return "", []
    cols = [list(getattr(kb, k, []) or []) for k in ("ts", "Open", "High", "Low", "Close")]
    if len({len(c) for c in cols}) != 1:
        log.warning("%s 隔日分鐘 K 欄位長度不一致，跳過", code)
        return "", []
    rows = []
    for raw, o, h, l, c in zip(*cols):
        t = _bar_time(raw)
        if t is None or t.time() > FLATTEN_AT:
            continue
        rows.append((t, float(o), float(h), float(l), float(c)))
    if not rows:
        return "", []
    rows.sort(key=lambda r: r[0])
    day = rows[0][0].date()
    return day.strftime("%Y-%m-%d"), [r for r in rows if r[0].date() == day]


def walk_day2(bars: list[tuple], stop: float, target: float) -> tuple[str, float, int]:
    """隔天的分鐘 K（含開盤價）由早到晚走一遍，回傳 (結果, 出場價, 用到第幾根)。

    第一根先看開盤價：跳空開在停損之下 → 以開盤價停損（比停損價更差）；
    跳空開在目標之上 → 以開盤價出場（比目標更好，同樣照實記）。
    之後同一根同時碰到停損與目標 → 判停損，跟第一天同一個保守假設。
    都沒碰到 → 13:25 收盤平倉。
    """
    if not bars:
        return "", 0.0, 0
    first_open = bars[0][1]
    if first_open <= stop:
        return STOP, first_open, 1
    if first_open >= target:
        return TARGET, first_open, 1
    for i, (_, _o, high, low, _c) in enumerate(bars, 1):
        if low <= stop:
            return STOP, stop, i
        if high >= target:
            return TARGET, target, i
    return FLAT, bars[-1][4], len(bars)


def resolve(broker, sig: dict, date: str | None = None,
            through: str | None = None) -> Outcome | None:
    """回推單一訊號的結局。拿不到 K 棒就回 None（不要猜）。

    through：可以看到哪一天為止（含）。只對可以留倉的訊號有意義 ——
    第一天沒結束的那一筆，要拿 through 之前的下一個交易日接著走。
    沒給（或下一個交易日還沒到）就回傳 result=CARRY：結局未定，不是結局。
    """
    date = date or datetime.now().strftime("%Y-%m-%d")
    fired = _parse_signal_time(sig, date)
    if fired is None:
        return None
    entry, stop, target = float(sig["entry"]), float(sig["stop"]), float(sig["target"])
    risk = entry - stop
    if risk <= 0:
        log.warning("%s 停損不在進場價之下，無法計算 R", sig.get("code"))
        return None

    code = str(sig["code"])
    # 這一筆可以抱幾天，看**發訊號當時**的規則，不看現在的 config ——
    # v5 的舊訊號拿 v6 的程式重跑，還是當沖。舊紀錄沒有這一欄 = 當沖。
    hold = int(_num(sig.get("max_hold_days")) or 1)
    if exits.uses_v10(sig) and hold < 2 and sig.get("half_at"):
        return _resolve_v10(broker, sig, date, code, fired, entry, stop, target)
    # 會留倉的那一筆，第一天要看到收盤那一根：你沒在 13:25 走。
    bars = bars_after(broker, code, date, fired,
                      until=SESSION_CLOSE if hold >= 2 else FLATTEN_AT)
    # 盤中 LiveTracker 用 tick 判定過的，以它為準。
    #
    # bars_after() 刻意丟掉訊號後的頭 60 秒（那一根 K 棒涵蓋訊號發出**前**的時間，
    # 留著會製造假停損）。但走得快的那幾筆就在那 60 秒裡結束 ——
    # 2026-09-29 允強 09:32:13 發訊號、09:32:25 到目標，整件事發生在那個空窗裡：
    # 即時推播說 +1.57R，收盤回推說 -1.00R（它只看到後來跌回去碰停損）。
    # tick 是實際成交，分鐘 K 是事後摘要；衝突時以 tick 為準。
    live_result = str(sig.get("live_result") or "")
    live_exit = _num(sig.get("live_exit"))
    live_date = str(sig.get("live_date") or "")
    exit_date, exit_at = "", ""
    day2: list[tuple] = []
    if live_result and live_exit is not None:
        result, exit_price, used = live_result, live_exit, 0   # 0 = 由 tick 判定
        exit_at = str(sig.get("live_at") or "")
        if live_date and live_date != date:
            exit_date = live_date            # 隔天盤中 tick 判定的
            if through:                      # 極值要算到隔天，K 棒還是要拿
                _, day2 = next_session_bars(broker, code, date, through)
    elif bars:
        result, exit_price, used = FLAT, bars[-1][3], len(bars)
        for i, (t, high, low, close) in enumerate(bars, 1):
            hit_stop, hit_target = low <= stop, high >= target
            # 13:25 之後是尾盤集合競價：只有一個成交價，沒有「剛好在停損價成交」
            # 這回事。2026-10-08 界霖 13:25 還在 97.50（停損 97），收盤集合競價
            # 一次撮合在 94.40 —— 照停損價 97 記，等於把那 2.6 元的跳空抹掉。
            # 跟隔天跳空開在停損之下一樣，用那一下真的成交得到的價格。
            auction = t.time() > FLATTEN_AT
            if hit_stop:                  # 同時觸及也判停損：分鐘 K 看不出先後
                result, exit_price, used = STOP, (min(stop, close) if auction else stop), i
                break
            if hit_target:
                result, exit_price, used = TARGET, (max(target, close) if auction else target), i
                break
        if result == FLAT:
            if hold >= 2:
                result = CARRY            # 出場價暫記第一天收盤，只是標記
            else:
                exit_at = FLATTEN_AT.strftime("%H:%M:%S")
        else:
            exit_at = bars[used - 1][0].strftime("%H:%M:%S")
    else:
        return None                        # 沒有 tick 判定也沒有 K 棒 —— 不要猜

    if result == CARRY and through:
        day2_date, day2 = next_session_bars(broker, code, date, through)
        if day2:
            result, exit_price, n2 = walk_day2(day2, stop, target)
            used = len(bars) + n2
            exit_date = day2_date
            exit_at = (FLATTEN_AT.strftime("%H:%M:%S") if result == FLAT
                       else day2[n2 - 1][0].strftime("%H:%M:%S"))

    overnight = bool(exit_date) or result == CARRY
    return _build(sig, date, code, entry, stop, target, result, exit_price, used,
                  exit_at, exit_date, bars, day2, overnight)


def day_bars_ohlcv(broker, code: str, date: str) -> list[tuple]:
    """當天**全部**分鐘 K：(時間, 開, 高, 低, 收, 量)。v10 要算均價線與量縮，
    所以訊號之前的 K 棒也要（均價線與「進場前平均量」是從 09:00 累計的）。"""
    from broker import _bar_time
    try:
        kb = broker.kbars(code, date, date)
    except Exception as e:
        log.warning("%s 分鐘 K 取得失敗：%s", code, e)
        return []
    cols = [list(getattr(kb, k, []) or []) for k in ("ts", "Open", "High", "Low", "Close", "Volume")]
    if not cols[0] or len({len(c) for c in cols}) != 1:
        log.warning("%s 分鐘 K 欄位不齊（v10 需要開高低收量），跳過", code)
        return []
    rows = []
    for raw, o, h, l, c, v in zip(*cols):
        t = _bar_time(raw)
        if t is not None:
            rows.append((t, float(o), float(h), float(l), float(c), float(v)))
    return sorted(rows, key=lambda r: r[0])


def walk_v10(full: list[tuple], sig: dict, fired: datetime):
    """用分鐘 K 照 v10 的六條走一遍。回傳 (結果, 出場價, 用了幾根, 出場時間, 先出一半的價位)；
    訊號之後一根 K 都沒有就回 None。

    均價線用 (高+低+收)/3 × 量 從 09:00 累計（kbars 沒有成交金額，跟 whynot 同一個近似）。
    盤中 tick 看到的才是真的；兩邊衝突時以 tick 為準（resolve 會先用 live_result）。
    """
    pos = exits.Position.from_signal(sig, fired)
    # 量縮的起點用 K 棒的累計量（訊號上記的是 tick 的，口徑不一定一樣）
    pos.entry_cum = None
    cum = pv = 0.0
    after, last = 0, None
    for t, _o, h, l, c, v in full:
        cum += v
        pv += (h + l + c) / 3 * v
        if t < fired + BAR_SPAN:
            continue
        if t.time() > FLATTEN_AT:
            break
        if after == 0:
            pos.entry_cum = cum - v
        after += 1
        last = c
        for ev in pos.step(t, h, l, c, pv / cum if cum else None, cum, bar=True):
            if ev[0] == "exit":
                return ev[1], ev[2], after, t.strftime("%H:%M:%S"), pos.half_price
    if not after:
        return None
    return FLAT, last, after, FLATTEN_AT.strftime("%H:%M:%S"), pos.half_price


def _resolve_v10(broker, sig: dict, date: str, code: str, fired: datetime,
                 entry: float, stop: float, target: float) -> "Outcome | None":
    full = day_bars_ohlcv(broker, code, date)
    bars = [(b[0], b[2], b[3], b[4]) for b in full
            if b[0] >= fired + BAR_SPAN and b[0].time() <= FLATTEN_AT]
    live_result = str(sig.get("live_result") or "")
    live_exit = _num(sig.get("live_exit"))
    if live_result and live_exit is not None:
        # 盤中 tick 判定過的以它為準（見 resolve 的說明）
        return _build(sig, date, code, entry, stop, target, live_result, live_exit, 0,
                      str(sig.get("live_at") or ""), "", bars, [], False,
                      half_exit=_num(sig.get("live_half")))
    walked = walk_v10(full, sig, fired) if full else None
    if walked is None:
        return None                        # 沒有 tick 判定也沒有 K 棒 —— 不要猜
    result, exit_price, used, exit_at, half = walked
    return _build(sig, date, code, entry, stop, target, result, exit_price, used,
                  exit_at, "", bars, [], False, half_exit=half)


def _build(sig: dict, date: str, code: str, entry: float, stop: float, target: float,
           result: str, exit_price: float, used: int, exit_at: str, exit_date: str,
           bars: list, day2: list, overnight: bool,
           half_exit: float | None = None) -> "Outcome":
    """resolve() 走完之後，把結果與發訊號當下的現場條件組成一列 Outcome。
    v10 先出過一半的，報酬與 R 用兩段合起來算（exits.blended）。"""
    risk = entry - stop
    if half_exit is None:
        gross = (exit_price - entry) / entry * 100
        r_mult = (exit_price - entry) / risk
    else:
        gross, r_mult = exits.blended(entry, stop, int(sig.get("lots", 0) or 0),
                                      half_exit, exit_price)
    or_high, vwap = _num(sig.get("or_high")), _num(sig.get("vwap"))
    # 整段持有期的極端值：算的是**全部** K 棒，不是只算到出場那一根。
    # 問題是「如果我沒出場會怎樣」，只看到出場為止就答不出來。抱到隔天的，
    # 隔天的 K 棒也算進來 —— 「到 +8% 之後續抱，最高走到哪」就是這兩欄在回答。
    # 極值仍然要用 K 棒算；沒有 K 棒（只有 tick 判定）時留空，不要猜一個數字出來。
    highs = [b[1] for b in bars] + [b[2] for b in day2]
    lows = [b[2] for b in bars] + [b[3] for b in day2]
    day_high = max(highs, default=None)
    day_low = min(lows, default=None)
    low_5m = min((b[2] for b in bars[:FILL_WINDOW_BARS]), default=None)
    # 盤中 tick 量到的同一個窗口。沒有這個欄位（舊紀錄、或當天沒收到報價）就留空。
    fill_low = _num(sig.get("fill_low"))
    # 09:30「時間到」那一刻的價位（signals.py 的 time_exit 寫回 state.json）。
    # 這一筆如果在 09:30 之前就碰到停損或目標，就不會有這個欄位 —— 那時候
    # 已經沒有部位了，留空代表不適用，不是 0。
    mark_0930 = _num(sig.get("exit_0930_price"))
    return Outcome(
        date=date, code=code, time=str(sig.get("time", "")),
        entry=entry, stop=stop, target=target, lots=int(sig.get("lots", 0) or 0),
        result=result, exit_price=round(exit_price, 2),
        r_multiple=round(r_mult, 2),
        gross_pct=round(gross, 3),
        net_pct=round(gross - config.round_trip_cost_pct(overnight=overnight), 3),
        bars=used,
        or_high=or_high, vwap=vwap,
        volume_surge=_num(sig.get("volume_surge")),
        extension_pct=_pct_above(entry, or_high),
        vwap_gap_pct=_pct_above(entry, vwap),
        mae_pct=_pct_above(day_low, entry) if day_low is not None else None,
        mfe_pct=_pct_above(day_high, entry) if day_high is not None else None,
        target_after_stop=((day_high >= target) if day_high is not None else None)
        if result == STOP else None,
        low_5m_pct=_pct_above(low_5m, entry) if low_5m is not None else None,
        fill_low_pct=_pct_above(fill_low, entry) if fill_low is not None else None,
        rank=int(sig.get("rank") or 0),
        category=str(sig.get("category") or ""),
        exit_at=exit_at,
        ruleset=str(sig.get("ruleset") or ""),
        bid_ask_ratio=_num(sig.get("bid_ask_ratio")),
        exit_0930=mark_0930,
        r_0930=(round((mark_0930 - entry) / risk, 2)
                if mark_0930 is not None and risk > 0 else None),
        exit_date=exit_date,
        close_pos_pct=_num(sig.get("close_pos_pct")),
        vs_vwap_pct=_num(sig.get("vs_vwap_pct")),
        volume_x=_num(sig.get("volume_x")),
        open_gap_pct=_num(sig.get("open_gap_pct")),
        low_gap_pct=_num(sig.get("low_gap_pct")),
        half_exit=round(half_exit, 2) if half_exit is not None else None,
    )


def resolve_all(broker, sigs: list[dict], date: str | None = None,
                through: str | None = None) -> list[Outcome]:
    out = []
    for s in sigs:
        try:
            o = resolve(broker, s, date, through=through)
        except Exception as e:                       # 一檔壞掉不該讓整份覆盤產不出來
            log.warning("%s 回推失敗：%s", s.get("code"), e)
            o = None
        if o:
            out.append(o)
    # 大盤只查一次，寫到當天每一列上。查不到就留空 —— 空白是空白，0 是平盤。
    if out:
        try:
            mkt_open, mkt_day = broker.market_day(date)
        except Exception as e:                       # 大盤查不到不該讓整份覆盤產不出來
            log.warning("大盤取得失敗：%s", e)
            mkt_open = mkt_day = None
        try:
            mkt_sig = broker.market_at(config.SIGNAL["signal_batch_at"][:5], date)
        except Exception as e:
            log.warning("決策當下的大盤取得失敗：%s", e)
            mkt_sig = None
        for o in out:
            o.mkt_open_pct, o.mkt_day_pct = mkt_open, mkt_day
            o.mkt_signal_pct = mkt_sig
    return out


def _row_key(row: dict) -> tuple:
    return (str(row.get("date", "")), str(row.get("code", "")), str(row.get("time", "")))


def append_csv(outcomes: list[Outcome], path=None) -> None:
    """累積到 outcomes.csv —— 20 天之後的統計靠這一份，不靠解析 Markdown。

    重跑會先把同一筆（日期 + 代號 + 訊號時間）的舊列刪掉，避免 review.py 跑兩次
    就重複計算。

    以前是「整天的舊列全部刪掉」。v6 之後那會出事：昨天留倉的那一筆今天才有
    結局，它的 date 是**昨天** —— 用日期刪，會把昨天當天就結束的那幾筆一起
    刪掉，累計勝率就無聲少了幾筆。
    """
    if not outcomes:
        return
    path = path or OUTCOME_FILE
    keys = {_row_key(asdict(o)) for o in outcomes}
    kept = []
    if path.exists():
        # utf-8-sig 讀得了有 BOM 與沒有 BOM 的檔，所以舊檔照樣接得下去
        with open(path, newline="", encoding="utf-8-sig") as f:
            kept = [r for r in csv.DictReader(f) if _row_key(r) not in keys]
    # 寫成帶 BOM 的 UTF-8：台灣的 Excel 預設用 cp950 開 csv，沒有 BOM 的話
    # 「停損」「目標」會變成一串亂碼。這份檔是要給人看的，不是只給程式讀的。
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in kept:
            w.writerow({k: r.get(k, "") for k in FIELDS})
        for o in outcomes:
            w.writerow(asdict(o))


# ── 被擋掉的候選 ───────────────────────────────────────
# signals.py 把訊號上限／一檔一次擋掉的訊號寫進 candidates.csv。
# 這裡用完全相同的邏輯回推它們的結局，只是寫到另一份檔，
# 不進 outcomes.csv、不進日報 —— 它們不是你會做的交易，是「沒做到的那些」。
CANDIDATE_FILE = config.BASE_DIR / "candidates.csv"
CANDIDATE_OUTCOME_FILE = config.BASE_DIR / "candidates_outcomes.csv"
CANDIDATE_OUT_FIELDS = FIELDS + ("reason",)


def load_candidates(date: str | None = None, path=None) -> list[dict]:
    """讀出指定日期的候選（預設今天）。格式就是 resolve() 吃得下的 sig dict。"""
    path = pathlib.Path(path) if path else CANDIDATE_FILE
    if not path.exists():
        return []
    date = date or datetime.now().strftime("%Y-%m-%d")
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if r.get("date") == date]


def resolve_candidates(broker, rows: list[dict],
                       date: str | None = None) -> list[tuple]:
    """回推候選的結局，回傳 [(Outcome, reason)]。"""
    out = []
    for r in rows:
        try:
            o = resolve(broker, r, date or r.get("date"))
        except Exception as e:
            log.warning("候選 %s 回推失敗：%s", r.get("code"), e)
            o = None
        if o:
            out.append((o, r.get("reason", "")))
    return out


def append_candidates_csv(pairs: list[tuple], path=None) -> None:
    """與 append_csv 同樣的「同日重跑先刪舊列」語意，多帶一欄 reason。"""
    if not pairs:
        return
    path = pathlib.Path(path) if path else CANDIDATE_OUTCOME_FILE
    dates = {o.date for o, _ in pairs}
    kept = []
    if path.exists():
        with open(path, newline="", encoding="utf-8-sig") as f:
            kept = [r for r in csv.DictReader(f) if r.get("date") not in dates]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CANDIDATE_OUT_FIELDS)
        w.writeheader()
        for r in kept:
            w.writerow({k: r.get(k, "") for k in CANDIDATE_OUT_FIELDS})
        for o, reason in pairs:
            row = asdict(o)
            row["reason"] = reason
            w.writerow(row)


_STR_FIELDS = ("date", "code", "time", "result", "category", "exit_at", "ruleset",
               "exit_date")
_BOOL_FIELDS = ("target_after_stop",)
_INT_FIELDS = ("lots", "bars")
_OPTIONAL_FIELDS = ("or_high", "vwap", "volume_surge", "extension_pct",
                    "vwap_gap_pct", "mae_pct", "mfe_pct", "low_5m_pct",
                    "fill_low_pct", "mkt_open_pct", "mkt_day_pct",
                    "exit_0930", "r_0930", "bid_ask_ratio", "mkt_signal_pct",
                    "close_pos_pct", "vs_vwap_pct", "volume_x",
                    "open_gap_pct", "low_gap_pct", "half_exit")


def _bool(value) -> bool | None:
    """CSV 讀回來是字串。空字串代表「不適用」，不是 False。"""
    text = str(value or "").strip()
    return None if not text else text.lower() == "true"


def load_csv(path=None) -> list[Outcome]:
    """把累積下來的 outcomes.csv 讀回來，用來算跨日的統計。

    壞掉的列跳過就好，不要讓一列爛資料害整份日報發不出去。
    """
    path = path or OUTCOME_FILE
    if not path.exists():
        return []
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f):
            try:
                kw = {k: str(raw.get(k, "")) for k in _STR_FIELDS}
                kw |= {k: int(float(raw[k])) for k in _INT_FIELDS}
                kw |= {k: float(raw[k]) for k in
                       ("entry", "stop", "target", "exit_price",
                        "r_multiple", "gross_pct", "net_pct")}
                kw |= {k: _num(raw.get(k)) for k in _OPTIONAL_FIELDS}
                kw |= {k: _bool(raw.get(k)) for k in _BOOL_FIELDS}
                # rank 是後來才加的欄位。9/24~9/29 寫下的列沒有它，
                # 當成必填會讓那幾天**整列被跳過** —— 累計勝率會無聲歸零。
                kw["rank"] = int(float(raw.get("rank") or 0))
                rows.append(Outcome(**kw))
            except (KeyError, TypeError, ValueError) as e:
                log.warning("outcomes.csv 有一列讀不進來，跳過：%s", e)
    return rows


def fill_pct(o: Outcome) -> float | None:
    """這一筆「掛進場價買不買得到」的那個數字，單位 %。None = 不知道。

    tick 量到的優先，分鐘 K 的當備援 —— 分鐘 K 看不到訊號後的頭 60 秒，
    對急拉型的訊號會偏悲觀（說「沒回到進場價」其實只是沒看到）。
    """
    return o.fill_low_pct if o.fill_low_pct is not None else o.low_5m_pct


def fill_stats(outcomes: list[Outcome]) -> dict:
    """掛限價在進場價、買得到幾筆。

    使用者自己講的那一題：「買不到就是空談」。勝率再高，買不到的那幾筆
    不會進你的帳戶 —— 所以這個數字要和勝率擺在一起看，不是附註。
    """
    known = [p for p in (fill_pct(o) for o in outcomes) if p is not None]
    if not known:
        return {"known": 0, "filled": 0, "rate": None, "unknown": len(outcomes)}
    filled = [p for p in known if p <= 0]
    return {
        "known": len(known),
        "filled": len(filled),
        "rate": round(len(filled) / len(known) * 100, 1),
        "unknown": len(outcomes) - len(known),
        # 買不到的那幾筆，當時最低價離進場價多遠（平均）—— 要追幾毛才追得上。
        "avg_miss_pct": round(sum(p for p in known if p > 0) / max(len(known) - len(filled), 1), 3)
        if len(known) > len(filled) else None,
    }


def trailing_losses(amounts: list[float]) -> int:
    """從最後一筆往前數，連續幾筆是虧的。

    閘門（signals.RiskGate）和覆盤的規則重跑（replay_rules）都要算這個。
    兩邊各寫一份的話，有一天會走偏 —— 而走偏的那天，覆盤算出來的
    「照規則會做幾筆」就不再是閘門真正會做的事，那整個模擬就沒有意義了。
    """
    n = 0
    for amount in reversed(amounts):
        if amount < 0:
            n += 1
        else:
            break
    return n


def replay_rules(outcomes: list[Outcome]) -> dict:
    """照風控閘門的規則把一天重跑一次，回傳實際會做到的那幾筆。

    為什麼不能只取前 N 筆（日報本來就是這樣算的，而那會算錯）：
    閘門看的是**已實現**損益與連敗筆數，而那取決於某一筆發訊號的時候，前面
    幾筆有沒有已經出場。所以要照訊號順序走，每一筆都用「此刻已出場的那些」
    去判斷閘門開不開。

    2026-10-01 就是這個差別第一次有代價的日子：五個訊號依序是四個停損 +
    最後一個目標。
      - 全部五筆：          -6,730 元
      - 日報的「前 4 筆」：  -12,622 元
      - 照完整規則：連三敗在第三筆之後就關閘，第 4、5 個訊號都不會做
                             → -9,515 元，3 筆收工
    日報少講了 3,107 元，而且少講的方向是「看起來更慘」。連敗停手那條規則
    今天其實是賺到的 —— 它擋掉了第四個停損。而它也擋掉了唯一的贏家。
    兩件事都要算進去，才知道這條線該訂在哪。

    exit_at 缺的那幾筆保守處理：當成「還沒出場」，也就是不計入閘門看到的
    已實現損益。寧可讓閘門晚關，不要讓它早關 —— 早關會讓這個模擬
    憑空少掉幾筆虧損，把結果講得比實際好。
    """
    r = config.RISK
    cap_trades = r["max_trades_per_day"]
    cap_loss = abs(r["max_daily_loss"])
    cap_streak = r["max_consecutive_losses"]

    ordered = sorted(outcomes, key=lambda o: str(o.time))
    taken: list[Outcome] = []
    blocked: list[tuple[Outcome, str]] = []
    reason = ""
    for o in ordered:
        if not reason:
            # 這一刻已經出場的那些，才算「已實現」。
            # 隔天才出場的（exit_date 有值）那天一定還沒實現 —— 它的 exit_at
            # 是隔天的時間，拿來跟今天的訊號時間比會把它當成早就出場了。
            closed = [t for t in taken if t.exit_at and not t.overnight
                      and str(t.exit_at) <= str(o.time)]
            realised = sum(t.net_amount for t in closed)
            streak = trailing_losses([t.net_amount for t in closed])
            if len(taken) >= cap_trades:
                reason = f"已達當日交易筆數上限 {cap_trades} 筆"
            elif realised <= -cap_loss:
                reason = f"當日實現虧損 {realised:,.0f} 元，觸及上限 {cap_loss:,} 元"
            elif streak >= cap_streak:
                reason = f"連續 {streak} 筆虧損，觸及上限 {cap_streak} 筆"
        if reason:
            blocked.append((o, reason))
        else:
            taken.append(o)

    return {
        "taken": taken,
        "blocked": blocked,
        "closed_reason": reason,
        "net_amount": sum(o.net_amount for o in taken),
        "total_r": round(sum(o.r_multiple for o in taken), 2),
        "missed_amount": sum(o.net_amount for o, _ in blocked),
    }


def summarise(outcomes: list[Outcome]) -> dict:
    """勝率與賺賠比。淨值一律以扣掉來回成本後計算。"""
    n = len(outcomes)
    if not n:
        return {"n": 0}
    wins = [o for o in outcomes if o.is_win]
    losses = [o for o in outcomes if not o.is_win]
    avg = lambda xs: sum(xs) / len(xs) if xs else 0.0
    avg_win = avg([o.net_pct for o in wins])
    avg_loss = avg([o.net_pct for o in losses])
    return {
        "n": n,
        "wins": len(wins),
        "win_rate": round(len(wins) / n * 100, 1),
        "avg_win_pct": round(avg_win, 3),
        "avg_loss_pct": round(avg_loss, 3),
        "payoff": round(avg_win / abs(avg_loss), 2) if avg_loss else None,
        "total_net_pct": round(sum(o.net_pct for o in outcomes), 3),
        "avg_r": round(avg([o.r_multiple for o in outcomes]), 2),
        "by_result": {r: sum(1 for o in outcomes if o.result == r)
                      for r in (TARGET, STOP, FLAT)},
    }
