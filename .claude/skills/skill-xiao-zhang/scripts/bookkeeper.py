#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小帳（Xiao Zhang）記帳引擎 — Sixhands Studio AI 數字員工 / 財務部
零依賴（只用 Python 標準庫）。所有金額用整數元計算，不用浮點數累加。

子指令：
  init      產生流水帳範例 CSV（教練照著填就好）
  classify  流水帳 CSV → 借貸分錄 CSV（自動判科目、自動拆營業稅）
  journal   分錄 CSV → 試算表 + 損益表 + 資產負債表（Markdown）
  vat       分錄 CSV → 營業稅（401）試算
"""
import argparse, csv, json, os, sys
from collections import OrderedDict, defaultdict
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = os.path.join(HERE, "..", "references", "accounts.json")
TAX_RATE = Decimal("0.05")          # 現行營業稅率，變動時改這裡

RAW_HEADERS = ["日期", "摘要", "金額", "收支", "付款方式", "稅別", "發票號碼", "對象"]
JRN_HEADERS = ["日期", "傳票號", "科目", "借方", "貸方", "摘要", "發票號碼", "對象", "稅別"]

ALIAS = {"date": "日期", "description": "摘要", "amount": "金額", "memo": "摘要",
         "type": "收支", "payment": "付款方式", "tax": "稅別",
         "invoice": "發票號碼", "counterparty": "對象"}


# ---------- 共用 ----------
def load_rules(path=RULES):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d["accounts"], d["payment_accounts"]


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = []
        for r in csv.DictReader(f):
            row = {}
            for k, v in r.items():
                if k is None:
                    continue
                key = k.strip()
                row[ALIAS.get(key.lower(), key)] = (v or "").strip()
            if any(row.values()):
                rows.append(row)
    return rows


def to_int(s):
    s = str(s).replace(",", "").replace("$", "").replace("元", "").strip()
    if not s:
        return 0
    return int(Decimal(s).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def split_tax(gross):
    """含稅金額 → (未稅, 稅額)，稅額四捨五入到元，未稅 = 含稅 - 稅額（確保加總對得起來）。"""
    g = Decimal(gross)
    net = (g / (1 + TAX_RATE)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(net), int(g - net)


def guess_account(memo, party, accounts, is_income):
    text = f"{memo} {party}".lower()
    want = ("收入",) if is_income else ("成本", "費用", "資產")
    best, best_len = None, 0
    for name, meta in accounts.items():
        if meta["type"] not in want:
            continue
        for kw in meta.get("keywords", []):
            if kw.lower() in text and len(kw) > best_len:
                best, best_len = name, len(kw)
    if best:
        return best, True
    return ("其他收入" if is_income else "其他費用"), False


def pay_account(payment, pay_map, is_income):
    p = (payment or "").strip()
    if p in pay_map:
        return pay_map[p]
    for k, v in pay_map.items():
        if k and k in p:
            return v
    return "應收帳款" if is_income else "現金"


# ---------- init ----------
def cmd_init(args):
    sample = [
        ["2026-08-01", "8月辦公室租金", "30000", "支出", "銀行", "應稅", "AB12345678", "房東王先生"],
        ["2026-08-03", "Claude Max 訂閱", "6200", "支出", "信用卡", "應稅(不可扣抵)", "", "Anthropic"],
        ["2026-08-05", "第三期訓練營學費 3 位", "89700", "收入", "銀行", "應稅", "CD87654321", "學員"],
        ["2026-08-07", "剪輯外包費", "12000", "支出", "轉帳", "應稅", "EF11223344", "阿德工作室"],
        ["2026-08-10", "高鐵台北-台南 講座", "2780", "支出", "現金", "應稅(不可扣抵)", "", ""],
        ["2026-08-15", "FB 廣告投放", "18000", "支出", "信用卡", "零稅率", "", "Meta"],
    ]
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(RAW_HEADERS)
        w.writerows(sample)
    print(f"✅ 已產生流水帳範例：{args.out}")
    print("   欄位：" + " / ".join(RAW_HEADERS))
    print("   收支＝收入 或 支出；付款方式＝現金/銀行/信用卡/月結/未收")
    print("   稅別＝應稅 / 應稅(不可扣抵) / 免稅 / 零稅率 / 無（應稅金額請填「含稅」總額）")


# ---------- classify ----------
def cmd_classify(args):
    accounts, pay_map = load_rules()
    rows = read_csv(args.infile)
    out, warnings, seq = [], [], 0

    for i, r in enumerate(rows, start=2):
        memo = r.get("摘要", "")
        gross = to_int(r.get("金額", 0))
        if gross <= 0:
            warnings.append(f"第 {i} 列「{memo}」金額為 0 或無法解析，已跳過")
            continue
        is_income = "收" in r.get("收支", "") and "支" not in r.get("收支", "")
        tax_type = r.get("稅別", "") or "無"
        deductible = tax_type.startswith("應稅") and "不可扣抵" not in tax_type
        seq += 1
        vno = f"{args.prefix}{seq:04d}"
        acct, hit = guess_account(memo, r.get("對象", ""), accounts, is_income)
        if not hit:
            warnings.append(f"第 {i} 列「{memo}」找不到對應科目 → 暫掛「{acct}」，請人工確認")
        pacct = pay_account(r.get("付款方式", ""), pay_map, is_income)
        net, tax = split_tax(gross) if deductible else (gross, 0)
        base = dict(日期=r.get("日期", ""), 傳票號=vno, 摘要=memo,
                     發票號碼=r.get("發票號碼", ""), 對象=r.get("對象", ""), 稅別=tax_type)

        def line(acc, dr=0, cr=0):
            d = dict(base); d.update(科目=acc, 借方=dr, 貸方=cr); out.append(d)

        if is_income:
            line(pacct, dr=gross)
            line(acct, cr=net)
            if tax:
                line("銷項稅額", cr=tax)
        else:
            line(acct, dr=net)
            if tax:
                line("進項稅額", dr=tax)
            line(pacct, cr=gross)

    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=JRN_HEADERS)
        w.writeheader()
        for d in out:
            w.writerow({k: d.get(k, "") for k in JRN_HEADERS})

    dr = sum(int(d["借方"] or 0) for d in out)
    cr = sum(int(d["貸方"] or 0) for d in out)
    print(f"✅ 已產生分錄：{args.out}（{seq} 張傳票 / {len(out)} 行）")
    print(f"   借方合計 {dr:,} ／ 貸方合計 {cr:,} ／ {'借貸平衡 ✅' if dr == cr else '⚠️ 不平衡，請檢查'}")
    if warnings:
        print("\n⚠️ 需要人工確認（絕不自己猜死）：")
        for w_ in warnings:
            print("   - " + w_)


# ---------- journal ----------
def load_journal(path):
    accounts, _ = load_rules()
    rows = read_csv(path)
    bal = OrderedDict()      # 科目 -> [借, 貸]
    unknown = []
    for r in rows:
        acc = r.get("科目", "").strip()
        if not acc:
            continue
        if acc not in accounts and acc not in unknown:
            unknown.append(acc)
        d, c = to_int(r.get("借方", 0)), to_int(r.get("貸方", 0))
        e = bal.setdefault(acc, [0, 0])
        e[0] += d
        e[1] += c
    return accounts, bal, unknown, rows


def acc_type(accounts, name):
    return accounts.get(name, {}).get("type", "未分類")


def cmd_journal(args):
    accounts, bal, unknown, rows = load_journal(args.infile)
    period = args.period or "（未指定期間）"
    L = []
    L.append(f"# 📒 財務報表｜{period}\n")
    if unknown:
        L.append("> ⚠️ 下列科目不在科目表中，請先確認：" + "、".join(unknown) + "\n")

    tdr = sum(v[0] for v in bal.values())
    tcr = sum(v[1] for v in bal.values())
    L.append("## 一、試算表\n")
    L.append("| 科目 | 屬性 | 借方 | 貸方 | 餘額 |")
    L.append("|:---|:---|---:|---:|---:|")
    for acc, (d, c) in bal.items():
        t = acc_type(accounts, acc)
        net = d - c if t in ("資產", "成本", "費用") else c - d
        L.append(f"| {acc} | {t} | {d:,} | {c:,} | {net:,} |")
    L.append(f"| **合計** | | **{tdr:,}** | **{tcr:,}** | {'✅ 平衡' if tdr == tcr else '⚠️ 不平衡'} |\n")

    def group(types, positive_side):
        g = []
        for acc, (d, c) in bal.items():
            if acc_type(accounts, acc) in types:
                v = (c - d) if positive_side == "貸" else (d - c)
                if v:
                    g.append((acc, v))
        return g

    rev = group(("收入",), "貸")
    cost = group(("成本",), "借")
    exp = group(("費用",), "借")
    trev, tcost, texp = sum(v for _, v in rev), sum(v for _, v in cost), sum(v for _, v in exp)
    profit = trev - tcost - texp

    L.append("## 二、損益表\n")
    L.append("| 項目 | 金額 | 佔營收 |")
    L.append("|:---|---:|---:|")
    pct = lambda v: f"{v / trev * 100:.1f}%" if trev else "—"
    for a, v in rev:
        L.append(f"| {a} | {v:,} | {pct(v)} |")
    L.append(f"| **營業收入合計** | **{trev:,}** | 100.0% |")
    for a, v in cost:
        L.append(f"| （減）{a} | {v:,} | {pct(v)} |")
    L.append(f"| **營業毛利** | **{trev - tcost:,}** | {pct(trev - tcost)} |")
    for a, v in exp:
        L.append(f"| （減）{a} | {v:,} | {pct(v)} |")
    L.append(f"| **本期損益** | **{profit:,}** | {pct(profit)} |\n")

    assets = group(("資產",), "借")
    liab = group(("負債",), "貸")
    eq = group(("權益",), "貸")
    ta, tl, te = sum(v for _, v in assets), sum(v for _, v in liab), sum(v for _, v in eq)

    L.append("## 三、資產負債表（管理用簡表）\n")
    L.append("| 資產 | 金額 | 負債及權益 | 金額 |")
    L.append("|:---|---:|:---|---:|")
    right = [(a, v) for a, v in liab] + [("—— 權益 ——", None)] + [(a, v) for a, v in eq] + [("本期損益", profit)]
    for i in range(max(len(assets), len(right))):
        la, lv = assets[i] if i < len(assets) else ("", None)
        ra, rv = right[i] if i < len(right) else ("", None)
        L.append(f"| {la} | {'' if lv is None else f'{lv:,}'} | {ra} | {'' if rv is None else f'{rv:,}'} |")
    L.append(f"| **資產合計** | **{ta:,}** | **負債及權益合計** | **{tl + te + profit:,}** |\n")
    diff = ta - (tl + te + profit)
    L.append(f"> 平衡檢查：資產 − (負債＋權益＋本期損益) = **{diff:,}**"
             + ("　✅ 平衡" if diff == 0 else "　⚠️ 有差額，通常是分錄漏行或期初餘額未輸入") + "\n")

    L.append("---\n")
    L.append("⚠️ 本報表由 AI 依教練提供之流水帳自動彙整，供**內部管理決策**使用，非經會計師查核之財務報表；"
             "對外申報與稅務簽證仍以委任之記帳士／會計師出具者為準。\n")
    L.append("＿Sixhands Studio AI數字員工 🦞 財務部・小帳＿")

    md = "\n".join(L)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"✅ 已輸出報表：{args.out}")
    else:
        print(md)


# ---------- vat ----------
def cmd_vat(args):
    _, bal, _, _ = load_journal(args.infile)
    out_tax = bal.get("銷項稅額", [0, 0])
    in_tax = bal.get("進項稅額", [0, 0])
    o = out_tax[1] - out_tax[0]
    i = in_tax[0] - in_tax[1]
    net = o - i
    print(f"# 🧾 營業稅（401）試算｜{args.period or '本期'}\n")
    print(f"| 項目 | 金額 |\n|:---|---:|")
    print(f"| 銷項稅額 | {o:,} |")
    print(f"| 進項稅額（可扣抵） | {i:,} |")
    if net >= 0:
        print(f"| **本期應納稅額** | **{net:,}** |")
    else:
        print(f"| **本期累積留抵稅額** | **{-net:,}** |")
    print("\n> 稅率 5%；僅為試算，實際申報金額以財政部電子申報系統與委任記帳士／會計師核算為準。")
    print("> 申報期限：每逢單月 15 日前，申報前兩個月（1-2月→3/15、3-4月→5/15…）。")


def main():
    p = argparse.ArgumentParser(description="小帳記帳引擎")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("init", help="產生流水帳範例 CSV")
    a.add_argument("--out", default="流水帳.csv")
    a.set_defaults(func=cmd_init)

    b = sub.add_parser("classify", help="流水帳 → 借貸分錄")
    b.add_argument("infile")
    b.add_argument("--out", default="分錄.csv")
    b.add_argument("--prefix", default="V", help="傳票號前綴")
    b.set_defaults(func=cmd_classify)

    c = sub.add_parser("journal", help="分錄 → 試算表/損益表/資產負債表")
    c.add_argument("infile")
    c.add_argument("--out", default=None)
    c.add_argument("--period", default=None)
    c.set_defaults(func=cmd_journal)

    d = sub.add_parser("vat", help="分錄 → 營業稅試算")
    d.add_argument("infile")
    d.add_argument("--period", default=None)
    d.set_defaults(func=cmd_vat)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
