#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小書 · 郵件日報產線 (mailbrief.py)
Sixhands Studio AI數字員工

  template --out mails.json        產一份郵件 JSON 欄位範本
  brief    --in mails.json [--out 郵件日報.md]
           讀 JSON → 風險掃描 → 個資遮罩 → 分級排序 → 產日報 Markdown

流程：用 Gmail MCP 抓信 → 逐封填成 JSON → 跑 brief。
🚨 這支腳本不會、也不該碰任何寄信動作。寄出永遠是教練按的。
"""
import argparse, json, os, re, sys, datetime

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, "references", "config.json")
FREE_DOMAINS = {"gmail.com", "yahoo.com.tw", "yahoo.com", "hotmail.com", "outlook.com",
                "qq.com", "163.com", "protonmail.com", "gmx.com", "mail.com"}
LEVELS = {"紅": "🔴 今天要回", "橙": "🟠 本週要回", "綠": "🟢 存查", "風險": "🚨 風險"}
ORDER = ["風險", "紅", "橙", "綠"]

TEMPLATE = {
    "日期": datetime.date.today().isoformat(),
    "查詢條件": "newer_than:1d -in:spam -category:promotions",
    "郵件": [{
        "thread_id": "從 Gmail MCP 取得，方便回頭開信",
        "寄件人": "王大明（中租迪和）",
        "寄件信箱": "wang@example.com.tw",
        "reply_to": "",
        "收件時間": "2026-08-30 09:12",
        "主旨": "關於 8/31 簽約日期確認",
        "一句話重點": "對方要在 8/31 前確認簽約日，否則檔期釋出。",
        "關鍵細節": ["金額 NT$120,000", "附件：合約草稿_v2.pdf", "窗口分機 #218"],
        "要做什麼": "回覆確定的簽約日期，並確認是否需要用印。",
        "回覆給誰": {"to": ["wang@example.com.tw"], "cc": ["acc@example.com.tw"]},
        "期限": "2026-08-31",
        "分級": "紅",
        "草稿要點": ["確認 9/2 下午 2 點", "需要對方帶大小章", "報價金額待教練確認"],
        "草稿已建立": False,
        "我方最後回覆日": "",
        "對方等待中": True,
        "內文摘錄": "貼一段原文，供風險掃描用（不用全文）"
    }]
}


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def mask(text):
    if not text:
        return text
    text = re.sub(r"\b([A-Za-z])(\d{5})(\d{4})\b", lambda m: f"{m.group(1)}*****{m.group(3)}", text)
    text = re.sub(r"\b(09)(\d{4})(\d{3})\b", r"\1****\3", text)
    text = re.sub(r"\b(\d{2,4})(\d{4,8})(\d{4})\b", lambda m: f"{m.group(1)}{'*'*len(m.group(2))}{m.group(3)}", text)
    return text


def scan_risk(mail, cfg):
    """回傳 [(類別, 命中詞)]。掃主旨＋內文摘錄＋要做什麼。"""
    blob = " ".join(str(mail.get(k, "")) for k in ("主旨", "內文摘錄", "要做什麼"))
    blob_l = blob.lower()
    hits = []
    for cat, words in cfg["風險關鍵字"].items():
        for w in words:
            if w.lower() in blob_l:
                hits.append((cat, w))
                break
    frm = (mail.get("寄件信箱") or "").lower()
    rto = (mail.get("reply_to") or "").lower()
    if rto and "@" in frm and "@" in rto and frm.split("@")[-1] != rto.split("@")[-1]:
        hits.append(("回覆位址不符", f"From {frm.split('@')[-1]} / Reply-To {rto.split('@')[-1]}"))
    name = mail.get("寄件人", "")
    if "@" in frm and frm.split("@")[-1] in FREE_DOMAINS and re.search(r"(公司|股份|有限|銀行|部|處|科技|Inc|Ltd|Corp)", name):
        hits.append(("公司名配免費信箱", frm.split("@")[-1]))
    return hits


def days_since(d):
    if not d:
        return None
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(d[:10])).days
    except Exception:
        return None


def due_flag(deadline):
    n = days_since(deadline)
    if n is None:
        return ""
    if n > 0:
        return f"⛔ 已逾期 {n} 天"
    if n == 0:
        return "⏰ 今天到期"
    if n >= -2:
        return f"⏰ 剩 {-n} 天"
    return ""


def cmd_template(a):
    out = a.out or "mails.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(TEMPLATE, f, ensure_ascii=False, indent=2)
    print(f"✓ 範本 → {out}")
    print("  用 Gmail MCP 抓信後，逐封填進『郵件』陣列，再跑：")
    print(f"  python3 {os.path.abspath(__file__)} brief --in {out}")


def cmd_brief(a):
    cfg = load_config()
    with open(a.infile, encoding="utf-8") as f:
        data = json.load(f)
    mails = data.get("郵件", [])
    if not mails:
        sys.exit("✗ JSON 裡沒有郵件")
    date = data.get("日期", datetime.date.today().isoformat())
    track_days = cfg["郵件"]["未回覆追蹤天數"]
    vips = [v.lower() for v in cfg["郵件"].get("VIP寄件人", [])]

    for m in mails:
        m["_risk"] = scan_risk(m, cfg)
        lvl = m.get("分級") or ""
        lvl = {"紅": "紅", "橙": "橙", "黃": "橙", "綠": "綠", "風險": "風險"}.get(lvl, "")
        if m["_risk"]:
            lvl = "風險"
        if not lvl:
            if due_flag(m.get("期限")):
                lvl = "紅"
            elif (m.get("寄件信箱", "").lower() in vips) or m.get("對方等待中"):
                lvl = "紅"
            elif m.get("要做什麼") and "存查" not in str(m.get("要做什麼")):
                lvl = "橙"
            else:
                lvl = "綠"
        m["_lvl"] = lvl
        m["_wait"] = days_since(m.get("收件時間"))

    mails.sort(key=lambda m: (ORDER.index(m["_lvl"]), m.get("期限") or "9999"))
    counts = {k: sum(1 for m in mails if m["_lvl"] == k) for k in ORDER}
    stale = [m for m in mails if m["_lvl"] in ("紅", "橙") and (m["_wait"] or 0) >= track_days]

    L = []
    L.append(f"# 📬 郵件日報 {date}")
    L.append("")
    L.append(f"> 共 {len(mails)} 封　|　🔴 今天要回 {counts['紅']}　🟠 本週 {counts['橙']}　🟢 存查 {counts['綠']}　🚨 風險 {counts['風險']}")
    L.append("> ")
    L.append("> 🚨 本報告由小書整理。**沒有任何一封信被寄出**，草稿一律待教練確認。")
    L.append("")
    top = next((m for m in mails if m["_lvl"] == "紅"), None)
    L.append("## 三句話結論")
    L.append("")
    L.append(f"1. 今天 {len(mails)} 封，{counts['紅']} 封今天要回，{counts['風險']} 封有風險。")
    L.append(f"2. 最急：{(top['寄件人'] + ' — ' + top['一句話重點']) if top else '沒有急件。'}")
    rk = next((m for m in mails if m["_lvl"] == "風險"), None)
    L.append(f"3. 風險：{('「' + rk['主旨'] + '」' + rk['_risk'][0][0] + ' → 別回、別點連結，另循管道查證。') if rk else '無。'}")
    L.append("")

    for lvl in ORDER:
        group = [m for m in mails if m["_lvl"] == lvl]
        if not group:
            continue
        L.append(f"## {LEVELS[lvl]}（{len(group)}）")
        L.append("")
        for i, m in enumerate(group, 1):
            frm = f"{m.get('寄件人','?')} <{m.get('寄件信箱','')}>"
            L.append(f"### {i}. {m.get('主旨','(無主旨)')}")
            L.append("")
            L.append(f"- **誰寄的**：{frm}　（收件 {m.get('收件時間','')}）")
            L.append(f"- **重點**：{mask(m.get('一句話重點',''))}")
            det = m.get("關鍵細節") or []
            if det:
                L.append("- **關鍵細節**：")
                for dd in det[:3]:
                    L.append(f"  - {mask(str(dd))}")
            if lvl == "風險":
                L.append("- **要我做什麼**：🚨 不回、不點連結、不提供任何資料。")
                L.append("- **哪裡不對勁**：")
                for cat, w in m["_risk"]:
                    L.append(f"  - {cat}：命中「{w}」")
                L.append("- **建議查證**：用電話或既有窗口找本人確認，不要在這條信件串裡問。")
            else:
                L.append(f"- **要我做什麼**：{mask(m.get('要做什麼','（未填）'))}")
                to = "、".join((m.get("回覆給誰") or {}).get("to", [])) or "（未填）"
                cc = "、".join((m.get("回覆給誰") or {}).get("cc", []))
                L.append(f"- **回覆給誰**：To：{to}" + (f"　Cc：{cc}" if cc else ""))
                dl = m.get("期限") or "（信中未寫）"
                L.append(f"- **期限**：{dl}　{due_flag(m.get('期限'))}")
                pts = m.get("草稿要點") or []
                if pts:
                    L.append("- **回覆要點**：")
                    for pp in pts:
                        L.append(f"  - {mask(str(pp))}")
                L.append(f"- **草稿**：{'✅ 已建立於 Gmail 草稿匣（未寄出）' if m.get('草稿已建立') else '尚未建立'}")
            L.append("")

    L.append(f"## ⏳ 超過 {track_days} 天沒回（{len(stale)}）")
    L.append("")
    if stale:
        L.append("| 對方 | 主旨 | 已過幾天 | 建議 |")
        L.append("|:---|:---|:---|:---|")
        for m in stale:
            L.append(f"| {m.get('寄件人','')} | {m.get('主旨','')[:28]} | {m['_wait']} 天 | 今天回或發一句話說明何時給答覆 |")
    else:
        L.append("無。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("整理：小書（Xiao Shu）｜**Sixhands Studio AI數字員工**")

    text = "\n".join(L)
    out = a.out
    if out:
        with open(os.path.expanduser(out), "w", encoding="utf-8") as f:
            f.write(text)
        print(f"✓ 日報 → {out}")
    else:
        print(text)

    print(f"\n📬 {date}：{len(mails)} 封｜🔴{counts['紅']} 🟠{counts['橙']} 🟢{counts['綠']} 🚨{counts['風險']}｜逾 {track_days} 天未回 {len(stale)}")
    if counts["風險"]:
        print("🚨 有風險信件，先看日報的『風險』段再動作。")


def main():
    p = argparse.ArgumentParser(description="小書 · 郵件日報產線")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("template"); s.add_argument("--out"); s.set_defaults(fn=cmd_template)
    s = sub.add_parser("brief"); s.add_argument("--in", dest="infile", required=True)
    s.add_argument("--out"); s.set_defaults(fn=cmd_brief)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
