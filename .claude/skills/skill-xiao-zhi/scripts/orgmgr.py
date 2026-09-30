#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
orgmgr.py — AI 員工「小織」的經銷組織架構管線工具
Sixhands Studio AI數字員工 🦞

零安裝、不連網、不用裝任何套件。所有資料都是你電腦裡的 CSV / JSON。

    python3 orgmgr.py init      --dir "./天麗組織資料"
    python3 orgmgr.py verdict   --dir "./天麗組織資料"
    python3 orgmgr.py comp      --dir "./天麗組織資料"
    python3 orgmgr.py blueprint --dir "./天麗組織資料" --target 300
    python3 orgmgr.py pipeline  --dir "./天麗組織資料"
    python3 orgmgr.py health    --dir "./天麗組織資料" --period 2026-09
    python3 orgmgr.py report    --dir "./天麗組織資料" --period 2026-09
    python3 orgmgr.py scan      --file "招募貼文.txt"

Windows 使用者把 python3 換成 python。
"""
import argparse
import csv
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import unicodedata

ENC = "utf-8-sig"          # CSV：讓 Excel 直接雙擊也不亂碼
JENC = "utf-8"             # JSON / 文字檔

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
DEFAULT_CONFIG = SKILL_ROOT / "references" / "config.json"
TPL_DIR = SKILL_ROOT / "範本"

# ─────────────────────────────────────────── 表格定義

TABLES = {
    "1_經銷商名冊.csv": [
        "編號", "加入日期", "稱呼", "聯絡方式", "階級", "推薦人編號", "所屬線",
        "狀態", "最近出貨日", "合規認證年度", "備註",
    ],
    "2_招募名單.csv": [
        "編號", "建檔日期", "來源", "稱呼", "聯絡方式", "負責推薦人",
        "目前階段", "面談健康題數", "下次聯繫日", "結果", "備註",
    ],
    "3_月結業績.csv": [
        "月份", "經銷商編號", "個人零售額", "自購額", "團隊零售額",
        "入會相關收入", "獎金", "期末庫存", "備註",
    ],
    "4_教育訓練紀錄.csv": [
        "日期", "經銷商編號", "課程代號", "課程名稱", "結果", "分數", "備註",
    ],
}

STAGES = ["觸及", "諮詢", "說明會", "面談", "簽約", "啟動中", "已啟動", "暫緩", "婉拒"]

SAMPLES = {
    "1_經銷商名冊.csv": [{
        "編號": "D-001", "加入日期": "2026-06-01", "稱呼": "★範例｜A 顧問",
        "聯絡方式": "LINE: aaa", "階級": "2", "推薦人編號": "", "所屬線": "L1",
        "狀態": "活動中", "最近出貨日": "2026-09-01", "合規認證年度": "2026",
        "備註": "★這是範例列，請刪掉再填自己的",
    }],
    "2_招募名單.csv": [{
        "編號": "R-001", "建檔日期": "2026-09-01", "來源": "既有客戶轉介",
        "稱呼": "★範例｜B 小姐", "聯絡方式": "LINE: bbb", "負責推薦人": "D-001",
        "目前階段": "面談", "面談健康題數": "9", "下次聯繫日": "2026-09-05",
        "結果": "", "備註": "★範例列，請刪除",
    }],
    "3_月結業績.csv": [{
        "月份": "2026-09", "經銷商編號": "D-001", "個人零售額": "48000",
        "自購額": "6000", "團隊零售額": "0", "入會相關收入": "0",
        "獎金": "14000", "期末庫存": "35000", "備註": "★範例列，請刪除",
    }],
    "4_教育訓練紀錄.csv": [{
        "日期": "2026-09-02", "經銷商編號": "D-001", "課程代號": "B2",
        "課程名稱": "合規必修", "結果": "通過", "分數": "90",
        "備註": "★範例列，請刪除",
    }],
}

# ─────────────────────────────────────────── 小工具

def die(msg):
    print("❌ " + msg)
    sys.exit(1)


def load_config(path=None):
    p = Path(path) if path else DEFAULT_CONFIG
    if not p.exists():
        die("找不到設定檔：{}\n　 請確認 skill 資料夾完整，或用 --config 指定。".format(p))
    with open(p, encoding=JENC) as f:
        return json.load(f)


def data_dir(args):
    d = Path(args.dir).expanduser()
    if not d.exists():
        die("找不到資料夾：{}\n　 請先執行：python3 orgmgr.py init --dir \"{}\"".format(d, args.dir))
    return d


def read_csv(d, name):
    p = d / name
    if not p.exists():
        die("找不到 {}。請先執行 init。".format(p))
    with open(p, newline="", encoding=ENC) as f:
        rows = list(csv.DictReader(f))
    # 自動略過還沒刪掉的 ★範例列
    return [r for r in rows if not any("★" in (v or "") for v in r.values())]


def read_brand(d):
    p = d / "0_品牌資料卡.json"
    if not p.exists():
        die("找不到 {}。請先執行 init。".format(p))
    with open(p, encoding=JENC) as f:
        return json.load(f)


def num(s, default=0.0):
    try:
        return float(str(s).replace(",", "").strip() or default)
    except (ValueError, AttributeError):
        return default


def pdate(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def pct(x):
    return "{:.1f}%".format(x * 100)


def light(value, green, red, higher_is_better=True):
    if higher_is_better:
        if value >= green:
            return "🟢"
        if value < red:
            return "🔴"
        return "🟡"
    else:
        if value <= green:
            return "🟢"
        if value > red:
            return "🔴"
        return "🟡"


def wlen(s):
    """計算顯示寬度（中日韓全形字算 2 格）"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(s))


def pad(s, width, align="left"):
    """依顯示寬度補空白，讓中英混排的表格對得齊"""
    s = str(s)
    gap = max(width - wlen(s), 0)
    if align == "right":
        return " " * gap + s
    return s + " " * gap


def title(t):
    print("\n" + "═" * 60)
    print("  " + t)
    print("═" * 60)


def current_period(d=None):
    d = d or date.today()
    return "{:04d}-{:02d}".format(d.year, d.month)


def period_end(period):
    y, m = int(period[:4]), int(period[5:7])
    if m == 12:
        return date(y + 1, 1, 1) - timedelta(days=1)
    return date(y, m + 1, 1) - timedelta(days=1)

# ─────────────────────────────────────────── init

def cmd_init(args, cfg):
    d = Path(args.dir).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    created, skipped = [], []

    for name, cols in TABLES.items():
        p = d / name
        if p.exists():
            skipped.append(name)
            continue
        with open(p, "w", newline="", encoding=ENC) as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for row in SAMPLES.get(name, []):
                w.writerow(row)
        created.append(name)

    for name in ("0_品牌資料卡.json", "參加前應告知事項檢核表.md", "範本說明.md"):
        src, dst = TPL_DIR / name, d / name
        if dst.exists():
            skipped.append(name)
            continue
        if src.exists():
            dst.write_text(src.read_text(encoding=JENC), encoding=JENC)
            created.append(name)

    title("小織 · 資料夾建立完成")
    print("📁 位置：{}".format(d.resolve()))
    for n in created:
        print("   ✅ 建立 {}".format(n))
    for n in skipped:
        print("   ⏭️  已存在，未覆蓋 {}".format(n))
    print("\n下一步：")
    print("  1. 打開 0_品牌資料卡.json，把「制度屬性」四題填完（最重要）")
    print("  2. 執行：python3 orgmgr.py verdict --dir \"{}\"".format(args.dir))
    print("\n⚠️ 請不要把這個資料夾放在 iCloud 同步位置（桌面／文件），會讀檔卡住。")

# ─────────────────────────────────────────── verdict：制度屬性判定

def cmd_verdict(args, cfg):
    d = data_dir(args)
    b = read_brand(d)
    s = b.get("制度屬性", {})

    down = s.get("獎金是否來自下線銷售")
    layers = int(num(s.get("推薦利益層數"), 0))
    paid = s.get("加入是否需付費或門檻進貨")
    fee = num(s.get("門檻進貨金額"), 0)
    filed = s.get("是否已向公平會報備")
    docno = (s.get("報備文號") or "").strip()
    written = s.get("契約是否書面")
    checklist = s.get("是否有應告知事項檢核表")

    title("小織 · 制度屬性判定書（第 0 號文件）")
    unknown = [k for k, v in (("獎金是否來自下線銷售", down),
                              ("加入是否需付費或門檻進貨", paid)) if v is None]
    if unknown:
        print("⚠️ 以下欄位還沒填，無法判定：")
        for k in unknown:
            print("   ・{}".format(k))
        print("\n→ 請先打開 0_品牌資料卡.json 的「制度屬性」把它填完（true / false）。")
        print("   參考：references/開工前必問15題.md 的第 1～4 題")
        return

    print("① 獎金是否來自下線銷售　：{}".format("是" if down else "否"))
    print("② 推薦利益層數　　　　　：{} 層".format(layers))
    print("③ 加入是否需付費／門檻進貨：{}{}".format(
        "是" if paid else "否", "（{:,.0f} 元）".format(fee) if paid and fee else ""))

    is_mlm = bool(down) and layers >= 2
    print("\n" + "─" * 60)
    if is_mlm:
        print("🔴 判定：**高度可能屬於《多層次傳銷管理法》所稱之多層次傳銷**")
        print("   → 事業應於開始實施前向公平交易委員會報備。")
        print("\n   報備狀態：{}{}".format(
            "✅ 已報備" if filed else "❌ 未報備／未填",
            "（文號 {}）".format(docno) if docno else ""))
        if not filed or not docno:
            print("\n🚨 停止所有招募動作。")
            print("   沒有報備文號以前，小織不會產出任何招募文案、招商簡報或說明會素材。")
            print("   這不是行銷問題，請先處理報備（交律師／向公平會諮詢）。")
        else:
            print("\n   ✅ 可往下走。但每一份對外文件都必須加註：")
            print("      「本事業已依法報備；報備不表示主管機關已對其傳銷制度或商品為推薦或保證。」")
        print("\n   適用架構：references/組織架構藍圖與階級設計.md →「多層次（階級制）」")
    elif bool(down) and layers == 1:
        print("🟡 判定：**單層推薦制**（獎金只及於第一代）")
        print("   → 一般認為未達多層次傳銷之「多層級」要件，但**制度實質仍可能被認定**，")
        print("     建議在制度定稿前向律師或公平會確認，並保留書面意見。")
        print("\n   適用架構：references/組織架構藍圖與階級設計.md →「雙層／有限層」")
    else:
        print("🟢 判定：**單層經銷／一般商業模式**")
        print("   → 走經銷契約與一般商業規範，不受多層次傳銷管理法拘束。")
        print("   小織建議：**先把單層做穩、確認零售真的賣得動，再考慮開多層。**")
        print("\n   適用架構：references/組織架構藍圖與階級設計.md →「單層經銷」")

    print("\n" + "─" * 60)
    print("附帶檢查：")
    print("   ・參加契約是否書面　　　：{}".format(
        "✅ 是" if written else "🔴 否／未填 → 依法應以書面為之"))
    print("   ・是否有應告知事項檢核表：{}".format(
        "✅ 有" if checklist else "🔴 無／未填 → 見 範本/參加前應告知事項檢核表.md"))
    if paid and fee > 0:
        print("   ・門檻進貨 {:,.0f} 元 → ⚠️ 金額越高，越可能被視為變相人頭費，且製造囤貨。".format(fee))
        print("     建議：起步包價格接近成本、明示可退，並把首購從「資格條件」拿掉。")

    print("\n📌 本判定為營運理解用，**不是法律意見**。制度定稿前請交執業律師確認。")

# ─────────────────────────────────────────── comp：獎金結構健檢

def cmd_comp(args, cfg):
    d = data_dir(args)
    b = read_brand(d)
    pool = b.get("獎金池實際值", {})
    struct = b.get("獎金結構實際值_佔獎金池", {})
    limits = cfg["獎金池"]
    sug = cfg["獎金結構_建議佔獎金池"]

    title("小織 · 獎金結構健檢")

    total = sum(num(v) for v in pool.values())
    if total == 0:
        print("⚠️ 0_品牌資料卡.json 的「獎金池實際值」還是 0，無法健檢。")
        print("   請先填入四個佔比（以零售價 100% 為基礎，小數表示，例如 0.25）。")
        print("   算法見 references/獎金制度健檢與零售佔比.md 第一節。")
        return

    rows = [
        ("商品成本", "商品成本", "商品成本_上限"),
        ("營運物流行銷", "營運物流行銷", "營運物流行銷_上限"),
        ("稅與備抵退貨", "稅與備抵退貨", "稅與備抵退貨_上限"),
        ("可分配獎金池", "可分配獎金池", "可分配獎金池_上限"),
    ]
    print("【一】獎金池天花板（以零售價 100% 為基礎）\n")
    print("  {}{}{}".format(pad("項目", 18), pad("實際", 10, "right"), pad("建議上限", 14, "right")))
    flags = []
    for label, k, lk in rows:
        v, lim = num(pool.get(k)), limits[lk]
        mark = "🟢" if v <= lim else "🔴"
        if v > lim:
            flags.append("{} 佔比 {} 超過建議上限 {}".format(label, pct(v), pct(lim)))
        print("  {}{}{}  {}".format(pad(label, 18), pad(pct(v), 10, "right"),
                                       pad(pct(lim), 14, "right"), mark))
    print("\n  合計：{}".format(pct(total)))
    if abs(total - 1.0) > 0.02:
        print("  ⚠️ 四項合計應接近 100%，目前 {} → 請檢查數字是否填錯。".format(pct(total)))

    pool_v = num(pool.get("可分配獎金池"))
    if pool_v > 0.55:
        print("\n  🔴 獎金池 {} 已超過 55%。".format(pct(pool_v)))
        print("     不是售價脫離『合理市價』，就是在用新人的錢付老人的獎金 —— 兩者都撞紅線。")
        print("     檢驗方法：這個價格，在完全沒有事業機會的情況下，賣得掉嗎？")

    print("\n【二】獎金池怎麼分（佔獎金池 %）\n")
    checks = [
        ("個人零售獎金", "個人零售獎金", sug["個人零售獎金_下限"], "min"),
        ("回購維繫獎金", "回購維繫獎金", sug["回購維繫獎金"], "info"),
        ("第一代推薦獎金", "第一代推薦獎金", sug["第一代推薦獎金_上限"], "max"),
        ("組織領導獎金", "組織領導獎金", sug["組織領導獎金_上限"], "max"),
        ("晉升一次性獎勵", "晉升一次性獎勵", sug["晉升一次性獎勵_上限"], "max"),
        ("入會相關收入", "入會相關收入", sug["入會相關收入_上限"], "zero"),
    ]
    s_total = sum(num(v) for v in struct.values())
    for label, k, ref, kind in checks:
        v = num(struct.get(k))
        if kind == "min":
            mark = "🟢" if v >= ref else "🔴"
            note = "應 ≥ {}".format(pct(ref))
            if v < ref:
                flags.append("個人零售獎金僅 {}，低於建議下限 {} → 制度在教人『別賣、去找人』".format(pct(v), pct(ref)))
        elif kind == "max":
            mark = "🟢" if v <= ref else "🟡"
            note = "應 ≤ {}".format(pct(ref))
        elif kind == "zero":
            mark = "🟢" if v <= 0.001 else "🔴"
            note = "應趨近 0"
            if v > 0.001:
                flags.append("獎金池中有 {} 來自入會相關收入 → 直接指向拉人頭（§18 紅線）".format(pct(v)))
        else:
            mark, note = "・", "參考 {}".format(pct(ref))
        print("  {}{}   {}{}".format(pad(label, 18), pad(pct(v), 8, "right"),
                                        pad(note, 14), mark))
    if s_total > 0 and abs(s_total - 1.0) > 0.05:
        print("\n  ⚠️ 分配合計 {}，與 100% 差距過大 → 請檢查。".format(pct(s_total)))

    print("\n【三】五個制度陷阱檢查\n")
    s = b.get("制度屬性", {})
    fee = num(s.get("門檻進貨金額"))
    traps = [
        ("高門檻首購", fee > 10000,
         "門檻進貨 {:,.0f} 元 → 實質接近人頭費，且製造囤貨".format(fee)),
        ("獎金綁每月自購", None, "請人工確認：獎金資格是否綁『每月自購 X 元』？若是 → 立即改成綁『個人零售』"),
        ("無限代等比獎金", None, "請人工確認：是否每代同比例且無代數上限？若是 → 數學上必然爆掉"),
        ("晉升只看單月", None, "請人工確認：晉升是否只需單月達標？→ 應改為連續 2 個月＋含個人零售"),
        ("訓練收費綁資格", None, "請人工確認：是否有付費課程是升階必要條件？→ 應完全脫鉤"),
    ]
    for name, hit, msg in traps:
        if hit is True:
            print("  🔴 {}：{}".format(name, msg))
            flags.append("{}：{}".format(name, msg))
        elif hit is False:
            print("  🟢 {}：未觸發".format(name))
        else:
            print("  ⚪ {}：{}".format(name, msg))

    print("\n" + "─" * 60)
    if flags:
        print("🚨 需要處理的問題 {} 項：".format(len(flags)))
        for i, f in enumerate(flags, 1):
            print("  {}. {}".format(i, f))
        print("\n→ 制度變更前請先跑 100 人／500 人分配模擬，並交律師確認。")
    else:
        print("✅ 結構層面沒有明顯紅旗。仍請每月用 health 追蹤實際數字（制度好看不代表行為健康）。")

# ─────────────────────────────────────────── 系譜工具

def build_tree(members):
    children = defaultdict(list)
    by_id = {}
    for m in members:
        mid = (m.get("編號") or "").strip()
        if not mid:
            continue
        by_id[mid] = m
        parent = (m.get("推薦人編號") or "").strip()
        children[parent].append(mid)
    roots = [mid for mid, m in by_id.items()
             if (m.get("推薦人編號") or "").strip() not in by_id]
    return by_id, children, roots


def max_depth(children, roots):
    best = 0
    stack = [(r, 1) for r in roots]
    seen = set()
    while stack:
        node, dep = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        best = max(best, dep)
        for c in children.get(node, []):
            stack.append((c, dep + 1))
    return best

# ─────────────────────────────────────────── blueprint

def cmd_blueprint(args, cfg):
    d = data_dir(args)
    b = read_brand(d)
    members = read_csv(d, "1_經銷商名冊.csv")
    thr = cfg["健檢門檻"]
    inactive_days = cfg["提醒天數"]["經銷商未出貨視為不活動_天"]

    title("小織 · 組織藍圖")
    if not members:
        print("⚠️ 1_經銷商名冊.csv 還沒有資料（或只有範例列）。")
        print("   先把現有經銷商填進去，小織才畫得出現況圖。")
        return

    today = date.today()
    alive = [m for m in members if (m.get("狀態") or "").strip() != "退出"]
    active = []
    for m in alive:
        dt = pdate(m.get("最近出貨日"))
        if dt and (today - dt).days <= inactive_days:
            active.append(m)

    by_id, children, roots = build_tree(alive)
    depth = max_depth(children, roots)
    first_gen = len(roots)

    line_count = Counter((m.get("所屬線") or "未分線").strip() for m in alive)
    biggest_line, biggest_n = (line_count.most_common(1)[0] if line_count else ("-", 0))
    conc = biggest_n / len(alive) if alive else 0
    act_rate = len(active) / len(alive) if alive else 0

    print("【現況圖】{}".format(today.isoformat()))
    print("  總人數（未退出）：{} 人".format(len(alive)))
    print("  活動人數（{} 天內有出貨）：{} 人　活動率 {} {}".format(
        inactive_days, len(active), pct(act_rate),
        light(act_rate, thr["活動率_綠燈"], thr["活動率_紅燈"])))
    print("  組織深度（最深幾層）：{} 層".format(depth))
    print("  第一代人數（直接掛在最上層）：{} 人".format(first_gen))
    print("  最大一條線：{}（{} 人，佔 {} {}）".format(
        biggest_line, biggest_n, pct(conc),
        light(conc, thr["單線集中度_綠燈"], thr["單線集中度_紅燈"], higher_is_better=False)))

    print("\n  診斷：")
    warned = False
    gaps = []
    if depth < 3:
        gaps.append("深度 {} 層（目標 ≥3）".format(depth))
    if act_rate < thr["活動率_綠燈"]:
        gaps.append("活動率 {}（目標 ≥{}）".format(pct(act_rate), pct(thr["活動率_綠燈"])))
    if conc > thr["單線集中度_綠燈"]:
        gaps.append("最大線 {}（目標 ≤{}）".format(pct(conc), pct(thr["單線集中度_綠燈"])))
    if first_gen > 20 and depth < 3:
        warned = True
        print("  🔴 第一代 {} 人但深度只有 {} 層 → **你是業務，不是領導人**。".format(first_gen, depth))
        print("     所有人都是你自己找的，沒有人在複製。先修 90 天啟動 SOP，不要再往外招。")
    if conc > thr["單線集中度_紅燈"]:
        warned = True
        print("  🔴 單線依賴：{} 佔了 {} → 那個人離開你就倒了。".format(biggest_line, pct(conc)))
        print("     12 個月目標：開出第 2、第 3 條獨立線。")
    if act_rate < thr["活動率_紅燈"]:
        warned = True
        print("  🔴 活動率 {} 過低 → 名冊上多數是掛名的人。".format(pct(act_rate)))
        print("     **先把現有的人救活，再談招募。** 招新人進來只會稀釋活動率。")
    if depth >= 3 and act_rate >= thr["活動率_綠燈"] and conc <= thr["單線集中度_綠燈"]:
        print("  🟢 結構健康：有深度、有活動、沒有單線依賴。可以進入擴張。")
    elif not warned:
        print("  🟡 沒有致命結構問題，但也還沒到綠燈。")
        print("     離綠燈還差：{}".format("、".join(gaps) if gaps else "（門檻已達，續追活動率）"))

    target = args.target or int(num(b.get("目標", {}).get("12個月_人數"), 0)) or max(len(alive) * 2, 30)
    print("\n【12 個月圖】目標 {} 人".format(target))
    leaders = [m for m in active if int(num(m.get("階級"), 1)) >= 3]
    n_leaders = len(leaders)
    print("  現有可帶人的夥伴（階級 ≥3 且活動中）：{} 人".format(n_leaders))
    need = max(target - len(alive), 0)
    print("  需要淨增：{} 人".format(need))
    if n_leaders == 0:
        print("  🔴 目前沒有任何一位「能帶人」的夥伴 →")
        print("     12 個月的第一件事不是招人，是**把 2～3 位現有夥伴培養成能開新人班的人**。")
        print("     沒有這一步，招進來的人會在 90 天內流失。")
    else:
        per = need / (n_leaders * 4.0)
        print("  建議節奏：每位夥伴**每季成功啟動 1 位新人**（90 天啟動 SOP）")
        print("            → {} 位夥伴 × 4 季 = {} 位新人；".format(n_leaders, n_leaders * 4))
        print("            目前缺口需要每位每季啟動 {:.1f} 位。".format(per))
        if per > 1.5:
            print("  ⚠️ 每季需啟動 {:.1f} 位 → 節奏過猛，90 天啟動品質會崩。".format(per))
            print("     建議：先把目標下修，或先增加『能帶人的人』數量（培養領導，不是增加人頭）。")
    print("\n  12 個月要達成的三個數字：")
    print("   ・活動率 ≥ {}".format(pct(thr["活動率_綠燈"])))
    print("   ・零售佔比 ≥ {}".format(pct(thr["零售佔比_綠燈"])))
    print("   ・最大單線 ≤ {}".format(pct(thr["單線集中度_綠燈"])))

    print("\n【36 個月圖】")
    print("  目標：3～5 條**獨立**主線，每條都有自己的區域夥伴與開課能力。")
    print("  判準：**創辦人請假一個月，業績掉幅 < 15%** → 系統成立。")
    print("        若掉幅 > 40% → 你沒有組織，你只有一群跟你買貨的朋友。")
    print("\n  依人數該補的內部職位（公司內部組織圖）：")
    for n, role in ((50, "專職客服／出貨 1 人"), (150, "專職教育訓練 1 人＋獎金結算系統化"),
                    (300, "專職合規 1 人＋區域經理"), (500, "財務稅務專責＋法務顧問常態化")):
        mark = "✅ 已到" if len(alive) >= n else "→ 到 {} 人時".format(n)
        print("   {:<12}{}".format(mark, role))

# ─────────────────────────────────────────── pipeline

def cmd_pipeline(args, cfg):
    d = data_dir(args)
    rows = read_csv(d, "2_招募名單.csv")
    rem = cfg["提醒天數"]
    today = date.today()

    title("小織 · 招募漏斗")
    if not rows:
        print("⚠️ 2_招募名單.csv 還沒有資料。")
        return

    cnt = Counter((r.get("目前階段") or "未填").strip() for r in rows)
    order = ["觸及", "諮詢", "說明會", "面談", "簽約", "啟動中", "已啟動"]
    rank = {st: i for i, st in enumerate(order)}
    # 累計通過人數：走到第 i 階（含之後）的人都算「通過過第 i 階」
    reached = []
    for i, st in enumerate(order):
        reached.append(sum(1 for r in rows
                           if rank.get((r.get("目前階段") or "").strip(), -1) >= i))
    print("【漏斗現況】（累計走到該階段的人數）\n")
    for i, st in enumerate(order):
        n = reached[i]
        conv = ""
        if i > 0 and reached[i - 1] > 0:
            conv = "　轉換 {}".format(pct(n / reached[i - 1]))
        bar = "█" * min(n, 40)
        print("  {}{} {}{}".format(pad(st, 8), pad(n, 4, "right"), bar, conv))
    dropped = [(st, cnt[st]) for st in ("暫緩", "婉拒", "未填") if cnt.get(st)]
    if dropped:
        print("\n  流出：" + "、".join("{} {} 人".format(a, b) for a, b in dropped))
    if reached[0] and reached[-1] / reached[0] < 0.1:
        print("\n  ⚠️ 觸及 → 已啟動 整體轉換 {} → 漏斗前段量夠但後段接不住。".format(
            pct(reached[-1] / reached[0])))
        print("     先看是卡在「說明會→面談」還是「簽約→啟動」，兩者的解法完全不同。")

    print("\n【今天該聯繫誰】\n")
    due = []
    for r in rows:
        if (r.get("目前階段") or "").strip() in ("已啟動", "婉拒"):
            continue
        nd = pdate(r.get("下次聯繫日"))
        if nd and nd <= today:
            due.append((nd, r))
    if not due:
        print("  ✅ 今天沒有到期的追蹤。")
    else:
        due.sort(key=lambda x: x[0])
        for nd, r in due:
            overdue = (today - nd).days
            tag = "🔴 逾期 {} 天".format(overdue) if overdue > 0 else "🟡 今天"
            print("  {} {}{}{}負責：{}".format(
                pad(tag, 12), pad(r.get("稱呼", ""), 12), pad(r.get("聯絡方式", ""), 14),
                pad(r.get("目前階段", ""), 8), r.get("負責推薦人", "")))

    print("\n【面談品質】\n")
    scored = [num(r.get("面談健康題數"), -1) for r in rows]
    scored = [s for s in scored if s >= 0]
    if scored:
        avg = sum(scored) / len(scored)
        low = len([s for s in scored if s <= 4])
        print("  已面談 {} 人，平均健康題數 {:.1f} / 12".format(len(scored), avg))
        print("  ≤4 分（應婉拒）：{} 人".format(low))
        if avg < 7:
            print("  ⚠️ 平均低於 7 → 名單來源品質有問題，不是話術問題。")
            print("     檢查：是不是在用『賺錢』當招募主軸？改用『商品體驗』開頭試試。")
    else:
        print("  尚無面談評分。面談 12 題見 references/招募與面談SOP.md")

    print("\n📌 提醒：簽約前必須完成〈參加前應告知事項檢核表〉與**書面契約**，")
    print("   順序是：告知 → 簽約 → 收款 → 出貨。顛倒就失去舉證能力。")

# ─────────────────────────────────────────── health

def compute_health(d, cfg, period):
    members = read_csv(d, "1_經銷商名冊.csv")
    perf = [r for r in read_csv(d, "3_月結業績.csv")
            if (r.get("月份") or "").strip() == period]
    train = read_csv(d, "4_教育訓練紀錄.csv")
    thr = cfg["健檢門檻"]
    # 當月還沒過完時，用今天當基準；否則用月底（避免月中執行時把人誤判成流失）
    end = min(period_end(period), date.today())
    inactive_days = cfg["提醒天數"]["經銷商未出貨視為不活動_天"]

    alive = [m for m in members if (m.get("狀態") or "").strip() != "退出"]
    retail = sum(num(r.get("個人零售額")) for r in perf)
    selfbuy = sum(num(r.get("自購額")) for r in perf)
    joinfee = sum(num(r.get("入會相關收入")) for r in perf)
    stock = sum(num(r.get("期末庫存")) for r in perf)
    revenue = retail + selfbuy + joinfee

    m = {}
    m["零售佔比"] = retail / revenue if revenue else 0
    m["入會相關收入佔比"] = joinfee / revenue if revenue else 0

    shipped = set()
    for r in perf:
        if num(r.get("個人零售額")) + num(r.get("自購額")) > 0:
            shipped.add((r.get("經銷商編號") or "").strip())
    m["活動率"] = len(shipped) / len(alive) if alive else 0

    cohort = [x for x in alive
              if pdate(x.get("加入日期"))
              and 90 <= (end - pdate(x.get("加入日期"))).days <= 180]
    survived = [x for x in cohort
                if pdate(x.get("最近出貨日"))
                and (end - pdate(x.get("最近出貨日"))).days <= inactive_days]
    m["新人90天存活率"] = (len(survived) / len(cohort)) if cohort else None

    lines = defaultdict(float)
    id2line = {(x.get("編號") or "").strip(): (x.get("所屬線") or "未分線").strip() for x in alive}
    for r in perf:
        ln = id2line.get((r.get("經銷商編號") or "").strip(), "未分線")
        lines[ln] += num(r.get("個人零售額")) + num(r.get("自購額"))
    tot_line = sum(lines.values())
    m["單線集中度"] = (max(lines.values()) / tot_line) if tot_line else 0
    biggest = max(lines, key=lines.get) if lines else "-"

    m["庫存週轉天數"] = (stock / retail * 30) if retail else 0

    yr = period[:4]
    certified = {(t.get("經銷商編號") or "").strip() for t in train
                 if (t.get("課程代號") or "").strip().upper() in ("B2", "CERT")
                 and (t.get("結果") or "").strip() == "通過"
                 and (t.get("日期") or "").startswith(yr)}
    not_cert = [x for x in alive if (x.get("編號") or "").strip() not in certified]

    return {
        "period": period, "members": alive, "perf": perf, "metrics": m,
        "revenue": revenue, "retail": retail, "selfbuy": selfbuy,
        "joinfee": joinfee, "stock": stock, "cohort": len(cohort),
        "biggest_line": biggest, "not_cert": not_cert, "thr": thr,
    }


def health_lines(h):
    m, thr = h["metrics"], h["thr"]
    out = []
    out.append(("零售佔比", m["零售佔比"], pct(m["零售佔比"]),
                light(m["零售佔比"], thr["零售佔比_綠燈"], thr["零售佔比_紅燈"]),
                "≥{} 綠 / <{} 紅".format(pct(thr["零售佔比_綠燈"]), pct(thr["零售佔比_紅燈"]))))
    out.append(("入會相關收入佔比", m["入會相關收入佔比"], pct(m["入會相關收入佔比"]),
                light(m["入會相關收入佔比"], thr["入會相關收入佔比_綠燈"],
                      thr["入會相關收入佔比_紅燈"], higher_is_better=False),
                "≤{} 綠 / >{} 紅".format(pct(thr["入會相關收入佔比_綠燈"]), pct(thr["入會相關收入佔比_紅燈"]))))
    out.append(("活動率", m["活動率"], pct(m["活動率"]),
                light(m["活動率"], thr["活動率_綠燈"], thr["活動率_紅燈"]),
                "≥{} 綠".format(pct(thr["活動率_綠燈"]))))
    if m["新人90天存活率"] is None:
        out.append(("新人90天存活率", None, "無樣本", "⚪", "需有 90～180 天前加入的人"))
    else:
        out.append(("新人90天存活率", m["新人90天存活率"], pct(m["新人90天存活率"]),
                    light(m["新人90天存活率"], thr["新人90天存活率_綠燈"], thr["新人90天存活率_紅燈"]),
                    "≥{} 綠".format(pct(thr["新人90天存活率_綠燈"]))))
    out.append(("單線集中度", m["單線集中度"], pct(m["單線集中度"]),
                light(m["單線集中度"], thr["單線集中度_綠燈"], thr["單線集中度_紅燈"], higher_is_better=False),
                "≤{} 綠（最大線：{}）".format(pct(thr["單線集中度_綠燈"]), h["biggest_line"])))
    out.append(("庫存週轉天數", m["庫存週轉天數"], "{:.0f} 天".format(m["庫存週轉天數"]),
                light(m["庫存週轉天數"], thr["庫存週轉天數_綠燈"], thr["庫存週轉天數_紅燈"], higher_is_better=False),
                "≤{:.0f} 天綠 / >{:.0f} 天紅（囤貨）".format(thr["庫存週轉天數_綠燈"], thr["庫存週轉天數_紅燈"])))
    return out


def cmd_health(args, cfg):
    d = data_dir(args)
    period = args.period or current_period()
    h = compute_health(d, cfg, period)

    title("小織 · 組織健檢　{}".format(period))
    if not h["perf"]:
        print("⚠️ 3_月結業績.csv 裡沒有 {} 的資料。".format(period))
        print("   請先補當月業績，或用 --period 指定其他月份（格式 2026-09）。")
        return

    print("營業額組成：零售 {:,.0f} ／ 自購 {:,.0f} ／ 入會相關 {:,.0f} ＝ 合計 {:,.0f}\n".format(
        h["retail"], h["selfbuy"], h["joinfee"], h["revenue"]))
    print("  {}{}  {}  {}".format(pad("指標", 22), pad("數值", 10, "right"), "燈", "門檻"))
    print("  " + "─" * 58)
    for name, _v, disp, lt, note in health_lines(h):
        print("  {}{}  {}  {}".format(pad(name, 22), pad(disp, 10, "right"), lt, note))

    m, thr = h["metrics"], h["thr"]
    print("\n" + "─" * 60)
    urgent = []
    if m["零售佔比"] < thr["零售佔比_紅燈"]:
        urgent.append("零售佔比僅 {} → 錢主要不是從『賣商品給最終消費者』來的。這已不是營運問題，是《多層次傳銷管理法》第 18 條的法律問題。".format(pct(m["零售佔比"])))
    if m["入會相關收入佔比"] > thr["入會相關收入佔比_紅燈"]:
        urgent.append("入會相關收入佔 {} → 收入結構指向拉人頭。立即檢討首購門檻與訓練收費。".format(pct(m["入會相關收入佔比"])))
    if m["庫存週轉天數"] > thr["庫存週轉天數_紅燈"]:
        urgent.append("庫存週轉 {:.0f} 天 → 經銷商在囤貨。依法他們可終止契約並要求 9 折買回，這是資產負債表上的定時炸彈。".format(m["庫存週轉天數"]))
    if urgent:
        print("🚨 紅燈事項（先處理這些，其他都可以等）：")
        for i, u in enumerate(urgent, 1):
            print("  {}. {}".format(i, u))
        print("\n→ 小織建議：暫停所有招募動作，並將制度交執業律師檢視。")
    else:
        print("✅ 沒有法律風險等級的紅燈。")

    advice = []
    if m["活動率"] < thr["活動率_綠燈"]:
        advice.append("活動率 {} 未達標 → **先救現有的人，不要招新人**（招新只會稀釋活動率）。".format(pct(m["活動率"])))
    if m["新人90天存活率"] is not None and m["新人90天存活率"] < thr["新人90天存活率_綠燈"]:
        advice.append("90 天存活率 {}（樣本 {} 人）→ 複製系統壞了，重跑 references/新人90天啟動SOP.md。".format(
            pct(m["新人90天存活率"]), h["cohort"]))
    if m["單線集中度"] > thr["單線集中度_綠燈"]:
        advice.append("最大線「{}」佔 {} → 開第二條線是今年最重要的事。".format(h["biggest_line"], pct(m["單線集中度"])))
    if advice:
        print("\n⚠️ 營運待辦：")
        for i, a in enumerate(advice, 1):
            print("  {}. {}".format(i, a))

    nc = h["not_cert"]
    print("\n【{} 年度合規認證】未通過 {} 人 / 共 {} 人".format(period[:4], len(nc), len(h["members"])))
    if nc:
        names = "、".join((x.get("稱呼") or x.get("編號") or "?") for x in nc[:15])
        print("  {}{}".format(names, " …" if len(nc) > 15 else ""))
        print("  → 依制度應暫停其組織獎金資格，直到通過為止。")

# ─────────────────────────────────────────── report

def cmd_report(args, cfg):
    d = data_dir(args)
    period = args.period or current_period()
    h = compute_health(d, cfg, period)
    b = read_brand(d)
    brand = b.get("品牌", {}).get("對外品牌名") or "天麗保養品"

    if not h["perf"]:
        die("3_月結業績.csv 裡沒有 {} 的資料，無法出月報。".format(period))

    lines = []
    lines.append("# {} 組織健檢月報　{}".format(brand, period))
    lines.append("")
    lines.append("> 產出：AI 員工「小織」／Sixhands Studio AI數字員工 🦞　產出日期：{}".format(date.today().isoformat()))
    lines.append("")
    lines.append("## 一、營業額組成")
    lines.append("")
    lines.append("| 項目 | 金額 | 佔比 |")
    lines.append("|:---|---:|---:|")
    for label, v in (("零售（賣給最終消費者）", h["retail"]),
                     ("自購", h["selfbuy"]),
                     ("入會相關收入", h["joinfee"])):
        share = v / h["revenue"] if h["revenue"] else 0
        lines.append("| {} | {:,.0f} | {} |".format(label, v, pct(share)))
    lines.append("| **合計** | **{:,.0f}** | 100.0% |".format(h["revenue"]))
    lines.append("")
    lines.append("## 二、六大指標")
    lines.append("")
    lines.append("| 指標 | 數值 | 燈號 | 門檻 |")
    lines.append("|:---|---:|:---:|:---|")
    for name, _v, disp, lt, note in health_lines(h):
        lines.append("| {} | {} | {} | {} |".format(name, disp, lt, note))
    lines.append("")
    lines.append("## 三、結論與待辦")
    lines.append("")
    m, thr = h["metrics"], h["thr"]
    todo = []
    if m["零售佔比"] < thr["零售佔比_紅燈"]:
        todo.append("🔴 **零售佔比 {} 未達 {}** —— 涉及《多層次傳銷管理法》第 18 條，暫停招募並交律師檢視制度。".format(
            pct(m["零售佔比"]), pct(thr["零售佔比_紅燈"])))
    if m["入會相關收入佔比"] > thr["入會相關收入佔比_紅燈"]:
        todo.append("🔴 **入會相關收入佔 {}** —— 檢討首購門檻與訓練收費。".format(pct(m["入會相關收入佔比"])))
    if m["庫存週轉天數"] > thr["庫存週轉天數_紅燈"]:
        todo.append("🔴 **庫存週轉 {:.0f} 天** —— 停止一切衝階話術，清理經銷商庫存。".format(m["庫存週轉天數"]))
    if m["活動率"] < thr["活動率_綠燈"]:
        todo.append("🟡 活動率 {} —— 本月不招新人，先做現有夥伴的復盤與陪談。".format(pct(m["活動率"])))
    if m["新人90天存活率"] is not None and m["新人90天存活率"] < thr["新人90天存活率_綠燈"]:
        todo.append("🟡 90 天存活率 {} —— 重跑新人啟動 SOP，檢查推薦人是否有做 D5 陪談。".format(pct(m["新人90天存活率"])))
    if m["單線集中度"] > thr["單線集中度_綠燈"]:
        todo.append("🟡 最大線「{}」佔 {} —— 本季目標：開出第二條獨立線。".format(h["biggest_line"], pct(m["單線集中度"])))
    if h["not_cert"]:
        todo.append("🟡 年度合規認證未通過 {} 人 —— 依制度暫停其組織獎金資格。".format(len(h["not_cert"])))
    if not todo:
        todo.append("🟢 六大指標全綠。本月維持節奏，重點放在領導人培養。")
    lines.extend("{}. {}".format(i, t) for i, t in enumerate(todo, 1))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("⚠️ 本報表為**內部管理用**，不是法律或稅務意見。")
    lines.append("制度、契約與報備事項之最終合法性，請交執業律師確認。")

    out = d / "月報_{}.md".format(period)
    out.write_text("\n".join(lines), encoding=JENC)
    title("小織 · 月報產出完成")
    print("📄 {}".format(out.resolve()))
    print("\n（可直接貼進簡報，或交小講做成月會投影片）")

# ─────────────────────────────────────────── scan

def cmd_scan(args, cfg):
    p = Path(args.file).expanduser()
    if not p.exists():
        die("找不到檔案：{}".format(p))
    text = p.read_text(encoding=JENC, errors="replace")
    lines = text.splitlines()
    kw = cfg["紅線關鍵字"]
    safe = sorted(cfg.get("安全例外語句", []), key=len, reverse=True)

    def strip_safe(line):
        """把合規免責句先扣掉再掃，避免『不具醫療效能』被判成『療效』"""
        for phrase in safe:
            line = line.replace(phrase, "　" * len(phrase))
        return line

    title("小織 · 文案合規稽核　{}".format(p.name))
    icons = {"收益保證與致富": "🔴", "拉人頭與囤貨": "🔴",
             "醫療效能與誇大": "🔴", "身分誤導": "🟡"}
    total = 0
    per_cat = Counter()
    for i, line in enumerate(lines, 1):
        scanline = strip_safe(line)
        for cat, words in kw.items():
            for w in words:
                if w in scanline:
                    total += 1
                    per_cat[cat] += 1
                    print("  {} L{:<4}[{}]　「{}」".format(icons.get(cat, "⚠️"), i, cat, w))
                    snippet = line.strip()
                    if len(snippet) > 60:
                        snippet = snippet[:60] + "…"
                    print("        {}".format(snippet))

    print("\n" + "─" * 60)
    if total == 0:
        print("✅ 沒有掃到紅線關鍵字。")
        print("\n但關鍵字掃描只擋得住『字』，擋不住『意思』。請人工再確認三件事：")
        print("  1. 有沒有暗示收入？（就算沒寫金額，『改變人生』也算）")
        print("  2. 有沒有暗示療效？（前後對比照本身就是一種宣稱）")
        print("  3. 有沒有揭露「無保證收入」與「報備不代表推薦或保證」？")
        return

    print("🚨 共 {} 處需要處理：".format(total))
    for cat, n in per_cat.most_common():
        print("   {} {}：{} 處".format(icons.get(cat, "⚠️"), cat, n))
    print("\n改寫對照表：")
    print("   ・收益／拉人頭 → references/多層次傳銷法規紅線與合規話術.md 第三節")
    print("   ・醫療效能　　 → references/保養品產品知識與化粧品法規.md 第三節")
    print("\n改完請再掃一次。文案本體要寫得漂亮 → 交小文；短影音腳本 → 交小爆。")
    print("**但最後一關永遠是這個指令。**")

# ─────────────────────────────────────────── main

def main():
    ap = argparse.ArgumentParser(
        description="小織 — 天麗保養品經銷組織架構管線工具（Sixhands Studio AI數字員工 🦞）")
    ap.add_argument("--config", help="自訂設定檔路徑（預設用 references/config.json）")
    sub = ap.add_subparsers(dest="cmd")

    def add(name, help_, need_dir=True, **extra):
        sp = sub.add_parser(name, help=help_)
        if need_dir:
            sp.add_argument("--dir", required=True, help="資料夾路徑")
        return sp

    add("init", "建立資料夾與範本檔")
    add("verdict", "制度屬性判定（第 0 號文件）")
    add("comp", "獎金結構健檢")
    sp = add("blueprint", "組織藍圖（現況／12 個月／36 個月）")
    sp.add_argument("--target", type=int, help="12 個月目標人數")
    add("pipeline", "招募漏斗與今日待聯繫")
    sp = add("health", "月度組織健檢六大指標")
    sp.add_argument("--period", help="月份，格式 2026-09（預設本月）")
    sp = add("report", "產出月報 Markdown")
    sp.add_argument("--period", help="月份，格式 2026-09（預設本月）")
    sp = sub.add_parser("scan", help="文案合規稽核")
    sp.add_argument("--file", required=True, help="要掃描的文字檔（.txt / .md）")

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return

    cfg = load_config(getattr(args, "config", None))
    fn = {
        "init": cmd_init, "verdict": cmd_verdict, "comp": cmd_comp,
        "blueprint": cmd_blueprint, "pipeline": cmd_pipeline,
        "health": cmd_health, "report": cmd_report, "scan": cmd_scan,
    }[args.cmd]
    if getattr(args, "period", None):
        if not re.match(r"^\d{4}-\d{2}$", args.period):
            die("--period 格式應為 2026-09")
    fn(args, cfg)


if __name__ == "__main__":
    main()
