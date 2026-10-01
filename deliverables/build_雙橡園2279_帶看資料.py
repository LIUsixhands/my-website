#!/usr/bin/env python3
"""雙橡園2279 買方帶看資料（銷售報告書版型：暖金＋奶油白）。
數字來源：.claude/skills/skill-xiao-deng/references/七期外·相鄰大樓行情.md 雙橡園2279 卡片
（實價登錄撈取日 2026-10-01）。改數字請先改行情卡，再回來改這裡。"""
import tempfile
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent
NAME = "雙橡園2279_帶看資料"
# 聯絡人與電話不寫進 repo（整個 repo 會被 Netlify 公開），執行時用環境變數帶入：
#   CONTACT_NAME=助哥 CONTACT_TEL=09xx-xxx-xxx python3 build_雙橡園2279_帶看資料.py
# 沒帶就不印聯絡區塊。產出的 PDF 已列入 .gitignore，只用 LINE 傳給買方。
CONTACT_NAME = os.environ.get("CONTACT_NAME", "")
CONTACT_TEL = os.environ.get("CONTACT_TEL", "")
CONTACT = f"{CONTACT_NAME}　{CONTACT_TEL}".strip("　")
FOOT = "永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號"

# 歷年不含車位中位（萬/坪）
TREND = [("110年 預售", 54.10, 123), ("111年 預售", 65.55, 26),
         ("112年 預售", 71.13, 2), ("113–114年 交屋後", 80.46, 4)]
# 近三年有效成交
DEALS = [("113/09/09", "21F", 63.17, 4725, "2／660萬", 74.80, 80.38, "3房", "交屋登記"),
         ("113/09/09", "22F", 79.16, 6060, "2／660萬", 76.55, 81.13, "3房", "交屋登記"),
         ("113/09/09", "22F", 63.20, 4855, "2／780萬", 76.82, 80.53, "3房", "交屋登記"),
         ("114/05/25", "9F", 79.25, 5800, "2／580萬", 73.19, 78.32, "4房", "轉售")]
FLOORS = [("2–10F", 40, 51.31), ("11–20F", 42, 54.06), ("21–30F", 38, 59.69), ("31–33F", 3, 60.58)]


def bars(data, vmax, w=600, h=230, color="#B08A4A", hi=None):
    n = len(data); bw = w / n * 0.52; gap = w / n
    out = [f'<svg viewBox="0 0 {w} {h+46}" width="100%">']
    out.append(f'<line x1="0" y1="{h}" x2="{w}" y2="{h}" stroke="#cdbb98" stroke-width="1"/>')
    for i, (lab, v, n_) in enumerate(data):
        bh = v / vmax * (h - 30); x = i * gap + (gap - bw) / 2
        c = "#7A5520" if i == hi else color
        out.append(f'<rect x="{x:.1f}" y="{h-bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{c}"/>')
        out.append(f'<text x="{x+bw/2:.1f}" y="{h-bh-8:.1f}" text-anchor="middle" font-size="17" font-weight="700" fill="#3A2E1C">{v:.2f}</text>')
        out.append(f'<text x="{x+bw/2:.1f}" y="{h+20}" text-anchor="middle" font-size="13" fill="#3A2E1C">{lab}</text>')
        out.append(f'<text x="{x+bw/2:.1f}" y="{h+38}" text-anchor="middle" font-size="11" fill="#8a7a5e">n={n_}</text>')
    out.append("</svg>")
    return "".join(out)


deal_rows = "".join(
    f"<tr><td>{d}</td><td>{f}</td><td>{a:.2f}</td><td>{p:,}</td><td>{c}</td><td>{u1:.2f}</td>"
    f"<td class='b'>{u2:.2f}</td><td>{r}</td><td>{k}</td></tr>" for d, f, a, p, c, u1, u2, r, k in DEALS)
# 市場在售（公開刊登平台，擷取 2026-10-01）：開價不是成交價。
# 單價＝開價÷權狀總坪數（含車位），與實登「含車位」口徑同。只標號別與樓層，不列戶別門牌。
LISTINGS = [  # (樓層, 號別, 開價萬, 權狀坪, 主建物坪, 格局, 刊登日, 平台)
    ("3F", "1號", 4468, 63.16, 27.68, "開放式格局", "2026-09-01", "591"),
    ("4F", "1號", 4318, 63.20, 27.69, "開放式格局", "2026-09-29", "591"),
    ("4F", "3號", 4818, 70.39, 32.87, "3房2廳2衛", "2026-09-17", "591"),
    ("6F", "1號", 4300, 63.20, 27.69, "3房2廳2衛", "2026-09-24", "樂屋"),
    ("26F", "3號", 5638, 70.54, 33.10, "3房2廳2衛", "2026-09-12", "591"),
    ("28F", "3號", 5638, 70.39, 32.87, "3房2廳2衛", "2026-08-14", "591"),
]
list_rows = "".join(
    f"<tr><td>{f}</td><td>{h}</td><td>{p:,}</td><td>{a:.2f}</td><td>{m:.2f}</td>"
    f"<td class='b'>{p/a:.2f}</td><td>{g}</td><td>{d}</td><td>{src}</td></tr>"
    for f, h, p, a, m, g, d, src in LISTINGS)
floor_rows = "".join(f"<tr><td>{b}</td><td>{n}</td><td class='b'>{v:.2f}</td></tr>" for b, n, v in FLOORS)

CSS = """
@page{size:A4;margin:0}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Noto Sans CJK TC",sans-serif;color:#2b2419;font-size:10.5pt;line-height:1.6;
 -webkit-print-color-adjust:exact;print-color-adjust:exact}
h1,h2,.serif{font-family:"Noto Serif CJK TC",serif}
.page{width:210mm;height:297mm;padding:18mm 17mm 20mm;background:#FBF6EC;position:relative;overflow:hidden;page-break-after:always}
.page:last-child{page-break-after:auto}
.foot{position:absolute;left:17mm;right:17mm;bottom:8mm;border-top:1px solid #d9c8a4;padding-top:2mm;
 font-size:7.5pt;color:#7a6a4e;display:flex;justify-content:space-between}
h2{font-size:17pt;color:#3A2E1C;border-left:5px solid #B08A4A;padding-left:4mm;margin-bottom:5mm}
h3{font-size:11.5pt;color:#7A5520;margin:5mm 0 2mm}
p{margin-bottom:2.5mm}
table{width:100%;border-collapse:collapse;font-size:9.5pt;margin:1mm 0 3mm}
th{background:#B08A4A;color:#fff;font-weight:700;padding:1.8mm 1.5mm}
td{padding:1.6mm 1.5mm;border-bottom:1px solid #e6d9bd;text-align:center}
td.l{text-align:left}
td.b{font-weight:700;color:#7A5520}
.note{font-size:8.5pt;color:#6b5c42}
.box{background:#F3E8D2;border-left:4px solid #B08A4A;padding:3.5mm 4.5mm;margin:3mm 0;font-size:10pt}
.warn{background:#FFF;border:1px solid #d9c8a4;padding:3.5mm 4.5mm;margin:3mm 0;font-size:9.5pt}
/* cover */
.cover{background:#3A2E1C;color:#FBF6EC;padding:0}
.cover .top{padding:30mm 20mm 0}
.cover .tag{letter-spacing:.3em;font-size:10pt;color:#D9B878}
.cover h1{font-size:40pt;line-height:1.2;margin:6mm 0 3mm;color:#fff}
.cover .sub{font-size:13pt;color:#E8D9B8}
.cover .gold{height:2px;background:#B08A4A;margin:12mm 20mm}
.kpis{display:grid;grid-template-columns:1fr 1fr;gap:6mm;padding:0 20mm}
.kpi{border:1px solid #6b5a3c;padding:5mm 6mm}
.kpi .v{font-family:"Noto Serif CJK TC",serif;font-size:24pt;color:#D9B878;font-weight:700;line-height:1.15}
.kpi .k{font-size:9.5pt;color:#E8D9B8}
.kpi .s{font-size:8pt;color:#b5a382;margin-top:1mm}
.concl{margin:12mm 20mm 0;font-size:11.5pt;line-height:1.8;color:#FBF6EC}
.concl b{color:#D9B878}
.cover .foot{color:#b5a382;border-color:#6b5a3c}
.cover .contact{position:absolute;left:20mm;right:20mm;bottom:22mm;border:1px solid #B08A4A;padding:4mm 6mm;
 display:flex;justify-content:space-between;align-items:center}
.cover .contact .n{font-size:10pt;color:#E8D9B8}
.cover .contact .t{font-family:"Noto Serif CJK TC",serif;font-size:20pt;font-weight:700;color:#D9B878;letter-spacing:.04em}
.card{position:absolute;left:17mm;bottom:30mm;width:105mm;background:#3A2E1C;color:#FBF6EC;padding:4mm 6mm}
.card .n{font-size:9.5pt;color:#E8D9B8}
.card .t{font-family:"Noto Serif CJK TC",serif;font-size:18pt;font-weight:700;color:#D9B878;letter-spacing:.04em}
.spec td:first-child{width:24%;text-align:left;font-weight:700;color:#7A5520}
.spec td{text-align:left}
.spec td:last-child{width:19%;font-size:8pt;color:#8a7a5e}
.fill td{height:10mm;text-align:left}
.fill td:first-child{width:42%;font-weight:700;color:#7A5520}
.seal{position:absolute;right:22mm;bottom:28mm;width:34mm;height:34mm;border:2.5px solid #B22222;border-radius:50%;
 color:#B22222;display:flex;align-items:center;justify-content:center;text-align:center;font-family:"Noto Serif CJK TC",serif;
 font-size:9.5pt;font-weight:700;line-height:1.35;transform:rotate(-12deg);opacity:.85}
"""

def foot(n): return f'<div class="foot"><span>{FOOT}</span><span>{CONTACT_NAME} {CONTACT_TEL}　{n} / 5</span></div>'

HTML = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>雙橡園2279 帶看資料</title>
<style>{CSS}</style></head><body>

<div class="page cover">
 <div class="top">
  <div class="tag">BUYER BRIEF・帶看資料</div>
  <h1>雙橡園 2279</h1>
  <div class="sub">台中市西屯區・單元二重劃區｜33 層・180 戶・SRC</div>
 </div>
 <div class="gold"></div>
 <div class="kpis">
  <div class="kpi"><div class="v">80.46<span style="font-size:12pt"> 萬/坪</span></div><div class="k">近三年成交中位・不含車位</div><div class="s">民國 113–114 年，n=4，區間 78.32–81.13</div></div>
  <div class="kpi"><div class="v">75.68<span style="font-size:12pt"> 萬/坪</span></div><div class="k">同樣本・含車位口徑</div><div class="s">591／樂居常見口徑，兩者差 6.3%</div></div>
  <div class="kpi"><div class="v">113/08</div><div class="k">建築完成</div><div class="s">實價登錄建物分頁</div></div>
  <div class="kpi"><div class="v">2.02<span style="font-size:12pt"> 車/戶</span></div><div class="k">車位 364 個 ÷ 180 戶</div><div class="s">推估值；車位均為坡道平面</div></div>
 </div>
 <div class="concl">
  看雙橡園的行情，先看<b>成交年份</b>。<br>
  實價登錄裡大部分是 110–111 年的<b>預售期成交</b>，中位約 57 萬／坪；
  交屋後（113 年起）的成交落在 <b>78–81 萬／坪</b>（不含車位）。<br>
  不同期別的價格不能直接相比，本資料把兩者分開呈現。
 </div>
 {f'<div class="contact"><div class="n">帶看與諮詢・永慶不動產 七期河南市政店</div><div class="t">{CONTACT}</div></div>' if CONTACT else ''}
 {foot(1)}
</div>

<div class="page">
 <h2>物件概要</h2>
 <p>雙橡園2279 位於西屯區馬龍潭路，屬單元二重劃區。基地約 2,278 坪，只蓋一棟 33 層的建築，
 全案 180 戶，以 3 房、4 房的大坪數格局為主。結構採 SRC（鋼骨鋼筋混凝土造），113 年 8 月完工。
 全案車位 364 個，平均每戶約 2 個，全部是坡道平面車位，沒有機械車位。</p>

 <h3>硬體規格</h3>
 <table class="spec">
  <tr><th style="text-align:left">項目</th><th style="text-align:left">內容</th><th style="text-align:left">來源</th></tr>
  <tr><td>地址</td><td>台中市西屯區馬龍潭路 1 號</td><td>實價登錄</td></tr>
  <tr><td>土地使用分區</td><td>第一之C種住宅區</td><td>實價登錄土地分頁</td></tr>
  <tr><td>規模</td><td>單棟 33 層／180 戶</td><td>樂居</td></tr>
  <tr><td>基地面積</td><td>約 2,278 坪</td><td>樂居</td></tr>
  <tr><td>結構</td><td>SRC 鋼骨鋼筋混凝土造</td><td>樂居、實價登錄</td></tr>
  <tr><td>建築完成</td><td>民國 113 年 8 月</td><td>實價登錄</td></tr>
  <tr><td>車位</td><td>364 個，坡道平面，每個約 6.31 坪</td><td>樂居、實價登錄</td></tr>
  <tr><td>防水建材</td><td>DAISIN 大信防水</td><td>樂居</td></tr>
  <tr><td>建設／營造</td><td>特區開發建設／全品營造工程</td><td>樂居</td></tr>
  <tr><td>建築設計</td><td>許獻叡建築師事務所</td><td>樂居</td></tr>
  <tr><td>學區</td><td>黎明國小、黎明國中</td><td>樂居（以教育局當年公告為準）</td></tr>
 </table>

 <h3>格局分布（預售期實價登錄）</h3>
 <table>
  <tr><th>格局</th><th>筆數</th><th>占比</th></tr>
  <tr><td>3 房 2 廳 2 衛</td><td>101</td><td>66.9%</td></tr>
  <tr><td>4 房 2 廳 2 衛</td><td>47</td><td>31.1%</td></tr>
  <tr><td>3 房 2 廳 3 衛</td><td>3</td><td>2.0%</td></tr>
 </table>
 <p class="note">預售期成交坪數：50–65 坪 53 筆（中位 63.20 坪）、65–80 坪 98 筆（中位 70.65 坪）。
 坪數為權狀總面積，含車位。</p>
 {foot(2)}
</div>

<div class="page">
 <h2>成交行情</h2>
 <h3>近三年有效成交（民國 113–115 年）</h3>
 <table>
  <tr><th>交易日</th><th>樓層</th><th>總面積<br>(坪)</th><th>總價<br>(萬)</th><th>車位<br>數／價</th><th>含車位<br>單價</th><th>不含車位<br>單價</th><th>格局</th><th>性質</th></tr>
  {deal_rows}
 </table>
 <p class="note">單價單位：萬元／坪。不含車位單價＝（總價－車位價）÷（總面積－車位面積），逐筆計算。
 已排除特殊關係交易 2 筆、基地原有透天 1 筆。</p>

 <h3>歷年成交中位（不含車位，萬元／坪）</h3>
 {bars(TREND, 90, hi=3)}
 <p class="note">110–112 年為預售期成交（實價登錄預售檔），113–114 年為交屋後成交（買賣檔）。
 預售價與交屋後成交價性質不同，價差不全是市場變動。</p>

 <div class="box"><b>為什麼網路上看到的單價不一樣？</b><br>
 ① <b>期別</b>：實價登錄買賣檔 89 筆中，82 筆是 110–111 年的預售期成交。不分期別直接算，會得到約 57 萬／坪，
 那是三、四年前的價格。<br>
 ② <b>口徑</b>：591、樂居常用含車位單價（75.68），本資料以不含車位為主（80.46），兩者差 6.3%。
 比較時請先確認是同一種口徑。</div>
 {foot(3)}
</div>

<div class="page">
 <h2>目前市場在售</h2>
 <p>以下為公開刊登平台上雙橡園2279 的在售物件（擷取日 2026-10-01，共 6 戶）。
 <b>開價是屋主的要價，不是成交價</b>，實際成交通常會經過議價。</p>
 <table>
  <tr><th>樓層</th><th>號別</th><th>開價<br>(萬)</th><th>權狀<br>(坪)</th><th>主建物<br>(坪)</th><th>開價單價<br>含車位</th><th>格局</th><th>刊登日</th><th>平台</th></tr>
  {list_rows}
 </table>
 <p class="note">開價單價＝開價÷權狀總坪數（含車位），單位萬元／坪，與實價登錄「含車位單價」為同一口徑。
 格局依刊登內容；同一物件在多個平台刊登時只列一次。</p>

 <h3>開價與成交對照（含車位口徑，萬元／坪）</h3>
 <table style="width:85%">
  <tr><th>樓層</th><th>在售開價</th><th>近三年成交</th></tr>
  <tr><td>3–6F</td><td class="b">68.04–70.74（4 戶，中位 68.39）</td><td>—（近三年無此樓層成交）</td></tr>
  <tr><td>9F</td><td>—</td><td class="b">73.19（114/05，1 筆）</td></tr>
  <tr><td>21–22F</td><td>—</td><td class="b">74.80–76.82（113/09，3 筆）</td></tr>
  <tr><td>26–28F</td><td class="b">79.93–80.10（2 戶）</td><td>—（近三年無此樓層成交）</td></tr>
 </table>

 <div class="box"><b>怎麼看這張表</b><br>
 ・在售物件集中在<b>低樓層（3–6F）</b>與<b>高樓層（26–28F）</b>，兩群開價差約 17%，與預售期的樓層價差（約 18%）同一個量級。<br>
 ・近三年成交在 9F 與 21–22F，跟在售樓層沒有重疊，<b>不能直接拿來判斷開價高低</b>；比價時請先對齊樓層、坪數與車位數。<br>
 ・開價單價含車位。若要換算不含車位單價，需要扣除該戶的車位價格與車位面積，現場可用第 5 頁的比對欄計算。</div>
 {foot(4)}
</div>

<div class="page">
 <h2>樓層、租金與注意事項</h2>
 <h3>樓層價差（民國 110 年預售成交，n=123，不含車位）</h3>
 <table style="width:70%">
  <tr><th>樓層帶</th><th>筆數</th><th>單價中位（萬/坪）</th></tr>
  {floor_rows}
 </table>
 <p class="note">只取同一年度，避免年份差異干擾。高樓帶比低樓帶約高 18%，可作為比較不同樓層物件的參考。</p>

 <h3>租金報酬率</h3>
 <p>本棟目前<b>尚無租賃實價登錄資料</b>，因此不試算租金報酬率。取得租賃成交後再補。</p>

 <h3>本戶比對（帶看現場填寫）</h3>
 <table class="fill">
  <tr><td>樓層／格局</td><td></td></tr>
  <tr><td>總面積（坪）／車位數</td><td></td></tr>
  <tr><td>開價（萬）</td><td></td></tr>
  <tr><td>換算不含車位單價（萬/坪）</td><td></td></tr>
  <tr><td>與近三年中位 80.46 相比</td><td></td></tr>
 </table>

 <div class="warn"><b>誠實揭露</b><br>
 ・近三年有效成交僅 4 筆，其中 3 筆為同一天的交屋登記，<b>筆數少，僅供參考</b>，不足以單獨作為估價依據。<br>
 ・交屋後實價登錄上的轉售成交目前只有 1 筆，原因可能是交屋時間尚短，不代表市場評價。<br>
 ・本案位於單元二重劃區，不屬於七期重劃區，七期的行情數字不適用於本案。<br>
 ・在售開價為屋主要價，非成交價，實際成交價格以議價結果為準。<br>
 ・過去成交價格不代表未來價格，本資料不對增值或報酬做任何保證。</div>

 <p class="note" style="margin-top:3mm"><b>資料來源</b>：內政部不動產實價登錄（買賣檔民國 109–115 年、預售檔民國 110–112 年，撈取日 2026-10-01）；
 樂居公開資料（撈取日 2026-10-01）；591、樂屋刊登資料（擷取日 2026-10-01）。<br>
 <b>免責聲明</b>：本資料由經紀人員依公開資料整理，僅供參考，實際成交價格受樓層、格局、屋況、車位及交易條件影響。
 物件實際狀況以現場及產權資料為準。</p>
 {f'<div class="card"><div class="n">有任何問題，歡迎直接聯絡</div><div class="t">{CONTACT}</div></div>' if CONTACT else ''}
 <div class="seal">百富國際<br>開發有限公司</div>
 {foot(5)}
</div>
</body></html>"""

# HTML 只當渲染中介，放暫存目錄：deliverables/ 下的 .html 會被 sitemap 收錄成公開網頁，
# 這份只透過 LINE 傳 PDF 給買方，不上網站。
html = Path(tempfile.mkdtemp()) / f"{NAME}.html"
html.write_text(HTML, encoding="utf-8")
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page()
    pg.goto(html.as_uri())
    pg.pdf(path=str(OUT / f"{NAME}.pdf"), format="A4", print_background=True, prefer_css_page_size=True)
    b.close()
print("ok")
