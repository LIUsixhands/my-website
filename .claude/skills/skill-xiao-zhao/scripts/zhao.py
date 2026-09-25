#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小招（Xiao Zhao）— 課程招生與開班行政專員　主程式
Sixhands Studio AI數字員工 / 行政部

子指令：
  init       產「開班基本資料卡」與 班務資料.json 範本
  plan       開班計畫表（含每班招生倒數）
  recruit    招生素材包（文案×3角度 / 貼文×5 / LINE話術 / 通路一頁紙 / 行前提醒）
  roster     現場行政包（名冊 / 簽到表 / 安全告知 / 肖像同意 / 工具清點）
  dashboard  各班招生進度與缺額告警（四級燈號）
  close      結案核銷包（憑證清冊 / 時數統計 / 成果報告草稿 / 退件自檢）
  scan       文案合規稽核（出門前必跑）

鐵律：簽到與人數等於現場真實發生；不代簽、不代填、不灌時數、不代送系統；
      文宣不寫保證就業與保證收入；「免費」的寫法必須等於真實金流。
"""
import argparse, base64, csv, datetime as dt, json, os, re, subprocess, sys, tempfile

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.join(SKILL_DIR, "assets", "logo.png")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BRAND = "Sixhands Studio AI數字員工"
CFG_PATH = "班務資料.json"
DISCLAIMER = ("本文件由「Sixhands Studio AI數字員工」AI 員工小招協助整理草擬，僅供單位內部作業參考。"
              "簽到、時數與人數一律以現場真實發生為準；期限、表格與補助規定以該補助案"
              "當年度作業要點及契約為準。正式送件、簽名、用印均由負責人確認後為之。")

# ------------------------------------------------------------------ 基礎

def TODO(label):
    return f'<span class="todo">【待補：{label}】</span>'

def load_cfg(path=CFG_PATH):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    print(f"⚠️  找不到 {path}，先用空白範本產出（欄位會印成【待補】）。", file=sys.stderr)
    print("    請先執行： python3 zhao.py init", file=sys.stderr)
    return {}

def g(cfg, dotted, label=None):
    cur = cfg
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur or cur[k] in ("", None, []):
            return TODO(label or dotted.split(".")[-1])
        cur = cur[k]
    return cur

def raw(cfg, dotted, default=None):
    cur = cfg
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur or cur[k] in ("", None, []):
            return default
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
thead { display: table-header-group; }
th,td { border:1px solid #999; padding:6px 7px; vertical-align:middle; }
th { background:#F2E4D8; font-weight:600; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.sign-row td { height:27px; }
table { page-break-inside:auto; }
tr { page-break-inside:avoid; }
.meta { width:100%; border:none; margin-bottom:10px; font-size:11pt; }
.meta td { border:none; padding:3px 0; }
.meta td:first-child { width:92px; color:#666; }
.todo { color:#B00020; font-weight:600; }
.warn { background:#FFF3F3; border-left:4px solid #B00020; padding:9px 12px; margin:10px 0;
        font-size:10.5pt; }
.note { background:#F7F4EF; border-left:4px solid #C8551B; padding:9px 12px; margin:10px 0;
        font-size:10.5pt; }
.copy { background:#FAFAF7; border:1px dashed #B4A48F; padding:11px 13px; margin:9px 0;
        font-size:10.5pt; white-space:pre-wrap; line-height:1.75; }
.foot { margin-top:22px; padding-top:8px; border-top:1px solid #ccc;
        font-size:8.5pt; color:#777; line-height:1.5; }
.pb { page-break-before:always; }
.warn,.note,.copy { page-break-inside:avoid; }
ol,ul { padding-left:22px; } li { margin:3px 0; }
.blank { border-bottom:1px solid #333; display:inline-block; min-width:110px; }
.g { color:#1B7F3B; font-weight:600; } .y { color:#B8860B; font-weight:600; }
.o { color:#D2691E; font-weight:600; } .r { color:#B00020; font-weight:600; }
"""

def html_doc(title, body, subtitle="", brand=True):
    lb = logo_b64()
    if brand:
        img = f'<img src="data:image/png;base64,{lb}">' if lb else f"<span>{BRAND}</span>"
        hdr = f'<div class="hdr"><div class="org">{BRAND}｜AI 員工 小招</div>{img}</div>'
        foot = f'<div class="foot">{DISCLAIMER}</div>'
    else:
        hdr, foot = "", ""
    sub = f'<div class="sub">{subtitle}</div>' if subtitle else ""
    return (f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
            f"<title>{title}</title><style>{CSS}</style></head><body>"
            f"{hdr}{sub}{body}{foot}</body></html>")

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
                   capture_output=True, timeout=180)
    os.unlink(tmp.name)
    if not os.path.exists(out_pdf):
        raise RuntimeError(f"PDF 產製失敗：{out_pdf}")
    print(f"  ✓ {out_pdf}")
    return out_pdf

def parse_date(s):
    for f in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(str(s).strip(), f).date()
        except ValueError:
            continue
    return None

def today():
    return dt.date.fromisoformat(os.environ.get("XIAOZHAO_TODAY", dt.date.today().isoformat()))

# ------------------------------------------------------------------ init

TEMPLATE = {
    "單位": {"名稱": "", "負責人": "", "統編": "", "電話": "", "LINE": "",
             "網站": "", "FB": "", "IG": "", "地址": ""},
    "補助": {"補助單位": "", "計畫名稱": "", "核定字號": "",
             "執行期間": {"起": "", "迄": ""}, "每人補助額": None,
             "金流模式": "",
             "_金流模式說明": "填『學員全程免費』或『學員先繳後退』——這決定文宣能不能寫「免費」",
             "核銷期限說明": "", "保存年限": ""},
    "課程": {"名稱": "原木手工筆體驗課", "時數": None, "堂數": None,
             "最低開班人數": None, "人數上限": None, "材料成本每人": None,
             "使用機具": [], "最低年齡": None},
    "班別": [{"編號": "B01", "日期": "", "時間": "",
              "場地": {"名稱": "", "地址": "", "聯絡人": "", "電話": ""},
              "講師": "", "助教": "", "報名數": 0, "實到數": None, "來源通路": "",
              "保險": {"公共意外": False, "學員平安": False},
              "狀態": "招生中",
              "_狀態選項": "招生中 / 已成班 / 已結課 / 已核銷 / 延期 / 取消"}],
    "通路": [{"名稱": "", "類型": "村里長", "聯絡人": "", "電話": "",
              "合作次數": 0, "帶來人數": 0, "備註": ""}],
    "展示紀錄": [{"場館": "", "日期": "", "停留人數": None, "留資數": None, "後續報名數": None}],
}

CARD_SECTIONS = [
    ("A. 單位身分", ["單位／工作室全名", "負責人姓名", "統一編號", "聯絡電話", "LINE ID",
                     "網站網址", "FB 粉專", "IG", "通訊地址"]),
    ("B. 補助案（🔴 最重要）", [
        "補助單位（哪個部會／地方政府）", "計畫名稱", "核定文號", "執行期間（起～迄）",
        "每人補助金額",
        "🔴 金流模式：學員全程免費？還是學員先繳費、補助下來再退？（這一題決定文宣能不能寫「免費」）",
        "核銷期限（結課後幾天內）", "文件保存年限"]),
    ("C. 課程規格", ["課程名稱", "一班幾小時", "幾堂課", "最低開班人數", "人數上限",
                     "每人材料成本", "使用哪些機具（車床／鑽床／刀具…）", "最低參加年齡"]),
    ("D. 場地與保險", ["常用場地有哪些（名稱＋地址＋聯絡人）", "公共意外責任險：有／無",
                       "學員團體平安險：有／無", "場地借用是否要付費"]),
    ("E. 招生現況", ["已開班次的學員從哪裡來（里長／協會／學校／臉書／舊生介紹…）",
                     "有沒有招不滿的班？怎麼處理", "展示在哪些場館、多久一次",
                     "展示現場目前有沒有留聯絡方式"]),
]

def cmd_init(a):
    if os.path.exists(CFG_PATH) and not a.force:
        print(f"⚠️  {CFG_PATH} 已存在，未覆寫（要重建請加 --force）。")
    else:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(TEMPLATE, f, ensure_ascii=False, indent=2)
        print(f"  ✓ {CFG_PATH}")

    rows = []
    for sec, items in CARD_SECTIONS:
        rows.append(f'<h2>{sec}</h2><table><tr><th style="width:56%">項目</th><th>填寫</th></tr>')
        for it in items:
            rows.append(f'<tr class="sign-row"><td>{it}</td><td></td></tr>')
        rows.append("</table>")
    body = ("<h1>開班基本資料卡</h1>"
            '<div class="sub">填一次，之後小招所有文件都自動帶入，不用再問</div>'
            '<div class="warn"><b>不知道的欄位請留空，不要猜。</b>'
            "留空會印成紅色【待補】，比填錯安全 —— 尤其是補助案的金額、期限與金流模式，"
            "填錯會直接影響核銷與文宣合法性。</div>" + "".join(rows) +
            '<div class="note">填完後把內容交給小招，小招會寫進 <code>班務資料.json</code>，'
            "之後 <code>plan／recruit／roster／dashboard／close</code> 全部自動帶入。</div>")
    write_pdf(html_doc("開班基本資料卡", body), a.out or "開班基本資料卡.pdf")

# ------------------------------------------------------------------ plan

def cmd_plan(a):
    cfg = load_cfg()
    classes = raw(cfg, "班別", []) or []
    td = today()
    rows = []
    for c in classes:
        d = parse_date(c.get("日期", ""))
        cd = f"{(d - td).days} 天" if d else TODO("日期")
        rows.append(
            "<tr>"
            f"<td>{c.get('編號') or TODO('編號')}</td>"
            f"<td>{c.get('日期') or TODO('日期')}<br><span style='color:#666'>{c.get('時間','')}</span></td>"
            f"<td>{(c.get('場地') or {}).get('名稱') or TODO('場地')}</td>"
            f"<td>{c.get('講師') or TODO('講師')}</td>"
            f"<td class='num'>{c.get('報名數', 0)}</td>"
            f"<td class='num'>{raw(cfg,'課程.最低開班人數') or TODO('最低人數')}</td>"
            f"<td>{cd}</td><td>{c.get('狀態','')}</td></tr>")
    if not rows:
        rows.append(f'<tr><td colspan="8">{TODO("尚未建立任何班別")}</td></tr>')

    body = (f"<h1>開班計畫表</h1>"
            f'<div class="sub">{g(cfg,"單位.名稱","單位名稱")}　製表日：{td}</div>'
            '<table><thead><tr><th>班別</th><th>日期時間</th><th>場地</th><th>講師</th>'
            '<th>報名</th><th>最低</th><th>倒數</th><th>狀態</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
            "<h2>每一班的固定節奏</h2>"
            "<table><thead><tr><th>時點</th><th>要做的事</th><th>指令</th></tr></thead><tbody>"
            "<tr><td>D-30</td><td>場地確認、通路開發、開始宣傳</td><td>recruit</td></tr>"
            "<tr><td>D-21</td><td>報名表上線、開始收單</td><td>roster</td></tr>"
            "<tr><td>D-14</td><td>缺額檢查（第一次）</td><td>dashboard</td></tr>"
            "<tr><td>D-7</td><td>缺額檢查（第二次）＋催單</td><td>dashboard / recruit</td></tr>"
            "<tr><td>D-3</td><td><b>開課／延期決策點</b></td><td>dashboard</td></tr>"
            "<tr><td>D-1</td><td>行前提醒（含安全與穿著）</td><td>recruit</td></tr>"
            "<tr><td>D-0</td><td>現場行政五件套</td><td>roster</td></tr>"
            "<tr><td>D+14</td><td>結案核銷</td><td>close</td></tr></tbody></table>"
            '<div class="warn">🔴 <b>免費課的報名數要打折看。</b>'
            "沒有累積出自己的真實報到率之前，一律以「報名數 × 0.7」估計實到人數。"
            "每班結束後把 <code>實到數</code> 回填進 <code>班務資料.json</code>，"
            "跑滿三班之後 dashboard 就會改用你自己的真實報到率。</div>")
    write_pdf(html_doc("開班計畫表", body), a.out or "開班計畫表.pdf")

    with open("開班計畫表.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["班別", "日期", "時間", "場地", "講師", "報名數", "實到數", "來源通路", "狀態"])
        for c in classes:
            w.writerow([c.get("編號", ""), c.get("日期", ""), c.get("時間", ""),
                        (c.get("場地") or {}).get("名稱", ""), c.get("講師", ""),
                        c.get("報名數", 0), c.get("實到數", ""), c.get("來源通路", ""),
                        c.get("狀態", "")])
    print("  ✓ 開班計畫表.csv")

# ------------------------------------------------------------------ recruit

def fee_line(cfg):
    """依金流模式產出合法的費用說明。沒填就印待補。"""
    mode = raw(cfg, "補助.金流模式", "")
    unit = raw(cfg, "補助.補助單位") or "【待補：補助單位】"
    if mode == "學員全程免費":
        return f"本課程由{unit}補助辦理，學員免費參加"
    if mode == "學員先繳後退":
        return f"本課程由{unit}補助辦理，報名時先繳【待補：金額】元，補助核撥後全額退還"
    return ('<span class="todo">【待補：費用說明 —— 必須先確認金流是「學員全程免費」'
            '還是「先繳後退」，兩者的合法寫法完全不同，未確認前不可寫「免費」】</span>')

def cmd_recruit(a):
    cfg = load_cfg()
    fee = fee_line(cfg)
    cls = None
    for c in raw(cfg, "班別", []) or []:
        if c.get("編號") == a.klass:
            cls = c
            break
    cls = cls or {}
    date = cls.get("日期") or TODO("日期")
    time = cls.get("時間") or TODO("時間")
    venue = (cls.get("場地") or {}).get("名稱") or TODO("場地名稱")
    addr = (cls.get("場地") or {}).get("地址") or TODO("場地地址")
    cap = raw(cfg, "課程.人數上限") or TODO("人數上限")
    link = raw(cfg, "單位.網站") or TODO("報名連結")
    hrs = raw(cfg, "課程.時數") or TODO("時數")

    def block(t):
        return f'<div class="copy">{t}</div>'

    a_copy = f"""一塊原木，{hrs} 小時，變成一支你自己的筆。

不是買的，是你自己車出來的。
木頭的紋路每一支都不一樣，所以你手上這支，全世界只有一支。

📅 {date} {time}
📍 {venue}（{addr}）
👥 限額 {cap} 人
💰 {fee}
🔗 報名：{link}"""

    b_copy = f"""找三個朋友，一起做一支筆。

我們這梯次就在 {venue}，走路就到。
不用會木工，不用自己帶工具，來就好。
做完直接帶回家，當天就能用。

三人以上一起報名，我們幫你們排在同一桌。
📅 {date} {time}｜👥 限額 {cap} 人
💰 {fee}
🔗 報名：{link}"""

    c_copy = f"""今年送什麼？送一支你自己做的筆。

刻上他的名字，木頭會愈用愈亮。
{hrs} 小時的課，換一個十年後還在他桌上的東西。

📅 {date} {time}｜📍 {venue}｜👥 限額 {cap} 人
💰 {fee}
🔗 報名：{link}"""

    posts = [
        ("D-30・成品特寫", "這支筆的木紋，是它自己長出來的。\n\n我們沒有畫上去，也沒有印上去，"
                           "那是這棵樹活著的時候留下的年輪。\n\n下一梯開課在 " + str(date) +
                           "，" + venue + "。\n" + fee),
        ("D-21・過程縮時", f"{hrs} 小時，從一塊方形木頭到這樣。\n\n很多人以為要學很久，"
                           "其實第一次來的人都做得出來 —— 因為機器我們架好、木料我們選好，"
                           "你只要負責把它變成你的。\n\n" + str(date) + "／" + venue),
        ("D-14・學員實拍", "（⚠️ 需真實個案並取得肖像同意書後才可發）\n\n"
                           "○○阿姨說她這輩子沒摸過車床。\n這是她的第一支筆。\n\n"
                           "下一梯 " + str(date) + "，" + venue + "。"),
        ("D-7・名額倒數", f"這梯次剩下【待補：真實剩餘名額】個位子。\n\n"
                          f"{date} {time}｜{venue}\n{fee}\n報名：{link}\n\n"
                          "（⚠️ 只寫真實剩餘數，不可寫「最後一名」催單）"),
        ("D-1・行前提醒", "明天見！三件事先講：\n\n"
                          "① 請穿包鞋，不要涼鞋拖鞋\n② 長頭髮請綁起來，不要戴垂下來的項鍊圍巾\n"
                          "③ 提早 10 分鐘到，我們要先講安全\n\n"
                          f"時間：{date} {time}\n地點：{venue}（{addr}）\n\n"
                          "臨時不能來請一定要跟我說，我把位子讓給候補的人 🙏"),
    ]
    post_html = "".join(f"<h3>{t}</h3>{block(c)}" for t, c in posts)

    channel = f"""里長好，我是做原木手工筆教學的{raw(cfg,'單位.負責人') or '【待補：姓名】'}。

我們這邊有{raw(cfg,'補助.補助單位') or '【待補：補助單位】'}的補助，可以在您這邊開一班，
居民不用花錢，{hrs} 小時做一支筆帶回家。

場地借用您這邊的活動中心就好，工具、材料、老師、保險我們全部帶過去，
場地我們也會清乾淨還給您。

您這邊大概能找到 {raw(cfg,'課程.最低開班人數') or '【待補：最低開班人數】'} 位以上的居民嗎？"""

    body = (f"<h1>招生素材包</h1>"
            f'<div class="sub">{g(cfg,"單位.名稱","單位名稱")}　'
            f'班別：{cls.get("編號") or TODO("班別編號")}　製作日：{today()}</div>'
            '<div class="warn">🔴 <b>出門前必跑合規檢查：</b>'
            "<code>python3 zhao.py scan 你的文案.txt</code>。<br>"
            "本包所有文案已避開保證性語句，但只要你手動改過一個字，就要重跑一次。</div>"
            "<h2>一、三個角度的主文案</h2>"
            f"<h3>角度 A：作品感（給第一次接觸的人）</h3>{block(a_copy)}"
            f"<h3>角度 B：揪團感（給社區、班群、退休族）</h3>{block(b_copy)}"
            f"<h3>角度 C：送禮感（教師節／母親節／退休禮／婚禮小物）</h3>{block(c_copy)}"
            f'<div class="pb"></div><h2>二、五則社群貼文（照時間軸發）</h2>{post_html}'
            f'<div class="pb"></div><h2>三、通路開發話術（打電話／拜訪用）</h2>{block(channel)}'
            '<div class="note"><b>為什麼這招有效：</b>對里長來說，這是一份'
            "「不用花錢的居民福利 ＋ 可以拍照的活動成果」，他有動機，而且他手上有現成的 LINE 群。"
            "<br><b>一個里長 ≒ 半班；一個社區發展協會 ≒ 一班。</b>"
            "這比投廣告有效，而且免費課的通路方會主動幫你發。</div>"
            "<h2>四、通路合作一頁紙（拜訪時留下）必含欄位</h2><ol>"
            "<li>我們是誰（含展示照片 2–3 張）</li>"
            "<li>學員會帶走什麼（成品照，這是最強的一格）</li>"
            "<li><b>你們要出什麼</b>：場地、人數、日期（寫愈具體愈好談）</li>"
            "<li><b>我們出什麼</b>：老師、工具、材料、保險、全部行政文件</li>"
            "<li>過去合作單位（真實的才寫）</li><li>聯絡方式</li></ol>"
            '<div class="warn">🚫 <b>禁用詞提醒：</b>保證學會／保證接單／學完就能賺／'
            "保證考取／政府認證／完全免費（若實際先繳後退）／最後一名（不實）／"
            "<b>預防失智</b>（長輩班最容易脫口而出，屬醫療效能宣稱，一律改成"
            "「動手動腦，很多長輩說做完很有成就感」）。</div>")
    write_pdf(html_doc("招生素材包", body), a.out or "招生素材包.pdf")

    dump = "\n\n".join([a_copy, b_copy, c_copy] + [c for _, c in posts] + [channel])
    dump = re.sub(r"<[^>]+>", "", dump)
    # 剝掉給你看的提醒行（以「（⚠️」開頭），否則 scan 會把提醒裡的禁用詞當成文案誤報
    dump = "\n".join(l for l in dump.split("\n") if not l.lstrip().startswith("（⚠️"))
    with open("招生文案.txt", "w", encoding="utf-8") as f:
        f.write(dump)
    print("  ✓ 招生文案.txt（可直接餵 scan 檢查）")

# ------------------------------------------------------------------ roster

def cmd_roster(a):
    cfg = load_cfg()
    cls = None
    for c in raw(cfg, "班別", []) or []:
        if c.get("編號") == a.klass:
            cls = c
            break
    cls = cls or {}
    cap = raw(cfg, "課程.人數上限") or 20
    try:
        n = int(cap)
    except (TypeError, ValueError):
        n = 20
    kid = cls.get("編號") or TODO("班別")
    date = cls.get("日期") or TODO("日期")
    venue = (cls.get("場地") or {}).get("名稱") or TODO("場地")
    hdr_meta = (f'<table class="meta"><tr><td>班別</td><td>{kid}</td></tr>'
                f"<tr><td>日期時間</td><td>{date} {cls.get('時間','')}</td></tr>"
                f"<tr><td>場地</td><td>{venue}</td></tr>"
                f"<tr><td>講師／助教</td><td>{cls.get('講師') or TODO('講師')}"
                f" ／ {cls.get('助教') or '—'}</td></tr></table>")

    def blank_rows(cols, cnt):
        return "".join("<tr class='sign-row'><td class='num'>%d</td>%s</tr>"
                       % (i + 1, "<td></td>" * (cols - 1)) for i in range(cnt))

    p1 = ("<h1>學員名冊</h1>" + hdr_meta +
          "<table><thead><tr><th style='width:34px'>#</th><th>姓名</th><th>手機／LINE</th>"
          "<th>居住區域</th><th>來源通路</th><th>補助資格文件<br>（已收請打勾）</th>"
          "<th>備註</th></tr></thead><tbody>" + blank_rows(7, n) + "</tbody></table>"
          '<div class="warn">個資最小蒐集：身分證影本等補助資格證明，'
          "<b>只在確定要送補助時才收</b>，收前須簽個資告知同意書，"
          "結案並屆滿保存年限後銷毀。名冊不可上傳到 LINE 群或公開雲端連結。</div>")

    p2 = ("<div class='pb'></div><h1>簽到表</h1>" + hdr_meta +
          '<div class="warn">🔴 <b>學員本人親簽。</b>不可代簽、不可預簽、不可事後補簽。'
          "簽到人數必須等於名冊人數、等於成果報告人數 —— 三個數字不一致是核銷退件第一名原因。</div>"
          "<table><thead><tr><th style='width:34px'>#</th><th style='width:22%'>姓名</th>"
          "<th>簽到（親簽）</th><th>到課時間</th><th>離場時間</th></tr></thead><tbody>" +
          blank_rows(5, n) + "</tbody></table>"
          "<table class='meta'><tr><td>應到人數</td><td><span class='blank'></span> 人　"
          "實到人數 <span class='blank'></span> 人</td></tr>"
          "<tr><td>講師簽名</td><td><span class='blank' style='min-width:220px'></span></td></tr></table>")

    machines = raw(cfg, "課程.使用機具", []) or []
    mtext = "、".join(machines) if machines else TODO("使用機具")
    age = raw(cfg, "課程.最低年齡") or TODO("最低年齡")
    p3 = ("<div class='pb'></div><h1>安全告知暨同意書</h1>" + hdr_meta +
          f"<h2>一、本課程使用之機具</h2><p>{mtext}</p>"
          "<h2>二、安全規定（請務必遵守）</h2><ol>"
          "<li>請穿<b>包鞋</b>，不可穿涼鞋、拖鞋。</li>"
          "<li>長髮請<b>束起</b>；不可配戴垂掛式項鍊、圍巾、手鍊，不可穿寬袖衣物。</li>"
          "<li>操作機具時<b>全程配戴護目鏡</b>。</li>"
          f"<li>未滿 {age} 歲須由家長或監護人<b>全程陪同</b>。</li>"
          "<li>身體不適、飲酒、服用可能造成嗜睡之藥物者，<b>不得操作機具</b>，請告知講師改採替代方式參與。</li>"
          "<li>未經講師指示，不得自行啟動或調整任何機具。</li>"
          "<li>如發生任何不適或受傷，請<b>立即停止操作並告知講師</b>。</li></ol>"
          "<h2>三、緊急資訊</h2><table class='meta'>"
          f"<tr><td>急救箱位置</td><td>{TODO('急救箱位置')}</td></tr>"
          f"<tr><td>最近醫療院所</td><td>{TODO('最近醫院名稱與地址')}</td></tr>"
          f"<tr><td>現場負責人／電話</td><td>{TODO('現場負責人與電話')}</td></tr></table>"
          "<h2>四、學員簽署</h2>"
          "<p>本人已閱讀並瞭解上述安全規定，同意於課程期間確實遵守，"
          "並已據實告知自身健康狀況。</p>"
          "<table><thead><tr><th style='width:34px'>#</th><th style='width:26%'>姓名</th>"
          "<th>簽名</th><th>緊急聯絡人／電話</th></tr></thead><tbody>" +
          blank_rows(4, n) + "</tbody></table>")

    p4 = ("<div class='pb'></div><h1>肖像權使用同意書</h1>" + hdr_meta +
          "<p>本課程將於上課期間拍攝照片，用途如下。請於您<b>同意的範圍</b>打勾，"
          "未勾選者視為僅同意最低必要之用途（核銷結案）。您可隨時以書面撤回同意。</p>"
          '<div class="warn">未成年學員由法定代理人簽署。'
          "<b>AI 生成的人像永遠不可以當成上課花絮照</b> —— "
          "這同時構成核銷不實與廣告不實。</div>"
          "<table><thead><tr><th style='width:34px'>#</th><th style='width:20%'>姓名</th>"
          "<th>□ 僅供補助<br>核銷結案</th><th>□ 可用於招生<br>宣傳／社群</th>"
          "<th>□ 僅可用背影<br>或手部特寫</th><th>簽名</th></tr></thead><tbody>" +
          blank_rows(6, n) + "</tbody></table>")

    p5 = ("<div class='pb'></div><h1>教材與工具清點表</h1>" + hdr_meta +
          "<table><thead><tr><th>品項</th><th>課前數量</th><th>課後數量</th>"
          "<th>差異</th><th>備註</th></tr></thead><tbody>" +
          "".join("<tr class='sign-row'><td></td><td></td><td></td><td></td><td></td></tr>"
                  for _ in range(14)) + "</tbody></table>"
          '<div class="warn">🔴 <b>刀具類必須逐把清點</b>，課前課後數量不符不可離場。</div>'
          "<h2>場地還原檢核</h2><ul>"
          "<li>□ 木屑清理完畢（含機具下方與角落）</li><li>□ 機具斷電、收納歸位</li>"
          "<li>□ 桌椅復位</li><li>□ 垃圾帶走</li><li>□ 場地方點交簽名：<span class='blank'></span></li></ul>")

    write_pdf(html_doc("現場行政包", p1 + p2 + p3 + p4 + p5), a.out or f"現場行政包_{a.klass}.pdf")

# ------------------------------------------------------------------ dashboard

def show_rate(cfg):
    """有三班以上實到資料就用真實報到率，否則用 0.7。"""
    pairs = [(c.get("報名數"), c.get("實到數")) for c in (raw(cfg, "班別", []) or [])]
    pairs = [(r, s) for r, s in pairs if isinstance(r, int) and isinstance(s, int) and r > 0]
    if len(pairs) >= 3:
        return sum(s for _, s in pairs) / sum(r for r, _ in pairs), True
    return 0.7, False

def judge(reg, est, lo, hi, days):
    """燈號同時看『差多少人』與『還剩幾天』——離開課還久的班不該被喊延期。"""
    if lo is None:
        return "—", "無法判定（請先填最低開班人數）"
    if hi and reg >= hi:
        return "🟢 滿班", "開候補名單，考慮加開一梯"
    if est >= lo * 1.2:
        return "🟢 安全", "照常開，發行前通知"
    if est >= lo:
        return "🟡 剛好", "催單＋行前提醒（剛好等於不夠，免費課會 no-show）"

    # 以下都是「估計人數不足」，接下來看還剩幾天
    gap = f"還差約 {max(1, round(lo - est))} 人"
    if days is None:
        return "🟡 缺額", f"{gap}；請先補上開課日期才能判斷急迫性"
    if days > 14:
        return "🟡 缺額", f"{gap}，但還有 {days} 天 —— 現在是通路開發期，不是延期期"
    if days > 7:
        return "🟠 危險", f"{gap}；通路加壓（里長／協會一通電話勝過十則貼文）"
    if days > 3:
        return "🟠 危險", f"{gap}；催單＋考慮與鄰近梯次併班，D-3 前要決定"
    if est >= lo * 0.6:
        return "🔴 決策點", f"{gap}；今天就要決定開或延，拖到當天取消傷害最大"
    return "🔴 建議延期", f"{gap}；提前通知比當天取消傷害小很多"

def cmd_dashboard(a):
    cfg = load_cfg()
    td = today()
    rate, real = show_rate(cfg)
    lo = raw(cfg, "課程.最低開班人數")
    hi = raw(cfg, "課程.人數上限")
    rows, lines = [], []
    for c in raw(cfg, "班別", []) or []:
        if c.get("狀態") in ("已結課", "已核銷", "取消"):
            continue
        reg = c.get("報名數", 0) or 0
        est = reg * rate
        d = parse_date(c.get("日期", ""))
        days = (d - td).days if d else None
        light, action = judge(reg, est, lo, hi, days)
        cd = f"{days} 天" if days is not None else "【待補】"
        cls_map = {"🟢": "g", "🟡": "y", "🟠": "o", "🔴": "r"}
        css = cls_map.get(light[0], "")
        rows.append(f"<tr><td>{c.get('編號','')}</td><td>{c.get('日期') or TODO('日期')}</td>"
                    f"<td>{cd}</td><td class='num'>{reg}</td><td class='num'>{est:.0f}</td>"
                    f"<td class='num'>{lo if lo else TODO('最低')}</td>"
                    f"<td class='{css}'>{light}</td><td>{action}</td></tr>")
        lines.append(f"{c.get('編號',''):>4}  {c.get('日期','?'):>10}  倒數{cd:>6}  "
                     f"報名{reg:>3}  估到{est:>5.0f}  {light}  {action}")

    note = (f"報到率採用<b>你自己的真實數據 {rate:.0%}</b>（已累積三班以上）"
            if real else
            "報到率採用<b>預設 0.7</b> —— 每班結束後把 <code>實到數</code> 回填進 "
            "<code>班務資料.json</code>，累積三班後會自動換成你自己的真實報到率。")
    body = (f"<h1>招生進度與缺額告警</h1>"
            f'<div class="sub">{g(cfg,"單位.名稱","單位名稱")}　基準日：{td}</div>'
            "<table><thead><tr><th>班別</th><th>開課日</th><th>倒數</th><th>報名</th>"
            "<th>估計實到</th><th>最低</th><th>燈號</th><th>建議動作</th></tr></thead>"
            f'<tbody>{"".join(rows) or "<tr><td colspan=8>目前沒有招生中的班別</td></tr>"}</tbody></table>'
            f'<div class="note">{note}</div>'
            '<div class="warn">🔴 <b>D-3 是開課／延期的決策點。</b>'
            "撐到當天才取消，會同時得罪學員、場地方與通路方，"
            "而且下一次那個里長不會再幫你發。</div>")
    write_pdf(html_doc("招生進度與缺額告警", body), a.out or "招生進度告警.pdf")

    print(f"\n  基準日 {td}｜報到率 {rate:.0%}" + ("（真實）" if real else "（預設）"))
    print("  " + "-" * 76)
    for l in lines:
        print("  " + l)
    if not lines:
        print("  目前沒有招生中的班別")
    print()

# ------------------------------------------------------------------ close

RETURN_RISKS = [
    ("憑證抬頭／統編錯誤", "開錯抬頭幾乎必退，且事後極難重開。收到憑證當下就核對。"),
    ("簽到人數 ≠ 名冊人數 ≠ 成果報告人數", "三個數字必須完全一致，這是退件第一名。"),
    ("日期矛盾", "憑證日期早於核定日、或落在計畫執行期間之外。"),
    ("照片無法佐證", "沒拍到簽到情形／沒有現場全景／看不出日期與地點。"),
]

def cmd_close(a):
    cfg = load_cfg()
    cls = None
    for c in raw(cfg, "班別", []) or []:
        if c.get("編號") == a.klass:
            cls = c
            break
    cls = cls or {}
    reg, act = cls.get("報名數", 0), cls.get("實到數")
    hrs = raw(cfg, "課程.時數")
    total_hr = (f"{act} 人 × {hrs} 小時 = {act * hrs} 人時"
                if isinstance(act, int) and isinstance(hrs, (int, float))
                else TODO("實到人數 × 時數"))

    risk = "".join(f"<tr><td>□</td><td><b>{t}</b></td><td>{d}</td></tr>" for t, d in RETURN_RISKS)
    body = (f"<h1>結案核銷包</h1>"
            f'<div class="sub">{g(cfg,"單位.名稱","單位名稱")}　'
            f'班別：{cls.get("編號") or TODO("班別")}　製作日：{today()}</div>'
            "<h2>一、班次結果</h2><table class='meta'>"
            f"<tr><td>開課日期</td><td>{cls.get('日期') or TODO('日期')}</td></tr>"
            f"<tr><td>場地</td><td>{(cls.get('場地') or {}).get('名稱') or TODO('場地')}</td></tr>"
            f"<tr><td>報名人數</td><td>{reg} 人</td></tr>"
            f"<tr><td>實到人數</td><td>{act if act is not None else TODO('實到人數')} 人</td></tr>"
            f"<tr><td>總授課人時</td><td>{total_hr}</td></tr>"
            f"<tr><td>來源通路</td><td>{cls.get('來源通路') or TODO('來源通路')}</td></tr></table>"
            '<div class="warn">🔴 <b>人數與時數一律等於現場真實發生。</b>'
            "沒到的人不列入成果、實際 2 小時不報 3 小時 —— "
            "這兩件事做了會被追繳並移送，無法用行政疏失解釋。</div>"
            "<h2>二、核銷文件檢核</h2><ul>"
            "<li>□ 成果報告（課程內容、時數、人數、照片）</li>"
            "<li>□ 簽到表正本（學員親簽）</li><li>□ 學員名冊（含補助資格證明）</li>"
            "<li>□ 經費支出憑證清冊</li><li>□ 原始憑證（抬頭統編正確）</li>"
            "<li>□ 照片（現場全景／上課過程／成品／簽到情形）</li>"
            "<li>□ 學員回饋表統計</li></ul>"
            "<h2>三、🔴 四種最常見退件原因（逐項打勾才送）</h2>"
            "<table><thead><tr><th style='width:34px'>✓</th><th style='width:38%'>風險</th>"
            f"<th>為什麼</th></tr></thead><tbody>{risk}</tbody></table>"
            '<div class="note">補助單位不是在刁難，是他們自己也要被審計。'
            "把這四項在<b>上課當天</b>就處理掉，核銷會從三天變成三十分鐘。</div>"
            "<div class='pb'></div><h2>四、成果報告草稿（請就實際情形增修）</h2>"
            f'<div class="copy">一、辦理依據：{raw(cfg,"補助.計畫名稱") or "【待補：計畫名稱】"}'
            f'（{raw(cfg,"補助.核定字號") or "【待補：核定字號】"}）\n\n'
            f'二、辦理時間：{cls.get("日期") or "【待補：日期】"} {cls.get("時間","")}\n\n'
            f'三、辦理地點：{(cls.get("場地") or {}).get("名稱") or "【待補：場地】"}\n\n'
            f'四、參加人數：{act if act is not None else "【待補】"} 人（實際到課）\n\n'
            f'五、課程內容：{raw(cfg,"課程.名稱") or "【待補】"}，'
            f'共 {hrs if hrs else "【待補】"} 小時。\n'
            "　　（此處請寫實際教了什麼、學員完成了什麼作品）\n\n"
            "六、辦理成效：【待補：請就實際情形填寫，不可套用制式讚美詞】\n\n"
            "七、檢討與建議：【待補】\n\n"
            "八、附件：簽到表、學員名冊、活動照片、支出憑證清冊</div>"
            "<h2>五、這一班要留下的四樣資產（最容易被忽略）</h2><ol>"
            "<li><b>成品照片</b>：挑 3 張最好的存進素材庫（這是下一班最強的招生素材）</li>"
            "<li><b>學員金句</b>：回饋表裡的一兩句真心話（經同意後可引用）</li>"
            "<li><b>通路來源</b>：這班的人從哪來 → 回填 <code>班務資料.json</code> 的通路帶來人數</li>"
            "<li><b>真實報到率</b>：回填 <code>實到數</code> → dashboard 的判斷才會準</li></ol>")
    write_pdf(html_doc("結案核銷包", body), a.out or f"結案核銷包_{a.klass}.pdf")

    with open(f"憑證清冊_{a.klass}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["序號", "憑證日期", "憑證號碼", "品名", "廠商", "抬頭是否正確",
                    "統編是否正確", "金額", "科目", "備註"])
    print(f"  ✓ 憑證清冊_{a.klass}.csv（空白表，金額請照原始憑證填，小招不代填）")

# ------------------------------------------------------------------ scan

RED = [
    (r"保證(學會|學得會|上手|接單|考|取得|過)|包會|包過|一定學得會", "效果／考照保證（公平法 §21）",
     "改寫成「課程結束可完成一支自己的作品」"),
    (r"學完就能賺|保證收入|月入|穩賺|躺著賺|輕鬆賺|包賺", "收入保證",
     "不提收入；真實個案須本人同意並註明為個案"),
    (r"政府認證|官方指定|教育部認證|國家認證師資", "冒用公權力背書",
     "改寫成「本課程由○○補助辦理」"),
    (r"預防失智|治療|療效|改善失眠|抗憂鬱|復健效果|醫療級", "醫療效能宣稱（醫療法概念）",
     "改寫成「動手動腦，很多長輩說做完很有成就感」"),
    (r"最後(一|1)(名|個|位)|僅剩(一|1)(名|個|位)", "不實稀缺促銷",
     "只寫真實剩餘名額"),
    (r"外面(都)?教錯|比.{0,6}老師教得好|同業.{0,4}(不專業|亂教)", "貶損同業（公平法 §24）",
     "不提同業"),
]
YELLOW = [
    (r"免費|不用錢|0 ?元|零元", "「免費」用詞",
     "必須等於真實金流：學員全程免費才可寫「免費」；先繳後退必須寫「先繳 $X，補助核撥後全額退還」"),
    (r"學員|阿姨|大哥|大姐|先生|小姐", "疑似引用學員個案",
     "須為真實個案且已取得肖像／引用同意書；照片不可用 AI 生成"),
    (r"名額|剩下|限額", "名額數字",
     "確認是真實剩餘數"),
    (r"【待補", "文案中仍有待補欄位", "上線前必須全部填完"),
]

def cmd_scan(a):
    text = open(a.file, encoding="utf-8").read()
    red = []
    for pat, why, fix in RED:
        for m in re.finditer(pat, text):
            red.append((m.group(0), why, fix))
    yellow = []
    for pat, why, fix in YELLOW:
        seen = set()
        for m in re.finditer(pat, text):
            if m.group(0) in seen:
                continue
            seen.add(m.group(0))
            yellow.append((m.group(0), why, fix))

    print(f"\n  📋 合規稽核：{a.file}")
    print("  " + "=" * 74)
    if red:
        print(f"\n  🔴 紅字 {len(red)} 處 —— 必改，不改不准交付\n")
        for hit, why, fix in red:
            print(f"     「{hit}」\n       原因：{why}\n       改成：{fix}\n")
    if yellow:
        print(f"  🟡 黃字 {len(yellow)} 處 —— 需要你確認事實\n")
        for hit, why, fix in yellow:
            print(f"     「{hit}」\n       檢查：{why}\n       規則：{fix}\n")
    if not red and not yellow:
        print("\n  🟢 通過，沒有發現紅字或需確認項目。\n")
    elif not red:
        print("  🟢 沒有紅字。黃字項目請自行確認事實後即可出門。\n")
    print("  " + "=" * 74)
    print("  ⚠️  scan 是機械比對，不能取代人看一遍。"
          "特別是「免費」的寫法，必須跟真實金流一模一樣。\n")
    return 1 if red else 0

# ------------------------------------------------------------------ main

def main():
    p = argparse.ArgumentParser(description="小招 — 課程招生與開班行政專員")
    sp = p.add_subparsers(dest="cmd", required=True)

    q = sp.add_parser("init", help="產基本資料卡與 班務資料.json")
    q.add_argument("--force", action="store_true"); q.add_argument("--out")
    q.set_defaults(func=cmd_init)

    q = sp.add_parser("plan", help="開班計畫表")
    q.add_argument("--out"); q.set_defaults(func=cmd_plan)

    q = sp.add_parser("recruit", help="招生素材包")
    q.add_argument("klass", nargs="?", default="B01", help="班別編號，例 B01")
    q.add_argument("--out"); q.set_defaults(func=cmd_recruit)

    q = sp.add_parser("roster", help="現場行政包")
    q.add_argument("klass", nargs="?", default="B01")
    q.add_argument("--out"); q.set_defaults(func=cmd_roster)

    q = sp.add_parser("dashboard", help="招生進度與缺額告警")
    q.add_argument("--out"); q.set_defaults(func=cmd_dashboard)

    q = sp.add_parser("close", help="結案核銷包")
    q.add_argument("klass", nargs="?", default="B01")
    q.add_argument("--out"); q.set_defaults(func=cmd_close)

    q = sp.add_parser("scan", help="文案合規稽核")
    q.add_argument("file"); q.set_defaults(func=cmd_scan)

    a = p.parse_args()
    sys.exit(a.func(a) or 0)

if __name__ == "__main__":
    main()
