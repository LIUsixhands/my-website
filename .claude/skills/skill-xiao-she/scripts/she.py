#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小社（Xiao She）— 社區發展協會行政與文書專員　主程式
Sixhands Studio AI數字員工

子指令：
  init      產「協會基本資料卡」與 協會資料.json 範本
  calendar  年度行事曆／未來 N 天待辦
  event     活動包（簽到表 + 活動紀錄卡 + 社會局系統貼上包）
  expense   憑證清冊 + 四種退件風險標示 + 經費結報表
  report    季度成果報告草稿
  meeting   會議包（開會通知/議程/簽到簿/會議紀錄/備查函）
  journal   年度會刊（六大單元）

鐵律：所有金額以原始憑證為準；所有期限以章程與主管機關函文為準；
      小社只產草稿，不代簽、不代送、不改金額。
"""
import argparse, base64, csv, datetime as dt, json, os, subprocess, sys, tempfile, textwrap

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.join(SKILL_DIR, "assets", "logo.png")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BRAND = "Sixhands Studio AI數字員工"
DISCLAIMER = ("本文件由「Sixhands Studio AI數字員工」AI 員工小社協助整理草擬，僅供協會內部作業參考。"
              "所有金額以原始憑證為準，所有期限與程序以貴會章程及主管機關函文為準。"
              "正式送件、簽名、用印均由協會權責人員確認後為之。")

# ---------------------------------------------------------------- 基礎工具

def TODO(label):
    return f'<span class="todo">【待補：{label}】</span>'

def load_cfg(path="協會資料.json"):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    print(f"⚠️  找不到 {path}，先用空白範本產出（欄位會印成【待補】）。", file=sys.stderr)
    print("    請先執行： python3 she.py init", file=sys.stderr)
    return {}

def g(cfg, dotted, label=None):
    """取巢狀欄位，缺就回 TODO 標記。"""
    cur = cfg
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur or cur[k] in ("", None, []):
            return TODO(label or dotted.split(".")[-1])
        cur = cur[k]
    return cur

def logo_b64():
    if os.path.exists(LOGO):
        return base64.b64encode(open(LOGO, "rb").read()).decode()
    return ""

CSS = """
@page { size: A4; margin: 16mm 15mm 18mm 15mm; }
* { box-sizing: border-box; }
body { font-family: "PingFang TC","Songti TC","Heiti TC","Microsoft JhengHei",sans-serif;
       color:#1a1a1a; font-size:11.5pt; line-height:1.7; margin:0; }
.hdr { display:flex; align-items:center; justify-content:space-between;
       border-bottom:2.5px solid #C8551B; padding-bottom:6px; margin-bottom:14px; }
.hdr .org { font-size:10pt; color:#666; letter-spacing:.5px; }
.hdr img { height:38px; }
h1 { font-size:19pt; text-align:center; letter-spacing:3px; margin:14px 0 4px; }
h2 { font-size:13pt; color:#C8551B; border-left:5px solid #C8551B;
     padding-left:9px; margin:20px 0 9px; }
h3 { font-size:12pt; margin:14px 0 6px; }
.sub { text-align:center; color:#666; font-size:10.5pt; margin-bottom:16px; }
table { width:100%; border-collapse:collapse; margin:9px 0; font-size:10.5pt; }
th,td { border:1px solid #999; padding:6px 7px; vertical-align:middle; }
th { background:#F2E4D8; font-weight:600; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.sign-row td { height:30px; }
.meta { width:100%; border:none; margin-bottom:10px; font-size:11pt; }
.meta td { border:none; padding:3px 0; }
.meta td:first-child { width:82px; color:#666; }
.todo { color:#B00020; font-weight:600; }
.warn { background:#FFF3F3; border-left:4px solid #B00020; padding:9px 12px; margin:10px 0;
        font-size:10.5pt; }
.note { background:#F7F4EF; border-left:4px solid #C8551B; padding:9px 12px; margin:10px 0;
        font-size:10.5pt; }
.foot { margin-top:22px; padding-top:8px; border-top:1px solid #ccc;
        font-size:8.5pt; color:#777; line-height:1.5; }
.pb { page-break-before:always; }
ol,ul { padding-left:22px; } li { margin:3px 0; }
.blank { border-bottom:1px solid #333; display:inline-block; min-width:110px; }
"""

def html_doc(title, body, subtitle=""):
    lb = logo_b64()
    img = f'<img src="data:image/png;base64,{lb}">' if lb else f'<span>{BRAND}</span>'
    sub = f'<div class="sub">{subtitle}</div>' if subtitle else ""
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<title>{title}</title><style>{CSS}</style></head><body>
<div class="hdr"><div class="org">{BRAND}｜AI 員工 小社</div>{img}</div>
{body}
<div class="foot">{DISCLAIMER}</div>
</body></html>"""

def write_pdf(html, out_pdf):
    os.makedirs(os.path.dirname(os.path.abspath(out_pdf)) or ".", exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
    tmp.write(html); tmp.close()
    if not os.path.exists(CHROME):
        alt = os.path.splitext(out_pdf)[0] + ".html"
        open(alt, "w", encoding="utf-8").write(html)
        print(f"⚠️  找不到 Chrome，改輸出 HTML：{alt}", file=sys.stderr)
        return alt
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={os.path.abspath(out_pdf)}", "file://" + tmp.name],
                   capture_output=True, timeout=120)
    os.unlink(tmp.name)
    if not os.path.exists(out_pdf):
        raise RuntimeError(f"PDF 產製失敗：{out_pdf}")
    print(f"  ✓ {out_pdf}")
    return out_pdf

def roc(d):
    """西元 date → 民國字串"""
    return f"{d.year - 1911}年{d.month}月{d.day}日"

def parse_date(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").date()

# ---------------------------------------------------------------- init

CARD = """# 協會基本資料卡（請總幹事填寫）

> 填一次，之後小社所有文件都自動帶入，不用再問。
> **不知道的欄位請留空，不要猜** —— 留空會印成【待補】，比填錯安全。

## A. 協會身分
- 立案全銜：
- 統一編號：
- 立案文號 / 日期：
- 會址：
- 聯絡電話 / Email：

## B. 主管機關
- 社會局（處）全銜：
- 承辦科室 / 承辦人 / 電話：
- 線上登錄系統名稱：
- 線上登錄系統網址：
- 每次活動要登錄的欄位（照抄系統上的欄位名）：
- 登錄期限（例：活動後 7 日內）：

## C. 章程（請翻章程本文抄，勿憑印象）
- 會員大會頻率（第__條）：
- 理監事會頻率（第__條）：
- 開會通知前置天數（第__條）：
- 會員大會出席門檻（第__條）：
- 決議門檻（第__條）：
- 目前屆次 / 任期起迄：
- 今年是否為改選年：

## D. 幹部
- 理事長 / 常務監事 / 總幹事：
- 會計 / 出納：

## E. 會員
- 個人會員數 / 團體會員數：

## F. 常態活動
### 週六共餐
- 時間 / 地點 / 平均人數：
- 是否收費 / 金額：
- 經費來源（哪個補助案）：
### 每週兩堂課程
- 課名 / 時間 / 講師：
- 鐘點費標準：
- 經費來源：
### 志工
- 志工人數 / 是否需記錄時數：

## G. 補助案（每案一組，可複製）
- 案名：
- 補助機關 / 作業要點名稱：
- 補助期間（起—迄）：
- 核定金額 / 自籌款：
- 申請期限 / 核銷期限：
- 結報應附文件：
- 單張金額門檻（超過需附領據/印領清冊）：

## H. 會刊與捐贈
- 往年會刊頁數 / 份數 / 開數 / 印刷廠 / 費用：
- 捐贈徵信現況（是否已確認捐贈人可否具名）：
- 是否有對外主動募款：

---
填完請交回，小社會轉成 `協會資料.json` 並產出全年度行事曆。
"""

def cmd_init(a):
    open(a.out, "w", encoding="utf-8").write(CARD)
    print(f"  ✓ {a.out}")
    tpl = os.path.join(os.path.dirname(os.path.abspath(a.out)) or ".", "協會資料.json")
    if not os.path.exists(tpl):
        skeleton = {
            "協會": {"全銜": "", "簡稱": "", "統一編號": "", "立案文號": "", "會址": "", "聯絡電話": ""},
            "主管機關": {"名稱": "", "承辦人": "", "電話": "", "線上系統名稱": "", "線上系統網址": "",
                     "線上系統欄位": ["活動名稱", "日期", "時間", "地點", "對象", "人次", "內容摘要", "經費來源"]},
            "幹部": {"理事長": "", "常務監事": "", "總幹事": "", "會計": "", "出納": ""},
            "章程": {"會員大會頻率": "", "理監事會頻率": "", "開會通知前置天數": "",
                   "會員大會出席門檻": "", "決議門檻": "", "屆次": ""},
            "會員": {"個人會員數": 0, "團體會員數": 0},
            "常態活動": {"共餐": {"頻率": "每週六", "時間": "", "地點": "", "平均人數": 0, "經費來源": ""},
                     "課程": {"頻率": "每週2堂", "課名與時間": [], "講師": [], "經費來源": ""}},
            "補助案": [{"案名": "", "補助機關": "", "補助期間": "", "核定金額": 0,
                     "申請期限": "", "核銷期限": "", "單張門檻": 0}],
            "會計": {"會計年度": "每年1月1日至12月31日"},
        }
        json.dump(skeleton, open(tpl, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  ✓ {tpl}（空白範本）")
    print("\n下一步：填完資料卡 → 把答案填進 協會資料.json → 執行 she.py calendar --all")

# ---------------------------------------------------------------- calendar

WEEKLY = [("每週六", "長者共餐", "簽到表、照片3-5張、當日採買憑證，**當週歸檔**"),
          ("每週(2堂)", "社區課程", "簽到表、照片、講師領據")]
QUARTERLY = [("每季初", "補助申請", "計畫書、經費預算表"),
             ("每季末", "經費結報", "結報表、憑證清冊、原始憑證、成果報告"),
             ("每季末", "成果報告", "場次/人次統計、照片頁、效益分析")]
ANNUAL = [("年底", "會員大會", "開會通知（依章程前置天數）、議程、簽到簿、會議紀錄、報備查"),
          ("年底", "年度決算 / 次年預算", "由財務部小帳產出，大會通過"),
          ("年底—年初", "年度會刊", "六大單元：理事長的話/會議時間/會員資料/捐贈徵信/帳戶/成果花絮"),
          ("年初", "會員資料更新", "會費收取、名冊更新"),
          ("改選年", "理監事改選", "提前一個月確認流程、當選公告、報備查")]

def cmd_calendar(a):
    cfg = load_cfg(a.cfg)
    name = g(cfg, "協會.簡稱", "協會名稱")
    today = dt.date.today()
    rows = []
    if a.all or a.days:
        pass
    # 週期性提醒表
    body = [f"<h1>年度行事曆</h1><div class='sub'>{name}｜製表日 {roc(today)}</div>"]
    body.append("<div class='note'>本表為<b>提醒骨架</b>。實際期限一律以貴會章程與主管機關當年度函文為準；"
                "拿到正式期限後請填入 <code>協會資料.json</code>，小社會改用真實日期提醒。</div>")

    def tbl(title, items, cols=("時點", "工作", "要收齊的東西")):
        s = [f"<h2>{title}</h2><table><tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>"]
        for it in items:
            s.append("<tr>" + "".join(f"<td>{x}</td>" for x in it) + "</tr>")
        s.append("</table>")
        return "".join(s)

    body.append(tbl("每週（固定性工作）", WEEKLY))
    body.append(tbl("每季（社會局補助）", QUARTERLY))
    body.append(tbl("每年", ANNUAL))

    # 未來 N 天的週六共餐推算
    if a.days:
        body.append(f"<h2>未來 {a.days} 天：週六共餐排程</h2><table>"
                    "<tr><th>日期</th><th>星期</th><th>活動</th><th>狀態</th></tr>")
        d = today
        n = 0
        while d <= today + dt.timedelta(days=a.days):
            if d.weekday() == 5:
                n += 1
                body.append(f"<tr><td>{d.isoformat()}</td><td>六</td><td>長者共餐</td>"
                            f"<td>□ 簽到表　□ 照片　□ 憑證　□ 系統登錄</td></tr>")
            d += dt.timedelta(days=1)
        body.append("</table>")
        body.append(f"<p style='font-size:10.5pt;color:#666'>共 {n} 場。"
                    f"每場請用：<code>she.py event --type 共餐 --date YYYY-MM-DD</code></p>")

    body.append("<div class='warn'><b>最容易出事的一件事</b>：活動當下沒收齊簽到表／照片／憑證，"
                "季末核銷補不回來。請把「當週歸檔」設成鐵律。</div>")

    write_pdf(html_doc("年度行事曆", "".join(body)), a.out or "年度行事曆.pdf")

# ---------------------------------------------------------------- event

def cmd_event(a):
    cfg = load_cfg(a.cfg)
    d = parse_date(a.date)
    full = g(cfg, "協會.全銜", "協會立案全銜")
    title = a.title or ("長者共餐" if a.type == "共餐" else "社區課程")
    loc = g(cfg, f"常態活動.{a.type}.地點", "地點") if a.type == "共餐" else TODO("地點")
    tm = g(cfg, f"常態活動.{a.type}.時間", "時間")
    src = g(cfg, f"常態活動.{a.type}.經費來源", "經費來源(補助案名)")
    outdir = a.out or "出件"
    os.makedirs(outdir, exist_ok=True)
    stem = f"{d.strftime('%Y%m%d')}_{a.type}"

    # 1) 簽到表
    meta = (f"<table class='meta'>"
            f"<tr><td>活動名稱</td><td>{title}</td></tr>"
            f"<tr><td>日　　期</td><td>{roc(d)}（{'一二三四五六日'[d.weekday()]}）</td></tr>"
            f"<tr><td>時　　間</td><td>{tm}</td></tr>"
            f"<tr><td>地　　點</td><td>{loc}</td></tr>"
            f"<tr><td>經費來源</td><td>{src}</td></tr></table>")
    rows = "".join(f"<tr class='sign-row'><td class='num'>{i}</td><td></td><td></td><td></td></tr>"
                   for i in range(1, a.rows + 1))
    body = (f"<h1>活動簽到表</h1><div class='sub'>{full}</div>{meta}"
            "<table><tr><th style='width:42px'>序</th><th style='width:26%'>姓　名</th>"
            "<th style='width:32%'>簽名 / 蓋章</th><th>備註（里別）</th></tr>"
            f"{rows}</table>"
            "<table style='margin-top:12px'><tr>"
            "<th style='width:25%'>實到人數合計</th><td style='width:25%'></td>"
            "<th style='width:25%'>記錄人</th><td></td></tr>"
            "<tr><th>負責人簽章</th><td colspan='3' style='height:38px'></td></tr></table>"
            "<div class='warn'>長輩不便簽名可蓋章或按指印；"
            "<b>不可由志工整排代簽</b>（核銷抽查最常被抓的一項）。本表<b>正本</b>須歸檔備查。</div>")
    write_pdf(html_doc("活動簽到表", body), os.path.join(outdir, f"{stem}_簽到表.pdf"))

    # 2) 活動紀錄卡
    body2 = (f"<h1>活動紀錄卡</h1><div class='sub'>{full}</div>{meta}"
             "<h2>活動內容摘要（3–5 行，寫實際做了什麼）</h2>"
             "<table><tr><td style='height:100px'></td></tr></table>"
             "<h2>實到人數</h2><table><tr>"
             "<th style='width:22%'>長者</th><td style='width:11%'></td>"
             "<th style='width:22%'>志工</th><td style='width:11%'></td>"
             "<th style='width:22%'>合計人次</th><td></td></tr></table>"
             "<h2>支出憑證（當日交總幹事）</h2>"
             "<table><tr><th style='width:16%'>日期</th><th>品名／用途</th>"
             "<th style='width:20%'>廠商</th><th style='width:15%'>金額</th></tr>"
             + "".join("<tr class='sign-row'><td></td><td></td><td></td><td></td></tr>" for _ in range(5))
             + "</table>"
             "<h2>照片清單（3–5 張，檔名照格式）</h2>"
             "<table><tr><th style='width:34%'>檔名</th><th>圖說（日期｜活動｜在做什麼）</th></tr>"
             + "".join(f"<tr class='sign-row'><td>{d.strftime('%Y%m%d')}_{a.type}_0{i}.jpg</td><td></td></tr>"
                       for i in range(1, 6)) + "</table>"
             "<div class='warn'><b>當週三件套</b>：①簽到表正本　②照片 3–5 張　③支出憑證。<br>"
             "缺一件，季末核銷就有風險。<b>禁止用 AI 生成圖或舊照片充當活動花絮。</b></div>")
    write_pdf(html_doc("活動紀錄卡", body2), os.path.join(outdir, f"{stem}_紀錄卡.pdf"))

    # 3) 社會局系統貼上包
    fields = cfg.get("主管機關", {}).get("線上系統欄位") or \
        ["活動名稱", "日期", "時間", "地點", "對象", "人次", "內容摘要", "經費來源"]
    vals = {"活動名稱": title, "日期": d.isoformat(), "時間": tm if "待補" not in str(tm) else "",
            "地點": loc if "待補" not in str(loc) else "", "對象": "社區長者／居民",
            "人次": "（填實到人次）", "內容摘要": "（貼活動紀錄卡的摘要）",
            "經費來源": src if "待補" not in str(src) else ""}
    sysname = cfg.get("主管機關", {}).get("線上系統名稱") or "（系統名稱待補）"
    sysurl = cfg.get("主管機關", {}).get("線上系統網址") or "（網址待補）"
    lines = [f"社會局線上系統 登錄貼上包", f"系統：{sysname}", f"網址：{sysurl}",
             f"活動：{title}　{d.isoformat()}", "=" * 42, ""]
    for f_ in fields:
        lines.append(f"【{f_}】")
        lines.append(str(vals.get(f_, "")))
        lines.append("")
    lines += ["=" * 42, "要一併上傳的檔案：",
              f"  □ {stem}_簽到表.pdf（掃描正本）",
              f"  □ 照片 3–5 張（{d.strftime('%Y%m%d')}_{a.type}_0X.jpg）",
              "  □ 憑證（若系統要求）", "",
              "※ 帳密由總幹事本人保管，小社不接觸、不代登入、不代送出。"]
    p = os.path.join(outdir, f"{stem}_系統貼上包.txt")
    open(p, "w", encoding="utf-8").write("\n".join(lines))
    print(f"  ✓ {p}")
    print(f"\n【這包是什麼】{roc(d)} {title} 的全套活動文件")
    print( "【你要做什麼】印簽到表帶到現場 → 活動後填紀錄卡 → 開系統照貼上包一格一格貼")
    print( "【什麼時候前】依社會局規定的登錄期限（待補），建議活動後 3 日內完成")

# ---------------------------------------------------------------- expense

def cmd_expense(a):
    cfg = load_cfg(a.cfg)
    full = str(g(cfg, "協會.全銜", "全銜"))
    tax_id = str(g(cfg, "協會.統一編號", "統編"))
    outdir = a.out or "出件"
    os.makedirs(outdir, exist_ok=True)

    with open(a.csvfile, encoding="utf-8-sig") as f:
        recs = list(csv.DictReader(f))
    if not recs:
        sys.exit("憑證明細 CSV 是空的。")

    start = parse_date(a.start) if a.start else None
    end = parse_date(a.end) if a.end else None
    risks = []
    total = 0
    by_subject = {}
    rows = []
    for i, r in enumerate(recs, 1):
        raw = (r.get("金額") or "0").replace(",", "").strip()
        try:
            amt = float(raw)
        except ValueError:
            amt = 0
            risks.append((i, "金額無法解析", f"原始值「{raw}」"))
        total += amt
        subj = (r.get("科目") or "未分類").strip()
        by_subject[subj] = by_subject.get(subj, 0) + amt
        flags = []
        ds = (r.get("日期") or "").strip()
        try:
            dd = parse_date(ds)
            if start and dd < start:
                flags.append("A")
                risks.append((i, "A 日期出界", f"{ds} 早於補助期間起日 {a.start}"))
            if end and dd > end:
                flags.append("A")
                risks.append((i, "A 日期出界", f"{ds} 晚於補助期間迄日 {a.end}"))
        except ValueError:
            flags.append("A")
            risks.append((i, "A 日期格式錯誤", f"「{ds}」非 YYYY-MM-DD"))
        head = (r.get("抬頭") or "").strip()
        if head and "待補" not in full and head != full:
            flags.append("B"); risks.append((i, "B 抬頭錯誤", f"「{head}」≠ 立案全銜「{full}」"))
        tid = (r.get("統編") or "").strip()
        if tid and "待補" not in tax_id and tid != tax_id:
            flags.append("C"); risks.append((i, "C 統編錯誤", f"「{tid}」≠ 協會統編「{tax_id}」"))
        if a.threshold and amt >= a.threshold and not (r.get("附件") or "").strip():
            flags.append("D")
            risks.append((i, "D 大額缺附件", f"{amt:,.0f} ≥ 門檻 {a.threshold:,.0f}，未註明領據／印領清冊"))
        rows.append((i, ds, r.get("品名", ""), r.get("廠商", ""), r.get("憑證種類", ""),
                     amt, subj, "／".join(sorted(set(flags)))))

    tr = "".join(f"<tr><td class='num'>{i}</td><td>{ds}</td><td>{nm}</td><td>{vd}</td>"
                 f"<td>{ty}</td><td class='num'>{amt:,.0f}</td><td>{sj}</td>"
                 f"<td style='color:#B00020;font-weight:600'>{fl}</td></tr>"
                 for i, ds, nm, vd, ty, amt, sj, fl in rows)
    body = (f"<h1>憑證清冊</h1><div class='sub'>{full}｜{a.period}</div>"
            "<table><tr><th style='width:38px'>序</th><th style='width:80px'>日期</th><th>品名／用途</th>"
            "<th style='width:14%'>廠商</th><th style='width:62px'>種類</th><th style='width:78px'>金額</th>"
            "<th style='width:78px'>科目</th><th style='width:58px'>風險</th></tr>"
            f"{tr}<tr><th colspan='5'>合計</th><th class='num'>{total:,.0f}</th><th colspan='2'></th></tr></table>"
            "<p style='font-size:10pt;color:#666'>序號請與原始憑證黏貼簿順序一致。</p>")

    # 科目彙總 + 結報表
    sub_rows = "".join(f"<tr><td>{k}</td><td class='num'>{v:,.0f}</td>"
                       f"<td class='num'>{v/total*100:.1f}%</td></tr>"
                       for k, v in sorted(by_subject.items(), key=lambda x: -x[1])) if total else ""
    body += ("<h2>科目彙總</h2><table><tr><th>科目</th><th style='width:110px'>實支金額</th>"
             f"<th style='width:80px'>占比</th></tr>{sub_rows}"
             f"<tr><th>合計</th><th class='num'>{total:,.0f}</th><th></th></tr></table>")

    budget_rows = "".join(f"<tr><td>{k}</td><td></td><td class='num'>{v:,.0f}</td><td></td><td></td></tr>"
                          for k in by_subject for v in [by_subject[k]])
    body += ("<h2 class='pb'>經費結報表</h2>"
             f"<div class='sub'>{full}｜{a.period}</div>"
             "<table><tr><th>科目</th><th style='width:15%'>核定預算</th><th style='width:15%'>實支金額</th>"
             "<th style='width:13%'>差異</th><th style='width:20%'>說明</th></tr>"
             f"{budget_rows}"
             f"<tr><th>合計</th><th></th><th class='num'>{total:,.0f}</th><th></th><th></th></tr></table>"
             "<div class='warn'><b>不准出表的情況</b>：實支金額 ≠ 憑證清冊加總。"
             "兩者不符請先找出差異，不要硬塞平。核定預算欄請照核定函填。</div>"
             "<table style='margin-top:16px'><tr><th style='width:25%'>製表（總幹事）</th><td style='height:42px'></td>"
             "<th style='width:25%'>理事長</th><td></td></tr></table>")

    write_pdf(html_doc("憑證清冊與經費結報表", body), os.path.join(outdir, f"{a.period}_憑證清冊與結報表.pdf"))

    # 風險清單（Markdown，給總幹事逐條看）
    md = [f"# {a.period} 核銷風險清單", "",
          f"總筆數 **{len(recs)}**　合計 **{total:,.0f} 元**　風險筆數 **{len({r[0] for r in risks})}**", "",
          "> 小社**只標示、不刪改**。要不要抽掉某筆，是總幹事＋承辦人的判斷。", ""]
    if risks:
        md += ["| 序號 | 風險 | 說明 |", "|---:|:---|:---|"]
        md += [f"| {i} | {k} | {v} |" for i, k, v in risks]
        md += ["", "## 處理方式", "",
               "- **A 日期出界** → 該筆抽掉，改列協會自籌",
               "- **B 抬頭錯誤 / C 統編錯誤** → 請廠商重開；無法重開就抽掉",
               "- **D 大額缺附件** → 補領據／估價單／印領清冊"]
    else:
        md += ["✅ 四項自動檢查未發現問題。",
               "",
               "⚠️ 但仍請人工確認：憑證正本是否齊全、品項描述是否具體（不可只寫「雜貨」）、",
               "講師鐘點是否已備領據與扣繳資料。"]
    if not a.start or not a.end:
        md += ["", "⚠️ **未提供補助期間**（--start / --end），A 類日期檢查未完整執行。"]
    if not a.threshold:
        md += ["", "⚠️ **未提供單張金額門檻**（--threshold），D 類檢查未執行。門檻請查該案作業要點。"]
    p = os.path.join(outdir, f"{a.period}_核銷風險清單.md")
    open(p, "w", encoding="utf-8").write("\n".join(md))
    print(f"  ✓ {p}")
    print(f"\n【這包是什麼】{a.period} 核銷的憑證清冊、結報表與風險清單")
    print(f"【你要做什麼】先看風險清單（{len({r[0] for r in risks})} 筆要處理）→ 處理完印結報表簽章")
    print( "【什麼時候前】依補助核定函的核銷期限，建議提前一週送")

# ---------------------------------------------------------------- report

def cmd_report(a):
    cfg = load_cfg(a.cfg)
    full = g(cfg, "協會.全銜", "全銜")
    outdir = a.out or "出件"
    os.makedirs(outdir, exist_ok=True)
    body = [f"<h1>成果報告</h1><div class='sub'>{full}｜{a.period}</div>",
            "<h2>一、計畫概述</h2>",
            "<table><tr><td style='height:76px'>（一段話說明本期辦理的計畫名稱、目的與服務對象）</td></tr></table>",
            "<h2>二、辦理情形總表</h2>",
            "<table><tr><th style='width:44px'>序</th><th style='width:92px'>日期</th><th>活動名稱</th>"
            "<th style='width:70px'>時數</th><th style='width:82px'>實到人數</th><th style='width:82px'>人次</th></tr>"]
    for i in range(1, a.slots + 1):
        body.append(f"<tr class='sign-row'><td class='num'>{i}</td><td></td><td></td><td></td><td></td><td></td></tr>")
    body.append("<tr><th colspan='4'>合計</th><th></th><th></th></tr></table>")
    body.append("<h2>三、各場次紀錄</h2>"
                "<p style='font-size:10.5pt;color:#666'>每場 3–5 行，寫<b>實際做了什麼</b>，不要寫成流水帳。</p>"
                "<table><tr><th style='width:92px'>日期</th><th style='width:22%'>活動名稱</th>"
                "<th>內容摘要</th><th style='width:66px'>實到</th></tr>"
                + "".join("<tr><td></td><td></td><td style='height:44px'></td><td></td></tr>" for _ in range(6))
                + "</table>")
    body.append("<h2 class='pb'>四、活動照片</h2>"
                "<p style='font-size:10.5pt;color:#666'>每場 2–3 張，圖說格式：<b>日期｜活動｜在做什麼</b>。"
                "若補助要求懸掛補助單位字樣布條，至少一張要清楚拍到。</p>"
                "<table><tr><td style='height:180px;width:50%'>（照片）</td><td style='height:180px'>（照片）</td></tr>"
                "<tr><td>圖說：</td><td>圖說：</td></tr>"
                "<tr><td style='height:180px'>（照片）</td><td style='height:180px'>（照片）</td></tr>"
                "<tr><td>圖說：</td><td>圖說：</td></tr></table>")
    body.append("<h2 class='pb'>五、效益分析</h2>"
                "<table><tr><th style='width:30%'>辦理場次</th><td></td></tr>"
                "<tr><th>服務總人次</th><td></td></tr>"
                "<tr><th>服務不重複人數</th><td></td></tr>"
                "<tr><th>涵蓋里別</th><td></td></tr>"
                "<tr><th>志工投入人次／時數</th><td></td></tr></table>"
                "<h3>質化回饋</h3>"
                "<table><tr><td style='height:90px'>（可直接引用長輩或家屬的原話，一兩句就很有力）</td></tr></table>")
    body.append("<h2>六、檢討與建議</h2>"
                "<table><tr><td style='height:110px'>（寫真的問題，例：場地不足、志工人力老化、"
                "共餐食材成本上漲。誠實寫，承辦人反而更信任）</td></tr></table>")
    body.append("<table style='margin-top:16px'><tr><th style='width:25%'>製表</th><td style='height:42px'></td>"
                "<th style='width:25%'>理事長</th><td></td></tr></table>")
    body.append("<div class='warn'><b>只寫真實發生的事。</b>沒辦的活動不寫、沒到的人數不灌、"
                "沒拍的照片不生成 —— AI 生成圖<b>永遠不可</b>當活動花絮照。</div>")
    write_pdf(html_doc("成果報告", "".join(body)), os.path.join(outdir, f"{a.period}_成果報告.pdf"))

# ---------------------------------------------------------------- meeting

def cmd_meeting(a):
    cfg = load_cfg(a.cfg)
    full = g(cfg, "協會.全銜", "全銜")
    addr = g(cfg, "協會.會址", "會址")
    tel = g(cfg, "協會.聯絡電話", "電話")
    chair = g(cfg, "幹部.理事長", "理事長")
    sec = g(cfg, "幹部.總幹事", "總幹事")
    term = g(cfg, "章程.屆次", "屆次")
    lead = g(cfg, "章程.開會通知前置天數", "章程第__條 前置天數")
    quorum = g(cfg, "章程.會員大會出席門檻", "章程第__條 出席門檻")
    d = parse_date(a.date)
    outdir = a.out or "出件"
    os.makedirs(outdir, exist_ok=True)
    kind = a.kind

    hdr_meta = (f"<table class='meta'>"
                f"<tr><td>會議名稱</td><td>{term} {kind}</td></tr>"
                f"<tr><td>時　　間</td><td>{roc(d)} <span class='blank'></span> 時 <span class='blank'></span> 分</td></tr>"
                f"<tr><td>地　　點</td><td>{a.place or TODO('地點')}</td></tr></table>")

    # 1 開會通知
    b1 = (f"<h1>開會通知</h1><div class='sub'>{full}</div>{hdr_meta}"
          "<h2>敬啟者</h2>"
          f"<p>茲訂於上開時間、地點召開「{term} {kind}」，議程如附。"
          "敬請 撥冗出席，並請攜帶本通知。若不克出席，請於會前告知本會。</p>"
          "<table class='meta'><tr><td>聯絡人</td><td>總幹事 " + str(sec) + "</td></tr>"
          f"<tr><td>電　　話</td><td>{tel}</td></tr>"
          f"<tr><td>會　　址</td><td>{addr}</td></tr></table>"
          f"<p style='margin-top:20px;text-align:right'>理事長　{chair}　敬邀</p>"
          f"<div class='warn'>本通知須依<b>章程規定之前置天數</b>送達：{lead}。"
          "請保留寄送或簽收紀錄 —— 通知不足期限，決議效力可能被質疑。</div>")
    write_pdf(html_doc("開會通知", b1), os.path.join(outdir, f"{d.strftime('%Y%m%d')}_{kind}_開會通知.pdf"))

    # 2 議程
    if kind == "會員大會":
        agenda = """<h2>一、主席致詞</h2>
<h2>二、報告事項</h2><ol>
<li>上次會議決議執行情形報告</li>
<li>本年度會務工作報告</li>
<li>本年度經費收支決算報告</li>
<li>監事會財務監察報告</li></ol>
<h2>三、討論事項</h2>
<table><tr><th style='width:66px'>案次</th><th>內容</th></tr>
<tr><td>第一案</td><td><b>案由：</b>次年度工作計畫（草案），請討論。<br>
<b>說明：</b><br><b>辦法：</b>通過後據以執行。<br><b>決議：</b>（會中填寫）</td></tr>
<tr><td>第二案</td><td><b>案由：</b>次年度經費收支預算（草案），請討論。<br>
<b>說明：</b><br><b>辦法：</b>通過後據以執行。<br><b>決議：</b>（會中填寫）</td></tr>
<tr><td>第三案</td><td><b>案由：</b>本年度經費收支決算，請追認。<br>
<b>說明：</b><br><b>辦法：</b><br><b>決議：</b>（會中填寫）</td></tr>
<tr><td>第四案</td><td><b>案由：</b><br><b>說明：</b><br><b>辦法：</b><br><b>決議：</b></td></tr></table>
<h2>四、臨時動議</h2><h2>五、散會</h2>"""
    else:
        agenda = """<h2>一、主席致詞</h2>
<h2>二、報告事項</h2><ol>
<li>上次會議決議執行情形報告</li>
<li>會務與活動辦理情形報告</li>
<li>財務收支報告</li></ol>
<h2>三、討論事項</h2>
<table><tr><th style='width:66px'>案次</th><th>內容</th></tr>
<tr><td>第一案</td><td><b>案由：</b><br><b>說明：</b><br><b>辦法：</b><br><b>決議：</b>（會中填寫）</td></tr>
<tr><td>第二案</td><td><b>案由：</b><br><b>說明：</b><br><b>辦法：</b><br><b>決議：</b></td></tr></table>
<h2>四、臨時動議</h2><h2>五、散會</h2>"""
    b2 = (f"<h1>議　程</h1><div class='sub'>{full}｜{term} {kind}</div>{hdr_meta}{agenda}"
          "<div class='note'><b>議案四要素：案由 → 說明 → 辦法 → 決議。</b>"
          "「決議」欄一律<b>開會當下填</b>，不可事後補寫。散會前請把各案決議唸一次確認。</div>")
    write_pdf(html_doc("議程", b2), os.path.join(outdir, f"{d.strftime('%Y%m%d')}_{kind}_議程.pdf"))

    # 3 簽到簿
    rows = "".join(f"<tr class='sign-row'><td class='num'>{i}</td><td></td><td></td><td></td></tr>"
                   for i in range(1, a.rows + 1))
    b3 = (f"<h1>簽到簿</h1><div class='sub'>{full}｜{term} {kind}</div>{hdr_meta}"
          "<table><tr><th style='width:42px'>序</th><th style='width:28%'>姓　名</th>"
          "<th style='width:32%'>親筆簽名</th><th>備註</th></tr>" + rows + "</table>"
          "<table style='margin-top:12px'><tr><th style='width:25%'>應到人數</th><td style='width:25%'></td>"
          "<th style='width:25%'>實到人數</th><td></td></tr>"
          f"<tr><th>是否達法定人數</th><td colspan='3'>□ 是　□ 否　（門檻：{quorum}）</td></tr></table>"
          "<div class='warn'><b>這張表是法定人數的唯一證明，正本務必保存。</b>"
          "未達法定人數不可硬開；請依章程處理（改期或續會），並在會議紀錄誠實記載實到人數。</div>")
    write_pdf(html_doc("簽到簿", b3), os.path.join(outdir, f"{d.strftime('%Y%m%d')}_{kind}_簽到簿.pdf"))

    # 4 會議紀錄
    b4 = (f"<h1>會議紀錄</h1><div class='sub'>{full}</div>"
          f"<table class='meta'>"
          f"<tr><td>會議名稱</td><td>{term} {kind}</td></tr>"
          f"<tr><td>時　　間</td><td>{roc(d)} <span class='blank'></span> 時 <span class='blank'></span> 分</td></tr>"
          f"<tr><td>地　　點</td><td>{a.place or TODO('地點')}</td></tr>"
          f"<tr><td>應到人數</td><td><span class='blank'></span> 人　　實到人數 <span class='blank'></span> 人</td></tr>"
          f"<tr><td>主　　席</td><td>{chair}　　記錄：<span class='blank'></span></td></tr>"
          f"<tr><td>出列席者</td><td></td></tr></table>"
          "<h2>壹、主席致詞</h2><table><tr><td style='height:60px'></td></tr></table>"
          "<h2>貳、報告事項</h2><table><tr><td style='height:110px'></td></tr></table>"
          "<h2>參、討論事項</h2>"
          "<table><tr><th style='width:66px'>案次</th><th>案由</th><th style='width:34%'>決議與表決結果</th></tr>"
          + "".join("<tr><td>第 案</td><td style='height:56px'></td><td></td></tr>" for _ in range(4)) + "</table>"
          "<h2>肆、臨時動議</h2><table><tr><td style='height:70px'></td></tr></table>"
          "<h2>伍、散會</h2><p>散會時間：<span class='blank'></span> 時 <span class='blank'></span> 分</p>"
          "<table style='margin-top:20px'><tr><th style='width:25%'>主席簽章</th><td style='height:46px'></td>"
          "<th style='width:25%'>記錄簽章</th><td></td></tr></table>"
          "<div class='warn'>決議須記載<b>表決結果</b>（通過／修正通過／保留／不通過，必要時記票數）。"
          "會議紀錄須於規定期限內<b>函報主管機關備查</b>，並檢附簽到簿。</div>")
    write_pdf(html_doc("會議紀錄", b4), os.path.join(outdir, f"{d.strftime('%Y%m%d')}_{kind}_會議紀錄.pdf"))

    # 5 報備查函
    b5 = (f"<h1>函</h1><div class='sub'>{full}</div>"
          f"<table class='meta'>"
          f"<tr><td>受文者</td><td>{g(cfg,'主管機關.名稱','社會局全銜')}</td></tr>"
          f"<tr><td>發文日期</td><td>中華民國 <span class='blank'></span> 年 <span class='blank'></span> 月 <span class='blank'></span> 日</td></tr>"
          f"<tr><td>發文字號</td><td><span class='blank' style='min-width:220px'></span></td></tr>"
          f"<tr><td>速　　別</td><td>普通件</td></tr>"
          f"<tr><td>附　　件</td><td>會議紀錄、簽到簿各乙份</td></tr></table>"
          f"<p><b>主旨：</b>檢陳本會「{term} {kind}」會議紀錄乙份，請 查照備查。</p>"
          "<p><b>說明：</b></p><ol>"
          f"<li>本會於 {roc(d)} 假 {a.place or '（地點）'} 召開「{term} {kind}」，"
          "應到 <span class='blank' style='min-width:56px'></span> 人，"
          "實到 <span class='blank' style='min-width:56px'></span> 人，已達法定人數。</li>"
          "<li>檢附會議紀錄及簽到簿各乙份，敬請查照。</li></ol>"
          f"<p style='margin-top:24px;text-align:center'>理事長　{chair}</p>"
          "<div class='warn'>發文字號、備查期限依主管機關規定；"
          "格式若與貴局公文範例不同，<b>以社會局提供的格式為準</b>。</div>")
    write_pdf(html_doc("報備查函", b5), os.path.join(outdir, f"{d.strftime('%Y%m%d')}_{kind}_報備查函.pdf"))

    print(f"\n【這包是什麼】{roc(d)} {kind} 的五件套文書")
    print("【你要做什麼】① 開會通知先發（依章程前置天數，見通知末頁提醒）"
          " ② 當天帶簽到簿與議程 ③ 會後填會議紀錄 ④ 用備查函函報社會局")
    print( "【什麼時候前】通知：依章程；備查：依主管機關規定期限")

# ---------------------------------------------------------------- journal

def cmd_journal(a):
    cfg = load_cfg(a.cfg)
    full = g(cfg, "協會.全銜", "全銜")
    chair = g(cfg, "幹部.理事長", "理事長")
    addr = g(cfg, "協會.會址", "會址")
    tel = g(cfg, "協會.聯絡電話", "電話")
    y = a.year
    outdir = a.out or "出件"
    os.makedirs(outdir, exist_ok=True)
    lb = logo_b64()
    img = f'<img src="data:image/png;base64,{lb}" style="height:74px">' if lb else ""

    cover = (f"<div style='text-align:center;padding-top:88px'>"
             f"<div style='font-size:15pt;letter-spacing:6px;color:#666'>{y} 年度</div>"
             f"<h1 style='font-size:30pt;margin:20px 0 8px;letter-spacing:8px'>會　刊</h1>"
             f"<div style='font-size:16pt;margin-top:14px'>{full}</div>"
             f"<div style='margin-top:70px'>{img}</div>"
             f"<div style='font-size:9.5pt;color:#888;margin-top:8px'>{BRAND}　協助編製</div></div>")

    u1 = ("<h2 class='pb'>壹、理事長的話</h2>"
          "<div class='note'>撰稿前請先跟理事長要三樣東西：①今年最有感的一件事 ②最想感謝誰 "
          "③明年最想做成哪一件事。有這三點才寫得出像本人講的話。</div>"
          "<table><tr><td style='height:300px'>"
          "<p>（第一段：感謝　會員、志工、捐贈人、社會局、里長）</p>"
          "<p>（第二段：今年做了什麼 —— <b>一定要有數字</b>：全年共餐 ○ 場、服務 ○ 人次、課程 ○ 堂、志工 ○ 小時）</p>"
          "<p>（第三段：明年方向 ＋ 邀請參與，要有明確的 call to action）</p>"
          "</td></tr></table>"
          f"<p style='text-align:right;margin-top:16px'>理事長　{chair}　謹誌</p>")

    u2 = ("<h2 class='pb'>貳、會議時間</h2>"
          f"<h3>{y} 年度已辦會議</h3>"
          "<table><tr><th style='width:110px'>日期</th><th>會議名稱</th>"
          "<th style='width:80px'>出席</th><th>主要決議</th></tr>"
          + "".join("<tr class='sign-row'><td></td><td></td><td></td><td></td></tr>" for _ in range(4)) + "</table>"
          f"<h3>{y+1} 年度預定會議與常態活動</h3>"
          "<table><tr><th style='width:130px'>時間</th><th>項目</th><th style='width:30%'>地點</th></tr>"
          "<tr><td>每週六</td><td>長者共餐</td><td></td></tr>"
          "<tr><td>每週（2 堂）</td><td>社區課程</td><td></td></tr>"
          "<tr><td>每季</td><td>補助申請與經費結報</td><td>—</td></tr>"
          "<tr><td>年底</td><td>會員大會</td><td></td></tr></table>")

    u3 = ("<h2 class='pb'>參、會員資料</h2><h3>本屆幹部名錄</h3>"
          "<table><tr><th style='width:26%'>職稱</th><th style='width:30%'>姓名</th><th>備註</th></tr>"
          "<tr><td>理事長</td><td></td><td></td></tr>"
          "<tr><td>常務理事</td><td></td><td></td></tr>"
          "<tr><td>理　事</td><td></td><td></td></tr>"
          "<tr><td>常務監事</td><td></td><td></td></tr>"
          "<tr><td>監　事</td><td></td><td></td></tr>"
          "<tr><td>總幹事</td><td></td><td></td></tr>"
          "<tr><td>會計 / 出納</td><td></td><td></td></tr></table>"
          "<h3>會員統計</h3>"
          "<table><tr><th style='width:34%'>個人會員</th><td></td>"
          "<th style='width:34%'>團體會員</th><td></td></tr>"
          "<tr><th>本年度新入會</th><td></td><th>志工人數</th><td></td></tr></table>"
          "<div class='warn'><b>公開版只列姓名或姓氏＋里別。</b>"
          "電話、住址、身分證字號一律<b>不印在會刊上</b>（個資法）。</div>")

    u4 = ("<h2 class='pb'>肆、捐贈徵信</h2>"
          "<p style='font-size:10.5pt;color:#666'>感謝以下善心人士與單位對本會的支持。</p>"
          "<h3>款項捐贈</h3>"
          "<table><tr><th style='width:44px'>序</th><th style='width:34%'>捐贈人</th>"
          "<th style='width:22%'>金額</th><th>用途／指定項目</th></tr>"
          + "".join(f"<tr class='sign-row'><td class='num'>{i}</td><td></td><td></td><td></td></tr>"
                    for i in range(1, 9)) + "</table>"
          "<h3>物資捐贈</h3>"
          "<table><tr><th style='width:44px'>序</th><th style='width:34%'>捐贈人</th>"
          "<th style='width:26%'>品項</th><th>數量</th></tr>"
          + "".join(f"<tr class='sign-row'><td class='num'>{i}</td><td></td><td></td><td></td></tr>"
                    for i in range(1, 6)) + "</table>"
          "<div class='warn'><b>三條規矩</b>：①經同意才具名，未確認一律寫「善心人士」　"
          "②金額是否公開先問捐贈人　③捐贈人電話住址永不公開。<br>"
          "協會若<b>對外主動勸募</b>，涉及《公益勸募條例》許可制，請先確認主管機關規定。</div>")

    u5 = ("<h2 class='pb'>伍、帳戶（年度收支對照）</h2>"
          f"<div class='sub'>{y} 年度</div>"
          "<table><tr><th style='width:60%'>項　　目</th><th>金　額（元）</th></tr>"
          "<tr><th colspan='2' style='text-align:left'>收入</th></tr>"
          "<tr><td>　會費收入</td><td class='num'></td></tr>"
          "<tr><td>　補助收入（社會局）</td><td class='num'></td></tr>"
          "<tr><td>　捐款收入</td><td class='num'></td></tr>"
          "<tr><td>　其他收入</td><td class='num'></td></tr>"
          "<tr><th>　收入合計</th><th class='num'></th></tr>"
          "<tr><th colspan='2' style='text-align:left'>支出</th></tr>"
          "<tr><td>　共餐支出</td><td class='num'></td></tr>"
          "<tr><td>　課程支出</td><td class='num'></td></tr>"
          "<tr><td>　行政支出</td><td class='num'></td></tr>"
          "<tr><td>　其他支出</td><td class='num'></td></tr>"
          "<tr><th>　支出合計</th><th class='num'></th></tr>"
          "<tr><th>本年度結餘</th><th class='num'></th></tr>"
          "<tr><td>上年度結轉</td><td class='num'></td></tr>"
          "<tr><th>期末結存</th><th class='num'></th></tr></table>"
          "<div class='warn'>此表數字<b>必須與會員大會通過的年度決算表一致</b>，"
          "否則會員一定當場問。數字由財務部小帳產出。<b>完整銀行帳號不印在會刊上。</b></div>")

    def photo_block(title):
        return (f"<h3>{title}</h3><table>"
                "<tr><td style='height:172px;width:50%'>（照片）</td><td style='height:172px'>（照片）</td></tr>"
                "<tr><td>圖說：日期｜活動｜在做什麼</td><td>圖說：</td></tr>"
                "<tr><td style='height:172px'>（照片）</td><td style='height:172px'>（照片）</td></tr>"
                "<tr><td>圖說：</td><td>圖說：</td></tr></table>")

    u6 = ("<h2 class='pb'>陸、成果花絮</h2>"
          + photo_block("週六長者共餐")
          + "<div class='pb'></div>" + photo_block("社區課程")
          + photo_block("節慶與其他活動")
          + "<div class='warn'>挑照片三原則：①有人臉有笑容 ②看得出人多 ③看得出在做什麼。<br>"
            "🚨 <b>禁止用 AI 生成圖或往年舊照冒充</b>；對外公開前請依個資與肖像權守則處理。</div>")

    back = (f"<div class='pb' style='text-align:center;padding-top:150px'>"
            f"<div style='font-size:15pt'>{full}</div>"
            f"<div style='margin-top:12px;font-size:11pt;color:#555'>{addr}</div>"
            f"<div style='font-size:11pt;color:#555'>電話：{tel}</div>"
            f"<div style='margin-top:56px'>{img}</div>"
            f"<div style='font-size:9.5pt;color:#888;margin-top:8px'>{BRAND}　協助編製</div></div>")

    html = html_doc(f"{y}年度會刊", cover + u1 + u2 + u3 + u4 + u5 + u6 + back)
    write_pdf(html, os.path.join(outdir, f"{y}年度會刊.pdf"))

    md = [f"# {y} 年度會刊 素材清單", "",
          "會刊骨架已產出，以下素材請備齊後回填：", "",
          "## ① 理事長的話", "- [ ] 理事長訪談三問（最有感的一件事／最想感謝誰／明年想做成什麼）",
          "- [ ] 全年統計數字（共餐場次、服務人次、課程堂數、志工時數）", "",
          "## ② 會議時間", "- [ ] 本年度已辦會議清單與主要決議", "- [ ] 次年度預定會議日期", "",
          "## ③ 會員資料", "- [ ] 本屆幹部名錄", "- [ ] 會員統計數字（**不列電話住址**）", "",
          "## ④ 捐贈徵信", "- [ ] 捐贈名單（款項＋物資）",
          "- [ ] **逐一確認每位捐贈人可否具名**（未確認寫「善心人士」）", "",
          "## ⑤ 帳戶", "- [ ] 年度收支決算表（財務部小帳產出）",
          "- [ ] 確認數字與大會通過的決算表一致", "",
          "## ⑥ 成果花絮", "- [ ] 共餐照片 4 張＋圖說", "- [ ] 課程照片 4 張＋圖說",
          "- [ ] 節慶活動照片 4 張＋圖說", "- [ ] 肖像權確認（有人要求撤下即無條件撤下）", "",
          "## 送印前", "- [ ] 六大單元齊全", "- [ ] 帳戶數字 = 決算表數字",
          "- [ ] 公開版無電話/住址/身分證字號", "- [ ] 照片全為真實活動照",
          "- [ ] 理事長已親自看過「理事長的話」", "- [ ] 錯字至少兩人校對（印一千份錯一個字很痛）"]
    p = os.path.join(outdir, f"{y}年度會刊_素材清單.md")
    open(p, "w", encoding="utf-8").write("\n".join(md))
    print(f"  ✓ {p}")
    print(f"\n【這包是什麼】{y} 年度會刊骨架（六大單元）＋ 素材清單")
    print( "【你要做什麼】照素材清單收集內容 → 回填 → 校對兩次 → 送印")
    print( "【什麼時候前】建議大會前完成，會上直接發給會員")

# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description="小社 — 社區發展協會行政與文書專員")
    p.add_argument("--cfg", default="協會資料.json", help="協會資料 JSON 路徑")
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("init", help="產協會基本資料卡")
    s.add_argument("--out", default="協會基本資料卡.md")
    s.set_defaults(func=cmd_init)

    s = sp.add_parser("calendar", help="年度行事曆")
    s.add_argument("--days", type=int, default=0, help="加列未來 N 天的週六共餐排程")
    s.add_argument("--all", action="store_true")
    s.add_argument("--out")
    s.set_defaults(func=cmd_calendar)

    s = sp.add_parser("event", help="活動包")
    s.add_argument("--type", required=True, choices=["共餐", "課程"])
    s.add_argument("--date", required=True, help="YYYY-MM-DD")
    s.add_argument("--title")
    s.add_argument("--rows", type=int, default=30, help="簽到表列數")
    s.add_argument("--out")
    s.set_defaults(func=cmd_event)

    s = sp.add_parser("expense", help="憑證清冊與結報表")
    s.add_argument("csvfile")
    s.add_argument("--period", required=True, help='例："115年第3季"')
    s.add_argument("--start", help="補助期間起日 YYYY-MM-DD")
    s.add_argument("--end", help="補助期間迄日 YYYY-MM-DD")
    s.add_argument("--threshold", type=float, help="單張金額門檻（依作業要點）")
    s.add_argument("--out")
    s.set_defaults(func=cmd_expense)

    s = sp.add_parser("report", help="成果報告草稿")
    s.add_argument("--period", required=True)
    s.add_argument("--slots", type=int, default=14, help="辦理情形總表列數")
    s.add_argument("--out")
    s.set_defaults(func=cmd_report)

    s = sp.add_parser("meeting", help="會議包")
    s.add_argument("--kind", default="會員大會", choices=["會員大會", "理事會", "監事會", "理監事聯席會議"])
    s.add_argument("--date", required=True)
    s.add_argument("--place")
    s.add_argument("--rows", type=int, default=32)
    s.add_argument("--out")
    s.set_defaults(func=cmd_meeting)

    s = sp.add_parser("journal", help="年度會刊")
    s.add_argument("--year", type=int, required=True, help="民國年，例：115")
    s.add_argument("--out")
    s.set_defaults(func=cmd_journal)

    a = p.parse_args()
    a.func(a)

if __name__ == "__main__":
    main()
