"""
preflight.py — 上線前的連線體檢。第一次跑、以及每次切換 SIMULATION 時執行一次。

    python3 preflight.py

這支程式的存在理由：整套系統對 Shioaji 回傳格式做了一堆假設
（欄位叫什麼、day_trade 是什麼值、分鐘 K 的 ts 是起點還是終點、
損益查不查得到）。那些假設錯了，**盤中不會報錯** —— 你只會得到一個
整天沉默、或是安靜地用錯誤水位算停損的系統。

它只讀不寫、不下單。逐項印出實際看到的值，讓你自己核對。
有任何 ❌ 會以 exit code 1 結束。
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import config

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

# 狀態符號：終端機印不出 emoji 時（Windows cp950）退回 ASCII 標記。
OK = config.symbol("✅", "[ OK ]")
WARN = config.symbol("⚠️ ", "[WARN]")
FAIL = config.symbol("❌", "[FAIL]")

SNAPSHOT_FIELDS = ("close", "high", "low", "total_volume", "average_price")
KBAR_FIELDS = ("ts", "High", "Low", "Volume")


@dataclass
class Result:
    status: str
    name: str
    detail: str

    def __str__(self):
        return f"{self.status} {self.name}\n   {self.detail}"


def check_config(_broker=None) -> Result:
    errs = config.validate()
    if errs:
        return Result(FAIL, "config 參數", "；".join(errs))
    mode = "模擬" if config.SIMULATION else "真錢"
    return Result(OK, "config 參數",
                  f"無矛盾。模式：{mode}（SIMULATION={'1' if config.SIMULATION else '0'}）"
                  f"，來回成本基準 {config.round_trip_cost_pct():.4f}%")


def check_contracts(broker) -> Result:
    stocks = broker.all_stocks()
    if not stocks:
        return Result(FAIL, "商品檔",
                      "抓不到任何股票合約。Contracts 可能還沒下載完（登入後需等待），"
                      "或 TSE/OTC 的屬性名稱與假設不同。")
    four = [c for c in stocks if getattr(c, "code", "").isdigit()
            and len(getattr(c, "code", "")) == 4]
    return Result(OK, "商品檔",
                  f"共 {len(stocks)} 檔，其中四碼普通股 {len(four)} 檔")


def check_day_trade_flag(broker) -> Result:
    """day_trade 的實際值分佈。screener 的第一道過濾整個靠它。"""
    stocks = broker.all_stocks()
    if not stocks:
        return Result(WARN, "當沖旗標", "沒有商品檔可檢查（見上一項）")

    counts: dict = {}
    for c in stocks:
        flag = broker.day_trade_flag(c)
        counts[flag] = counts.get(flag, 0) + 1
    dist = "、".join(f"{k}={v}" for k, v in sorted(counts.items()))
    tradable = sum(1 for c in stocks if broker.is_day_tradable(c))

    if counts.get("未知", 0) == len(stocks):
        return Result(FAIL, "當沖旗標",
                      f"全部都認不出來（{dist}）。`day_trade` 的值與假設的 "
                      f"Yes/No/OnlyBuy 不同，screener 會篩出 0 檔。請看實際值後修正 "
                      f"broker.day_trade_flag()。")
    if tradable == 0:
        return Result(FAIL, "當沖旗標",
                      f"分佈 {dist}，但可當沖判定為 0 檔 —— screener 會回空清單。")
    return Result(OK, "當沖旗標",
                  f"分佈 {dist}；依目前 allow_short={config.SIGNAL['allow_short']} "
                  f"判定可當沖 {tradable} 檔")


def check_snapshots(broker) -> Result:
    stocks = [c for c in broker.all_stocks()
              if getattr(c, "code", "").isdigit() and len(getattr(c, "code", "")) == 4]
    if not stocks:
        return Result(WARN, "snapshots", "沒有商品檔可檢查")
    sample = stocks[:5]
    try:
        snaps = broker.snapshots(sample)
    except Exception as e:
        return Result(FAIL, "snapshots", f"呼叫失敗：{e}")
    if not snaps:
        return Result(FAIL, "snapshots", "回傳空清單，screener 的量價過濾會全部落空")

    s = snaps[0]
    missing = [f for f in SNAPSHOT_FIELDS if getattr(s, f, None) is None]
    zeros = [f for f in SNAPSHOT_FIELDS if not getattr(s, f, 0)]
    detail = (f"取樣 {len(snaps)} 檔，第一檔 {getattr(s, 'code', '?')}："
              + "，".join(f"{f}={getattr(s, f, None)}" for f in SNAPSHOT_FIELDS))
    if missing:
        return Result(FAIL, "snapshots", f"缺少欄位 {missing}。{detail}")
    if zeros:
        return Result(WARN, "snapshots",
                      f"這些欄位是 0：{zeros}（非交易時段可能正常，開盤日再確認一次）。{detail}")
    return Result(OK, "snapshots", detail)


KBAR_LOOKBACK_DAYS = 10


def check_kbars(broker) -> Result:
    """分鐘 K 的欄位與 ts 語意 —— 開盤區間補算與量比都靠它。

    回看十天而不是只查今天：週末或假日跑體檢時，只查今天必然是空的，
    那樣什麼都驗不到。回看十天至少會涵蓋一個交易日。
    """
    stocks = [c for c in broker.all_stocks()
              if getattr(c, "code", "").isdigit() and len(getattr(c, "code", "")) == 4]
    if not stocks:
        return Result(WARN, "kbars", "沒有商品檔可檢查")
    code = stocks[0].code
    end = datetime.now()
    start = end - timedelta(days=KBAR_LOOKBACK_DAYS)
    span = f"{start:%Y-%m-%d}~{end:%Y-%m-%d}"
    try:
        kb = broker.kbars(code, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    except Exception as e:
        return Result(FAIL, "kbars", f"{code} {span} 分鐘 K 呼叫失敗：{e}")

    # 「欄位不存在」和「欄位存在但沒資料」是兩件事：
    # 前者代表欄位名稱猜錯了（程式必壞），後者只是這段期間沒有交易資料。
    absent = [f for f in KBAR_FIELDS if not hasattr(kb, f)]
    if absent:
        available = [a for a in dir(kb) if not a.startswith("_")][:12]
        return Result(FAIL, "kbars",
                      f"欄位名稱不符，缺少 {absent}；opening_range() 與量比都會失效。"
                      f"這個物件實際有的屬性：{available}")

    ts = list(getattr(kb, "ts") or [])
    if not ts:
        return Result(WARN, "kbars",
                      f"{code} 欄位名稱正確（{list(KBAR_FIELDS)} 都在），"
                      f"但 {span} 沒有任何資料。連假或權限不足都可能 —— "
                      f"開盤日再跑一次才能確認 ts 語意。")

    from broker import _bar_time
    times = [_bar_time(t) for t in ts]
    valid = [t for t in times if t]
    if not valid:
        return Result(FAIL, "kbars",
                      f"{code} 有 {len(ts)} 根 K，但 ts 解析不出時間（樣本：{ts[:3]}）。"
                      f"_bar_time() 的時間戳假設需要修正。")

    # 取最後一個交易日的第一根，用來判斷 ts 是該分鐘的起點還是終點
    last_day = max(t.date() for t in valid)
    first_of_day = min(t for t in valid if t.date() == last_day)
    hhmm = first_of_day.strftime("%H:%M")
    mark = config.symbol("⚠️", "[!]")
    if hhmm in ("09:00", "09:01"):
        note = (f"落在開盤第一分鐘，時區解讀正確，"
                f"opening_range() 的 09:00~09:15 抓得到 {config.symbol('✓', 'OK')}")
    elif 9 <= first_of_day.hour < 14:
        note = (f"{mark} 在盤中但不是 09:00 —— 這檔可能開盤前幾分鐘沒成交，"
                f"通常無妨；若每檔都這樣請回報。")
    else:
        note = (f"{mark} 落在 {hhmm}，完全不在台股盤中（09:00~13:30）—— "
                f"時區解讀錯誤。差 8 小時就是 ts 被當成本地時間再加一次偏移。")
    # 印出原始值與兩種解讀，時區問題一眼可判
    raw = ts[0]
    from datetime import timezone as _tz
    try:
        as_utc = datetime.fromtimestamp(float(raw) / 1e9, tz=_tz.utc).replace(tzinfo=None)
        as_local = datetime.fromtimestamp(float(raw) / 1e9)
        probe = f"（首筆 ts={raw}；以 UTC 解 {as_utc:%m-%d %H:%M}、以本機時區解 {as_local:%m-%d %H:%M}）"
    except Exception:
        probe = f"（首筆 ts={raw!r}）"
    return Result(OK, "kbars",
                  f"{code} {span} 共 {len(ts)} 根；最後一個交易日 {last_day} "
                  f"的第一根是 {first_of_day:%H:%M:%S}。{note}{probe}")


def check_opening_range(broker) -> Result:
    stocks = [c for c in broker.all_stocks()
              if getattr(c, "code", "").isdigit() and len(getattr(c, "code", "")) == 4]
    if not stocks:
        return Result(WARN, "開盤區間補算", "沒有商品檔可檢查")
    code = stocks[0].code
    cfg = config.SIGNAL
    rng = broker.opening_range(code, cfg["or_start"], cfg["or_end"])
    if rng is None:
        return Result(WARN, "開盤區間補算",
                      f"{code} 補不到（非交易日或尚未開盤屬正常）。"
                      f"開盤日 09:15 之後要再跑一次確認。")
    return Result(OK, "開盤區間補算", f"{code} {cfg['or_start']}~{cfg['or_end']} "
                                      f"高 {rng[0]:.2f} / 低 {rng[1]:.2f}")


def check_ca(broker) -> Result:
    """電子憑證。真錢模式下，帳務查詢（也就是整個風控）都靠它。"""
    if config.SIMULATION:
        return Result(OK, "電子憑證", "模擬模式不需要憑證（切到 SIMULATION=0 前再確認一次）")
    if not config.CA_PATH:
        return Result(FAIL, "電子憑證",
                      "真錢模式但沒設定 SHIOAJI_CA_PATH。帳務查不到 → "
                      "風控會直接關閘停手。請在 e-Leader 下載憑證後填進 .env。")
    from pathlib import Path as _P
    if not _P(config.CA_PATH).exists():
        return Result(FAIL, "電子憑證", f"檔案不存在：{config.CA_PATH}")
    if not config.PERSON_ID:
        return Result(WARN, "電子憑證", "沒有設定 SHIOAJI_PERSON_ID，啟用可能會被拒")
    return Result(OK, "電子憑證", f"已載入 {_P(config.CA_PATH).name}（登入時啟用成功）")


def check_pnl(broker) -> Result:
    """風控最重要的一項：日虧上限與連敗停手都建立在這裡。"""
    rows = broker.realized_pnl_rows_today()
    if rows is None:
        if config.SIMULATION:
            return Result(WARN, "已實現損益",
                          "查不到。模擬模式下屬正常（模擬帳沒有損益），風控會以 0 計並警告。"
                          "切到 SIMULATION=0 之前必須讓這一項變成 ✅。")
        return Result(FAIL, "已實現損益",
                      "真錢模式查不到損益 → 日虧上限與連敗停手都失效，"
                      "風控閘門會在第一個訊號時直接關閘停手。"
                      "最常見原因是電子憑證沒啟用（見上一項），其次是帳號沒有查詢權限。")
    return Result(OK, "已實現損益",
                  f"查得到，今日 {len(rows)} 筆平倉，合計 {sum(rows):,.0f} 元")


def check_trades(broker) -> Result:
    trades = broker.trades_today()
    if trades is None:
        if config.SIMULATION:
            return Result(WARN, "成交紀錄",
                          "查不到（多半是金鑰沒有帳務查詢權限）。模擬模式下風控會以 0 筆計算，"
                          "但切到 SIMULATION=0 前必須讓這一項變成 ✅ —— "
                          "否則「當日交易筆數上限」這條紅線等於沒有。")
        return Result(FAIL, "成交紀錄",
                      "真錢模式查不到成交紀錄 → 交易筆數上限失效，"
                      "風控閘門會在第一個訊號時關閘停手。請確認金鑰的帳務查詢權限。")
    if not trades:
        return Result(WARN, "成交紀錄",
                      "今日無成交（沒下單就是正常的）。有下單的日子要再確認一次欄位。")
    t = trades[0]
    import review
    return Result(OK, "成交紀錄",
                  f"{len(trades)} 筆，第一筆 code={review._trade_code(t)}、"
                  f"成交均價={review._deal_price(t):.2f}")


def check_telegram(_broker=None) -> Result:
    import signals
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return Result(WARN, "Telegram 推播",
                      "沒有設定金鑰，訊號只會印在畫面上。"
                      "盤中你不會一直盯著終端機 —— 建議設定。")
    if signals.requests is None:
        return Result(FAIL, "Telegram 推播",
                      "已設定金鑰但沒有安裝 requests，訊號推不出去。"
                      "請執行 pip install -r requirements.txt。")
    signals.notify("✅ preflight 測試推播：你會在盤中收到的就是這個樣式的訊息。")
    return Result(OK, "Telegram 推播", "已送出測試訊息，請確認手機有收到")


CHECKS = (check_config, check_contracts, check_day_trade_flag, check_snapshots,
          check_kbars, check_opening_range, check_ca, check_pnl, check_trades,
          check_telegram)


def main():
    print("=" * 62)
    print("當沖訊號系統 — 上線前連線體檢（只讀，不下單）")
    print("=" * 62)

    results = [check_config()]
    print(results[0], "\n")

    broker = None
    if results[0].status != FAIL:
        try:
            from broker import Broker
            broker = Broker()
        except Exception as e:
            results.append(Result(FAIL, "登入", str(e)))
            print(results[-1], "\n")

    if broker is not None:
        results.append(Result(OK, "登入", f"成功（simulation={config.SIMULATION}）"))
        print(results[-1], "\n")
        for check in CHECKS[1:]:
            try:
                r = check(broker)
            except Exception as e:
                r = Result(FAIL, check.__name__, f"檢查本身拋出例外：{e!r}")
            results.append(r)
            print(r, "\n")

    fails = [r for r in results if r.status == FAIL]
    warns = [r for r in results if r.status == WARN]
    print("=" * 62)
    print(f"結果：{len(results) - len(fails) - len(warns)} 項通過、"
          f"{len(warns)} 項待確認、{len(fails)} 項不通過")
    if fails:
        print("\n不通過的項目（修好再上線）：")
        for r in fails:
            print(f"  {FAIL} {r.name}")
        raise SystemExit(1)
    if warns:
        print("\n待確認的項目多半是「現在不是交易時段」造成的。"
              "\n開盤日 09:15 之後再跑一次，warning 應該要自己消失。")
    print("\n下一步：python3 dryrun.py 驗證管線，再照 README 的上線順序走。")


if __name__ == "__main__":
    main()
