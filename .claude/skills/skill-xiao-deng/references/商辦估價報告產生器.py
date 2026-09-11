#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
商辦估價報告產生器 — 小登 · Sixhands Studio
用途：把七期商辦行情庫的實登數據，產出「給屋主／賣方」的 A4 估價報告書 PDF。
規格依 skill-report-factory：深海軍藍 #0E2233 ＋ 黃銅金 ＋ 奶油白、A4 直式、
       系統 Noto CJK 字型（不引用 Google Fonts）、SVG 圖表實色、法定揭露 footer。
渲染：Playwright(Chromium) → page.pdf(prefer_css_page_size=True)
換棟：改 D 字典即可。
"""
import json, sys, subprocess
from pathlib import Path

SC = Path("/tmp/claude-0/-home-user-my-website/c41d1137-671d-5c73-871e-48ec90c18d56/scratchpad")
d = json.load(open(SC/"report_data.json"))
S, BANDS, YEARS = d["summary"], d["bands"], d["years"]

D = {
 "案名":"聯聚中雍大廈 The Landmark",
 "地址":"臺中市西屯區市政北七路 98 號",
 "副標":"七期頂級企業總部商辦 · 全棟行情分析暨建議售價",
 "報告編號":"LJZY-2026-0911",
 "日期":"2026/09/11",
 "撈取日":"2026-09-11",
 "查詢區間":"101/01 ~ 115/07",
}

CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; margin:0; padding:0; }
body { font-family:"Noto Sans CJK TC",sans-serif; color:#1a1a1a; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.page { width:210mm; height:297mm; position:relative; overflow:hidden; page-break-after:always; background:#FAF7F0; }
.page:last-child { page-break-after:auto; }
h1,h2,h3,.serif { font-family:"Noto Serif CJK TC",serif; }
.navy { background:#0E2233; color:#FAF7F0; }
.pad { padding:16mm 16mm 0 16mm; }
.ttl { font-size:19pt; color:#0E2233; font-weight:700; border-left:5px solid #B8924F; padding-left:9px; margin-bottom:3mm; }
.sub { font-size:9pt; color:#6b6b6b; margin-bottom:5mm; line-height:1.6; }
table { width:100%; border-collapse:collapse; font-size:8.6pt; }
th { background:#0E2233; color:#FAF7F0; padding:5px 7px; text-align:left; font-weight:500; font-size:8.4pt; }
td { padding:5px 7px; border-bottom:1px solid #e3ddd0; }
tr:nth-child(even) td { background:#f4efe4; }
.hl td { background:#B8924F !important; color:#fff; font-weight:700; }
.num { font-variant-numeric:tabular-nums; text-align:right; }
.foot { position:absolute; bottom:0; left:0; right:0; height:13mm; background:#0E2233; color:#c9bfa8;
        font-size:6.6pt; display:flex; align-items:center; justify-content:space-between; padding:0 16mm; }
.card { background:#fff; border:1px solid #e0d8c6; border-top:3px solid #B8924F; padding:6mm; }
.kpi { display:flex; gap:4mm; margin-bottom:5mm; }
.kpi>div { flex:1; background:#fff; border:1px solid #e0d8c6; border-top:3px solid #B8924F; padding:4mm 3mm; text-align:center; }
.kpi .v { font-family:"Noto Serif CJK TC",serif; font-size:20pt; color:#0E2233; font-weight:700; line-height:1.1; }
.kpi .l { font-size:7.4pt; color:#7a7a7a; margin-top:2mm; letter-spacing:.05em; }
.kpi .u { font-size:8pt; color:#B8924F; }
.note { background:#fdf6e8; border-left:4px solid #B8924F; padding:4mm 5mm; font-size:8.4pt; line-height:1.75; }
.warn { background:#fdeceb; border-left:4px solid #b3352c; padding:4mm 5mm; font-size:8.4pt; line-height:1.75; }
.g { color:#B8924F; } .b{font-weight:700;}
ul { margin-left:5mm; } li { font-size:8.6pt; line-height:1.85; margin-bottom:1mm; }
"""

def foot(pg):
    return ('<div class="foot"><span>永慶不動產 七期河南市政店 ／ 百富國際開發有限公司 ／ '
            '中市地價二字第1070032073號</span>'
            f'<span>{D["案名"]}　估價報告書　{D["報告編號"]}　— {pg} —</span></div>')

# ── P1 封面 ──
p1 = f"""<div class="page navy">
 <div style="padding:30mm 20mm 0 20mm">
  <div style="font-size:8.4pt;letter-spacing:.5em;color:#B8924F">SIXHANDS ／ 市場行情分析</div>
  <div style="width:52mm;height:2px;background:#B8924F;margin:6mm 0 9mm"></div>
  <h1 style="font-size:31pt;line-height:1.3;font-weight:700">房地產市場行情分析<br>暨建議售價報告</h1>
  <div style="font-size:12.5pt;color:#B8924F;margin-top:9mm;letter-spacing:.05em">{D['案名']}</div>
  <div style="font-size:9.6pt;color:#b9b0a0;margin-top:2.5mm;line-height:1.9">{D['地址']}<br>{D['副標']}</div>

  <div style="margin-top:15mm;border-top:1px solid #2c4256;border-bottom:1px solid #2c4256;padding:9mm 0">
   <div style="font-size:8pt;color:#8fa3b5;letter-spacing:.25em;margin-bottom:6mm">核 心 結 論</div>
   <div style="display:flex;gap:8mm">
    <div style="flex:1"><div style="font-size:7.8pt;color:#8fa3b5">全棟成交中位（成屋轉售 {S['n']} 筆）</div>
      <div class="serif" style="font-size:27pt;color:#B8924F;font-weight:700">{S['md']:.1f}<span style="font-size:11pt"> 萬/坪</span></div></div>
    <div style="flex:1"><div style="font-size:7.8pt;color:#8fa3b5">近 3 年成交均價（{S['r3n']} 筆）</div>
      <div class="serif" style="font-size:27pt;color:#B8924F;font-weight:700">{S['r3avg']:.1f}<span style="font-size:11pt"> 萬/坪</span></div></div>
    <div style="flex:1"><div style="font-size:7.8pt;color:#8fa3b5">全棟最高成交（30F）</div>
      <div class="serif" style="font-size:27pt;color:#B8924F;font-weight:700">{S['mx']:.1f}<span style="font-size:11pt"> 萬/坪</span></div></div>
   </div>
  </div>

  <div style="margin-top:10mm;font-size:9.2pt;line-height:2.05;color:#dcd5c6">
   本報告以 <span class="g b">內政部不動產交易實價登錄 {S['total']} 筆買賣</span>（{D['查詢區間']}，4F–39F 全樓層）
   與 <span class="g b">5 筆租賃實登</span>為基礎，單價一律自行扣除車位重算，
   並區分預售與成屋轉售兩波，建立本案<span class="g b">分樓層價格階梯</span>與<span class="g b">投報率結構</span>。
  </div>
  <div style="margin-top:6mm;font-size:8.2pt;color:#8fa3b5;line-height:1.9">
   報告編號 {D['報告編號']}　｜　製表日 {D['日期']}　｜　資料撈取日 {D['撈取日']}<br>
   製表：小登 · 實登行情數據官（Sixhands Studio AI 數字員工）
  </div>
 </div>
 {foot(1)}</div>"""

# ── P2 標的基本資料 ──
BASIC=[("案名","聯聚中雍大廈 The Landmark"),("地址","西屯區市政北七路 98 號"),
 ("建設／營造","聯聚建設 ／ 拓洋營造"),("建築設計","張德昌建築師事務所"),
 ("完工","107/06（屋齡 8 年）"),("建築規劃","地上 39 層／地下 7 層"),
 ("建築高度","192 公尺"),("構造","SC 鋼骨造"),
 ("總戶數","73 戶"),("配置","每層 2 戶雙拼（之1／之2）"),
 ("基地面積","1,086 坪"),("標準層高","約 4.5 米"),
 ("主建物","約 132.4 坪／戶"),("權狀（扣車位）","約 220.4 坪／戶"),
 ("公設比","39.96%"),("管理費","160 元／坪／月"),
 ("車位","430 席・坡道平面・9.65 坪/席"),("車位比","5.89 席／戶"),
 ("土地","惠國段 92 地號"),("使用分區","都市：第四種新市政中心專用區"),
 ("主要用途","辦公用（實登）"),("學區","惠文國小(雙語)／惠來國小(雙語)／惠文高中國中部"),
]
def _cell(k,v):
    return (f"<td style='background:#f4efe4;width:21%;font-weight:500'>{k}</td>"
            f"<td style='width:29%'>{v}</td>")
_pairs=[BASIC[i:i+2] for i in range(0,len(BASIC),2)]
rows="".join("<tr>"+"".join(_cell(k,v) for k,v in pr)
             + ("<td></td><td></td>" if len(pr)==1 else "") + "</tr>" for pr in _pairs)
p2=f"""<div class="page"><div class="pad">
 <div class="ttl">一、標的基本資料</div>
 <div class="sub">資料來源：內政部實價登錄建物明細（撈取日 {D['撈取日']}）＋ 樂居公開基本資料，兩造交叉驗證。</div>
 <table>{rows}</table>

 <div style="margin-top:6mm" class="note">
  <span class="b g">◆ 公設比經雙重驗證。</span>實登反推（主建物 132.35 ÷ 扣車位權狀 220.42）＝ <span class="b">39.96%</span>，
  與樂居揭露之 39.95% 完全吻合。<br>
  <span class="b">實務意義：</span>每購入一坪，可實際使用約 <span class="b">0.60 坪</span>。
  以全棟中位 {S['md']:.2f} 萬/坪換算，<span class="b g">每坪可用空間的真實成本約 {S['md']/0.6004:.1f} 萬元</span>。
  此為頂級商辦常態（入口大廳、梯廳、機電、中繼機房均計入公設），非本案獨有。
 </div>

 <div style="margin-top:5mm" class="warn">
  <span class="b">◆ 分類提醒（易誤判）：</span>本案實登「建物型態」欄登載為
  <span class="b">住宅大樓（11層含以上有電梯）</span>，但「主要用途」欄為 <span class="b">辦公用</span>、
  建物明細為 <span class="b">辦公室</span>；租賃實登之型態欄則登載為「辦公商業大樓」。
  <span class="b">同一標的存在兩套型態標示</span>，若以「建物型態」篩選比較標的，將整棟誤歸住宅並污染均價。
  本報告一律以「主要用途」為分類依據。
 </div>

 <div style="margin-top:5mm" class="card">
  <div class="serif" style="font-size:11.5pt;color:#0E2233;font-weight:700;margin-bottom:3mm">標準層配置</div>
  <div style="font-size:8.6pt;line-height:1.95">
   每層 2 戶雙拼，<span class="b">C 棟＝98號-1</span>、<span class="b">D 棟＝98號-2</span>，共用中央梯間（專有梯廳 1.55 坪/戶）。<br>
   兩戶可整層合併，合計扣車位權狀約 <span class="b g">441 坪</span>。
   實登佐證：15F 之1・之2 於 115/07/03 同日同價成交；11F 之1・之2 於 114/02/09 同日同價成交；
   租賃端 9F、10F 亦各以整層（440.81 坪）於同日同價出租。
  </div>
 </div>
</div>{foot(2)}</div>"""

# ── P3 實登總覽 ──
ymax=max(y["avg"] for y in YEARS); ymin=min(y["avg"] for y in YEARS)
bars=""
BW,GAP,H0,BASEY = 34,9,150,205
for i,y in enumerate(YEARS):
    h=(y["avg"]-50)/(ymax-50)*H0
    x=40+i*(BW+GAP)
    bars+=(f'<rect x="{x}" y="{BASEY-h:.1f}" width="{BW}" height="{h:.1f}" fill="#0E2233"/>'
           f'<text x="{x+BW/2}" y="{BASEY-h-6:.1f}" font-size="11" fill="#0E2233" text-anchor="middle" font-weight="700">{y["avg"]:.1f}</text>'
           f'<text x="{x+BW/2}" y="{BASEY+14}" font-size="10.5" fill="#555" text-anchor="middle">{y["y"]}</text>'
           f'<text x="{x+BW/2}" y="{BASEY+26}" font-size="9" fill="#999" text-anchor="middle">n={y["n"]}</text>')
p3=f"""<div class="page"><div class="pad">
 <div class="ttl">二、實價登錄總覽</div>
 <div class="sub">內政部不動產交易實價查詢服務網｜查詢區間 {D['查詢區間']}｜撈取日 {D['撈取日']}｜
  條件：市政北七路98號・房地(土地+建物)及含車位・<span class="b">全樓層無篩選</span>｜主要用途 100% 辦公用</div>

 <div class="kpi">
  <div><div class="v">{S['total']}</div><div class="l">買賣實登總筆數</div></div>
  <div><div class="v">{S['pre_n']}</div><div class="l">預售（104 年）</div></div>
  <div><div class="v">{S['n']}</div><div class="l">成屋轉售（106 起）</div></div>
  <div><div class="v">4–39<span class="u">F</span></div><div class="l">樓層涵蓋</div></div>
 </div>

 <div class="card" style="margin-bottom:5mm">
  <div class="serif" style="font-size:11.5pt;color:#0E2233;font-weight:700;margin-bottom:2.5mm">單價口徑（本報告一律自行重算）</div>
  <div style="font-size:8.5pt;line-height:1.85">
   <span class="b">淨單價 ＝（總價 − 車位價）÷（總面積 − 9.65 × 車位數）</span><br>
   車位價：34 筆已揭露者採實際值（173～228 萬/席）；37 筆未揭露者採實據中位 <span class="b">191 萬/席</span>。<br>
   <span class="b" style="color:#b3352c">※ 實登「單價」欄不可直接比較</span>——車位價有揭露者系統已扣車位，未揭露者未扣，
   兩種口徑混列。例：某筆實登欄 58.69 看似偏高，統一口徑後 58.68 實為全場最低。
  </div>
 </div>

 <table style="margin-bottom:5mm">
  <tr><th>群組</th><th class="num">筆數</th><th class="num">最低</th><th class="num">中位</th><th class="num">均價</th><th class="num">最高</th></tr>
  <tr><td>預售（104/03–104/08，早於完工）</td><td class="num">{S['pre_n']}</td><td class="num">53.09</td><td class="num">56.06</td><td class="num">{S['pre_avg']:.2f}</td><td class="num">68.47</td></tr>
  <tr class="hl"><td>成屋轉售（106 年起）★ 估價基準</td><td class="num">{S['n']}</td><td class="num">{S['mn']:.2f}</td><td class="num">{S['md']:.2f}</td><td class="num">{S['avg']:.2f}</td><td class="num">{S['mx']:.2f}</td></tr>
  <tr><td>近 3 年（113–115）</td><td class="num">{S['r3n']}</td><td class="num">—</td><td class="num">{S['r3md']:.2f}</td><td class="num">{S['r3avg']:.2f}</td><td class="num">—</td></tr>
 </table>
 <div style="font-size:7.8pt;color:#777;margin-bottom:5mm">單位：萬元／坪（淨單價，不含車位）。
  成屋轉售較預售高 <span class="b">+10.5%</span>；預售屬建商定價，不代表市場行情，故估價一律採成屋轉售組。</div>

 <div class="serif" style="font-size:11.5pt;color:#0E2233;font-weight:700;margin-bottom:2mm">成屋轉售逐年均價（萬/坪）</div>
 <svg viewBox="0 0 480 240" style="width:100%;height:52mm">
  <line x1="34" y1="{BASEY}" x2="470" y2="{BASEY}" stroke="#c9bfa8" stroke-width="1"/>
  {bars}
 </svg>
 <div style="font-size:7.8pt;color:#777;margin-top:1mm">
  107–109 均 63.14 → 113–115 均 {S['r3avg']:.2f}，<span class="b">6 年 +14.2%，年化 2.23%</span>。
  113 年均價偏高係由 2 筆 30F 交易（含全場最高 89.83）拉升，<span class="b">年度均價受樓層組合影響甚大，須併同下頁樓層帶判讀</span>。
 </div>
</div>{foot(3)}</div>"""

# ── P4 樓層溢價 + 價格階梯 ★核心 ──
base=BANDS[0]["avg"]
brows=""; chart=""
CW,CG,CH,CB = 66,14,130,190
for i,b in enumerate(BANDS):
    h=(b["avg"]-52)/(BANDS[-1]["avg"]-52)*CH
    x=30+i*(CW+CG)
    chart+=(f'<rect x="{x}" y="{CB-h:.1f}" width="{CW}" height="{h:.1f}" fill="#0E2233"/>'
            f'<text x="{x+CW/2}" y="{CB-h-7:.1f}" font-size="13" fill="#0E2233" text-anchor="middle" font-weight="700">{b["avg"]:.1f}</text>'
            f'<text x="{x+CW/2}" y="{CB+15}" font-size="10.5" fill="#444" text-anchor="middle">{b["name"].split(" ")[1]}</text>'
            f'<text x="{x+CW/2}" y="{CB+28}" font-size="10" fill="#B8924F" text-anchor="middle" font-weight="700">'
            + ("基準" if i==0 else "+%.1f%%" % ((b["avg"]/base-1)*100)) + '</text>')
    few = ' <span style="color:#b3352c">⚠</span>' if b["n"]<10 else ""
    rec = f'{b["ravg"]:.2f} <span style="color:#999">(n={b["rn"]})</span>' if b["ravg"] else '<span style="color:#999">無成交</span>'
    # 防守底價=全期中位；合理帶=中位~均價；開價=合理上緣×1.06（近3年n>=3則取近3年均為上緣）
    up = b["ravg"] if (b["rn"]>=3 and b["ravg"]>b["avg"]) else b["avg"]
    brows+=(f'<tr><td class="b">{b["name"]}{few}</td><td class="num">{b["n"]}</td>'
            f'<td class="num">{b["mn"]:.2f}</td><td class="num">{b["md"]:.2f}</td><td class="num">{b["avg"]:.2f}</td>'
            f'<td class="num">{b["mx"]:.2f}</td><td class="num">{rec}</td>'
            f'<td class="num b" style="color:#0E2233">{b["md"]:.1f}</td>'
            f'<td class="num b" style="color:#0E2233">{b["md"]:.1f}–{up:.1f}</td>'
            f'<td class="num b g">{up*1.06:.1f}</td></tr>')
p4=f"""<div class="page"><div class="pad">
 <div class="ttl">三、樓層溢價曲線與分樓層價格階梯</div>
 <div class="sub">僅採「成屋轉售 {S['n']} 筆」計算，排除預售定價干擾。實登樓層分布中無 16F 成交紀錄。</div>

 <svg viewBox="0 0 430 236" style="width:100%;height:50mm">
  <line x1="24" y1="{CB}" x2="424" y2="{CB}" stroke="#c9bfa8"/>{chart}
 </svg>

 <table style="margin-top:3mm">
  <tr><th rowspan="2">樓層帶</th><th class="num" rowspan="2">筆數</th>
      <th colspan="4" style="text-align:center;background:#1b3348">實際成交（萬/坪）</th>
      <th class="num" rowspan="2">近3年均</th>
      <th colspan="3" style="text-align:center;background:#B8924F">建議價格階梯</th></tr>
  <tr><th class="num" style="background:#1b3348">最低</th><th class="num" style="background:#1b3348">中位</th>
      <th class="num" style="background:#1b3348">均價</th><th class="num" style="background:#1b3348">最高</th>
      <th class="num" style="background:#B8924F">防守底價</th><th class="num" style="background:#B8924F">合理成交帶</th>
      <th class="num" style="background:#B8924F">建議開價</th></tr>
  {brows}
 </table>
 <div style="font-size:7.6pt;color:#777;margin-top:1.5mm">
  單位：萬元／坪（淨單價，不含車位）。<span style="color:#b3352c">⚠</span> 標示者樣本數 &lt;10，僅供參考。
  防守底價＝該樓層帶全期中位；合理成交帶＝中位至均價（近 3 年有 3 筆以上且高於均價者取近 3 年均為上緣）；建議開價＝合理上緣 ×1.06（預留議價空間，議價幅度為業界慣例推估，非實登數據）。
 </div>

 <div style="margin-top:5mm" class="note">
  <span class="b g">◆ 樓層溢價約 16%，且跳躍點在 10F。</span>
  低樓層（4–9F）均 {BANDS[0]['avg']:.2f} 萬/坪，10F 以上即跳升約 <span class="b">+9%</span>，
  至頂層（33–39F）達 {BANDS[-1]['avg']:.2f} 萬/坪、累計 <span class="b">+{(BANDS[-1]['avg']/base-1)*100:.1f}%</span>。<br>
  <span class="b">對屋主的意義：</span>高樓層開價高於低樓層 15% 上下，<span class="b">是本棟自身成交紀錄支持的市場行情，不是漫天喊價</span>；
  買方若以低樓層成交價比價，本表即為回應依據。
 </div>

 <div style="margin-top:4mm" class="warn">
  <span class="b">◆ 近 3 年高樓層出現跳價，但樣本極少，不宜當定價依據。</span>
  中高樓層近 3 年均 {BANDS[2]['ravg']:.2f}（n={BANDS[2]['rn']}）、高樓層近 3 年均 {BANDS[3]['ravg']:.2f}（n={BANDS[3]['rn']}），
  均由 115/05 兩筆 18F（81.85）與 113/10 一筆 30F（89.83）拉升。
  <span class="b">建議：以此為「衝高目標價」，而非「預期成交價」</span>；預期成交仍應落在合理成交帶。
 </div>
</div>{foot(4)}</div>"""

# ── P5 租金與投報 ──
p5=f"""<div class="page"><div class="pad">
 <div class="ttl">四、租金行情與投資報酬率</div>
 <div class="sub">租賃實價登錄 5 筆（112/05 ~ 113/12）。租金口徑同買賣，一律扣除車位租金與車位面積後重算。</div>

 <table>
  <tr><th>訂約日</th><th>樓別</th><th class="num">月租總額(萬)</th><th class="num">總面積(坪)</th><th class="num">車位</th>
      <th class="num">實登單價</th><th class="num">統一口徑(元/坪/月)</th><th>標的／備註</th></tr>
  <tr><td>112/05/16</td><td class="b">9F</td><td class="num">63.01</td><td class="num">440.81</td><td class="num">10</td><td class="num">0.17</td><td class="num b">1,728</td><td>房地+車位｜整層 之1+之2</td></tr>
  <tr><td>112/05/16</td><td class="b">10F</td><td class="num">63.01</td><td class="num">440.81</td><td class="num">10</td><td class="num">0.17</td><td class="num b">1,728</td><td>房地+車位｜整層 之1+之2</td></tr>
  <tr><td>112/05/25</td><td class="b">31F</td><td class="num">58.11</td><td class="num">224.00</td><td class="num">5</td><td class="num">0.26</td><td class="num b g">3,185</td><td>建物｜含稅、含車位清潔費</td></tr>
  <tr><td>112/08/04</td><td class="b">19F</td><td class="num">38.00</td><td class="num">262.52</td><td class="num">4</td><td class="num">0.14</td><td class="num b">1,621</td><td>建物</td></tr>
  <tr><td>113/12/06</td><td class="b">21F</td><td class="num">44.42</td><td class="num">223.90</td><td class="num">4</td><td class="num">0.23</td><td class="num b">2,289</td><td>房屋+車位｜含稅｜租期 5 年</td></tr>
 </table>
 <div style="font-size:7.6pt;color:#777;margin-top:1.5mm">
  車位月租實據：20,000元/4席＝5,000、35,000元/10席＝3,500，未揭露者採 4,250 元/席/月。
  <span style="color:#b3352c">租賃單價欄亦有相同口徑問題</span>：31F 實登欄 0.26，統一口徑後 0.3185，差 23%。
 </div>

 <div class="serif" style="margin-top:5mm;font-size:11.5pt;color:#0E2233;font-weight:700">全棟投報率（租金中位 1,728 ÷ 成交中位 {S['md']:.2f} 萬/坪）</div>
 <div class="kpi" style="margin-top:3mm">
  <div><div class="v">3.20<span class="u">%</span></div><div class="l">毛投報率</div></div>
  <div><div class="v">2.90<span class="u">%</span></div><div class="l">扣管理費 160 元/坪/月</div></div>
  <div><div class="v">2.54<span class="u">%</span></div><div class="l">再扣持有稅 0.4%＋空置 8%</div></div>
 </div>

 <table>
  <tr><th>樓別</th><th class="num">實登租金(元/坪/月)</th><th class="num">該樓層帶售價(萬/坪)</th><th class="num">毛投報率</th></tr>
  <tr><td>9F</td><td class="num">1,728</td><td class="num">{BANDS[0]['avg']:.2f}</td><td class="num">3.49%</td></tr>
  <tr><td>10F</td><td class="num">1,728</td><td class="num">{BANDS[1]['avg']:.2f}</td><td class="num">3.20%</td></tr>
  <tr><td>19F</td><td class="num">1,621</td><td class="num">{BANDS[2]['avg']:.2f}</td><td class="num">3.00%</td></tr>
  <tr><td>21F</td><td class="num">2,289</td><td class="num">{BANDS[2]['avg']:.2f}</td><td class="num">4.23%</td></tr>
  <tr class="hl"><td>31F</td><td class="num">3,185</td><td class="num">{BANDS[3]['avg']:.2f}</td><td class="num">5.61%</td></tr>
 </table>

 <div style="margin-top:5mm" class="note">
  <span class="b g">◆ 關鍵發現：售價尚未充分反映高樓層的租金價值。</span><br>
  31F 租金 3,185 元/坪相對 9–10F 之 1,728 元/坪，<span class="b">租金溢價達 +84%</span>；
  但同期高樓層售價相對低樓層之溢價僅 <span class="b">+14.6%</span>。
  租金溢價為售價溢價的 5.7 倍，<span class="b">高樓層毛投報率反而明顯較高（5.61% 對 3.20–3.49%）</span>。<br>
  <span class="b">對屋主的意義：</span>若持有高樓層戶別，<span class="b">開價具備高於樓層溢價曲線的談判空間</span>，
  可改以「租金收益還原」而非「每坪單價」與買方議價。<br>
  <span class="b" style="color:#b3352c">※ 樣本僅 5 筆且口徑不一</span>（含稅／未註明、含土地／僅建物、車位租金揭露與否），
  方向可信，幅度須更多樣本驗證。保守以實登原始欄 2,600 元/坪重算，31F 仍達 4.58%，結論方向不變。
 </div>
</div>{foot(5)}</div>"""

# ── P6 市場判讀與訂價策略 ──
p6=f"""<div class="page"><div class="pad">
 <div class="ttl">五、市場判讀與訂價策略建議</div>
 <div class="sub">以本棟自身成交紀錄為主要錨點，輔以七期商辦同級競品位階比較。</div>

 <div class="serif" style="font-size:11.5pt;color:#0E2233;font-weight:700;margin-bottom:2.5mm">1. 價格走勢判讀</div>
 <div class="card" style="margin-bottom:5mm">
  <div style="font-size:8.6pt;line-height:1.95">
   成屋轉售 107–109 年均 63.14 → 113–115 年均 {S['r3avg']:.2f} 萬/坪，
   <span class="b">6 年上漲 14.2%，年化 2.23%</span>。<br>
   <span class="b g">判讀：保值性成立，增值幅度溫和。</span>
   本案價格區間長期穩定、未見明顯下跌；相較之下，七期住宅同期經歷 2024 年高峰後近一年修正約 −9.96%，
   <span class="b">本案波動明顯較小</span>。此一特性與「自用比例高、長期持有者居多」的持有結構一致。<br>
   <span class="b" style="color:#b3352c">※ 本判讀為歷史資料之描述，不構成對未來價格之預測或保證。</span>
  </div>
 </div>

 <div class="serif" style="font-size:11.5pt;color:#0E2233;font-weight:700;margin-bottom:2.5mm">2. 同級競品位階</div>
 <table style="margin-bottom:1.5mm">
  <tr><th>等級</th><th>案名</th><th class="num">坪數規劃</th><th class="num">單價（萬/坪）</th><th>資料性質</th></tr>
  <tr class="hl"><td>頂級企業總部級</td><td>聯聚中雍大廈（本案）</td><td class="num">225–450</td><td class="num">{S['md']:.2f}（中位）／{S['mx']:.2f}（最高）</td><td>實價登錄 {S['n']} 筆</td></tr>
  <tr><td>頂級企業總部級</td><td>聯聚中維大廈</td><td class="num">—</td><td class="num">—</td><td>尚未建檔</td></tr>
  <tr><td>進階級</td><td>NTC 國家商貿中心</td><td class="num">—</td><td class="num">—</td><td>未揭露</td></tr>
  <tr><td>進階級</td><td>CBD 時代廣場</td><td class="num">50–300</td><td class="num">42–58</td><td>同業公開資訊</td></tr>
  <tr><td>進階級</td><td>豐邑市政都心廣場</td><td class="num">—</td><td class="num">約 44</td><td>同業公開資訊</td></tr>
  <tr><td>入門～中階</td><td>市政壹號廣場</td><td class="num">25–48</td><td class="num">—</td><td>同業公開資訊</td></tr>
 </table>
 <div style="font-size:7.6pt;color:#777;margin-bottom:4mm">
  競品單價引自同業公開網頁（darren-chang.com，2025 年更新），<span class="b">非實價登錄，僅供相對位階參考，不得作為報價依據</span>。
  本案數據則全數來自實價登錄。
 </div>
 <div class="note" style="margin-bottom:5mm">
  <span class="b g">◆ 位階驗算：</span>本案中位 {S['md']:.2f} ÷ CBD 中位 50 ＝ <span class="b">1.30 倍</span>；
  ÷ 豐邑 44 ＝ <span class="b">1.48 倍</span>。本案價格較同區進階級商辦高出約 <span class="b">30–50%</span>。<br>
  <span class="b">真正的分級機制是最小坪數而非單價</span>：25–48 坪 → 50–300 坪 → 225–450 坪，
  坪數門檻即客群篩選器。需求 40 坪的企業不會成為本案買方，因產品不存在。
 </div>

 <div class="serif" style="font-size:11.5pt;color:#0E2233;font-weight:700;margin-bottom:2.5mm">3. 訂價與銷售策略</div>
 <ul>
  <li><span class="b">依樓層帶訂價，切勿以全棟均價套用。</span>低樓層與頂層落差達 {(BANDS[-1]['avg']/base-1)*100:.1f}%，以全棟均價報低樓層將高估約 5～6 萬/坪，反致滯銷。</li>
  <li><span class="b">買方比價時，以本棟自身成交紀錄回應。</span>{S['n']} 筆成屋轉售即為最強錨點，無須引用他棟。</li>
  <li><span class="b">高樓層改以租金收益還原議價。</span>租金溢價 +84% 遠高於售價溢價 +14.6%，對收租型買方，高樓層投報率反優於低樓層。</li>
  <li><span class="b">預期管理：本案買方以自用與企業形象為主，非高投報標的。</span>實質淨投報約 2.5–2.9%，宜於接洽初期即揭露，避免後段破局。</li>
  <li><span class="b">毛胚屋戶別須計入裝修成本。</span>實登 5 筆註記毛胚屋，買方須自行裝修，議價時可納入折讓評估。</li>
  <li><span class="b">整層需求可主打 C＋D 合併 441 坪。</span>本棟已有多次整層成交與整層出租紀錄，為明確可行之產品型態。</li>
 </ul>

 <div style="margin-top:4mm" class="warn">
  <span class="b">◆ 若已委託銷售逾 3 個月無出價，建議依序檢視：</span>
  ① 開價是否超出該樓層帶「合理成交帶」上緣；② 是否以全棟均價套用於低樓層戶別；
  ③ 買方客群是否投報導向（本案不適配）；④ 毛胚屋是否未於揭露階段說明裝修成本。
 </div>
</div>{foot(6)}</div>"""

# ── P7 免責與來源 ──
p7=f"""<div class="page"><div class="pad">
 <div class="ttl">六、資料來源與免責聲明</div>

 <div class="card" style="margin-bottom:5mm">
  <div class="serif" style="font-size:11.5pt;color:#0E2233;font-weight:700;margin-bottom:3mm">資料來源</div>
  <table>
   <tr><th>項目</th><th>來源</th><th>期別／撈取日</th></tr>
   <tr><td>買賣成交 {S['total']} 筆</td><td>內政部不動產交易實價查詢服務網</td><td>{D['查詢區間']}／{D['撈取日']}</td></tr>
   <tr><td>租賃成交 5 筆</td><td>內政部不動產交易實價查詢服務網</td><td>{D['查詢區間']}／{D['撈取日']}</td></tr>
   <tr><td>建物基本資料、公設比、管理費</td><td>樂居 leju.com.tw 公開資料</td><td>撈取日 {D['撈取日']}</td></tr>
   <tr><td>競品單價、產品分級</td><td>同業公開網頁 darren-chang.com</td><td>頁面標示 2025 年更新</td></tr>
   <tr><td>持有稅率、空置率、議價幅度</td><td>業界慣例推估值</td><td>非實測數據</td></tr>
  </table>
 </div>

 <div class="card" style="margin-bottom:5mm">
  <div class="serif" style="font-size:11.5pt;color:#0E2233;font-weight:700;margin-bottom:3mm">數據處理說明</div>
  <ul style="margin-left:4mm">
   <li>單價一律自行重算：淨單價 ＝（總價 − 車位價）÷（總面積 − 9.65 × 車位數）。</li>
   <li>車位價未揭露之 37 筆，採 34 筆已揭露實據之中位 191 萬／席估算。</li>
   <li>預售（104 年，早於 107/06 完工）與成屋轉售分列，估價採成屋轉售組。</li>
   <li>經檢視，全部 {S['total']} 筆備註欄均無「親友／員工／共有人／特殊關係」等註記，無排除筆數。</li>
   <li>樣本數少於 10 筆之樓層帶已於表中標示，其統計值僅供參考。</li>
  </ul>
 </div>

 <div class="warn" style="line-height:2">
  <div class="b" style="font-size:10pt;margin-bottom:2.5mm">免責聲明</div>
  一、本報告為<span class="b">市場行情分析</span>，係依公開之實價登錄資料整理分析而成，
  <span class="b">非不動產估價師法所稱之估價報告書</span>，不得作為金融機構鑑價、法院、稅務或其他法定用途之依據。<br>
  二、實際成交價格受個別戶別之樓層、面向、視野、屋況、裝修程度、交易條件、付款方式及買賣雙方議價情形影響甚大，
  本報告所列區間<span class="b">不構成成交價格之保證</span>。<br>
  三、本報告所載歷史價格走勢僅為既有資料之描述，
  <span class="b">不構成對未來價格之預測，亦無任何增值或投資報酬之保證或暗示</span>。<br>
  四、投報率試算之租金、稅費、空置率等參數載於本報告，實際收益因租約條件而異，<span class="b">不保證達成</span>。<br>
  五、本報告引用之同業公開資訊僅供相對位階參考，其正確性由該來源自負，本公司不為其真實性背書。<br>
  六、本報告所載資料截至 {D['撈取日']}；實價登錄有申報作業期間，最新交易可能尚未揭露。
 </div>

 <div style="margin-top:8mm;text-align:center;border-top:1px solid #d8cfb8;padding-top:6mm">
  <div class="serif" style="font-size:13pt;color:#0E2233;font-weight:700;letter-spacing:.1em">永慶不動產 七期河南市政店</div>
  <div style="font-size:9pt;color:#555;margin-top:2mm;line-height:1.9">
   百富國際開發有限公司<br>中市地價二字第 1070032073 號
  </div>
  <div style="font-size:8pt;color:#8a8a8a;margin-top:4mm">
   製表：小登 · 實登行情數據官（Sixhands Studio AI 數字員工）　｜　{D['報告編號']}　｜　{D['日期']}
  </div>
 </div>
</div>{foot(7)}</div>"""

html=f"<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'><style>{CSS}</style></head><body>{p1}{p2}{p3}{p4}{p5}{p6}{p7}</body></html>"
out=Path("/home/user/my-website/deliverables")
out.mkdir(exist_ok=True)
(out/"聯聚中雍_估價報告書.html").write_text(html, encoding="utf-8")
print("HTML 完成", len(html), "bytes")

from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    import os
    exe=os.environ.get("CHROME_EXE","/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    b=pw.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
    pg=b.new_page()
    pg.goto((out/"聯聚中雍_估價報告書.html").as_uri())
    pg.wait_for_timeout(900)
    pg.pdf(path=str(out/"聯聚中雍_估價報告書.pdf"), prefer_css_page_size=True, print_background=True)
    b.close()
print("PDF 完成")
