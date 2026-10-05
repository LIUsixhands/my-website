"""
analyse.py — 把累積下來的 outcomes.csv 變成可以回答問題的數字。

20 天跑完要決定的事：一天做幾筆、只做前 N 名嗎、綠盤日該不該做、
量能倍數高的是不是真的比較好。這支程式就是去回答那些問題的。

但它最重要的工作是**不要給出看起來像答案的雜訊**。

一個用 12 筆算出來的勝率，印在螢幕上和用 2000 筆算出來的長得一模一樣 ——
60.0%。差別全在看不見的地方。所以這裡每一個數字後面都強制帶著它的
95% 信賴區間，而兩組的區間只要重疊，就直接印「分不出來」。

這不是謹慎，是算術：n=12 的勝率，區間寬度超過 ±27 個百分點。
那個數字唯一能支持的結論是「還不知道」。

用法：
    python analyse.py                  # 看 outcomes.csv
    python analyse.py --file 別的.csv
"""
import argparse
import math
from collections import defaultdict

import config
import outcome as oc

# 勝率的 95% 信賴區間用常態近似，1.96 個標準誤。
Z = 1.96

# 低於這個數字連區間都不印 —— 印了只會讓人盯著中間那個點看。
TOO_FEW = 5


def win_rate_ci(wins: int, n: int) -> tuple[float, float, float]:
    """回傳 (勝率%, 下界%, 上界%)，用 Wilson score 區間。n=0 時全部回 0。

    **不能用常態近似（Wald）**，而我第一版就是用它，然後馬上在真實形狀的
    資料上炸了：8 筆全輸時 p=0，`sqrt(p(1-p)/n)` 也是 0，於是區間變成
    (0%, 0%) —— 寬度為零。接著「兩組區間有沒有重疊」就會說「沒有重疊，
    這兩組真的有差」。

    8 筆全輸當然不代表勝率確定是 0%。那正是這支程式存在的目的 ——
    它卻會印出一個比任何數字都更有自信的假答案。

    Wilson 區間在 p=0 和 p=1 時仍然有寬度（8 筆全輸 → 0%~24.3%），
    小樣本時也不會像 Wald 那樣偏窄。
    """
    if n <= 0:
        return 0.0, 0.0, 0.0
    p = wins / n
    denom = 1 + Z * Z / n
    centre = (p + Z * Z / (2 * n)) / denom
    half = Z / denom * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))
    lo, hi = max(0.0, centre - half), min(1.0, centre + half)
    return round(p * 100, 1), round(lo * 100, 1), round(hi * 100, 1)


def signal_order(rows: list) -> dict[int, list]:
    """每一筆是它那天的第幾個訊號。

    outcomes.csv 沒有直接記「第幾個」，但同一天依時間排序就是。
    這一欄回答使用者問的那題：「最好的那個能不能排第一個」——
    不能，但如果後面的訊號系統性地比較好，那「等一下再做」就是有根據的。
    """
    by_day = defaultdict(list)
    for o in rows:
        by_day[o.date].append(o)
    out = defaultdict(list)
    for day_rows in by_day.values():
        for i, o in enumerate(sorted(day_rows, key=lambda r: str(r.time)), 1):
            out[i].append(o)
    return dict(out)


def _bucket(rows: list, key, labels: list) -> dict:
    out = {label: [] for label in labels}
    for o in rows:
        label = key(o)
        if label is not None:
            out.setdefault(label, []).append(o)
    return out


def by_ruleset(rows: list) -> dict:
    """按規則版本分組。**混在一起算等於把兩把不同的尺量出來的數字相加。**

    09-29 改 R 值、10-02 改停損 —— 每一次都讓前後的資料不能直接比。
    有這一欄才能「邊改邊累積」，而不是每改一次就要重新等 20 天。
    """
    out: dict = {}
    for o in rows:
        out.setdefault(o.ruleset or "（未標版本）", []).append(o)
    return dict(sorted(out.items()))


def by_rank(rows: list) -> dict:
    """盤前名次。0 = 不知道（舊紀錄，或當天沒跑盤前選股）。"""
    def key(o):
        if not o.rank:
            return None
        return "名次 1-5" if o.rank <= 5 else ("名次 6-10" if o.rank <= 10 else "名次 11+")
    return _bucket(rows, key, ["名次 1-5", "名次 6-10", "名次 11+"])


def market_known_before(o) -> float | None:
    """這一筆的訊號發出**之前**就已知的大盤漲跌 %。沒有就回 None。

    這裡原本直接用 09:15 的大盤，docstring 寫著「這是唯一在訊號發出前就已知
    的因子」。v1–v3 訊號全部發在 09:17 之後，那時是對的；v4 起 09:05 就批次
    發完，09:15 變成事後十分鐘的資訊。拿事後資訊分組，再拿分組結果去定「大盤
    走弱就不做」的規則，就是未來函數 —— 回測好看，實盤用不了。

    所以逐筆判斷：
      1. 有決策當下的大盤（mkt_signal_pct，v5 起才有）→ 用它
      2. 沒有，但訊號時間晚於 09:15 → 09:15 那個數字對這一筆是事前的，可以用
      3. 都不是 → None。寧可少一筆，也不要混進一筆事後資訊
    """
    from broker import MARKET_EARLY_AT
    if o.mkt_signal_pct is not None:
        return o.mkt_signal_pct
    if o.mkt_open_pct is not None and (o.time or "")[:5] > MARKET_EARLY_AT:
        return o.mkt_open_pct
    return None


def by_market(rows: list) -> dict:
    """訊號發出前就已知的大盤方向。怎麼判「事前」見 market_known_before()。"""
    def key(o):
        pct = market_known_before(o)
        if pct is None:
            return None
        return "大盤開高" if pct > 0 else "大盤開低"
    return _bucket(rows, key, ["大盤開高", "大盤開低"])


def by_volume_surge(rows: list) -> dict:
    def key(o):
        if o.volume_surge is None:
            return None
        return "量能 <3x" if o.volume_surge < 3 else ("量能 3-5x" if o.volume_surge < 5
                                                      else "量能 5x+")
    return _bucket(rows, key, ["量能 <3x", "量能 3-5x", "量能 5x+"])


def by_fill(rows: list) -> dict:
    """掛進場價買不買得到。買不到的那些不會進你的帳戶 —— 它們的勝率再高也沒用。"""
    def key(o):
        pct = oc.fill_pct(o)
        if pct is None:
            return None
        return "掛得到" if pct <= 0 else "掛不到"
    return _bucket(rows, key, ["掛得到", "掛不到"])


def stopped_but_reached_target(rows: list) -> dict:
    """被停損的那些，當天後來有沒有還是走到目標。

    這是「停損是不是太緊」唯一直接的證據。比例高 = 你被雜訊掃出場，
    而不是看錯方向。10-02 把停損加上結構線，就是為了這個 —— 但**要不要
    再放寬，得看這個數字，不是看誰講話比較大聲**。
    """
    stopped = [o for o in rows if o.result == oc.STOP and o.target_after_stop is not None]
    if not stopped:
        return {"n": 0}
    hit = [o for o in stopped if o.target_after_stop]
    rate, lo, hi = win_rate_ci(len(hit), len(stopped))
    return {"n": len(stopped), "hit": len(hit), "rate": rate, "lo": lo, "hi": hi}


def group_stats(rows: list) -> dict:
    wins = sum(1 for o in rows if o.is_win)
    rate, lo, hi = win_rate_ci(wins, len(rows))
    avg_r = round(sum(o.r_multiple for o in rows) / len(rows), 2) if rows else 0.0
    return {"n": len(rows), "wins": wins, "rate": rate, "lo": lo, "hi": hi,
            "avg_r": avg_r,
            "amount": sum(round(o.net_amount) for o in rows)}


def overlapping(groups: dict) -> bool:
    """任兩組的信賴區間是否互相重疊。全部重疊 = 這個因子還分不出差別。"""
    usable = [group_stats(r) for r in groups.values() if len(r) >= TOO_FEW]
    if len(usable) < 2:
        return True
    lo = max(g["lo"] for g in usable)
    hi = min(g["hi"] for g in usable)
    return lo <= hi


def render_group(title: str, groups: dict, question: str) -> list[str]:
    lines = ["", f"## {title}", f"_{question}_", "",
             "| 分組 | 筆數 | 勝率（95% 區間） | 平均 R | 合計金額 |",
             "|---|---|---|---|---|"]
    shown = 0
    for label, rows in groups.items():
        if not rows:
            continue
        shown += 1
        g = group_stats(rows)
        if g["n"] < TOO_FEW:
            rate = f"— （n={g['n']}，太少）"
        else:
            rate = f"{g['rate']}%（{g['lo']}~{g['hi']}）"
        lines.append(f"| {label} | {g['n']} | {rate} | {g['avg_r']:+.2f} | "
                     f"{g['amount']:+,.0f} |")
    if not shown:
        lines.append("| — | 0 | 還沒有資料 | — | — |")
        return lines
    lines.append("")
    if overlapping(groups):
        lines.append("> **分不出來。** 各組的信賴區間互相重疊 —— 以目前的樣本，"
                     "這個因子沒有證據說哪一組比較好。再多跑幾天。")
    else:
        lines.append("> 各組的信賴區間**沒有**重疊。這是目前唯一可以說「真的有差」"
                     "的分組 —— 但仍然只是觀察，不是保證。")
    return lines


def report(rows: list) -> list[str]:
    if not rows:
        return ["# 當沖訊號分析", "",
                "_`outcomes.csv` 是空的或不存在。跑過幾天覆盤之後再來。_"]

    days = len({o.date for o in rows})
    total = oc.summarise(rows)
    fills = oc.fill_stats(rows)
    lines = [
        "# 當沖訊號分析", "",
        f"- 樣本：**{len(rows)} 筆**／{days} 個有訊號的交易日",
        f"- 整體勝率：**{total['win_rate']}%**"
        f"（{win_rate_ci(total['wins'], len(rows))[1]}~"
        f"{win_rate_ci(total['wins'], len(rows))[2]}）",
        f"- 平均 {total['avg_r']:+.2f}R　合計 "
        f"{sum(round(o.net_amount) for o in rows):+,.0f} 元",
        f"- 掛進場價買得到：{fills['filled']}/{fills['known']} 筆"
        if fills.get("known") else "- 掛進場價買得到：還沒有資料",
        "",
        "> 括號裡是 95% 信賴區間。**看區間，不要看中間那個數字** —— "
        "區間越寬代表樣本越少，而寬到一定程度時，中間那個數字沒有任何意義。",
    ]

    lines += render_group(
        "〇、規則版本", by_ruleset(rows),
        "改過規則的前後不能混算。這一組要是互相重疊，代表那次修改在目前的"
        "樣本下看不出差別 —— 那也是一個答案。")
    lines += render_group(
        "一、第幾個訊號", signal_order(rows),
        "「最好的能不能排第一個」—— 不能（訊號是事件，不是名單）。"
        "但如果後面的訊號系統性地比較好，「等一下再做」就有根據。")
    lines += render_group(
        "二、盤前名次", by_rank(rows),
        "「只做前幾名會不會比較好」—— 回答要不要砍監看名單。")
    lines += render_group(
        "三、訊號發出前的大盤方向", by_market(rows),
        "這套系統只做多。綠盤日逆風多少？只收訊號發出**之前**就已知的大盤 ——"
        "v4 起訊號 09:05 就發完，09:15 的大盤對那些訊號是事後資訊，不算進來。")
    lines += render_group(
        "四、量能倍數", by_volume_surge(rows),
        "量能門檻該訂多高。")
    lines += render_group(
        "五、掛不掛得到", by_fill(rows),
        "買不到的那些不會進你的帳戶 —— 它們的勝率再高也不算數。")

    stops = stopped_but_reached_target(rows)
    lines += ["", "## 六、停損之後，當天還是走到目標了嗎", "",
              "_「停損是不是太緊」唯一直接的證據。比例高 = 被雜訊掃出場，不是看錯方向。_", ""]
    if not stops["n"]:
        lines.append("_還沒有可判定的停損樣本。_")
    elif stops["n"] < TOO_FEW:
        lines.append(f"_只有 {stops['n']} 筆停損，太少，不給數字。_")
    else:
        lines.append(f"- **{stops['hit']}/{stops['n']} 筆**停損之後當天仍碰到目標"
                     f"（{stops['rate']}%，區間 {stops['lo']}~{stops['hi']}）")
        lines.append("")
        lines.append("> 區間下界若明顯高於 50%，才有理由再放寬停損。"
                     "**不到那個程度就不要動它** —— 停損是這套系統的地基。")

    lines += ["", "---", "",
              "*本分析只描述已發生的樣本，不預測未來，不構成投資建議。*"]
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="分析累積的當沖訊號結果")
    ap.add_argument("--file", default=None, help="要讀的 CSV（預設 outcomes.csv）")
    args = ap.parse_args()
    path = config.BASE_DIR / args.file if args.file else oc.OUTCOME_FILE
    rows = oc.load_csv(path)
    print(config.console_text("\n".join(report(rows))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
