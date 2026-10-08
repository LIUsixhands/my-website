"""
review.py — 盤後覆盤。收盤後 14:00 跑一次。

這是整套系統最有價值的一層。它做兩件事：
  1. 把「系統發了什麼訊號」和「你實際做了什麼」擺在一起對照
  2. 機械式地列出你今天違反了哪幾條自己訂的規則

產出 journal/YYYYMMDD.md。接到你既有的 Google Drive 交易日誌流程後，
讓排程的 Claude 讀整個 journal/ 目錄做跨日稽核 —— 單日看不出壞習慣，
一個月的日誌看得出來。
"""
import argparse
import json
import logging
from datetime import datetime

import config

log = logging.getLogger("review")


def load_signals() -> tuple[list[dict], dict]:
    """回傳 (訊號清單, 當日狀態)。

    沒有 state.json 時一定要回傳兩個值。原本只回傳 []，呼叫端做
    `signals, state = load_signals()` 會直接 ValueError ——
    也就是「今天沒發任何訊號」的那些日子，覆盤根本產不出來。
    """
    if not config.STATE_FILE.exists():
        return [], {}
    s = json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
    today = datetime.now().strftime("%Y-%m-%d")
    if s.get("date") != today:
        log.warning("state.json 是 %s 的，不是今天的，視為今日無訊號紀錄", s.get("date"))
        return [], {}
    return s.get("signals", []), s


def load_carried() -> list[dict]:
    """之前留倉、今天要回推結局的那幾筆（v6）。

    正常情況：今天 signals.py 啟動時已經從昨天的 state 搬進 state["carried"]。
    但如果今天**沒開監看**，state.json 還是昨天的 —— 那就從它直接挑出可以
    抱兩天、盤中沒判定結束的那幾筆。不做這一步，那幾筆的結局永遠不會進
    outcomes.csv，而且不會有任何錯誤訊息。
    """
    if not config.STATE_FILE.exists():
        return []
    s = json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
    today = datetime.now().strftime("%Y-%m-%d")
    date = str(s.get("date", ""))
    if date == today:
        return list(s.get("carried", []))
    if date > today:
        return []
    out = []
    for sig in s.get("signals", []):
        if int(sig.get("max_hold_days") or 1) < 2:
            continue
        if sig.get("live_result") in ("停損", "目標"):
            continue
        out.append(dict(sig, carry_from=date))
    # 平日休市那天電腦照樣開了監看：留倉被搬進那天的 carried，但那天沒開盤。
    out += [dict(c) for c in s.get("carried", [])
            if c.get("carry_from") and not c.get("live_result")]
    if out:
        log.warning("今天沒開監看；從 %s 的 state.json 補回留倉 %d 筆", date, len(out))
    return out


def resolve_carried(broker, carried: list[dict], through: str | None = None) -> list:
    """留倉的那幾筆用「發訊號那天 + 下一個交易日」的 K 棒回推。

    按發訊號的日期分組再丟給 resolve_all —— 大盤欄位要查的是**那一天**的大盤。
    """
    import outcome as oc
    through = through or datetime.now().strftime("%Y-%m-%d")
    groups: dict[str, list] = {}
    for c in carried:
        groups.setdefault(str(c.get("carry_from") or ""), []).append(c)
    out = []
    for day, sigs in sorted(groups.items()):
        if not day:
            log.warning("留倉紀錄沒有 carry_from，無法回推：%s",
                        "、".join(str(c.get("code")) for c in sigs))
            continue
        out += oc.resolve_all(broker, sigs, day, through=through)
    return out


def _trade_code(t):
    return getattr(getattr(t, "contract", None), "code", None)


def _deal_price(t) -> float:
    """成交均價；拿不到就退回委託價。

    原本寫成 `deal_quantity and price`，那是個真值運算式，
    未成交時印 0、成交時印委託價，兩種情況都不是成交均價。
    """
    st = getattr(t, "status", None)
    for attr in ("deal_price", "modified_price", "avg_price"):
        v = getattr(st, attr, None)
        if v:
            return float(v)
    return float(getattr(getattr(t, "order", None), "price", 0) or 0)


def audit(signals: list[dict], trades: list, state: dict) -> list[str]:
    """紀律稽核：只看有沒有違規，不評論賺賠。賺錢的違規也是違規。"""
    issues = []
    signal_codes = {s["code"] for s in signals}
    traded_codes = {c for c in (_trade_code(t) for t in trades) if c}

    off_plan = traded_codes - signal_codes
    if off_plan:
        issues.append(f"❌ 做了計畫外的標的：{'、'.join(sorted(off_plan))}"
                      f" —— 這是盤中臨時起意，不是系統。")

    if state.get("closed") and trades:
        issues.append(f"❌ 風控閘門已因「{state.get('closed_reason', '')}」關閉，"
                      f"但當日仍有成交紀錄。這是最危險的一條。")

    # 一檔 = 一筆當沖來回（SIGNAL.max_signals_per_symbol = 1 保證同檔一天只發一次）
    if len(traded_codes) > config.RISK["max_trades_per_day"]:
        issues.append(f"❌ 交易檔數 {len(traded_codes)} 超過上限 "
                      f"{config.RISK['max_trades_per_day']}。")

    if len(signals) > config.RISK["max_signals_per_day"]:
        issues.append(f"❌ 訊號數 {len(signals)} 超過上限 "
                      f"{config.RISK['max_signals_per_day']} —— 風控閘門沒有生效，請查 state.json。")

    oversized = [s["code"] for s in signals if s.get("oversized")]
    if oversized:
        issues.append(f"⚪ 單筆風險超標的訊號：{'、'.join(sorted(set(oversized)))}"
                      f" —— 一張的停損金額就超過 {config.RISK['per_trade_risk']:,} 元，"
                      f"如果做了，記下為什麼。")

    skipped = signal_codes - traded_codes
    if skipped:
        issues.append(f"⚪ 有訊號但沒做：{'、'.join(sorted(skipped))}"
                      f" —— 不算違規，但要寫下當時為什麼沒做。")

    if not issues:
        issues.append("✅ 今日無違規紀錄。")
    return issues


def _connect():
    """連券商拿帳務。連不上就回 (None, None, 說明) —— 覆盤還是要產出來。

    帳務查不到的日子照樣要有日誌，否則 journal/ 會缺日，跨日稽核就看不出連續性。
    """
    try:
        from broker import Broker
        broker = Broker()
    except Exception as e:
        log.warning("無法連線券商：%s", e)
        return [], None, f"⚠️ 無法連線券商（{e}），成交與損益欄位為空，請自行補上。", None
    trades = broker.trades_today()
    pnl = broker.realized_pnl_today()
    notes = []
    if trades is None:
        notes.append("⚠️ 成交查詢失敗，當日成交紀錄未知（不是「沒有成交」）。")
        trades = []
    if pnl is None:
        notes.append("⚠️ 損益查詢失敗，當日實現損益未知（不是 0）。")
    return trades, pnl, "　".join(notes), broker


def render(signals: list[dict], trades: list, state: dict,
           pnl: float | None, note: str = "", outcomes: list | None = None,
           carried: list | None = None) -> list[str]:
    """把覆盤內容算成 Markdown 行。抽出來讓 dryrun.py 也能用同一份版型。"""
    pnl_text = f"{pnl:,.0f} 元" if pnl is not None else "未知（查詢失敗）"
    if state.get("closed"):
        gate_text = "已關閉 — " + state.get("closed_reason", "")
    elif state:
        gate_text = "全日維持開啟"
    else:
        gate_text = "無紀錄（signals.py 今天沒跑過？）"

    lines = [
        f"# 當沖覆盤 {datetime.now():%Y-%m-%d}",
        "",
        f"- 系統訊號數：{len(signals)}",
        f"- 實際成交筆數：{len(trades)}",
        f"- 當日實現損益：{pnl_text}",
        f"- 來回成本基準：{config.round_trip_cost_pct():.4f}%",
        f"- 風控閘門：{gate_text}",
    ]
    if note:
        lines += ["", note]
    lines += [
        "",
        "## 一、系統訊號",
        "",
        "| 時間 | 代號 | 進場 | 停損 | 目標 | 建議張數 | 量能倍數 |",
        "|------|------|------|------|------|----------|----------|",
    ]
    for s in signals:
        lines.append(f"| {s['time']} | {s['code']} | {s['entry']:.2f} | {s['stop']:.2f} | "
                     f"{s['target']:.2f} | {s['lots']} | {s['volume_surge']:.2f}x |")
    if not signals:
        lines.append("| — | — | — | — | — | — | — |")

    lines += outcome_section(signals, outcomes)
    lines += carried_section(carried)

    lines += ["", "## 三、實際成交", "",
              "| 代號 | 買賣 | 成交均價 | 成交量 | 狀態 |",
              "|------|------|----------|--------|------|"]
    for t in trades:
        o = getattr(t, "order", None)
        st = getattr(t, "status", None)
        lines.append(
            f"| {_trade_code(t) or '?'} | {getattr(o, 'action', '?')} | "
            f"{_deal_price(t):.2f} | {getattr(st, 'deal_quantity', 0)} | "
            f"{getattr(st, 'status', '?')} |")
    if not trades:
        lines.append("| — | — | — | — | — |")

    lines += ["", "## 四、紀律稽核（機器判定，不含情緒）", ""]
    lines += [f"- {i}" for i in audit(signals, trades, state)]

    lines += [
        "", "## 五、手寫欄位（當天寫，隔天不算數）", "",
        "**今天最想凹的那一筆是哪一筆？當下在想什麼？**", "", "> ", "",
        "**如果重來一次，哪一個決定會改？**", "", "> ", "",
        "**明天只改一件事，是什麼？**", "", "> ", "",
        "---", "",
        "*本紀錄為個人交易覆盤，非投資建議。*",
    ]

    return lines


def _fill_cell(o) -> str:
    """表格裡那一格：買得到 / 差多少 / 不知道。空白會被當成「沒事」，所以不留空。"""
    import outcome as oc
    pct = oc.fill_pct(o)
    if pct is None:
        return "？"
    return "\u2705" if pct <= 0 else f"\u2716 +{pct:.2f}%"


def _fill_text(fills: dict) -> str:
    if not fills.get("known"):
        return "無資料（當天沒收到報價，不代表買不到）"
    text = f"{fills['filled']}/{fills['known']} 筆（{fills['rate']}%）"
    if fills.get("avg_miss_pct") is not None:
        text += f"，買不到的平均要追 +{fills['avg_miss_pct']:.2f}%"
    if fills.get("unknown"):
        text += f"；另有 {fills['unknown']} 筆無資料"
    return text


def outcome_section(signals: list[dict], outcomes: list | None) -> list[str]:
    """訊號後來怎麼了。沒有這一段，20 天跑完也算不出勝率。"""
    lines = ["", "## 二、訊號結果（分鐘 K 回推，保守判定）", ""]
    # 先看有沒有訊號。沒有訊號卻說「未連線券商」，會讓人以為是故障 ——
    # 而「今天沒有任何一檔突破」才是最常見、也完全正常的情況。
    if not signals:
        lines.append("_今日無訊號（沒有任何一檔滿足進場條件）。這是正常的。_")
        return lines
    if outcomes is None:
        lines.append("_有訊號但未回推（未連線券商或未取得分鐘 K）。_")
        return lines
    if not outcomes:
        lines.append("_有訊號，但分鐘 K 不足以判定結果。_")
        return lines

    import outcome as oc
    lines += ["| 代號 | 結果 | 出場價 | R | 毛報酬% | 扣成本後% | 持有K棒 | 掛得到? |",
              "|------|------|--------|---|---------|-----------|---------|---------|"]
    for o in outcomes:
        lines.append(f"| {o.code} | {o.result} | {o.exit_price:.2f} | {o.r_multiple:+.2f} "
                     f"| {o.gross_pct:+.3f} | {o.net_pct:+.3f} | {o.bars} "
                     f"| {_fill_cell(o)} |")

    # 留倉中的不是結局：出場價只是今天收盤，報酬是未實現的。不進勝率。
    holding = [o for o in outcomes if o.result == oc.CARRY]
    outcomes = [o for o in outcomes if o.result != oc.CARRY]
    if holding:
        lines += ["", f"- 留倉過夜 **{len(holding)} 筆**（上表「{oc.CARRY}」那幾列的出場價是"
                  "今天收盤、報酬是未實現的）—— 明天收盤後才有結局，不計入今天的勝率。"]
    if not outcomes:
        return lines

    st = oc.summarise(outcomes)
    fills = oc.fill_stats(outcomes)
    rules = oc.replay_rules(outcomes)
    payoff = f"{st['payoff']}" if st.get("payoff") else "—（今日無虧損樣本）"
    lines += [
        "",
        f"- 勝率（扣成本後為正才算贏）：**{st['win_rate']}%**（{st['wins']}/{st['n']}）",
        f"- 掛進場價買得到：**{_fill_text(fills)}**"
        f"　—— 買不到的筆數不會進你的帳戶，這個數字和勝率要一起看。",
        f"- 平均賺 {st['avg_win_pct']:+.3f}%　平均賠 {st['avg_loss_pct']:+.3f}%　賺賠比 {payoff}",
        f"- 當日合計（扣成本後）：**{st['total_net_pct']:+.3f}%**　平均 {st['avg_r']:+.2f}R",
        f"- 結局分佈：{st['by_result']}",
        "",
        "> 判定偏保守：同一根 K 同時觸及停損與目標時判停損；成交價以訊號價計，"
        "未計滑價；13:25 前一律平倉。**實際成績只會比這裡差，不會更好。**",
    ]
    lines += rules_section(rules)
    return lines


def carried_section(carried: list | None) -> list[str]:
    """昨天留倉、今天才結束的那幾筆。它們的 date 是昨天，結局是今天。"""
    if not carried:
        return []
    import outcome as oc
    lines = ["", "## 二之一、昨日留倉的結局", "",
             "| 代號 | 訊號日 | 結果 | 出場日 | 出場價 | R | 扣成本後% | 持有期最高% |",
             "|------|--------|------|--------|--------|---|-----------|-------------|"]
    for o in carried:
        mfe = f"{o.mfe_pct:+.2f}" if o.mfe_pct is not None else "？"
        lines.append(f"| {o.code} | {o.date} | {o.result} | {o.exit_date or '—'} | "
                     f"{o.exit_price:.2f} | {o.r_multiple:+.2f} | {o.net_pct:+.3f} | {mfe} |")
    if any(o.result == oc.CARRY for o in carried):
        lines += ["", f"_「{oc.CARRY}」= 還拿不到下一個交易日的 K 棒，明天重跑會補上。_"]
    lines += ["", f"> 留倉的成本以證交稅全額計（來回 "
              f"{config.round_trip_cost_pct(overnight=True):.3f}%）。"
              "隔天跳空穿過停損的，出場價記開盤價，不記停損價。"]
    return lines


def _amount(rows) -> float:
    """金額一律「各筆先四捨五入再相加」—— 和逐筆明細用同一個約定。
    兩邊各算各的，遲早會差一塊錢，而差一塊錢會讓人懷疑哪個數字才是對的。"""
    return sum(round(o.net_amount) for o in rows)


def rules_section(rules: dict) -> list[str]:
    """照完整規則今天會做到哪幾筆。

    上面那一段算的是「每個訊號後來怎麼了」，而不是「你照規則做得到哪幾筆」。
    兩者在打滿上限或觸及紅線的日子會差很多，而那正是最需要看清楚的日子。
    """
    if not rules.get("blocked"):
        return ["", "_今日沒有任何訊號被風控擋掉，上面的數字就是照規則的數字。_"]
    lines = ["", "### 照完整規則（筆數上限 + 日虧上限 + 連敗停手）", "",
             f"- 實際會做：**{len(rules['taken'])} 筆**，"
             f"{_amount(rules['taken']):+,.0f} 元（{rules['total_r']:+.2f}R）",
             f"- 關閘原因：{rules['closed_reason']}",
             f"- 被擋掉的那幾筆合計："
             f"{_amount([o for o, _ in rules['blocked']]):+,.0f} 元", ""]
    lines += ["| 代號 | 時間 | 結果 | 金額 | 做了嗎 |",
              "|------|------|------|------|--------|"]
    for o in rules["taken"]:
        lines.append(f"| {o.code} | {o.time} | {o.result} | "
                     f"{round(o.net_amount):+,.0f} | 做 |")
    for o, why in rules["blocked"]:
        lines.append(f"| {o.code} | {o.time} | {o.result} | "
                     f"{round(o.net_amount):+,.0f} | 擋（{why}） |")
    lines += ["",
              "> 被擋掉的那幾筆是賺的時候，這條線的代價就是那個數字；是賠的時候，"
              "這條線替你省下那個數字。**兩邊都要看，才知道線該訂在哪。**"]
    return lines


def write_journal(lines: list[str], date: str | None = None) -> "Path":
    from pathlib import Path
    date = date or datetime.now().strftime("%Y%m%d")
    config.JOURNAL_DIR.mkdir(exist_ok=True)
    path = Path(config.JOURNAL_DIR) / f"{date}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def format_push(signals: list[dict], outcomes, history: list,
                carried: list | None = None) -> str:
    """推到手機上的當日結果。

    覆盤寫進 journal 而沒有人看，等於沒寫。這則訊息的工作是讓你在手機上
    兩秒鐘看完今天的結論，細節留在 journal 裡。
    """
    import outcome as oc
    from signals import RESOLUTION_MARK

    date = datetime.now().strftime("%Y-%m-%d")
    head = f"\U0001f4ca {date} 收盤覆盤"
    names = {str(s.get("code")): (s.get("name") or "") for s in signals}
    lines = [head, "────────────────"]

    if not signals:
        lines.append("今天沒有任何訊號 —— 這是正常的一天，不是系統壞了。")
    elif outcomes is None:
        lines.append(f"今天有 {len(signals)} 個訊號，但沒有回推到結局"
                     "（未連線券商或拿不到分鐘 K）。")
    elif not outcomes:
        lines.append(f"今天有 {len(signals)} 個訊號，但一筆都回推不出來。")
    else:
        holding = [o for o in outcomes if o.result == oc.CARRY]
        outcomes = [o for o in outcomes if o.result != oc.CARRY]
        day = oc.summarise(outcomes) if outcomes else {"wins": 0, "n": 0}
        lines.append(f"今日 {len(signals)} 個訊號｜"
                     f"{day['wins']} 勝 {day['n'] - day['wins']} 敗"
                     + (f"｜留倉 {len(holding)}" if holding else ""))
        amount = lambda rows: sum(round(o.net_amount) for o in rows)
        lines.append(f"合計 {sum(o.r_multiple for o in outcomes):+.2f}R　"
                     f"{amount(outcomes):+,.0f} 元")
        today_fill = oc.fill_stats(outcomes)
        if today_fill.get("known"):
            lines.append(f"掛進場價買得到 {today_fill['filled']}/{today_fill['known']} 筆")
        # 「照規則今天真的會做到哪幾筆」要把閘門整套跑一遍，不是取前 N 筆。
        # 原本寫成 outcomes[:cap]，那只算了筆數上限，沒算日虧上限與連敗停手 ——
        # 2026-10-01 五訊號（四停損 + 最後一個目標）下，前 4 筆算出 -12,622 元，
        # 而連敗停手其實在第三筆之後就關閘了，真正的數字是 -9,515 元／3 筆。
        # 日報把那一天講得比實際慘 3,107 元。
        rules = oc.replay_rules(outcomes)
        if rules["blocked"]:
            lines.append(f"照完整規則只做 {len(rules['taken'])} 筆："
                         f"{amount(rules['taken']):+,.0f} 元")
            lines.append(f"　（{rules['closed_reason']}）")
        lines.append("")
        for o in outcomes:
            label = f"{o.code} {names.get(o.code, '')}".strip()
            lines.append(f"{RESOLUTION_MARK.get(o.result, '')} {label}　{o.result}")
            lines.append(f"　{o.r_multiple:+.2f}R　{round(o.net_amount):+,.0f} 元")
        for o in holding:
            label = f"{o.code} {names.get(o.code, '')}".strip()
            lines.append(f"\U0001f4e6 {label}　留倉過夜")
            lines.append(f"　收盤 {o.exit_price:.2f}（未實現 {o.gross_pct:+.2f}%）"
                         f"　停損 {o.stop:.2f}／目標 {o.target:.2f}")

    if carried:
        lines += ["────────────────", "昨日留倉的結局"]
        for o in carried:
            if o.result == oc.CARRY:
                lines.append(f"\U0001f4e6 {o.code}　還沒有隔天的 K 棒，明天重跑補上")
                continue
            lines.append(f"{RESOLUTION_MARK.get(o.result, '')} {o.code}　{o.result}"
                         f"（{o.exit_date or '當天'}）")
            lines.append(f"　{o.r_multiple:+.2f}R　{round(o.net_amount):+,.0f} 元")

    if history:
        lines += cumulative_lines(history)

    lines += [
        "────────────────",
        f"勝＝扣掉 {config.round_trip_cost_pct():.3f}% 來回成本後為正",
        "金額依訊號的建議張數與目前成本設定估算。",
        "驗證期未下單，這不是你的實際損益。",
    ]
    return "\n".join(lines)


def cumulative_lines(history: list) -> list[str]:
    """日報最下面的累計：**只算目前這一版規則**，全部版本只留一行參考。

    以前是 9/24 起每一筆全部相加 —— 停損 1.5% 跟 3%、單筆風險 2,000／3,000／
    4,000 元、當沖跟抱兩天全混在一起。那個數字回答不了「現在這套規則好不好」，
    而手機上每天看到的就是它。使用者 10-07 看到之後決定改成分版本。
    """
    import outcome as oc
    version = config.RULESET
    current = [o for o in history if o.ruleset == version]
    lines = ["────────────────"]
    if current:
        days = len({o.date for o in current})
        total = oc.summarise(current)
        lines += [
            f"{version} 累計 {days} 個有訊號的交易日／{total['n']} 筆"
            f"（{min(o.date for o in current)} 起）",
            f"勝率 {total['win_rate']}%　平均 {total['avg_r']:+.2f}R",
            f"掛進場價買得到 {_fill_text(oc.fill_stats(current))}",
            f"平均賺 {total['avg_win_pct']:+.2f}%　"
            f"平均賠 {total['avg_loss_pct']:+.2f}%",
            f"{version} 累計損益 {sum(round(o.net_amount) for o in current):+,.0f} 元",
        ]
    else:
        lines.append(f"{version} 還沒有結束的交易 —— 累計從第一筆結束的交易開始算。")
    older = len(history) - len(current)
    if older:
        lines.append(f"（全部版本合計 {len(history)} 筆　"
                     f"{sum(round(o.net_amount) for o in history):+,.0f} 元 —— "
                     "不同規則混算，只供參考）")
    return lines


def push_summary(signals: list[dict], outcomes, carried: list | None = None) -> None:
    """推播失敗不該讓覆盤跟著失敗 —— journal 已經寫好了。"""
    from signals import notify
    import outcome as oc
    try:
        history = oc.load_csv()
    except Exception as e:
        log.warning("讀不到 outcomes.csv，累計數字先略過：%s", e)
        history = []
    try:
        notify(format_push(signals, outcomes, history, carried))
    except Exception as e:
        log.error("當日結果推播失敗：%s", e)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="盤後覆盤")
    ap.add_argument("--no-push", action="store_true",
                    help="不要把結果推到 Telegram（同一天重跑時用，免得重複推播）")
    return ap.parse_args(argv)


FAILURE_DETAIL_CHARS = 400


def format_failure(exc: BaseException) -> str:
    """覆盤失敗也要出聲。

    14:00 的排程如果安靜地掛掉，你只會發現「今天沒收到日報」，而分不出是
    「今天沒訊號」還是「程式當了」。這兩件事該做的處置完全相反 ——
    後者代表**今天的結果沒進 outcomes.csv，20 天的統計就少一天**，而且補不回來。
    """
    detail = f"{type(exc).__name__}: {exc}".strip()
    if len(detail) > FAILURE_DETAIL_CHARS:
        detail = detail[:FAILURE_DETAIL_CHARS] + "…（完整訊息在電腦上）"
    return "\n".join([
        f"\u26a0\ufe0f {datetime.now().strftime('%Y-%m-%d %H:%M')} 盤後覆盤失敗",
        "────────────────",
        detail,
        "────────────────",
        "今天的結果沒有記進 outcomes.csv —— 這一天的資料會缺，而且補不回來。",
        "到電腦上手動跑一次 python review.py 就會看到完整錯誤。",
    ])


def push_failure(exc: BaseException) -> None:
    """推失敗通知。推播自己壞掉也不能蓋掉原始錯誤，所以整段包起來。"""
    from signals import notify
    try:
        notify(format_failure(exc))
    except Exception as e:
        log.error("連失敗通知都送不出去：%s", e)


def run(args) -> None:
    import outcome as oc
    signals, state = load_signals()
    trades, pnl, note, broker = _connect()
    outcomes = None
    carried_out = None
    if broker is not None and signals:
        outcomes = oc.resolve_all(broker, signals)
        # 留倉中的那幾筆還沒有結局，不寫 —— 明天回推出來才寫。
        oc.append_csv([o for o in outcomes if o.result != oc.CARRY])
    carried = load_carried()
    if broker is not None and carried:
        carried_out = resolve_carried(broker, carried)
        oc.append_csv([o for o in carried_out if o.result != oc.CARRY])
    if broker is not None:
        # 被上限擋掉的候選也回推一份，寫到另一份檔。
        # 刻意不進日報 —— 每天看到「你少賺了多少」只會讓人想把上限拆掉。
        try:
            pending = oc.load_candidates()
            if pending:
                oc.append_candidates_csv(oc.resolve_candidates(broker, pending))
        except Exception as e:                   # 候選壞掉不可以讓日報產不出來
            log.warning("候選回推失敗（不影響日報）：%s", e)
    lines = render(signals, trades, state, pnl, note, outcomes, carried_out)
    path = write_journal(lines)
    print("\n".join(lines))
    print(f"\n→ 已寫入 {path}")
    if not args.no_push:
        push_summary(signals, outcomes, carried_out)


def main(argv=None):
    args = parse_args(argv)
    try:
        run(args)
    except Exception as exc:
        if not args.no_push:
            push_failure(exc)
        raise


if __name__ == "__main__":
    main()
