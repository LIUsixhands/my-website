#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
devicemgr.py — Sixhands Studio AI 數字員工 🦞 / 小械（醫療器材管理專員）核心工具

零安裝：只用 Python 標準函式庫，不需要 pandas。
所有 CSV 以 utf-8-sig 讀寫，Excel／Numbers 直接打開不會亂碼。

用法：
  python3 devicemgr.py init   [--dir 資料夾]              建立五張表的空白範本
  python3 devicemgr.py check  [--dir 資料夾] [--days N]    六大健檢：效期/許可證/庫存/借出/保養/流向缺漏
  python3 devicemgr.py stock  [--dir 資料夾] [--item 品號] 庫存彙總 + FEFO 出貨建議
  python3 devicemgr.py trace  [--dir 資料夾] (--lot 批號 | --serial 序號 | --item 品號)
                                                          單一批號/序號的來源流向追溯表
  python3 devicemgr.py report [--dir 資料夾] [--period 2026年8月] [--out 月報.md]
                                                          月度管理報告（Markdown）

⚠️ 本工具只做「內部管理與提醒」。不代為向主管機關申報、不判定法規適用等級。
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime

# ─────────────────────────── 表格定義 ───────────────────────────

FILES = {
    "devices":     "1_器材主檔.csv",
    "stock":       "2_庫存批號.csv",
    "trace":       "3_來源流向.csv",
    "loans":       "4_借出試用機.csv",
    "maintenance": "5_保養校正.csv",
}

HEADERS = {
    "devices": [
        "品項編號", "品名", "型號", "品牌", "製造廠", "原廠國別",
        "風險等級", "許可證字號", "許可證有效期限", "UDI-DI",
        "是否植入式", "是否公告申報品項", "單位", "保存條件",
        "供應商", "供應商聯絡", "採購成本", "建議售價", "安全庫存", "備註",
    ],
    "stock": [
        "庫存編號", "品項編號", "批號", "序號", "數量",
        "製造日期", "有效期限", "進貨日期", "進貨單號", "儲位", "狀態", "備註",
    ],
    "trace": [
        "紀錄日期", "類別", "品項編號", "品名", "批號", "序號", "數量",
        "對象名稱", "對象統編或機構代碼", "對象地址", "交貨日期",
        "製造日期", "有效期限", "單據號碼", "病人姓名", "病人身分證號", "備註",
    ],
    "loans": [
        "借出單號", "品項編號", "品名", "序號", "借用單位", "聯絡人", "電話",
        "借出日", "應歸還日", "實際歸還日", "押金", "狀態", "備註",
    ],
    "maintenance": [
        "設備序號", "品項編號", "品名", "所在單位", "類型",
        "上次執行日", "週期月數", "下次到期日", "負責人", "狀態", "備註",
    ],
}

SAMPLES = {
    "devices": [{
        "品項編號": "MD-001", "品名": "（範例）床邊型生理監視器", "型號": "X-200",
        "品牌": "示範品牌", "製造廠": "Demo Medical Co., Ltd.", "原廠國別": "日本",
        "風險等級": "2", "許可證字號": "衛部醫器輸字第00000號",
        "許可證有效期限": "2028-12-31", "UDI-DI": "04712345678901",
        "是否植入式": "N", "是否公告申報品項": "N", "單位": "台",
        "保存條件": "常溫、避免潮濕", "供應商": "示範原廠",
        "供應商聯絡": "sales@example.com", "採購成本": "80000",
        "建議售價": "128000", "安全庫存": "2",
        "備註": "★這是範例列，填完自己的資料請刪掉這一列",
    }],
    "stock": [{
        "庫存編號": "S-0001", "品項編號": "MD-001", "批號": "LOT2026A",
        "序號": "SN-000123", "數量": "1", "製造日期": "2026-01-10",
        "有效期限": "2029-01-09", "進貨日期": "2026-02-01",
        "進貨單號": "PO-2026-001", "儲位": "A-01", "狀態": "在庫",
        "備註": "★範例列，請刪除",
    }],
    "trace": [{
        "紀錄日期": "2026-02-01", "類別": "進貨", "品項編號": "MD-001",
        "品名": "（範例）床邊型生理監視器", "批號": "LOT2026A", "序號": "SN-000123",
        "數量": "1", "對象名稱": "Demo Medical Co., Ltd.",
        "對象統編或機構代碼": "—", "對象地址": "Tokyo, Japan",
        "交貨日期": "2026-02-01", "製造日期": "2026-01-10", "有效期限": "2029-01-09",
        "單據號碼": "PO-2026-001", "病人姓名": "", "病人身分證號": "",
        "備註": "★範例列，請刪除。類別只能填「進貨」或「出貨」",
    }],
    "loans": [{
        "借出單號": "L-0001", "品項編號": "MD-001", "品名": "（範例）床邊型生理監視器",
        "序號": "SN-000123", "借用單位": "示範醫院 心臟內科", "聯絡人": "王護理長",
        "電話": "02-0000-0000", "借出日": "2026-08-01", "應歸還日": "2026-08-31",
        "實際歸還日": "", "押金": "0", "狀態": "借出中", "備註": "★範例列，請刪除",
    }],
    "maintenance": [{
        "設備序號": "SN-000123", "品項編號": "MD-001",
        "品名": "（範例）床邊型生理監視器", "所在單位": "示範醫院 心臟內科",
        "類型": "年度保養", "上次執行日": "2026-03-15", "週期月數": "12",
        "下次到期日": "", "負責人": "工程部小林", "狀態": "正常",
        "備註": "★範例列，請刪除。下次到期日留空會自動用上次執行日＋週期月數推算",
    }],
}

# ─────────────────────────── 共用工具 ───────────────────────────

def script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def load_config():
    path = os.path.join(script_dir(), "..", "references", "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "提醒天數": {
                "效期到期預警天數": 180, "效期紅色警戒天數": 60,
                "許可證到期預警天數": 180, "保養校正到期預警天數": 30,
                "借出逾期預警天數": 7, "申報期預警天數": 30,
            },
            "法規參數": {"季申報截止日": ["01-20", "04-20", "07-20", "10-20"]},
        }


def parse_date(s):
    """接受 2026-08-23 / 2026/8/23 / 20260823 / 民國115.08.23；解析不出來回 None。"""
    if not s:
        return None
    s = str(s).strip().replace("　", "").replace(" ", "")
    if not s or s in {"—", "-", "無", "N/A", "NA"}:
        return None
    if s.count(".") == 2 and len(s.split(".")[0]) <= 3:      # 民國 115.08.23
        try:
            y, m, d = s.split(".")
            return date(int(y) + 1911, int(m), int(d))
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y.%m.%d", "%Y-%m", "%Y/%m"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def add_months(d, months):
    y, m = d.year, d.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def to_int(s, default=0):
    try:
        return int(float(str(s).replace(",", "").strip()))
    except (ValueError, AttributeError, TypeError):
        return default


def read_table(dirpath, key, required=True):
    path = os.path.join(dirpath, FILES[key])
    if not os.path.exists(path):
        if required:
            print(f"⚠️  找不到 {FILES[key]}，先跑一次： python3 devicemgr.py init --dir \"{dirpath}\"")
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    # 濾掉範例列與整列空白
    out = []
    for r in rows:
        r = {(k or "").strip(): (v or "").strip() for k, v in r.items()}
        if not any(r.values()):
            continue
        if "★" in r.get("備註", ""):
            continue
        out.append(r)
    return out


def write_table(dirpath, key, rows):
    path = os.path.join(dirpath, FILES[key])
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS[key])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HEADERS[key]})
    return path


def days_between(target, today):
    return (target - today).days


def fmt_money(n):
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return str(n)

# ─────────────────────────── init ───────────────────────────

def cmd_init(args):
    os.makedirs(args.dir, exist_ok=True)
    made, skipped = [], []
    for key in FILES:
        path = os.path.join(args.dir, FILES[key])
        if os.path.exists(path) and not args.force:
            skipped.append(FILES[key])
            continue
        write_table(args.dir, key, SAMPLES.get(key, []))
        made.append(FILES[key])
    print("📋 小械｜建表完成")
    print(f"   位置：{os.path.abspath(args.dir)}")
    for m in made:
        print(f"   ✅ 已建立 {m}")
    for s in skipped:
        print(f"   ⏭️  已存在，未覆蓋 {s}（要重建請加 --force）")
    print("\n下一步：")
    print("   1. 用 Excel／Numbers 打開，把★範例列刪掉，換成自己的資料")
    print("   2. 先填「1_器材主檔.csv」，其他表都靠品項編號串起來")
    print(f"   3. 填完跑健檢： python3 devicemgr.py check --dir \"{args.dir}\"")

# ─────────────────────────── check ───────────────────────────

def cmd_check(args):
    cfg = load_config()
    warn = cfg.get("提醒天數", {})
    today = parse_date(args.today) or date.today()
    d_exp   = args.days if args.days else warn.get("效期到期預警天數", 180)
    d_red   = warn.get("效期紅色警戒天數", 60)
    d_lic   = warn.get("許可證到期預警天數", 180)
    d_maint = warn.get("保養校正到期預警天數", 30)
    d_loan  = warn.get("借出逾期預警天數", 7)
    d_file  = warn.get("申報期預警天數", 30)

    devices = read_table(args.dir, "devices")
    stock   = read_table(args.dir, "stock", required=False)
    trace   = read_table(args.dir, "trace", required=False)
    loans   = read_table(args.dir, "loans", required=False)
    maint   = read_table(args.dir, "maintenance", required=False)
    dmap = {d.get("品項編號", ""): d for d in devices}

    alerts = defaultdict(list)   # 區塊 -> [(等級, 文字)]

    # ① 效期
    for s in stock:
        if s.get("狀態") in {"已出貨", "報廢", "已退貨"}:
            continue
        exp = parse_date(s.get("有效期限"))
        name = dmap.get(s.get("品項編號", ""), {}).get("品名", s.get("品項編號", "?"))
        tag = f"{name}／批號 {s.get('批號') or '—'}／序號 {s.get('序號') or '—'}／{s.get('數量') or '?'} {dmap.get(s.get('品項編號',''),{}).get('單位','')}"
        if exp is None:
            alerts["效期"].append(("🟡", f"{tag}：**有效期限空白或格式看不懂**（法定來源資料必填，請補）"))
            continue
        n = days_between(exp, today)
        if n < 0:
            alerts["效期"].append(("🔴", f"{tag}：**已過期 {abs(n)} 天**（{exp}）→ 立即隔離、標示、不得出貨"))
        elif n <= d_red:
            alerts["效期"].append(("🔴", f"{tag}：剩 {n} 天到期（{exp}）→ 優先出貨或與原廠談退換"))
        elif n <= d_exp:
            alerts["效期"].append(("🟠", f"{tag}：剩 {n} 天到期（{exp}）"))

    # ② 許可證
    for d in devices:
        exp = parse_date(d.get("許可證有效期限"))
        nm = f"{d.get('品項編號')} {d.get('品名')}"
        if exp is None:
            alerts["許可證"].append(("🟡", f"{nm}：許可證有效期限未填 → 無法判斷能不能繼續銷售，請補"))
            continue
        n = days_between(exp, today)
        if n < 0:
            alerts["許可證"].append(("🔴", f"{nm}：**許可證已於 {exp} 到期（{abs(n)} 天前）** → 停止銷售，確認展延狀態"))
        elif n <= d_lic:
            alerts["許可證"].append(("🟠", f"{nm}：許可證 {exp} 到期（剩 {n} 天）→ 展延要提前送件，別壓線"))

    # ③ 安全庫存
    on_hand = defaultdict(int)
    for s in stock:
        if s.get("狀態") in {"在庫", "", "借出"}:
            on_hand[s.get("品項編號", "")] += to_int(s.get("數量"), 0)
    for d in devices:
        safe = to_int(d.get("安全庫存"), -1)
        if safe < 0:
            continue
        have = on_hand.get(d.get("品項編號", ""), 0)
        if have < safe:
            alerts["庫存"].append(("🟠", f"{d.get('品項編號')} {d.get('品名')}：在庫 {have}，低於安全庫存 {safe} → 缺 {safe - have} {d.get('單位','')}"))

    # ④ 借出／試用機
    for l in loans:
        if l.get("實際歸還日") or l.get("狀態") in {"已歸還", "已結案"}:
            continue
        due = parse_date(l.get("應歸還日"))
        tag = f"{l.get('借出單號')} {l.get('品名') or l.get('品項編號')}／序號 {l.get('序號') or '—'}／{l.get('借用單位')}（{l.get('聯絡人')} {l.get('電話')}）"
        if due is None:
            alerts["借出"].append(("🟡", f"{tag}：應歸還日未填 → 試用機沒有歸還日等於送人，請補"))
            continue
        n = days_between(due, today)
        if n < 0:
            alerts["借出"].append(("🔴", f"{tag}：**逾期 {abs(n)} 天未還**（應還 {due}）→ 今天打電話"))
        elif n <= d_loan:
            alerts["借出"].append(("🟠", f"{tag}：{n} 天後到期（{due}）→ 提前一週通知，順便問要不要買"))

    # ⑤ 保養／校正
    for m in maint:
        due = parse_date(m.get("下次到期日"))
        if due is None:
            last, cyc = parse_date(m.get("上次執行日")), to_int(m.get("週期月數"), 0)
            if last and cyc:
                due = add_months(last, cyc)
        tag = f"{m.get('品名') or m.get('品項編號')}／序號 {m.get('設備序號')}／{m.get('所在單位')}／{m.get('類型')}"
        if due is None:
            alerts["保養校正"].append(("🟡", f"{tag}：算不出到期日（上次執行日或週期月數沒填）"))
            continue
        n = days_between(due, today)
        if n < 0:
            alerts["保養校正"].append(("🔴", f"{tag}：**逾期 {abs(n)} 天未執行**（應於 {due}）→ 排工程師"))
        elif n <= d_maint:
            alerts["保養校正"].append(("🟠", f"{tag}：{n} 天後到期（{due}）→ 先跟客戶約時間"))

    # ⑥ 來源流向法定欄位缺漏
    legal_in  = ["品項編號", "批號", "數量", "對象名稱", "有效期限"]
    legal_out = ["品項編號", "批號", "數量", "對象名稱", "對象地址", "交貨日期"]
    for i, t in enumerate(trace, start=2):
        kind = t.get("類別", "")
        need = legal_in if "進" in kind else legal_out
        miss = [c for c in need if not t.get(c)]
        if not t.get("批號") and t.get("序號"):
            miss = [c for c in miss if c != "批號"]      # 有序號可代替批號
        if miss:
            alerts["來源流向"].append(("🔴", f"第 {i} 列（{t.get('紀錄日期','?')} {kind} {t.get('品名') or t.get('品項編號')}）缺法定欄位：{'、'.join(miss)}"))
        pid = t.get("品項編號", "")
        if pid and pid not in dmap:
            alerts["來源流向"].append(("🟡", f"第 {i} 列品項編號 {pid} 不在器材主檔 → 主檔漏建或編號打錯"))
        if t.get("病人身分證號") and dmap.get(pid, {}).get("是否植入式", "").upper() != "Y":
            alerts["來源流向"].append(("🟡", f"第 {i} 列填了病人身分證號，但主檔不是植入式 → 非必要別蒐個資，確認後刪除"))

    # ⑦ 季申報期
    need_file = [d for d in devices if d.get("是否公告申報品項", "").upper() == "Y"]
    if need_file:
        for md in cfg.get("法規參數", {}).get("季申報截止日", []):
            try:
                mm, dd = md.split("-")
                due = date(today.year, int(mm), int(dd))
                if due < today:
                    due = date(today.year + 1, int(mm), int(dd))
            except (ValueError, AttributeError):
                continue
            n = days_between(due, today)
            if n <= d_file:
                alerts["申報期"].append(("🟠", f"公告申報品項共 {len(need_file)} 項，最近申報截止日 {due}（剩 {n} 天）→ 備妥來源流向資料，由公司法規窗口上系統申報"))
                break

    # ── 輸出 ──
    order = ["效期", "許可證", "來源流向", "借出", "保養校正", "庫存", "申報期"]
    icons = {"效期": "⏳", "許可證": "📜", "來源流向": "🔗", "借出": "🔁",
             "保養校正": "🔧", "庫存": "📦", "申報期": "🗓️"}
    lines = []
    red = sum(1 for k in alerts for lv, _ in alerts[k] if lv == "🔴")
    org = sum(1 for k in alerts for lv, _ in alerts[k] if lv == "🟠")
    yel = sum(1 for k in alerts for lv, _ in alerts[k] if lv == "🟡")

    lines.append(f"# 📋 小械健檢報告｜{today}")
    lines.append("")
    lines.append(f"掃描：器材主檔 {len(devices)} 項／庫存 {len(stock)} 筆／來源流向 {len(trace)} 筆／借出 {len(loans)} 筆／保養校正 {len(maint)} 筆")
    lines.append("")
    lines.append(f"**🔴 立即處理 {red} 件　🟠 一週內 {org} 件　🟡 補資料 {yel} 件**")
    lines.append("")
    if not (red or org or yel):
        lines.append("✅ 全部通過，沒有告警。（若這是第一次跑，先確認資料真的填進去了）")
    for k in order:
        if not alerts.get(k):
            continue
        lines.append(f"## {icons[k]} {k}（{len(alerts[k])}）")
        for lv in ("🔴", "🟠", "🟡"):
            for level, txt in alerts[k]:
                if level == lv:
                    lines.append(f"- {lv} {txt}")
        lines.append("")
    lines.append("---")
    lines.append("⚠️ 本報告為內部管理提醒，不代表法規適用判定，亦未代為向主管機關申報。")
    lines.append("")
    lines.append("＿Sixhands Studio AI數字員工 🦞 營運部・小械＿")

    out = "\n".join(lines)
    print(out)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"\n💾 已存檔：{args.out}", file=sys.stderr)
    return out

# ─────────────────────────── stock ───────────────────────────

def cmd_stock(args):
    today = parse_date(args.today) or date.today()
    devices = read_table(args.dir, "devices")
    stock = read_table(args.dir, "stock", required=False)
    dmap = {d.get("品項編號", ""): d for d in devices}

    groups = defaultdict(list)
    for s in stock:
        if s.get("狀態") in {"已出貨", "報廢", "已退貨"}:
            continue
        if args.item and s.get("品項編號") != args.item:
            continue
        groups[s.get("品項編號", "")].append(s)

    print(f"# 📦 庫存彙總（FEFO 出貨建議）｜{today}\n")
    if not groups:
        print("（沒有在庫資料）")
        return
    total_value = 0
    for pid, rows in sorted(groups.items()):
        d = dmap.get(pid, {})
        unit = d.get("單位", "")
        qty = sum(to_int(r.get("數量"), 0) for r in rows)
        cost = to_int(d.get("採購成本"), 0)
        total_value += qty * cost
        safe = to_int(d.get("安全庫存"), -1)
        flag = "　⚠️ 低於安全庫存" if 0 <= safe > qty else ""
        print(f"## {pid}　{d.get('品名', '（主檔查無此品號）')}")
        print(f"在庫合計：**{qty} {unit}**　"
              f"{'安全庫存 ' + str(safe) + unit if safe >= 0 else ''}{flag}　"
              f"{'庫存成本 ' + fmt_money(qty * cost) + ' 元' if cost else ''}")
        print("")
        print("| 出貨順序 | 批號 | 序號 | 數量 | 有效期限 | 剩餘天數 | 儲位 | 狀態 |")
        print("|:--|:--|:--|--:|:--|--:|:--|:--|")
        rows_sorted = sorted(rows, key=lambda r: (parse_date(r.get("有效期限")) or date(9999, 12, 31)))
        for i, r in enumerate(rows_sorted, 1):
            exp = parse_date(r.get("有效期限"))
            n = days_between(exp, today) if exp else None
            mark = "①先出" if i == 1 else str(i)
            ntxt = ("**已過期**" if n is not None and n < 0 else (str(n) if n is not None else "—"))
            print(f"| {mark} | {r.get('批號') or '—'} | {r.get('序號') or '—'} | {r.get('數量')} | "
                  f"{r.get('有效期限') or '—'} | {ntxt} | {r.get('儲位') or '—'} | {r.get('狀態') or '在庫'} |")
        print("")
    if total_value:
        print(f"**全庫存帳面成本合計：{fmt_money(total_value)} 元**（依主檔採購成本估算，非會計帳）\n")
    print("---\n出貨原則：**FEFO — 效期先到的先出**，不是先進先出。表中①即為建議出貨批號。\n")
    print("＿Sixhands Studio AI數字員工 🦞 營運部・小械＿")

# ─────────────────────────── trace ───────────────────────────

def cmd_trace(args):
    cfg = load_config()
    today = date.today()
    devices = read_table(args.dir, "devices")
    trace = read_table(args.dir, "trace", required=False)
    dmap = {d.get("品項編號", ""): d for d in devices}

    def hit(t):
        if args.lot:
            return t.get("批號") == args.lot
        if args.serial:
            return t.get("序號") == args.serial
        if args.item:
            return t.get("品項編號") == args.item
        return False

    rows = [t for t in trace if hit(t)]
    key = args.lot or args.serial or args.item
    print(f"# 🔗 來源流向追溯表｜查詢鍵：{key}｜產表日 {today}\n")
    if not rows:
        print("（查無紀錄。確認批號／序號有沒有打錯，或該筆進出貨還沒登錄到 3_來源流向.csv）")
        return

    ins  = [t for t in rows if "進" in t.get("類別", "")]
    outs = [t for t in rows if "出" in t.get("類別", "")]
    pid = rows[0].get("品項編號", "")
    d = dmap.get(pid, {})
    print(f"**品項**：{pid}　{d.get('品名') or rows[0].get('品名','') or '（主檔查無此品號）'}　"
          f"型號 {d.get('型號') or '—'}　風險等級 {d.get('風險等級') or '—'}　"
          f"許可證 {d.get('許可證字號') or '—'}　UDI-DI {d.get('UDI-DI') or '—'}\n")

    print("## 一、來源（進貨）\n")
    print("| 進貨日 | 供應來源 | 統編/代碼 | 地址 | 批號 | 序號 | 數量 | 製造日期 | 有效期限 | 單據 |")
    print("|:--|:--|:--|:--|:--|:--|--:|:--|:--|:--|")
    for t in sorted(ins, key=lambda x: parse_date(x.get("紀錄日期")) or date(1900, 1, 1)):
        print(f"| {t.get('紀錄日期')} | {t.get('對象名稱')} | {t.get('對象統編或機構代碼') or '—'} | "
              f"{t.get('對象地址') or '—'} | {t.get('批號') or '—'} | {t.get('序號') or '—'} | "
              f"{t.get('數量')} | {t.get('製造日期') or '—'} | {t.get('有效期限') or '—'} | {t.get('單據號碼') or '—'} |")
    if not ins:
        print("| — | **查無進貨紀錄（來源斷鏈，必須補）** | | | | | | | | |")

    print("\n## 二、流向（出貨）\n")
    print("| 出貨日 | 交貨日 | 供應對象 | 統編/代碼 | 地址 | 批號 | 序號 | 數量 | 單據 |")
    print("|:--|:--|:--|:--|:--|:--|:--|--:|:--|")
    for t in sorted(outs, key=lambda x: parse_date(x.get("紀錄日期")) or date(1900, 1, 1)):
        print(f"| {t.get('紀錄日期')} | {t.get('交貨日期') or '—'} | {t.get('對象名稱')} | "
              f"{t.get('對象統編或機構代碼') or '—'} | {t.get('對象地址') or '—'} | "
              f"{t.get('批號') or '—'} | {t.get('序號') or '—'} | {t.get('數量')} | {t.get('單據號碼') or '—'} |")
    if not outs:
        print("| — | | **尚無出貨紀錄（仍在庫）** | | | | | | |")

    qin  = sum(to_int(t.get("數量"), 0) for t in ins)
    qout = sum(to_int(t.get("數量"), 0) for t in outs)
    print(f"\n**進 {qin}　出 {qout}　帳面差 {qin - qout}**")
    if qin - qout < 0:
        print("\n🔴 出貨量大於進貨量 → 來源紀錄一定有漏，立刻回查。")

    keep = cfg.get("法規參數", {})
    is_report_item = d.get("是否公告申報品項", "").upper() == "Y"
    print("\n---")
    print(f"保存年限：{'**永久保存**（公告申報品項）' if is_report_item else str(keep.get('來源流向資料保存年限_一般', 3)) + ' 年'}"
          f"　｜依據：醫療器材來源流向資料建立及管理辦法")
    print("\n⚠️ 本表為內部整理，供自主管理與備查準備使用；正式提報內容與格式請以主管機關公告系統為準。\n")
    print("＿Sixhands Studio AI數字員工 🦞 營運部・小械＿")

# ─────────────────────────── report ───────────────────────────

def cmd_report(args):
    today = parse_date(args.today) or date.today()
    period = args.period or f"{today.year}年{today.month}月"
    devices = read_table(args.dir, "devices")
    stock   = read_table(args.dir, "stock", required=False)
    trace   = read_table(args.dir, "trace", required=False)
    loans   = read_table(args.dir, "loans", required=False)

    # 期間內進出
    def in_period(t):
        d = parse_date(t.get("紀錄日期"))
        return bool(d) and d.year == today.year and d.month == today.month
    p_in  = [t for t in trace if in_period(t) and "進" in t.get("類別", "")]
    p_out = [t for t in trace if in_period(t) and "出" in t.get("類別", "")]

    dmap = {d.get("品項編號", ""): d for d in devices}
    rev = 0
    for t in p_out:
        d = dmap.get(t.get("品項編號", ""), {})
        rev += to_int(d.get("建議售價"), 0) * to_int(t.get("數量"), 0)

    on_hand = defaultdict(int)
    for s in stock:
        if s.get("狀態") not in {"已出貨", "報廢", "已退貨"}:
            on_hand[s.get("品項編號", "")] += to_int(s.get("數量"), 0)
    inv_value = sum(q * to_int(dmap.get(p, {}).get("採購成本"), 0) for p, q in on_hand.items())
    open_loans = [l for l in loans if not l.get("實際歸還日") and l.get("狀態") not in {"已歸還", "已結案"}]

    # 借健檢文字（重導 stdout）
    import io
    buf, old = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        ns = argparse.Namespace(dir=args.dir, days=None, today=str(today), out=None)
        cmd_check(ns)
    finally:
        sys.stdout = old
    check_txt = buf.getvalue()
    body = check_txt.split("\n", 2)[2] if check_txt.count("\n") > 2 else check_txt

    md = []
    md.append(f"# 🩺 醫療器材管理月報｜{period}\n")
    md.append("## 三句話結論\n")
    md.append(f"1. **進出**：本月進貨 {len(p_in)} 筆、出貨 {len(p_out)} 筆"
              f"{'，出貨帳面金額約 ' + fmt_money(rev) + ' 元' if rev else ''}。")
    md.append(f"2. **庫存**：在管品項 {len(devices)} 項、在庫批號 {len(stock)} 筆"
              f"{'，帳面成本約 ' + fmt_money(inv_value) + ' 元' if inv_value else ''}；"
              f"在外試用／借出機 {len(open_loans)} 台。")
    md.append("3. **要盯的一件事**：見下方健檢🔴項；沒有🔴就盯最近到期的效期與保養。\n")
    md.append("## 一、健檢結果\n")
    md.append(body.strip())
    md.append("\n## 二、本月進出明細\n")
    md.append("| 日期 | 類別 | 品項 | 批號/序號 | 數量 | 對象 | 單據 |")
    md.append("|:--|:--|:--|:--|--:|:--|:--|")
    for t in sorted(p_in + p_out, key=lambda x: parse_date(x.get("紀錄日期")) or date(1900, 1, 1)):
        md.append(f"| {t.get('紀錄日期')} | {t.get('類別')} | {t.get('品名') or t.get('品項編號')} | "
                  f"{t.get('批號') or t.get('序號') or '—'} | {t.get('數量')} | "
                  f"{t.get('對象名稱')} | {t.get('單據號碼') or '—'} |")
    if not (p_in or p_out):
        md.append("| — | — | （本月無進出貨紀錄，或紀錄日期未填） | — | — | — | — |")
    md.append("\n## 三、在外試用／借出機\n")
    if open_loans:
        md.append("| 單號 | 品項 | 序號 | 借用單位 | 聯絡人 | 借出日 | 應歸還日 |")
        md.append("|:--|:--|:--|:--|:--|:--|:--|")
        for l in open_loans:
            md.append(f"| {l.get('借出單號')} | {l.get('品名') or l.get('品項編號')} | {l.get('序號') or '—'} | "
                      f"{l.get('借用單位')} | {l.get('聯絡人')} | {l.get('借出日')} | {l.get('應歸還日') or '**未填**'} |")
    else:
        md.append("（本期無在外機台）")
    md.append("\n## 四、待確認清單（請老闆回覆後才定案）\n")
    md.append("- [ ] 本月有無不良事件／客訴／退貨？（有的話要走通報與回收流程，見 references/法規要點與紅線.md）")
    md.append("- [ ] 有無新增品項尚未建主檔／新許可證尚未登錄？")
    md.append("- [ ] 效期🔴品項的處理方式：退原廠／報廢／降價出清（醫材效期品不得展延）")
    md.append("\n---")
    md.append("⚠️ 本報告由 AI 依所提供之資料整理，供內部管理使用；**非**法規符合性認證，亦未代為向主管機關申報或通報。"
              "醫療器材許可、運銷、通報、回收等法定義務，請以公司法規負責人及主管機關公告為準。\n")
    md.append("＿Sixhands Studio AI數字員工 🦞 營運部・小械＿")

    out = "\n".join(md)
    path = args.out or os.path.join(args.dir, f"月報_{today.year}{today.month:02d}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(out)
    print(f"\n💾 已存檔：{path}", file=sys.stderr)

# ─────────────────────────── main ───────────────────────────

def main():
    p = argparse.ArgumentParser(description="小械｜醫療器材管理工具", formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--dir", default="./器材資料", help="資料資料夾（預設 ./器材資料）")
        sp.add_argument("--today", default=None, help="模擬日期 YYYY-MM-DD（測試用）")

    sp = sub.add_parser("init", help="建立五張表的空白範本"); common(sp)
    sp.add_argument("--force", action="store_true", help="覆蓋既有檔案")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("check", help="六大健檢"); common(sp)
    sp.add_argument("--days", type=int, default=None, help="效期預警天數（覆蓋 config）")
    sp.add_argument("--out", default=None, help="另存 Markdown")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("stock", help="庫存彙總與 FEFO 出貨建議"); common(sp)
    sp.add_argument("--item", default=None, help="只看單一品項編號")
    sp.set_defaults(func=cmd_stock)

    sp = sub.add_parser("trace", help="來源流向追溯"); common(sp)
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--lot", help="批號")
    g.add_argument("--serial", help="序號")
    g.add_argument("--item", help="品項編號")
    sp.set_defaults(func=cmd_trace)

    sp = sub.add_parser("report", help="月度管理報告"); common(sp)
    sp.add_argument("--period", default=None, help="期間標題，例如 2026年8月")
    sp.add_argument("--out", default=None, help="輸出路徑")
    sp.set_defaults(func=cmd_report)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
