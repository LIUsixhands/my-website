#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小泌 medmkt.py — 泌尿科診所行銷內容管理與合規稽核工具
Sixhands Studio AI數字員工

純標準庫、零安裝。CSV 一律 utf-8-sig，Excel／Numbers 開啟不亂碼。

  init    建立內容資產表、行事曆、關鍵字矩陣、評論回覆紀錄
  scan    🔴 合規稽核：掃描文案，抓出醫療法／藥事法高風險用語
  plan    依關鍵字矩陣產出內容行事曆
  kw      列出泌尿科關鍵字矩陣（依難度／急迫度排序）
  report  內容成效月報

用法：
  python3 medmkt.py init   --dir "./行銷資料"
  python3 medmkt.py scan   貼文.md
  python3 medmkt.py scan   --text "本院保證根治攝護腺肥大"
  python3 medmkt.py scan   --dir "./草稿" --out 稽核報告.md
  python3 medmkt.py plan   --dir "./行銷資料" --weeks 12 --start 2026-09-01
  python3 medmkt.py kw     --dir "./行銷資料"
  python3 medmkt.py report --dir "./行銷資料" --month 2026-09
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "..", "references", "config.json")

ENC = "utf-8-sig"


# ────────────────────────────────────────────────────────────
# 基礎工具
# ────────────────────────────────────────────────────────────

def load_config(path=None):
    p = path or CONFIG_PATH
    if not os.path.exists(p):
        sys.exit(f"✗ 找不到設定檔：{p}\n  請確認 references/config.json 還在。")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_csv(path, header, rows=None):
    if os.path.exists(path):
        print(f"  · 已存在，跳過：{os.path.basename(path)}")
        return False
    with open(path, "w", encoding=ENC, newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in (rows or []):
            w.writerow(r)
    print(f"  ✓ 建立：{os.path.basename(path)}")
    return True


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f))


def today():
    return dt.date.today()


# ────────────────────────────────────────────────────────────
# 泌尿科關鍵字矩陣（內建，可在 3_關鍵字矩陣.csv 增修）
# 難言之隱度：病人越不敢問人 → 越依賴搜尋 → 內容價值越高
# ────────────────────────────────────────────────────────────

KEYWORD_BANK = [
    # 主題,        族群,        難言之隱度(1-5), 就醫急迫度(1-5), 內容型態
    ("攝護腺肥大 症狀",      "50歲以上男性", 3, 3, "長文"),
    ("夜尿 頻尿 原因",       "50歲以上男性", 2, 3, "長文"),
    ("尿不乾淨 尿柱變細",     "50歲以上男性", 3, 3, "短文"),
    ("PSA 指數 過高",        "50歲以上男性", 3, 4, "長文"),
    ("攝護腺癌 早期症狀",     "50歲以上男性", 3, 5, "長文"),
    ("血尿 是不是癌症",       "全年齡",      2, 5, "長文"),
    ("腎結石 痛 怎麼辦",      "30-60歲",     1, 5, "長文"),
    ("尿路結石 預防 喝水",    "30-60歲",     1, 2, "短文"),
    ("泌尿道感染 反覆發作",      "女性",        3, 4, "長文"),
    ("反覆膀胱炎 怎麼辦",     "女性",        4, 3, "長文"),
    ("尿失禁 漏尿 產後",      "女性",        5, 3, "長文"),
    ("勃起功能障礙 原因",     "30-70歲男性",  5, 3, "長文"),
    ("早發性射精 治療",       "20-50歲男性",  5, 2, "長文"),
    ("性功能障礙 要看哪一科",  "男性",        5, 2, "短文"),
    ("包皮 過長 需要開刀嗎",   "全年齡男性",   4, 2, "長文"),
    ("包皮龜頭炎 反覆",       "全年齡男性",   4, 3, "短文"),
    ("睪丸 腫痛 硬塊",        "15-40歲男性",  4, 5, "長文"),
    ("精索靜脈曲張 不孕",     "20-40歲男性",  4, 3, "長文"),
    ("男性不孕 精液檢查",     "20-40歲男性",  5, 3, "長文"),
    ("性病 檢查 匿名",        "全年齡",      5, 4, "長文"),
    ("菜花 尖銳濕疣 治療",     "全年齡",      5, 4, "長文"),
    ("小便痛 灼熱感",         "全年齡",      3, 4, "短文"),
    ("兒童 尿床 幾歲要看醫生", "兒童家長",     2, 2, "長文"),
    ("結紮 手術 恢復",        "30-50歲男性",  4, 1, "長文"),
    ("泌尿科 第一次看診 流程", "全年齡",      4, 1, "短影音"),
    ("看泌尿科 會不會很尷尬",  "全年齡",      5, 1, "短影音"),
    ("男生 幾歲 要做健檢",     "40歲以上男性", 2, 2, "短影音"),
    ("腎功能 指數 看不懂",     "全年齡",      1, 3, "長文"),
]


def kw_priority(shy, urgency):
    """優先序分數：難言之隱度權重高（搜尋依賴度高、競爭者少、且最需要衛教）"""
    return shy * 2 + urgency


# ────────────────────────────────────────────────────────────
# init
# ────────────────────────────────────────────────────────────

def cmd_init(args):
    d = args.dir
    os.makedirs(d, exist_ok=True)
    print(f"🩺 小泌｜建立行銷資料表 → {d}\n")

    write_csv(os.path.join(d, "1_內容資產表.csv"), [
        "內容編號", "標題", "內容型態", "主題關鍵字", "目標族群",
        "平台", "網址", "發布日期", "合規稽核日", "稽核結果",
        "字數", "狀態", "備註",
    ])

    write_csv(os.path.join(d, "2_內容行事曆.csv"), [
        "排程日期", "星期", "內容型態", "主題關鍵字", "目標族群",
        "優先序", "負責人", "狀態", "內容編號", "備註",
    ])

    rows = []
    for i, (topic, seg, shy, urg, kind) in enumerate(KEYWORD_BANK, 1):
        rows.append([f"KW{i:03d}", topic, seg, shy, urg,
                     kw_priority(shy, urg), kind, "", "未產出"])
    write_csv(os.path.join(d, "3_關鍵字矩陣.csv"), [
        "關鍵字編號", "主題關鍵字", "目標族群", "難言之隱度", "就醫急迫度",
        "優先序分數", "建議內容型態", "已產出內容編號", "狀態",
    ], rows)

    write_csv(os.path.join(d, "4_評論回覆紀錄.csv"), [
        "日期", "平台", "評論摘要", "星等", "類型",
        "回覆日期", "回覆人", "是否已回", "備註",
    ])

    write_csv(os.path.join(d, "5_成效追蹤.csv"), [
        "月份", "內容編號", "曝光", "點擊", "停留秒數",
        "官網掛號點擊", "來電", "備註",
    ])

    print(f"\n完成。五張表都在 {d}／，全部 utf-8-sig，Excel 直接開不亂碼。")
    print("下一步：先把 references/config.json 的「診所資料」填完，再跑 plan。")


# ────────────────────────────────────────────────────────────
# scan — 合規稽核（核心功能）
# ────────────────────────────────────────────────────────────

LEVEL_META = {
    "紅": ("🔴", "必須修改（發布即高風險）"),
    "橙": ("🟠", "建議修改（易被認定誇大不實）"),
    "黃": ("🟡", "請人工確認上下文"),
}

# 診間／衛教用途的排除語境：出現這些字時，「術前術後」等詞不一定違規
CONTEXT_EXEMPT = ["診間", "衛教說明", "醫療機構內", "本文為衛教"]


def _iter_terms(cfg):
    """回傳 [(level, category, term), ...]"""
    out = []
    for cat, terms in cfg["違規詞庫"].items():
        level = cat[0]  # 紅 / 橙 / 黃
        for t in terms:
            out.append((level, cat, t))
    # 長詞優先比對，避免「最新」被「最」吃掉（雖已移除裸「最」，仍保險）
    out.sort(key=lambda x: -len(x[2]))
    return out


def scan_text(text, cfg, source="(貼上的文字)"):
    terms = _iter_terms(cfg)
    advice = cfg.get("改寫建議", {})
    lines = text.splitlines()

    hits = {"紅": [], "橙": [], "黃": []}
    seen = set()  # (line_no, start, end) 去重，避免重疊詞重複計

    for ln, line in enumerate(lines, 1):
        occupied = []
        for level, cat, term in terms:
            start = 0
            low_line = line
            low_term = term
            # 英文藥名不分大小寫
            if re.fullmatch(r"[A-Za-z ]+", term):
                low_line = line.lower()
                low_term = term.lower()
            while True:
                i = low_line.find(low_term, start)
                if i < 0:
                    break
                j = i + len(term)
                if any(not (j <= a or i >= b) for a, b in occupied):
                    start = i + 1
                    continue
                occupied.append((i, j))
                key = (ln, i, j)
                if key not in seen:
                    seen.add(key)
                    snippet = line.strip()
                    if len(snippet) > 46:
                        s = max(0, i - 16)
                        snippet = ("…" if s > 0 else "") + line[s:i + 30].strip() + "…"
                    hits[level].append({
                        "line": ln, "pos": i, "term": term, "cat": cat,
                        "snippet": snippet,
                        "advice": advice.get(term, ""),
                    })
                start = i + 1

    # 必備要素檢查
    req = cfg["必備要素檢查"]
    def has_any(keys):
        return any(k in text for k in keys)

    elements = {
        "衛教聲明": has_any(req["衛教聲明關鍵字"]),
        "就醫建議": has_any(req["就醫建議關鍵字"]),
        "風險揭露": has_any(req["風險揭露關鍵字"]),
    }
    mentions_procedure = any(k in text for k in
                             ["手術", "開刀", "治療", "療程", "注射", "雷射", "電燒", "碎石"])

    # 同一行同一個詞只報一次（附出現次數），並依行號→出現位置排序
    for level in hits:
        merged = {}
        for h in hits[level]:
            k = (h["line"], h["term"])
            if k in merged:
                merged[k]["count"] += 1
            else:
                h["count"] = 1
                merged[k] = h
        hits[level] = sorted(merged.values(), key=lambda h: (h["line"], h["pos"]))

    return {
        "source": source, "chars": len(re.sub(r"\s", "", text)),
        "hits": hits, "elements": elements,
        "mentions_procedure": mentions_procedure,
    }


def render_report(res, cfg):
    L = []
    a = L.append
    a(f"### {res['source']}")
    a(f"字數 {res['chars']}（不含空白）")
    a("")

    total_red = len(res["hits"]["紅"])
    total_orange = len(res["hits"]["橙"])
    total_yellow = len(res["hits"]["黃"])

    for level in ("紅", "橙", "黃"):
        hs = res["hits"][level]
        icon, label = LEVEL_META[level]
        if not hs:
            continue
        a(f"**{icon} {label}｜{len(hs)} 處**")
        a("")
        for h in hs:
            cat = h["cat"].split("_", 1)[-1]
            times = f" ×{h['count']}" if h.get("count", 1) > 1 else ""
            a(f"- `L{h['line']}` **{h['term']}**{times}（{cat}）")
            a(f"  - 原文：{h['snippet']}")
            if h["advice"]:
                a(f"  - 建議：{h['advice']}")
        a("")

    a("**必備要素**")
    a("")
    e = res["elements"]
    a(f"- {'✅' if e['衛教聲明'] else '❌'} 衛教聲明（「本文為衛教資訊，不能取代醫師診察」）")
    a(f"- {'✅' if e['就醫建議'] else '❌'} 就醫建議（引導至門診評估）")
    if res["mentions_procedure"]:
        a(f"- {'✅' if e['風險揭露'] else '❌'} 風險揭露 ← **本文提到手術或治療，必須揭露適應症／禁忌症／副作用**")
    else:
        a(f"- {'—' if not e['風險揭露'] else '✅'} 風險揭露（本文未提及手術或治療，非必要）")
    a("")

    missing_required = (not e["衛教聲明"]) or (not e["就醫建議"]) or \
                       (res["mentions_procedure"] and not e["風險揭露"])

    if total_red or missing_required:
        verdict = "🔴 不可發布 — 先修完紅色項目與必備要素"
    elif total_orange:
        verdict = "🟠 修改後可發布 — 橙色項目請逐條處理"
    elif total_yellow:
        verdict = "🟡 人工確認後可發布"
    else:
        verdict = "✅ 通過 — 未偵測到高風險用語，必備要素齊全"

    a(f"**判定：{verdict}**")
    a("")
    a("> ⚠️ 本工具是**字詞層級的初篩**，不是法律意見。")
    a("> 它抓得到「保證」，抓不到「整篇文章的目的是不是招徠患者」。")
    a("> 對外發布前，仍請由醫師本人與（必要時）法律顧問確認。")
    return "\n".join(L), verdict


def cmd_scan(args):
    cfg = load_config(args.config)
    targets = []

    if args.text:
        targets.append(("(--text 傳入)", args.text))
    if args.dir:
        for root, _, files in os.walk(args.dir):
            for fn in sorted(files):
                if fn.lower().endswith((".md", ".txt")):
                    p = os.path.join(root, fn)
                    with open(p, encoding="utf-8", errors="replace") as f:
                        targets.append((os.path.relpath(p, args.dir), f.read()))
    for p in args.files:
        if not os.path.exists(p):
            print(f"✗ 找不到檔案：{p}")
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            targets.append((os.path.basename(p), f.read()))

    if not targets:
        # 從 stdin 讀
        if not sys.stdin.isatty():
            targets.append(("(stdin)", sys.stdin.read()))
        else:
            sys.exit("✗ 沒有東西可以掃。請給檔名，或用 --text \"...\"，或 --dir 資料夾。")

    out = ["# 🩺 小泌｜醫療行銷合規稽核報告", "",
           f"稽核日期：{today().isoformat()}　｜　依據：醫療法 §84-§87、§103；藥事法 §65/§67",
           ""]
    verdicts = []
    for name, text in targets:
        body, verdict = render_report(scan_text(text, cfg, name), cfg)
        out.append(body)
        out.append("---")
        out.append("")
        verdicts.append((name, verdict))

    out.append("## 總表")
    out.append("")
    out.append("| 檔案 | 判定 |")
    out.append("|:---|:---|")
    for n, v in verdicts:
        out.append(f"| {n} | {v} |")
    out.append("")
    out.append("🦞 Sixhands Studio AI數字員工")

    report = "\n".join(out)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"✓ 稽核報告已寫入：{args.out}")
        for n, v in verdicts:
            print(f"  {v.split(' ')[0]} {n}")
    else:
        print(report)


# ────────────────────────────────────────────────────────────
# plan
# ────────────────────────────────────────────────────────────

WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}


def cmd_plan(args):
    cfg = load_config(args.config)
    d = args.dir
    kw_path = os.path.join(d, "3_關鍵字矩陣.csv")
    rows = read_csv(kw_path)
    if not rows:
        sys.exit(f"✗ 讀不到 {kw_path}，請先跑 init。")

    pending = [r for r in rows if r.get("狀態", "") != "已產出"]
    pending.sort(key=lambda r: -int(r.get("優先序分數") or 0))

    start = args.start
    if start:
        d0 = dt.date.fromisoformat(start)
    else:
        s = cfg["排程"].get("內容行事曆起始日", "")
        d0 = dt.date.fromisoformat(s) if re.match(r"\d{4}-\d{2}-\d{2}", s) else today()

    weekdays = [WEEKDAY_MAP[w] for w in cfg["排程"]["每週固定發文星期"] if w in WEEKDAY_MAP]
    if not weekdays:
        weekdays = [1, 4]

    slots = []
    cur = d0
    weeks = args.weeks
    end = d0 + dt.timedelta(weeks=weeks)
    while cur < end:
        if cur.weekday() in weekdays:
            slots.append(cur)
        cur += dt.timedelta(days=1)

    out_rows = []
    wd_name = "一二三四五六日"
    for i, day in enumerate(slots):
        if i >= len(pending):
            break
        r = pending[i]
        out_rows.append([
            day.isoformat(), wd_name[day.weekday()],
            r.get("建議內容型態", ""), r.get("主題關鍵字", ""),
            r.get("目標族群", ""), r.get("優先序分數", ""),
            "", "待撰稿", "", f"來源 {r.get('關鍵字編號','')}",
        ])

    path = os.path.join(d, "2_內容行事曆.csv")
    with open(path, "w", encoding=ENC, newline="") as f:
        w = csv.writer(f)
        w.writerow(["排程日期", "星期", "內容型態", "主題關鍵字", "目標族群",
                    "優先序", "負責人", "狀態", "內容編號", "備註"])
        w.writerows(out_rows)

    print(f"🩺 小泌｜已排 {len(out_rows)} 篇，{d0} 起共 {weeks} 週")
    print(f"   固定發文日：星期{'、'.join(cfg['排程']['每週固定發文星期'])}")
    print(f"   寫入：{path}\n")
    for r in out_rows[:10]:
        print(f"   {r[0]}（{r[1]}）{r[2]:<4} {r[3]}")
    if len(out_rows) > 10:
        print(f"   …其餘 {len(out_rows)-10} 篇見 CSV")


# ────────────────────────────────────────────────────────────
# kw
# ────────────────────────────────────────────────────────────

def cmd_kw(args):
    rows = read_csv(os.path.join(args.dir, "3_關鍵字矩陣.csv")) if args.dir else []
    if not rows:
        rows = [{"關鍵字編號": f"KW{i:03d}", "主題關鍵字": t, "目標族群": s,
                 "難言之隱度": str(a), "就醫急迫度": str(b),
                 "優先序分數": str(kw_priority(a, b)), "建議內容型態": k, "狀態": "未產出"}
                for i, (t, s, a, b, k) in enumerate(KEYWORD_BANK, 1)]
    rows.sort(key=lambda r: -int(r.get("優先序分數") or 0))

    print("🩺 小泌｜泌尿科內容關鍵字矩陣（優先序高→低）")
    print("   優先序 = 難言之隱度×2 + 就醫急迫度")
    print("   邏輯：病人越不敢問人，越只能靠搜尋，衛教內容的價值就越高\n")
    print(f"   {'編號':<7}{'分':<4}{'隱':<3}{'急':<3}{'型態':<6}{'主題關鍵字':<24}族群")
    print("   " + "─" * 78)
    for r in rows:
        print(f"   {r['關鍵字編號']:<7}{r['優先序分數']:<4}{r['難言之隱度']:<3}"
              f"{r['就醫急迫度']:<3}{r['建議內容型態']:<6}{r['主題關鍵字']:<24}{r['目標族群']}")
    print(f"\n   共 {len(rows)} 題。狀態為「已產出」的會自動從 plan 排程中排除。")


# ────────────────────────────────────────────────────────────
# report
# ────────────────────────────────────────────────────────────

def cmd_report(args):
    d = args.dir
    month = args.month or today().strftime("%Y-%m")
    assets = read_csv(os.path.join(d, "1_內容資產表.csv"))
    cal = read_csv(os.path.join(d, "2_內容行事曆.csv"))
    kws = read_csv(os.path.join(d, "3_關鍵字矩陣.csv"))
    reviews = read_csv(os.path.join(d, "4_評論回覆紀錄.csv"))
    perf = read_csv(os.path.join(d, "5_成效追蹤.csv"))

    pub = [a for a in assets if (a.get("發布日期") or "").startswith(month)]
    planned = [c for c in cal if (c.get("排程日期") or "").startswith(month)]
    done_plan = [c for c in planned if c.get("狀態") == "已發布"]
    unscanned = [a for a in pub if not (a.get("合規稽核日") or "").strip()]
    failed = [a for a in pub if "🔴" in (a.get("稽核結果") or "")]
    unreplied = [r for r in reviews if (r.get("是否已回") or "").strip() not in ("是", "Y", "y", "✓")]
    covered = len([k for k in kws if k.get("狀態") == "已產出"])

    mp = [p for p in perf if (p.get("月份") or "").startswith(month)]
    def total(col):
        s = 0
        for p in mp:
            try:
                s += int(float(p.get(col) or 0))
            except ValueError:
                pass
        return s

    L = [f"# 🩺 小泌｜{month} 月度行銷報告", "",
         f"產出日期：{today().isoformat()}", "", "## 一、這個月做了什麼", "",
         f"- 排程 {len(planned)} 篇，實際發布 **{len(done_plan)}** 篇"
         f"（達成率 {round(len(done_plan)/len(planned)*100) if planned else 0}%）",
         f"- 內容資產累計 {len(assets)} 篇，關鍵字矩陣覆蓋 {covered}/{len(kws)} 題",
         f"- 曝光 {total('曝光'):,}　點擊 {total('點擊'):,}　官網掛號點擊 {total('官網掛號點擊'):,}　來電 {total('來電'):,}",
         "", "## 二、要處理的事", ""]

    if failed:
        L.append(f"- 🔴 **{len(failed)} 篇已發布內容稽核未通過**，請立即下架或修改：")
        for a in failed:
            L.append(f"  - {a.get('內容編號','')} {a.get('標題','')}（{a.get('平台','')}）")
    if unscanned:
        L.append(f"- 🟠 **{len(unscanned)} 篇已發布但沒有合規稽核紀錄**，請補跑 `scan`：")
        for a in unscanned[:8]:
            L.append(f"  - {a.get('內容編號','')} {a.get('標題','')}")
    if unreplied:
        L.append(f"- 🟠 **{len(unreplied)} 則評論未回覆**（目標時效 48 小時內）")
    if len(planned) - len(done_plan) > 0:
        L.append(f"- 🟡 {len(planned)-len(done_plan)} 篇排程未完成，順延或砍掉請直接改 CSV")
    if not (failed or unscanned or unreplied or len(planned) - len(done_plan)):
        L.append("- ✅ 沒有待辦。這個月很乾淨。")

    L += ["", "## 三、下個月建議", "",
          "1. 先補完關鍵字矩陣中優先序最高、尚未產出的題目（跑 `medmkt.py kw` 看排序）",
          "2. 每一篇發布前都跑過 `scan`，稽核結果回填到 `1_內容資產表.csv`",
          "3. 評論回覆一律不確認就醫事實、不談病情細節（見 `平台操作SOP.md`）",
          "", "---", "🦞 Sixhands Studio AI數字員工"]

    text = "\n".join(L)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"✓ 已寫入 {args.out}")
    else:
        print(text)


# ────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="小泌 — 泌尿科診所行銷內容管理與合規稽核工具（Sixhands Studio AI數字員工）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="建立五張表")
    p.add_argument("--dir", default="./行銷資料")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("scan", help="合規稽核（核心）")
    p.add_argument("files", nargs="*", help="要掃的 .md/.txt 檔")
    p.add_argument("--text", help="直接傳入一段文字")
    p.add_argument("--dir", help="掃整個資料夾內的 .md/.txt")
    p.add_argument("--out", help="輸出 Markdown 報告路徑")
    p.add_argument("--config", help="自訂 config.json 路徑")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("plan", help="產出內容行事曆")
    p.add_argument("--dir", default="./行銷資料")
    p.add_argument("--weeks", type=int, default=12)
    p.add_argument("--start", help="起始日 YYYY-MM-DD")
    p.add_argument("--config")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("kw", help="列出關鍵字矩陣")
    p.add_argument("--dir")
    p.set_defaults(func=cmd_kw)

    p = sub.add_parser("report", help="月度報告")
    p.add_argument("--dir", default="./行銷資料")
    p.add_argument("--month", help="YYYY-MM")
    p.add_argument("--out")
    p.set_defaults(func=cmd_report)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
