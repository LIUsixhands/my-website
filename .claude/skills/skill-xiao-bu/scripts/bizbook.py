#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小簿（Xiao Bu）— 生意帳引擎
Sixhands Studio AI數字員工 / 財務部 / 小店家記帳專員

設計原則：
1. 零依賴（只用 Python 標準庫），學員電腦不裝任何東西就能跑。
2. 金額一律整數元 + Decimal，絕不用 float 累加。
3. 不出借貸分錄——老闆看的是「賺不賺、撐多久、該不該漲價」。
4. 猜不到的一律列「待確認」丟回人類，絕不自己認定。

子指令：
  init     建立我的生意帳資料夾（profile.json + ledger.csv）
  add      快速記一筆
  tidy     自動分類 + 體檢（重複、缺憑證、可疑金額）
  report   月度老闆儀表板
  cash     現金流跑道 + 應收應付到期
  price    定價體檢 / 損益兩平 / 該不該漲價
  handoff  記帳士交接包（憑證清冊 + 缺漏清單）
  alert    今天要注意的一行話
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

# ---------------------------------------------------------------- 基礎工具

LEDGER_FIELDS = ["日期", "收支", "項目", "金額", "分類", "付款方式", "對象", "發票憑證", "備註"]
AR_FIELDS = ["到期日", "類型", "對象", "項目", "金額", "狀態", "備註"]

D0 = Decimal("0")


def money(v) -> Decimal:
    """把任何輸入轉成整數元的 Decimal。空值 → 0。"""
    if v is None:
        return D0
    s = str(v).strip().replace(",", "").replace("$", "").replace("元", "")
    if not s:
        return D0
    try:
        return Decimal(s).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except Exception:
        return D0


def fmt(v: Decimal) -> str:
    return f"{int(v):,}"


def pct(part: Decimal, whole: Decimal, digits=1) -> str:
    if whole == 0:
        return "—"
    return f"{(part / whole * 100):.{digits}f}%"


def parse_date(s):
    s = str(s).strip().replace("/", "-")
    for f in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%m-%d"):
        try:
            d = datetime.strptime(s, f)
            if f == "%m-%d":
                d = d.replace(year=date.today().year)
            return d.date()
        except ValueError:
            continue
    return None


def load_profile(base: Path) -> dict:
    p = base / "profile.json"
    if not p.exists():
        die(f"找不到 {p}。請先執行：python3 bizbook.py init --dir {base}")
    return json.loads(p.read_text(encoding="utf-8"))


def load_ledger(base: Path) -> list:
    p = base / "ledger.csv"
    if not p.exists():
        die(f"找不到 {p}。請先執行 init，或把流水帳存成這個檔名。")
    rows = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):
            if not any((r.get(k) or "").strip() for k in LEDGER_FIELDS):
                continue
            r["_行"] = i
            r["_日期"] = parse_date(r.get("日期", ""))
            r["_金額"] = money(r.get("金額"))
            r["_收支"] = (r.get("收支") or "").strip()
            rows.append(r)
    return rows


def presets() -> dict:
    p = Path(__file__).resolve().parent.parent / "references" / "industry_presets.json"
    return json.loads(p.read_text(encoding="utf-8"))


def die(msg):
    print(f"\n❌ {msg}\n", file=sys.stderr)
    sys.exit(1)


def brand_footer() -> str:
    return (
        "\n---\n"
        "> 🦞 由 **Sixhands Studio AI數字員工** 小簿產出｜這是**內部管理帳**，"
        "非稅務申報文件、非查核簽證財報。\n"
        "> 對外申報請交由委任之記帳士／會計師辦理；數字以你手上的憑證與銀行帳戶為準。\n"
    )


def write_out(base: Path, name: str, text: str) -> Path:
    out = base / "out"
    out.mkdir(exist_ok=True)
    p = out / name
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------- init

def cmd_init(args):
    base = Path(args.dir).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    ps = presets()
    ind = args.industry
    if ind not in ps:
        die(f"不認識的行業「{ind}」。可選：{'、'.join(ps.keys())}")
    preset = ps[ind]

    prof = {
        "店名": args.name or "（待填）",
        "老闆": "（待填）",
        "行業": ind,
        "開始記帳月份": args.month or date.today().strftime("%Y-%m"),
        "期初現金": 0,
        "_期初現金說明": "記帳起始日，銀行帳戶餘額 + 手上零用金 + 收銀機備用金，整數元",
        "老闆每月投入時數": preset.get("預設老闆時數", 200),
        "_老闆時數說明": "含備料、採買、客服、記帳、進修——不是只算站在店裡的時間",
        "老闆每月要領走的錢": 0,
        "_領走說明": "你家裡每月開銷，用來算這門生意到底夠不夠養你",
        "營業稅身分": "（待確認：免用統一發票／使用統一發票／未達起徵點）",
        "_營業稅說明": "不確定就寫待確認，小簿不會自己猜；影響 5% 稅要不要拆",
        "固定成本": preset["固定成本範例"],
        "_固定成本說明": "每個月不管有沒有生意都要付的錢。金額改成你的實際數字",
        "行業參考值": preset["健康值"],
        "_行業參考值說明": "這是同業經驗區間，不是法規也不是你的目標，請用自己 3 個月數字校準",
    }
    (base / "profile.json").write_text(
        json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lp = base / "ledger.csv"
    if lp.exists() and not args.force:
        print(f"⚠️  {lp} 已存在，保留不動（要覆蓋加 --force）")
    else:
        with lp.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
            w.writeheader()
            for ex in preset["流水帳範例"]:
                w.writerow(ex)

    ap = base / "receivables.csv"
    if not ap.exists():
        with ap.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=AR_FIELDS)
            w.writeheader()
            w.writerow({
                "到期日": (date.today() + timedelta(days=14)).isoformat(),
                "類型": "應收", "對象": "（範例）某某公司", "項目": "尾款",
                "金額": "0", "狀態": "未收", "備註": "改成你的實際款項，沒有就整列刪掉",
            })

    print(f"""
✅ 小簿工作資料夾建好了：{base}

  profile.json      ← 先去把「（待填）」和固定成本金額改成你的實際數字
  ledger.csv        ← 每天記一行的流水帳（已放 {len(preset['流水帳範例'])} 筆 {ind} 範例，看懂後刪掉）
  receivables.csv   ← 別人欠你的、你欠別人的（沒有就留空）

📌 記帳只有一條規矩：**跟憑證一致**。想不起來的先照實寫「不確定」，不要編。

下一步：
  python3 bizbook.py add    --dir {base} --io 收入 --item "現場銷售" --amount 3200
  python3 bizbook.py tidy   --dir {base}
  python3 bizbook.py report --dir {base} --month {prof['開始記帳月份']}
""")


# ---------------------------------------------------------------- add

def cmd_add(args):
    base = Path(args.dir).expanduser()
    lp = base / "ledger.csv"
    if not lp.exists():
        die(f"找不到 {lp}，請先 init。")
    row = {
        "日期": (args.date or date.today().isoformat()),
        "收支": args.io,
        "項目": args.item,
        "金額": str(int(money(args.amount))),
        "分類": args.cat or "",
        "付款方式": args.pay or "",
        "對象": args.who or "",
        "發票憑證": args.doc or "",
        "備註": args.note or "",
    }
    with lp.open("a", encoding="utf-8-sig", newline="") as f:
        csv.DictWriter(f, fieldnames=LEDGER_FIELDS).writerow(row)
    tag = "💰" if args.io == "收入" else "💸"
    print(f"{tag} 已記一筆：{row['日期']}　{row['項目']}　${fmt(money(row['金額']))}"
          + ("" if row["發票憑證"] else "　⚠️ 沒填憑證，月底交記帳士會被退"))


# ---------------------------------------------------------------- tidy

def guess_category(row, preset):
    """用關鍵字猜分類。猜不到回 (None, 原因)。"""
    text = " ".join([
        str(row.get("項目") or ""), str(row.get("對象") or ""), str(row.get("備註") or "")
    ])
    io = row["_收支"]
    table = preset["收入關鍵字"] if io == "收入" else preset["支出關鍵字"]
    hits = []
    for cat, kws in table.items():
        for kw in kws:
            if kw and kw in text:
                hits.append((cat, kw))
                break
    if len(hits) == 1:
        return hits[0][0], None
    if len(hits) > 1:
        return None, "同時像 " + "／".join(h[0] for h in hits)
    return None, "沒有對應關鍵字"


def cmd_tidy(args):
    base = Path(args.dir).expanduser()
    prof = load_profile(base)
    preset = presets()[prof["行業"]]
    rows = load_ledger(base)
    if not rows:
        die("ledger.csv 裡沒有資料。")

    todo, filled = [], 0
    for r in rows:
        if not r["_日期"]:
            todo.append((r["_行"], r.get("項目", ""), "日期看不懂，請寫成 2026-08-15"))
            continue
        if r["_收支"] not in ("收入", "支出"):
            todo.append((r["_行"], r.get("項目", ""), f"「收支」欄要填 收入 或 支出，現在是「{r['_收支']}」"))
        if r["_金額"] <= 0:
            todo.append((r["_行"], r.get("項目", ""), "金額是 0 或空的"))
        if not (r.get("分類") or "").strip():
            cat, why = guess_category(r, preset)
            if cat:
                r["分類"] = cat
                filled += 1
            else:
                todo.append((r["_行"], r.get("項目", ""), f"分類猜不出來（{why}）"))
        if r["_收支"] == "支出" and r["_金額"] >= money(args.doc_threshold) \
                and not (r.get("發票憑證") or "").strip():
            todo.append((r["_行"], r.get("項目", ""),
                         f"支出 ${fmt(r['_金額'])} 沒有發票／收據號碼"))

    # 重複檢查：同日 + 同金額 + 同項目
    seen = defaultdict(list)
    for r in rows:
        seen[(str(r["_日期"]), str(r["_金額"]), (r.get("項目") or "").strip())].append(r["_行"])
    dups = [(k, v) for k, v in seen.items() if len(v) > 1 and k[1] != "0"]

    # 寫回已分類檔（不覆蓋原檔，原檔是學員的手稿）
    outp = base / "ledger_已分類.csv"
    with outp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in LEDGER_FIELDS})

    lines = [f"# 🧾 帳本體檢報告（{prof.get('店名')}）", "",
             f"- 總筆數：**{len(rows)}** 筆",
             f"- 自動補上分類：**{filled}** 筆",
             f"- 需要你確認：**{len(todo)}** 筆",
             f"- 疑似重複：**{len(dups)}** 組", "",
             f"已產生 `{outp.name}`（原始 ledger.csv 沒有被改動）", ""]

    if todo:
        lines += ["## ⚠️ 這些我不敢自己決定，請你確認", "",
                  "| 第幾行 | 項目 | 問題 |", "|---:|:---|:---|"]
        for ln, item, why in todo:
            lines.append(f"| {ln} | {item} | {why} |")
        lines.append("")
    if dups:
        lines += ["## 🔁 疑似重複（同一天、同金額、同項目）", "",
                  "| 日期 | 金額 | 項目 | 行號 |", "|:---|---:|:---|:---|"]
        for (d, amt, item), ln in dups:
            lines.append(f"| {d} | {fmt(money(amt))} | {item} | {'、'.join(map(str, ln))} |")
        lines += ["", "> 真的刷兩次就留著，重複登記就刪一行。", ""]
    if not todo and not dups:
        lines += ["## ✅ 這批帳很乾淨", "", "沒有缺分類、沒有缺憑證、沒有重複。可以直接跑 report。", ""]

    text = "\n".join(lines) + brand_footer()
    p = write_out(base, "體檢報告.md", text)
    print(text)
    print(f"\n📄 已存檔：{p}")


# ---------------------------------------------------------------- report

def month_rows(rows, ym):
    out = []
    for r in rows:
        if r["_日期"] and r["_日期"].strftime("%Y-%m") == ym:
            out.append(r)
    return out


def split_cost(rows, preset):
    """把支出拆成 變動成本 / 固定成本 / 老闆支出。回傳 (dict分類→金額, 三大類合計)"""
    by_cat = defaultdict(lambda: D0)
    kind_of = preset["支出屬性"]
    var, fix, owner, unknown = D0, D0, D0, D0
    for r in rows:
        if r["_收支"] != "支出":
            continue
        cat = (r.get("分類") or "未分類").strip() or "未分類"
        by_cat[cat] += r["_金額"]
        kind = kind_of.get(cat)
        if kind == "變動":
            var += r["_金額"]
        elif kind == "固定":
            fix += r["_金額"]
        elif kind == "老闆":
            owner += r["_金額"]
        else:
            unknown += r["_金額"]
    return by_cat, var, fix, owner, unknown


def enrich(rows, preset):
    """分析類指令共用：在記憶體裡即時補分類，不寫檔。
    唯一真相永遠是 ledger.csv —— 避免 tidy 產出的副本過期。"""
    for r in rows:
        if not (r.get("分類") or "").strip():
            cat, _ = guess_category(r, preset)
            if cat:
                r["分類"] = cat
    return rows


def cmd_report(args):
    base = Path(args.dir).expanduser()
    prof = load_profile(base)
    preset = presets()[prof["行業"]]
    rows = enrich(load_ledger(base), preset)
    ym = args.month or date.today().strftime("%Y-%m")
    mr = month_rows(rows, ym)
    if not mr:
        die(f"{ym} 這個月沒有任何紀錄。要不要換 --month，或先去記帳？")

    rev = sum((r["_金額"] for r in mr if r["_收支"] == "收入"), D0)
    by_cat, var, fix, owner, unknown = split_cost(mr, preset)
    exp = var + fix + owner + unknown
    gross = rev - var                       # 毛利＝營收 − 變動成本
    net = rev - exp                          # 淨利（老闆支出也算進去，因為錢真的離開了）
    net_excl_owner = rev - var - fix - unknown  # 不含老闆自己領的錢

    hours = Decimal(str(prof.get("老闆每月投入時數") or 0))
    hourly = (net_excl_owner / hours).quantize(Decimal("1")) if hours > 0 else None
    var_rate = (var / rev) if rev > 0 else D0
    be = (fix / (1 - var_rate)).quantize(Decimal("1")) if rev > 0 and var_rate < 1 else None
    days_in_month = 30
    need_daily = (be / days_in_month).quantize(Decimal("1")) if be else None
    need_take = money(prof.get("老闆每月要領走的錢"))

    L = [f"# 📊 {prof.get('店名')}　{ym} 月結儀表板", ""]

    # ---- 三句話（老闆只看這裡）
    L += ["## 一、三句話講完", ""]
    verdict = "賺" if net_excl_owner > 0 else ("打平" if net_excl_owner == 0 else "賠")
    L.append(f"1. **這個月{verdict}了 ${fmt(abs(net_excl_owner))}**"
             f"（營收 ${fmt(rev)}　−　支出 ${fmt(var + fix + unknown)}，未計你自己領的錢）")
    if hourly is not None:
        cmp_note = ""
        if args.minwage:
            mw = money(args.minwage)
            cmp_note = f"，{'高於' if hourly >= mw else '**低於**'}你設定的比較基準 ${fmt(mw)}/小時"
        L.append(f"2. **你的真實時薪 ${fmt(hourly)}／小時**"
                 f"（投入 {int(hours)} 小時{cmp_note}）")
    else:
        L.append("2. 真實時薪算不出來 — profile.json 的「老闆每月投入時數」還是 0")
    if be:
        L.append(f"3. **損益兩平點：月營收 ${fmt(be)}**（每天約 ${fmt(need_daily)}）"
                 f"，這個月{'✅ 有過' if rev >= be else '❌ 沒過，差 $' + fmt(be - rev)}")
    else:
        L.append("3. 損益兩平算不出來 — 變動成本率異常，先看第三節")
    L.append("")

    # ---- 損益
    L += ["## 二、錢從哪來、去哪了", "",
          "| 項目 | 金額 | 佔營收 |", "|:---|---:|---:|",
          f"| 營業收入 | ${fmt(rev)} | 100% |",
          f"| − 變動成本（做一單就多花一次） | ${fmt(var)} | {pct(var, rev)} |",
          f"| **＝ 毛利** | **${fmt(gross)}** | **{pct(gross, rev)}** |",
          f"| − 固定成本（開門就要付） | ${fmt(fix)} | {pct(fix, rev)} |"]
    if unknown > 0:
        L.append(f"| − 未歸類支出 ⚠️ | ${fmt(unknown)} | {pct(unknown, rev)} |")
    L.append(f"| **＝ 營業利益（未計老闆薪水）** | **${fmt(net_excl_owner)}** | **{pct(net_excl_owner, rev)}** |")
    if owner > 0:
        L.append(f"| − 老闆自己領走／私人支出 | ${fmt(owner)} | {pct(owner, rev)} |")
        L.append(f"| **＝ 實際留在生意裡的錢** | **${fmt(net)}** | **{pct(net, rev)}** |")
    L.append("")

    # ---- 支出排行
    exp_cats = sorted(((c, a) for c, a in by_cat.items()), key=lambda x: -x[1])[:8]
    if exp_cats:
        L += ["## 三、支出排行（錢最多花在這）", "",
              "| 分類 | 金額 | 佔營收 | 屬性 |", "|:---|---:|---:|:---|"]
        for c, a in exp_cats:
            L.append(f"| {c} | ${fmt(a)} | {pct(a, rev)} | {preset['支出屬性'].get(c, '⚠️ 未設定')} |")
        L.append("")

    # ---- 行業對照
    hv = prof.get("行業參考值") or {}
    checks, too_low = [], []
    for cat, rng in hv.items():
        if cat not in by_cat:
            continue
        r_ = (by_cat[cat] / rev * 100) if rev > 0 else D0
        lo, hi = Decimal(str(rng[0])), Decimal(str(rng[1]))
        flag = "✅ 在區間內" if lo <= r_ <= hi else ("🔺 偏高" if r_ > hi else "🔻 偏低")
        checks.append(f"| {cat} | {r_:.1f}% | {rng[0]}–{rng[1]}% | {flag} |")
        # 只對「變動成本」示警：變動成本與營收有機械連動，偏低多半是漏記。
        # 固定成本（薪資、房租）偏低通常是經營選擇（一人店、自家店面），不算異常。
        if r_ < lo * Decimal("0.75") and preset["支出屬性"].get(cat) == "變動":
            too_low.append((cat, r_, lo))
    if checks:
        L += ["## 四、跟同業比（經驗區間，不是法規）", "",
              "| 分類 | 你的比率 | 同業參考 | |", "|:---|---:|:---:|:---|"] + checks
        L += ["", "> ⚠️ 這區間是同業經驗值，店型、地段、坪數差很多。"
              "累積 3 個月自己的數字之後，就改用自己的平均當基準。", ""]

    # ---- 該盯的異常
    L += ["## 五、下個月要盯的一件事", ""]
    todo = []
    if unknown > 0:
        todo.append(f"有 ${fmt(unknown)} 支出沒歸類，先跑 `tidy` 補完，不然上面的毛利率是假的")
    for cat, r_, lo in too_low:
        todo.append(
            f"🚨 「{cat}」只佔 {r_:.1f}%，同業最低都有 {lo}% — "
            f"**這通常不是你省得好，是有支出沒記到**"
            f"（最常見：現金付款、拿不到發票的那幾筆就忘了寫）。"
            f"成本被低估＝利潤假的高，你會以為可以擴店。"
            f"先把這個月的現金支出翻一次，對不上就是漏了。")
    if need_take > 0 and net_excl_owner < need_take:
        todo.append(f"你家裡每月要 ${fmt(need_take)}，這門生意這個月只生出 ${fmt(net_excl_owner)}，"
                    f"差 ${fmt(need_take - net_excl_owner)} — 這是最該解的洞")
    if be and rev < be:
        todo.append(f"營收沒過損益兩平（差 ${fmt(be - rev)}）。"
                    f"要嘛每天多做 ${fmt((be - rev) / days_in_month)}，要嘛砍固定成本")
    if exp_cats and rev > 0 and exp_cats[0][1] / rev > Decimal("0.4"):
        todo.append(f"「{exp_cats[0][0]}」一項就吃掉 {pct(exp_cats[0][1], rev)} 營收，先動它效益最大")
    if hourly is not None and hourly < money(args.minwage or 0):
        todo.append(f"真實時薪 ${fmt(hourly)} 低於你的比較基準 — 不是生意不好，是你把自己算太便宜")
    if not todo:
        todo.append("數字很健康。下個月維持記帳習慣，累積到 3 個月就能看趨勢了")
    for i, t in enumerate(todo[:3], 1):
        L.append(f"{i}. {t}")
    L.append("")

    text = "\n".join(L) + brand_footer()
    p = write_out(base, f"月結_{ym}.md", text)
    print(text)
    print(f"\n📄 已存檔：{p}")


# ---------------------------------------------------------------- cash

def cmd_cash(args):
    base = Path(args.dir).expanduser()
    prof = load_profile(base)
    preset = presets()[prof["行業"]]
    rows = enrich(load_ledger(base), preset)
    today = date.today()

    opening = money(prof.get("期初現金"))
    rev = sum((r["_金額"] for r in rows if r["_收支"] == "收入"), D0)
    exp = sum((r["_金額"] for r in rows if r["_收支"] == "支出"), D0)
    cash_now = opening + rev - exp

    # 近 3 個完整月的平均月支出當燒錢率
    by_month = defaultdict(lambda: D0)
    for r in rows:
        if r["_收支"] == "支出" and r["_日期"]:
            by_month[r["_日期"].strftime("%Y-%m")] += r["_金額"]
    months = sorted(by_month.keys())[-3:]
    burn = (sum((by_month[m] for m in months), D0) / len(months)).quantize(Decimal("1")) if months else D0
    by_month_rev = defaultdict(lambda: D0)
    for r in rows:
        if r["_收支"] == "收入" and r["_日期"]:
            by_month_rev[r["_日期"].strftime("%Y-%m")] += r["_金額"]
    inflow = (sum((by_month_rev[m] for m in months), D0) / len(months)).quantize(Decimal("1")) if months else D0
    net_burn = burn - inflow
    runway = (cash_now / net_burn).quantize(Decimal("0.1")) if net_burn > 0 else None

    L = [f"# 💵 {prof.get('店名')}　現金流（{today}）", "",
         "## 現在手上有多少", "",
         "| 項目 | 金額 |", "|:---|---:|",
         f"| 期初現金 | ${fmt(opening)} |",
         f"| ＋ 累計收入 | ${fmt(rev)} |",
         f"| − 累計支出 | ${fmt(exp)} |",
         f"| **＝ 帳上現金** | **${fmt(cash_now)}** |", "",
         "> 這是帳本算出來的。**去對一次銀行 App 餘額**，對不上就是有筆沒記到。", ""]

    L += [f"## 撐得了多久（近 {len(months)} 個月平均）", "",
          f"- 平均每月流出：${fmt(burn)}",
          f"- 平均每月流入：${fmt(inflow)}"]
    if runway is not None:
        icon = "🔴" if runway < 3 else ("🟡" if runway < 6 else "🟢")
        L.append(f"- **淨燒 ${fmt(net_burn)}／月 → 現金跑道 {icon} 約 {runway} 個月**")
        if runway < 3:
            L.append("\n> 🔴 **不到 3 個月**。現在該做的不是行銷，是先把最大一筆固定支出砍掉、"
                     "或把應收款催回來。")
    else:
        L.append("- 🟢 **收入大於支出，沒有在燒錢** — 這門生意目前自己養得活自己。")
    L.append("")

    # 應收應付
    ap = base / "receivables.csv"
    if ap.exists():
        items = []
        with ap.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                d = parse_date(r.get("到期日", ""))
                amt = money(r.get("金額"))
                if not d or amt <= 0:
                    continue
                if (r.get("狀態") or "").strip() in ("已收", "已付"):
                    continue
                items.append((d, r.get("類型", ""), r.get("對象", ""), r.get("項目", ""), amt))
        items.sort()
        if items:
            L += ["## 別人欠你的 / 你欠別人的", "",
                  "| 到期日 | 剩餘 | 類型 | 對象 | 項目 | 金額 |",
                  "|:---|---:|:---|:---|:---|---:|"]
            ar_over = D0
            for d, t, who, item, amt in items:
                left = (d - today).days
                tag = f"**逾期 {abs(left)} 天** 🔴" if left < 0 else (f"{left} 天 🟡" if left <= 7 else f"{left} 天")
                if left < 0 and t == "應收":
                    ar_over += amt
                L.append(f"| {d} | {tag} | {t} | {who} | {item} | ${fmt(amt)} |")
            L.append("")
            if ar_over > 0:
                L.append(f"> 🔴 **逾期應收 ${fmt(ar_over)}**。這是已經賺到但沒進口袋的錢，"
                         f"催一通電話的效益大於做一檔促銷。\n")

    text = "\n".join(L) + brand_footer()
    p = write_out(base, "現金流.md", text)
    print(text)
    print(f"\n📄 已存檔：{p}")


# ---------------------------------------------------------------- price

def cmd_price(args):
    base = Path(args.dir).expanduser()
    prof = load_profile(base)
    preset = presets()[prof["行業"]]
    rows = enrich(load_ledger(base), preset)
    ym = args.month or date.today().strftime("%Y-%m")
    mr = month_rows(rows, ym)

    rev = sum((r["_金額"] for r in mr if r["_收支"] == "收入"), D0)
    _, var, fix, owner, unknown = split_cost(mr, preset)
    var_rate = (var / rev) if rev > 0 else Decimal(str(args.var_rate or 0)) / 100

    L = [f"# 🏷 定價體檢（依 {ym} 實際數字）", ""]
    if rev <= 0 and not args.var_rate:
        die(f"{ym} 沒有收入紀錄，也沒給 --var-rate，算不出來。")

    fix_total = fix + money(prof.get("老闆每月要領走的錢"))
    L += ["## 一、你的成本結構", "",
          "| 項目 | 數字 | 意思 |", "|:---|---:|:---|",
          f"| 變動成本率 | {var_rate * 100:.1f}% | 每收 100 元，就有 {var_rate * 100:.0f} 元是為了做出這一單而花掉的 |",
          f"| 毛利率 | {(1 - var_rate) * 100:.1f}% | 每收 100 元，剩 {(1 - var_rate) * 100:.0f} 元去付房租水電和你自己 |",
          f"| 每月固定成本 | ${fmt(fix)} | 沒客人也要付 |",
          f"| ＋ 你要領走的 | ${fmt(money(prof.get('老闆每月要領走的錢')))} | 你家裡的開銷 |",
          f"| **＝ 每月要扛的** | **${fmt(fix_total)}** | |", ""]

    if var_rate >= 1:
        L.append("> 🔴 **變動成本率超過 100%** — 每做一單就賠一單。這時候客人愈多賠愈多，"
                 "先停下來看是不是有支出歸錯類，或這個品項根本不該賣。\n")
    else:
        be = (fix_total / (1 - var_rate)).quantize(Decimal("1"))
        L += ["## 二、你每個月至少要做多少", "",
              f"- **損益兩平（含你要領的錢）：月營收 ${fmt(be)}**",
              f"- 換算每天（以 30 天計）：**${fmt((be / 30).quantize(Decimal('1')))}**"]
        if args.ticket:
            t = money(args.ticket)
            if t > 0:
                L.append(f"- 客單價 ${fmt(t)} → 每天要 **{int((be / 30 / t).quantize(Decimal('1'), ROUND_HALF_UP))} 位客人**")
        L.append("")

        # 漲價分析
        # 單位毛利：漲價前 (1−v)，漲價 u 後 (1+u−v)。要維持總毛利不變，
        # 可保留的客量 = (1−v)/(1+u−v)，故可承受流失 = u/(1+u−v)。
        def loss_tolerance(u_pct: Decimal) -> Decimal:
            u = u_pct / 100
            denom = 1 + u - var_rate
            return (u / denom * 100) if denom > 0 else D0

        up = Decimal(str(args.up or 10))
        L += [f"## 三、漲價 {up:.0f}% 撐得住嗎", "",
              f"漲價 {up:.0f}%、成本不變的情況下，"
              f"**客人少掉 {loss_tolerance(up):.1f}% 以內，你的毛利還是比現在多**。", "",
              "| 漲幅 | 可承受的客量流失 |", "|---:|---:|"]
        for u in (Decimal("5"), Decimal("10"), Decimal("15"), Decimal("20")):
            L.append(f"| {u:.0f}% | {loss_tolerance(u):.1f}% |")
        L += ["", f"> 讀法：你的毛利率 {(1 - var_rate) * 100:.0f}%。"
              "**毛利率愈低的生意，漲價的槓桿愈大** — 因為漲的錢幾乎整筆落進毛利；"
              "但同樣的，低毛利生意**降價的殺傷力也最大**，打折前先算這張表。", "",
              "> ⚠️ 這只算數字，不算你的市場。漲價前先問三個老客人。", ""]

    text = "\n".join(L) + brand_footer()
    p = write_out(base, f"定價體檢_{ym}.md", text)
    print(text)
    print(f"\n📄 已存檔：{p}")


# ---------------------------------------------------------------- handoff

def cmd_handoff(args):
    base = Path(args.dir).expanduser()
    prof = load_profile(base)
    preset = presets()[prof["行業"]]
    rows = enrich(load_ledger(base), preset)
    ym = args.month or date.today().strftime("%Y-%m")
    mr = month_rows(rows, ym)
    if not mr:
        die(f"{ym} 沒有紀錄。")

    # 老闆私人領現／家用不是營業支出，不該出現在給事務所的缺憑證清單裡
    owner_rows = [r for r in mr if preset["支出屬性"].get((r.get("分類") or "").strip()) == "老闆"]
    missing = [r for r in mr if r["_收支"] == "支出"
               and r["_金額"] >= money(args.doc_threshold)
               and not (r.get("發票憑證") or "").strip()
               and preset["支出屬性"].get((r.get("分類") or "").strip()) != "老闆"]
    by_cat = defaultdict(lambda: [D0, 0])
    for r in mr:
        k = f"{r['_收支']}／{(r.get('分類') or '未分類').strip() or '未分類'}"
        by_cat[k][0] += r["_金額"]
        by_cat[k][1] += 1

    # 憑證清冊 CSV
    csvp = base / "out"
    csvp.mkdir(exist_ok=True)
    cp = csvp / f"憑證清冊_{ym}.csv"
    with cp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["日期", "收支", "分類", "項目", "對象", "金額", "發票憑證", "付款方式", "備註"])
        for r in sorted(mr, key=lambda x: (x["_日期"] or date.min)):
            w.writerow([r.get("日期"), r.get("收支"), r.get("分類"), r.get("項目"),
                        r.get("對象"), int(r["_金額"]), r.get("發票憑證"),
                        r.get("付款方式"), r.get("備註")])

    L = [f"# 📦 交給記帳士的資料包　{ym}", "",
         f"**{prof.get('店名')}**｜營業稅身分：{prof.get('營業稅身分')}", "",
         "## 一、這包裡有什麼", "",
         f"- `憑證清冊_{ym}.csv` — {len(mr)} 筆明細（已按日期排序）",
         "- 進項發票／收據正本或掃描檔（請你另外附）",
         "- 銷項發票存根聯或平台對帳單（請你另外附）",
         "- 銀行存摺／網銀當月交易明細（請你另外附）", "",
         "## 二、分類彙總", "",
         "| 收支／分類 | 筆數 | 金額 |", "|:---|---:|---:|"]
    for k in sorted(by_cat.keys()):
        amt, n = by_cat[k][0], by_cat[k][1]
        L.append(f"| {k} | {n} | ${fmt(amt)} |")
    L.append("")

    if missing:
        L += [f"## 三、🔴 缺憑證 {len(missing)} 筆（事務所一定會退件）", "",
              "| 日期 | 項目 | 對象 | 金額 |", "|:---|:---|:---|---:|"]
        for r in sorted(missing, key=lambda x: -x["_金額"]):
            L.append(f"| {r.get('日期')} | {r.get('項目')} | {r.get('對象', '')} | ${fmt(r['_金額'])} |")
        L += ["", "> 找不到憑證的處理方式：**照實跟事務所說找不到**，由他們判斷能不能列帳。"
              "不要為了列帳去湊一張別的發票 — 那是逃漏稅，不是節稅。", ""]
    else:
        L += ["## 三、✅ 憑證齊全", "", f"金額 ${fmt(money(args.doc_threshold))} 以上的支出都有憑證號碼。", ""]

    if owner_rows:
        owner_sum = sum((r["_金額"] for r in owner_rows), D0)
        L += ["## 三之一、已排除：老闆私人支出", "",
              f"本月有 {len(owner_rows)} 筆、共 **${fmt(owner_sum)}** 標記為老闆私人領用，"
              "**沒有**列入上面的缺憑證清單。", "",
              "> 私人領現不是營業費用，不必也不該去湊憑證。"
              "但獨資／合夥與公司的處理方式不同（股東往來、盈餘分配），"
              "**請事務所確認你這個組織型態要怎麼記**。", ""]

    L += ["## 四、要問事務所的問題（小簿不能替你判斷）", ""]
    for q in preset.get("常見待確認", []):
        L.append(f"- {q}")
    L += ["", "> 🚨 以上判斷屬記帳士／會計師的專業範圍。小簿只負責把資料整理齊、把問題列出來。", ""]

    text = "\n".join(L) + brand_footer()
    p = write_out(base, f"記帳士交接包_{ym}.md", text)
    print(text)
    print(f"\n📄 已存檔：{p}\n📄 憑證清冊：{cp}")


# ---------------------------------------------------------------- alert

def cmd_alert(args):
    base = Path(args.dir).expanduser()
    prof = load_profile(base)
    preset = presets()[prof["行業"]]
    rows = load_ledger(base)   # alert 刻意不 enrich：要看得見「還沒分類」這件事
    today = date.today()
    msgs = []

    # 幾天沒記帳
    last = max((r["_日期"] for r in rows if r["_日期"]), default=None)
    if last:
        gap = (today - last).days
        if gap >= 3:
            msgs.append(f"🟡 已經 {gap} 天沒記帳了（最後一筆 {last}）。記帳斷了，月結就是猜的。")
    else:
        msgs.append("🟡 帳本還是空的，今天記第一筆吧。")

    # 缺憑證（老闆私人領用不算 —— 那本來就不需要憑證）
    def kind(r):
        c = (r.get("分類") or "").strip() or (guess_category(r, preset)[0] or "")
        return preset["支出屬性"].get(c)

    nodoc = [r for r in rows if r["_收支"] == "支出"
             and r["_金額"] >= money(args.doc_threshold)
             and not (r.get("發票憑證") or "").strip()
             and kind(r) != "老闆"]
    if nodoc:
        msgs.append(f"🟡 有 {len(nodoc)} 筆大額支出沒填憑證號（共 ${fmt(sum((r['_金額'] for r in nodoc), D0))}）。")

    # 逾期應收
    ap = base / "receivables.csv"
    if ap.exists():
        with ap.open(encoding="utf-8-sig", newline="") as f:
            over = []
            for r in csv.DictReader(f):
                d = parse_date(r.get("到期日", ""))
                amt = money(r.get("金額"))
                if d and amt > 0 and (r.get("狀態") or "").strip() not in ("已收", "已付") \
                        and d < today and (r.get("類型") or "") == "應收":
                    over.append((r.get("對象", ""), amt, (today - d).days))
        if over:
            tot = sum((a for _, a, _ in over), D0)
            who = "、".join(f"{w}(${fmt(a)}，逾期{d}天)" for w, a, d in over[:3])
            msgs.append(f"🔴 逾期應收 ${fmt(tot)}：{who}。今天打一通電話。")

    # 未分類：只提示「連猜都猜不到」的，能自動判斷的不算問題
    #（否則跑完 tidy 提示還在，因為 tidy 不回寫 ledger.csv）
    hard = [r for r in rows
            if not (r.get("分類") or "").strip() and guess_category(r, preset)[0] is None]
    if hard:
        msgs.append(f"⚪ {len(hard)} 筆連我也猜不出分類，跑 `tidy` 看清單。")

    print(f"\n🧮 小簿早報　{today}　{prof.get('店名')}\n")
    if msgs:
        for m in msgs:
            print(f"  {m}")
    else:
        print("  ✅ 帳很乾淨，沒有要處理的事。")
    tc = Path(__file__).resolve().parent / "tax_calendar.py"
    print(f"\n  📅 稅務期限：python3 {tc.name} --days 30"
          f"（小簿只提醒期限，不代辦申報）\n")


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(
        description="小簿（Xiao Bu）生意帳引擎 — Sixhands Studio AI數字員工",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--dir", default="./我的生意帳", help="工作資料夾（預設 ./我的生意帳）")

    p = sub.add_parser("init", help="建立生意帳資料夾")
    common(p)
    p.add_argument("--industry", required=True, help="行業（見 references/industry_presets.json）")
    p.add_argument("--name", help="店名")
    p.add_argument("--month", help="開始記帳月份 YYYY-MM")
    p.add_argument("--force", action="store_true", help="覆蓋既有 ledger.csv")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("add", help="快速記一筆")
    common(p)
    p.add_argument("--io", required=True, choices=["收入", "支出"])
    p.add_argument("--item", required=True, help="項目")
    p.add_argument("--amount", required=True, help="金額（整數元）")
    p.add_argument("--date", help="日期，預設今天")
    p.add_argument("--cat", help="分類，留空由 tidy 猜")
    p.add_argument("--pay", help="付款方式：現金／轉帳／刷卡／行動支付")
    p.add_argument("--who", help="對象")
    p.add_argument("--doc", help="發票或收據號碼")
    p.add_argument("--note", help="備註")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("tidy", help="自動分類 + 帳本體檢")
    common(p)
    p.add_argument("--doc-threshold", default="1000", help="多少錢以上一定要有憑證（預設 1000）")
    p.set_defaults(func=cmd_tidy)

    p = sub.add_parser("report", help="月度老闆儀表板")
    common(p)
    p.add_argument("--month", help="YYYY-MM，預設本月")
    p.add_argument("--minwage", help="拿來比較真實時薪的基準時薪（例如你去打工的時薪）")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("cash", help="現金流跑道 + 應收應付")
    common(p)
    p.set_defaults(func=cmd_cash)

    p = sub.add_parser("price", help="定價體檢 / 損益兩平 / 漲價分析")
    common(p)
    p.add_argument("--month", help="YYYY-MM，預設本月")
    p.add_argument("--ticket", help="客單價，用來換算每天要幾個客人")
    p.add_argument("--up", type=float, default=10, help="想漲價幾 %%（預設 10）")
    p.add_argument("--var-rate", type=float, help="沒有帳可算時，直接給變動成本率（%%）")
    p.set_defaults(func=cmd_price)

    p = sub.add_parser("handoff", help="記帳士交接包")
    common(p)
    p.add_argument("--month", help="YYYY-MM，預設本月")
    p.add_argument("--doc-threshold", default="1000")
    p.set_defaults(func=cmd_handoff)

    p = sub.add_parser("alert", help="今天要注意的事")
    common(p)
    p.add_argument("--doc-threshold", default="1000")
    p.set_defaults(func=cmd_alert)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
