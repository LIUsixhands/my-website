"""
review.py — 盤後覆盤。收盤後 14:00 跑一次。

這是整套系統最有價值的一層。它做兩件事：
  1. 把「系統發了什麼訊號」和「你實際做了什麼」擺在一起對照
  2. 機械式地列出你今天違反了哪幾條自己訂的規則

產出 journal/YYYYMMDD.md。接到你既有的 Google Drive 交易日誌流程後，
讓排程的 Claude 讀整個 journal/ 目錄做跨日稽核 —— 單日看不出壞習慣，
一個月的日誌看得出來。
"""
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
           pnl: float | None, note: str = "", outcomes: list | None = None) -> list[str]:
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
    lines += ["| 代號 | 結果 | 出場價 | R | 毛報酬% | 扣成本後% | 持有K棒 |",
              "|------|------|--------|---|---------|-----------|---------|"]
    for o in outcomes:
        lines.append(f"| {o.code} | {o.result} | {o.exit_price:.2f} | {o.r_multiple:+.2f} "
                     f"| {o.gross_pct:+.3f} | {o.net_pct:+.3f} | {o.bars} |")

    st = oc.summarise(outcomes)
    payoff = f"{st['payoff']}" if st.get("payoff") else "—（今日無虧損樣本）"
    lines += [
        "",
        f"- 勝率（扣成本後為正才算贏）：**{st['win_rate']}%**（{st['wins']}/{st['n']}）",
        f"- 平均賺 {st['avg_win_pct']:+.3f}%　平均賠 {st['avg_loss_pct']:+.3f}%　賺賠比 {payoff}",
        f"- 當日合計（扣成本後）：**{st['total_net_pct']:+.3f}%**　平均 {st['avg_r']:+.2f}R",
        f"- 結局分佈：{st['by_result']}",
        "",
        "> 判定偏保守：同一根 K 同時觸及停損與目標時判停損；成交價以訊號價計，"
        "未計滑價；13:25 前一律平倉。**實際成績只會比這裡差，不會更好。**",
    ]
    return lines


def write_journal(lines: list[str], date: str | None = None) -> "Path":
    from pathlib import Path
    date = date or datetime.now().strftime("%Y%m%d")
    config.JOURNAL_DIR.mkdir(exist_ok=True)
    path = Path(config.JOURNAL_DIR) / f"{date}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main():
    import outcome as oc
    signals, state = load_signals()
    trades, pnl, note, broker = _connect()
    outcomes = None
    if broker is not None and signals:
        outcomes = oc.resolve_all(broker, signals)
        oc.append_csv(outcomes)
    lines = render(signals, trades, state, pnl, note, outcomes)
    path = write_journal(lines)
    print("\n".join(lines))
    print(f"\n→ 已寫入 {path}")


if __name__ == "__main__":
    main()
