#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
七期商辦整體分析報告產生器 — 小登 · Sixhands Studio
對象：買方／潛在企業客戶。版型依 skill-report-factory「銷售報告書」：暖金＋奶油白。
圖表依 dataviz skill：三色 categorical 已通過 validate_palette（light）。
章節獨立，可直接拆成網站文章。
"""
import json, statistics as st
from pathlib import Path
HERE=Path(__file__).resolve().parent
SC=Path("/tmp")          # 暫存（HTML 中繼檔）
D=json.load(open(HERE/"七期商辦_九案數據.json",encoding="utf-8"))
TIER={"入門":"#2a78d6","中階":"#eb6834","頂級":"#1baf7a"}
YS=[d['y'] for d in D if d['y']]

CSS="""
@page { size:A4; margin:0; }
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Noto Sans CJK TC",sans-serif;color:#2b2419;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.page{width:210mm;height:297mm;position:relative;overflow:hidden;page-break-after:always;background:#FAF7F0}
.page:last-child{page-break-after:auto}
h1,h2,h3,.serif{font-family:"Noto Serif CJK TC",serif}
.pad{padding:15mm 15mm 0 15mm}
.ch{font-size:8pt;letter-spacing:.35em;color:#B8924F;margin-bottom:2mm}
.ttl{font-size:20pt;color:#3A2E1C;font-weight:700;margin-bottom:2mm;font-family:"Noto Serif CJK TC",serif}
.lead{font-size:9.2pt;color:#6b5c46;line-height:1.85;margin-bottom:6mm}
table{width:100%;border-collapse:collapse;font-size:8.3pt}
th{background:#3A2E1C;color:#FAF7F0;padding:5px 6px;text-align:left;font-weight:500;font-size:8pt}
td{padding:5px 6px;border-bottom:1px solid #e6dcc8}
tr:nth-child(even) td{background:#f5efe2}
.hl td{background:#B8924F!important;color:#fff;font-weight:700}
.hl td span{color:#fdf3dc!important}
.num{font-variant-numeric:tabular-nums;text-align:right}
.foot{position:absolute;bottom:0;left:0;right:0;height:12mm;background:#3A2E1C;color:#cbbfa6;font-size:6.5pt;
 display:flex;align-items:center;justify-content:space-between;padding:0 15mm}
.note{background:#fdf6e6;border-left:4px solid #B8924F;padding:4mm 5mm;font-size:8.4pt;line-height:1.8}
.warn{background:#fbeee9;border-left:4px solid #c1502e;padding:4mm 5mm;font-size:8.4pt;line-height:1.8}
.card{background:#fff;border:1px solid #e6dcc8;border-top:3px solid #B8924F;padding:5mm}
.g{color:#B8924F}.b{font-weight:700}
.kpi{display:flex;gap:4mm;margin-bottom:5mm}
.kpi>div{flex:1;background:#fff;border:1px solid #e6dcc8;border-top:3px solid #B8924F;padding:4mm 2mm;text-align:center}
.kpi .v{font-family:"Noto Serif CJK TC",serif;font-size:19pt;color:#3A2E1C;font-weight:700;line-height:1.1}
.kpi .l{font-size:7.2pt;color:#8a7a60;margin-top:2mm}
ul{margin-left:5mm}li{font-size:8.5pt;line-height:1.8;margin-bottom:1mm}
.lg{display:flex;gap:6mm;font-size:8pt;margin:2mm 0 3mm}
.lg i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:3px;vertical-align:-1px}
"""
def foot(p,t=""):
    return ('<div class="foot"><span>永慶不動產 七期河南市政店 ／ 百富國際開發有限公司 ／ 中市地價二字第1070032073號</span>'
            f'<span>台中七期商辦全解析　{t}　— {p} —</span></div>')

# ── P1 封面 ──
p1=f"""<div class="page" style="background:#3A2E1C">
<div style="padding:32mm 18mm 0 18mm;color:#FAF7F0">
 <div style="font-size:8pt;letter-spacing:.5em;color:#B8924F">TAICHUNG 7TH DISTRICT ／ OFFICE MARKET</div>
 <div style="width:48mm;height:2px;background:#B8924F;margin:6mm 0 9mm"></div>
 <h1 style="font-size:30pt;line-height:1.35;font-weight:700">台中七期商辦<br>全解析</h1>
 <div style="font-size:11.5pt;color:#B8924F;margin-top:8mm;letter-spacing:.08em">九大建案・完整比較・怎麼挑</div>
 <div style="font-size:9pt;color:#bdb19a;margin-top:3mm;line-height:1.9">
  依內政部不動產交易實價登錄 2,700+ 筆逐筆重算<br>不採用任何坊間或同業公開資訊
 </div>
 <div style="margin-top:14mm;border-top:1px solid #5a4a33;border-bottom:1px solid #5a4a33;padding:8mm 0">
  <div style="font-size:7.6pt;color:#9d9280;letter-spacing:.25em;margin-bottom:5mm">本 報 告 回 答 五 個 問 題</div>
  <div style="font-size:10pt;line-height:2.1;color:#e8e0d0">
   ① 七期商辦到底有哪幾棟？<br>
   ② 它們怎麼分級？我屬於哪一級？<br>
   ③ 空間大小差多少？我要的坪數有幾棟在賣？<br>
   ④ 投報率真的有差嗎？<br>
   ⑤ 我該怎麼挑？
  </div>
 </div>
 <div style="margin-top:10mm;font-size:8pt;color:#9d9280;line-height:1.9">
  資料撈取日 2026-09-11｜製表 2026-09-12<br>
  劉力助　永慶不動產 七期河南市政店
 </div>
</div>{foot(1)}</div>"""

# ── P2 第一章 全貌 ──
def usable(d):
    """扣除公設後之實際可用坪。七期商辦公設比 36%–42%，取 0.58–0.64 區間估算。"""
    return f'{round(d["ping"]*0.58)}–{round(d["ping"]*0.64)}'
def row(d):
    tot = f'{d["tot"]/10000:.2f} 億' if d["tot"] and d["tot"]>=10000 else (f'{d["tot"]:,.0f} 萬' if d["tot"] else '—')
    age = d["age"] if isinstance(d["age"],str) else f'{d["age"]} 年'
    y = f'{d["y"]:.2f}%' if d["y"] else '—'
    c = TIER[d["tier"]]
    return (f'<tr><td><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:{c};margin-right:4px"></span>'
            f'<span class="b">{d["n"]}</span></td><td>{d["addr"]}</td><td>{d["dev"]}</td>'
            f'<td class="num">{age}</td><td class="num">{d["fl"]}</td><td class="num">{d["hh"]}</td>'
            f'<td class="num b">{d["p"]:.1f}</td>'
            f'<td class="num">{d["ping"]:.0f}<br><span style="font-size:7pt;color:#8a7a60">{usable(d)}</span></td>'
            f'<td class="num b">{tot}</td><td class="num">{y}</td></tr>')
tbl="".join(row(d) for d in D)

# ── 地理示意（2026-09-12 校正：依實登門牌與路口實查重繪）──
# 東西向道路由北而南：臺灣大道三段 → 市政北七路 → 市政北二路 → 市政北一路 → 市政路
# 南北向道路由西而東：朝富路 → 河南路 → 惠來路 → 惠中路 → 文心路
#   （市政北七路自東向西序：惠中路→惠來路→惠民路→河南路→朝富路，故朝富路最西）
#   （市政路、市政北各路門牌皆自東端起編，號碼越大越偏西）
EW=[("臺灣大道三段",46),("市政北七路",108),("市政北二路",170),("市政北一路",218),("市政路",274)]
NS=[("朝富路",108),("河南路",212),("惠來路",342),("惠中路",452),("文心路",558)]
gy=""
for nm,y in EW:
    gy+=f'<line x1="86" y1="{y}" x2="574" y2="{y}" stroke="#d9cdb4" stroke-width="2"/>'
    gy+=f'<text x="80" y="{y+3.5}" font-size="9" fill="#8a7a60" text-anchor="end">{nm}</text>'
for nm,x in NS:
    gy+=f'<line x1="{x}" y1="28" x2="{x}" y2="296" stroke="#d9cdb4" stroke-width="2"/>'
    gy+=f'<text x="{x}" y="310" font-size="9" fill="#8a7a60" text-anchor="middle">{nm}</text>'

# 每案座標＋標籤避讓（dx, dy, anchor）
# ⭐ 2026-09-12 助哥手繪校正版：x 座標逐點對位自助哥在列印稿上圈註的位置。
#    助哥是七期在地經紀人，其標註為最終權威，優先於門牌推估與網路資料。
POS={"市政壹號廣場":      (440, 46, 0,-12,"middle"),   # 臺灣大道三段，近惠中路（助哥標）
     "親家T-POWER":       (285,108, 0,-12,"middle"),   # 市政北七路186（河南路～惠來路間，助哥標）
     "聯聚中雍大廈":      (390,108, 0, 19,"middle"),   # 市政北七路98（惠來路～惠中路間，助哥標）
     "NTC國家商貿中心":   (145,170, 0,-12,"middle"),   # 市政北二路282 × 朝富路口
     "鼎盛BHW":           (214,170, 0,-12,"middle"),   # 市政北二路236/238 × 河南路口
     "CBD時代廣場":       (108,212,13,  4,"start" ),   # 朝富路213
     "聯聚中維大廈":      (415,218, 0,-12,"middle"),   # 市政北一路／市政路，近惠中路（助哥標）
     "親家T3市政國際中心":(275,274, 0,-12,"middle"),   # 市政路500（河南路～惠來路間，助哥標）
     "豐邑市政都心廣場":  (383,274, 0,-12,"middle")}   # 市政路386（惠來路東側，助哥標）
# 地標層（灰色空心方塊，刻意弱於建案色點）
LM=[("秋紅谷",       108, 46, 13,  4,"start" ),  # 朝富路30・臺灣大道×朝富路口
    ("大遠百・新光", 405, 77,  0, 16,"middle"),  # 臺灣大道三段251/301・惠來～惠中間
    ("臺中市政府",   505, 77,  0, 16,"middle"),  # 臺灣大道三段99・惠中路～文心路間
    ("國家歌劇院",   322,170,  0,-13,"middle")]  # 惠來路二段101（對街聯聚仁愛88＝市政北二路口）
for nm,x,y,dx,dy,anc in LM:
    gy+=(f'<rect x="{x-5}" y="{y-5}" width="10" height="10" rx="2" '
         f'fill="#FAF7F0" stroke="#a9997a" stroke-width="2"/>')
    gy+=(f'<text x="{x+dx}" y="{y+dy}" font-size="8.6" fill="#8a7a60" '
         f'text-anchor="{anc}">{nm}</text>')

for d in D:
    x,y,dx,dy,anc=POS[d["n"]]; c=TIER[d["tier"]]
    gy+=f'<circle cx="{x}" cy="{y}" r="6" fill="{c}" stroke="#FAF7F0" stroke-width="2"/>'
    gy+=(f'<text x="{x+dx}" y="{y+dy}" font-size="9.5" fill="#3A2E1C" '
         f'text-anchor="{anc}" font-weight="700">{d["n"]}</text>')

p2=f"""<div class="page"><div class="pad">
 <div class="ch">第 一 章</div><div class="ttl">七期商辦全貌：九大建案</div>
 <div class="lead">「七期商辦」不是一個產品，是<span class="b">九個定位截然不同的建案</span>。
 下表所有數字皆由實價登錄逐筆重算（扣除車位、排除特殊關係交易、交屋潮與中古轉售分列），
 <span class="b">未採用任何坊間或同業資訊</span>。</div>

 <div class="lg"><span><i style="background:{TIER['入門']}"></i>入門</span>
  <span><i style="background:{TIER['中階']}"></i>中階</span>
  <span><i style="background:{TIER['頂級']}"></i>頂級總部</span>
  <span><i style="background:#FAF7F0;border:2px solid #a9997a"></i>地標</span></div>

 <table>
  <tr><th>建案</th><th>位置</th><th>建設公司</th><th class="num">屋齡</th><th class="num">樓</th><th class="num">戶數</th>
      <th class="num">單價<br>萬/坪</th><th class="num">坪數中位<br><span style="font-weight:400;opacity:.75">實際可用</span></th><th class="num">總價<br>中位</th><th class="num">毛<br>投報</th></tr>
  {tbl}
 </table>
 <div style="font-size:7.4pt;color:#8a7a60;margin-top:1.5mm">
  單價＝淨單價（總價與面積皆已扣除車位）。<b>成屋案採「屋主中古轉售」成交，已排除建商交屋期那批低價；預售案（聯聚中維、市政壹號）為建商銷售成交價，非市場轉售價，不宜與成屋案直接比較。</b>坪數為扣車位後之權狀坪，<b>含公設</b>；「實際可用」為扣除公設後之估算值。
  聯聚中維、市政壹號為預售案，尚無租賃實登故無投報率。
 </div>

 <div style="margin-top:6mm" class="ch">位 置 分 布</div>
 <svg viewBox="0 0 600 318" style="width:100%;height:67mm">{gy}</svg>
 <div style="font-size:7.4pt;color:#8a7a60">※ 示意圖，非按實際比例與距離，僅表達主要幹道與各案之相對關係。為求清晰，市政北三／五／六路與惠民路、惠文路未繪（七期無市政北四路）。各案定位經在地經紀人現場核對校正（2026-09-12）。</div>

 <div style="margin-top:5mm" class="note">
  <span class="b g">◆ 一句話認識七期商辦：</span>
  全區<span class="b">九個建案、2,000 餘戶</span>，單價從 <span class="b">28.8 到 80.6 萬/坪</span>（差 2.8 倍），
  總價門檻從 <span class="b">1,850 萬到 1.44 億</span>（差近 8 倍）。
  <span class="b">差距不在「好壞」，在「產品定位」</span>——下一章說明怎麼分。
 </div>
</div>{foot(2,"第一章 全貌")}</div>"""

# ── P3 第二章 分級 ──
srt=sorted([d for d in D if d['tot']], key=lambda x:x['tot'])
mx=max(x['tot'] for x in srt)
bars=""
for i,d in enumerate(srt):
    w=d['tot']/mx*380; y=18+i*30; c=TIER[d['tier']]
    lab=f'{d["tot"]/10000:.2f} 億' if d['tot']>=10000 else f'{d["tot"]:,.0f} 萬'
    bars+=(f'<rect x="150" y="{y}" width="{w:.0f}" height="16" rx="4" fill="{c}"/>'
           f'<text x="144" y="{y+12}" font-size="9.5" fill="#3A2E1C" text-anchor="end">{d["n"]}</text>'
           f'<text x="{150+w+6:.0f}" y="{y+12}" font-size="9.5" fill="#3A2E1C" font-weight="700">{lab}</text>')
bars+='<line x1="150" y1="10" x2="150" y2="265" stroke="#d9cdb4" stroke-width="1"/>'

p3=f"""<div class="page"><div class="pad">
 <div class="ch">第 二 章</div><div class="ttl">怎麼分級？看總價，不是看單價</div>
 <div class="lead">市場上常用「單價」判斷等級，這在七期商辦<span class="b">會得到相反的答案</span>。</div>

 <div class="warn" style="margin-bottom:5mm">
  <span class="b">◆ 一組會讓人誤判的數字</span>
  <table style="margin-top:3mm;font-size:8.4pt">
   <tr><th>建案</th><th class="num">單價</th><th class="num">坪數中位</th><th class="num">總價中位</th><th>實際門檻</th></tr>
   <tr><td class="b">市政壹號廣場</td><td class="num b">80.6 萬/坪（全區最高）</td><td class="num">26.2 坪</td><td class="num b">2,338 萬</td><td>最低</td></tr>
   <tr><td class="b">聯聚中雍大廈</td><td class="num">64.9 萬/坪（低於前者）</td><td class="num">220.4 坪</td><td class="num b">1.44 億</td><td>最高</td></tr>
  </table>
  <div style="margin-top:3mm"><span class="b">單價最高的那一棟，進場門檻最低。</span>
  因為<span class="b">決定你買不買得起的是總價，而總價＝單價 × 坪數</span>，
  七期商辦的坪數差距（26 坪 vs 220 坪，8 倍）遠大於單價差距（2.8 倍）。</div>
 </div>

 <div class="ch">總 價 門 檻（由低到高）</div>
 <svg viewBox="0 0 600 275" style="width:100%;height:60mm">{bars}</svg>

 <table style="margin-top:4mm">
  <tr><th>級別</th><th>總價門檻</th><th>建案</th><th>典型買方</th></tr>
  <tr><td class="b" style="color:{TIER['入門']}">入門</td><td class="b">1,850 – 2,400 萬</td>
      <td>親家 T3 市政國際中心、市政壹號廣場</td><td>新創、事務所、公司登記、小型團隊</td></tr>
  <tr><td class="b" style="color:{TIER['中階']}">中階</td><td class="b">2,500 – 3,400 萬</td>
      <td>親家 T-POWER、NTC 國家商貿中心、鼎盛 BHW、CBD 時代廣場、豐邑市政都心廣場</td>
      <td>成長期企業、區域營運據點、專業事務所</td></tr>
  <tr><td class="b" style="color:{TIER['頂級']}">頂級總部</td><td class="b">9,000 萬 – 1.5 億</td>
      <td>聯聚中維大廈、聯聚中雍大廈</td><td>上市櫃總部、企業門面、長期資產配置</td></tr>
 </table>

 <div style="margin-top:5mm" class="note">
  <span class="b g">◆ 中階這一層有 5 個建案，總價只差 900 萬。</span>
  這代表<span class="b">中階是替代性最高的一層</span>——同樣的預算有多個選擇，
  對買方是好事（比較空間大），選案時<span class="b">要比的是產品細節而非價格</span>。<br>
  <span class="b g">◆ 反過來，總價 9,000 萬以上只有聯聚雙塔。</span>沒有替代品，這是它們的稀有性來源。
 </div>
</div>{foot(3,"第二章 分級")}</div>"""

# ── P4 第三章 空間大小 + 定位矩陣 ──
SHORT={"市政壹號廣場":"市政壹號","聯聚中維大廈":"聯聚中維","聯聚中雍大廈":"聯聚中雍",
       "NTC國家商貿中心":"NTC","CBD時代廣場":"CBD","鼎盛BHW":"鼎盛BHW",
       "親家T-POWER":"T-POWER","豐邑市政都心廣場":"豐邑都心","親家T3市政國際中心":"親家T3"}
LAB={"市政壹號":(10,4,"start"),"聯聚中維":(0,-13,"middle"),"聯聚中雍":(-10,4,"end"),
     "NTC":(10,4,"start"),"鼎盛BHW":(0,-13,"middle"),"CBD":(10,4,"start"),
     "T-POWER":(-10,4,"end"),"豐邑都心":(10,4,"start"),"親家T3":(-6,4,"end")}
PX,PY=90,300
def sx(p): return PX+(p-20)/(230-20)*(560-PX)
def sy(v): return PY-(v-25)/(85-25)*(PY-30)

dots=""
for d in D:
    x,y=sx(d['ping']),sy(d['p']); c=TIER[d['tier']]
    dots+=f'<circle cx="{x:.0f}" cy="{y:.0f}" r="7" fill="{c}" stroke="#FAF7F0" stroke-width="2"/>'
    sn=SHORT[d['n']]; dx,dy,anc=LAB[sn]
    dots+=f'<text x="{x+dx:.0f}" y="{y+dy:.0f}" font-size="9.5" fill="#3A2E1C" text-anchor="{anc}" font-weight="700">{sn}</text>'
ax=f'<line x1="{PX}" y1="{PY}" x2="570" y2="{PY}" stroke="#c8bda4" stroke-width="1.5"/><line x1="{PX}" y1="20" x2="{PX}" y2="{PY}" stroke="#c8bda4" stroke-width="1.5"/>'
for v in (25,40,55,70,85): ax+=f'<text x="{PX-8}" y="{sy(v)+4:.0f}" font-size="9" fill="#8a7a60" text-anchor="end">{v}</text>'
for p in (25,75,125,175,225): ax+=f'<text x="{sx(p):.0f}" y="{PY+16}" font-size="9" fill="#8a7a60" text-anchor="middle">{p}</text>'
ax+=f'<text x="{PX-8}" y="16" font-size="9" fill="#8a7a60" text-anchor="end">萬/坪</text><text x="570" y="{PY+16}" font-size="9" fill="#8a7a60" text-anchor="end">坪數（扣車位）</text>'

p4=f"""<div class="page"><div class="pad">
 <div class="ch">第 三 章</div><div class="ttl">空間大小：選案的第一道篩子</div>
 <div class="lead">先問「我要幾坪」，比先問「我有多少預算」更快找到答案——
 因為<span class="b">很多建案根本沒有你要的坪數</span>。</div>

 <div class="lg"><span><i style="background:{TIER['入門']}"></i>入門</span>
  <span><i style="background:{TIER['中階']}"></i>中階</span>
  <span><i style="background:{TIER['頂級']}"></i>頂級總部</span></div>
 <svg viewBox="0 0 600 326" style="width:100%;height:70mm">{ax}{dots}</svg>
 <div style="font-size:7.4pt;color:#8a7a60;margin-top:1mm">橫軸＝扣除車位後之權狀坪數中位；縱軸＝淨單價。每點為一建案；圖中為簡稱，全名見第一章。</div>

 <div style="margin-top:5mm" class="note">
  <span class="b g">◆ 看得出一條規律：坪數越大、單價越低。</span>
  市政壹號 26 坪／80.6 萬，親家 T3 61 坪／28.8 萬，聯聚中雍 220 坪／64.9 萬。<br>
  例外是<span class="b">聯聚雙塔</span>——坪數大、單價也高，因為它賣的不是空間，是<span class="b">企業門面與地標性</span>。
 </div>

 <div style="margin-top:5mm" class="ch">依 坪 數 需 求 找 建 案</div>
 <table>
  <tr><th>你需要的坪數</th><th>可選建案</th><th>備註</th></tr>
  <tr><td class="b">25 – 35 坪<br><span style="font-weight:400;font-size:7.2pt;color:#8a7a60">可用約 15–22 坪</span></td><td>市政壹號廣場</td><td>全區唯一的小坪數新案（預售）</td></tr>
  <tr><td class="b">60 – 75 坪<br><span style="font-weight:400;font-size:7.2pt;color:#8a7a60">可用約 35–48 坪</span></td><td>親家 T3、親家 T-POWER、NTC 國家商貿中心</td><td>選擇最多的區間</td></tr>
  <tr><td class="b">80 – 105 坪<br><span style="font-weight:400;font-size:7.2pt;color:#8a7a60">可用約 46–67 坪</span></td><td>鼎盛 BHW、CBD 時代廣場、豐邑市政都心廣場</td><td>中大型辦公需求</td></tr>
  <tr><td class="b">130 – 160 坪<br><span style="font-weight:400;font-size:7.2pt;color:#8a7a60">可用約 75–102 坪</span></td><td>聯聚中維大廈</td><td>亦有 80 坪級小戶型</td></tr>
  <tr class="hl"><td class="b">220 坪以上／整層<br><span style="font-weight:400;font-size:7.2pt;color:#8a7a60">可用約 128 坪以上</span></td><td>聯聚中雍大廈</td><td>可兩戶合併約 441 坪，全區唯一</td></tr>
 </table>
 <div style="font-size:7.4pt;color:#8a7a60;margin-top:1.5mm">
  ※ 上表為各案「主力坪數」。NTC 與 CBD 另有大坪數戶（實登最大分別達 838 坪、456 坪），屬少數特例。
 </div>

 <div style="margin-top:4mm" class="warn">
  <span class="b">◆ 別忽略公設比。</span>七期商辦公設比約 <span class="b">36% – 42%</span>，
  也就是每買一坪，<span class="b">實際可用約 0.58 – 0.64 坪</span>。
  大廳、電梯廳、機電、中繼機房都在公設裡，這是頂級商辦的常態，不是缺點；
  但<span class="b">算「實際每坪可用成本」時要納入</span>。公設比最低的是 CBD 時代廣場（36.17%）。
 </div>
</div>{foot(4,"第三章 空間")}</div>"""

# ── P5 第四章 價格與總價帶 ──
PB=[("NTC國家商貿中心","≤107",32.48,44.67),("鼎盛BHW","≤104",28.64,34.65),
    ("CBD時代廣場","≤104",29.38,35.05),("親家T3市政國際中心","≤103",24.58,28.83),
    ("親家T-POWER","≤102",28.74,33.33),("豐邑市政都心廣場","≤102",26.68,30.39)]
wrow="".join(
 f'<tr><td class="b">{n}</td><td class="num">民國 {w} 年</td><td class="num">{a:.2f}</td>'
 f'<td class="num b">{b:.2f}</td><td class="num b g">+{(b/a-1)*100:.1f}%</td></tr>'
 for n,w,a,b in sorted(PB,key=lambda x:-(x[3]/x[2])))

# 單價長條（水平）
BX,BW=118,430; mx=max(d['p'] for d in D)
bars=""
for i,d in enumerate(sorted(D,key=lambda x:-x['p'])):
    y=10+i*26; w=d['p']/mx*BW; c=TIER[d['tier']]
    bars+=f'<text x="{BX-8}" y="{y+13}" font-size="9.5" fill="#3A2E1C" text-anchor="end">{d["n"]}</text>'
    bars+=f'<rect x="{BX}" y="{y+2}" width="{w:.1f}" height="15" rx="4" fill="{c}"/>'
    bars+=f'<text x="{BX+w+7:.0f}" y="{y+13}" font-size="9.5" font-weight="700" fill="#3A2E1C">{d["p"]:.1f}</text>'

p5=f"""<div class="page"><div class="pad">
 <div class="ch">第 四 章</div><div class="ttl">價格：單價看成本，總價看門檻</div>
 <div class="lead">單價（萬元／坪）全部<span class="b">扣除車位後重算</span>——
 實價登錄原始的「單價」欄位只在車位價格有揭露時才扣，是不可直接比較的。
 這是本報告與坊間資訊最大的差別。</div>

 <div class="lg"><span><i style="background:{TIER['入門']}"></i>入門</span>
  <span><i style="background:{TIER['中階']}"></i>中階</span>
  <span><i style="background:{TIER['頂級']}"></i>頂級總部</span></div>
 <svg viewBox="0 0 600 256" style="width:100%;height:55mm">{bars}
  <text x="{BX}" y="252" font-size="9" fill="#8a7a60">淨單價（萬元／坪）・已扣車位</text></svg>

 <div class="note" style="margin-top:2mm">
  <span class="b g">◆ 單價從 28.8 到 80.6，差 2.8 倍；但這不代表貴的就買不起。</span>
  市政壹號 80.6 萬／坪是全場最高，總價卻只要 2,338 萬——因為它只有 26 坪。
  <span class="b">單價決定每坪成本，總價決定你進不進得來。</span>
 </div>

 <div style="margin-top:6mm" class="ch">交 屋 潮 ≠ 行 情 ： 估 價 必 分 的 兩 組 數 字</div>
 <div style="font-size:8.5pt;color:#6b5c46;line-height:1.8;margin-bottom:2mm">
  新案交屋那幾年會出現一批「建商銷售的成交」，價格明顯低於日後的中古轉售。
  把兩者混在一起平均，會<span class="b">嚴重低估行情（最多差 37.5%）</span>。本報告一律只採中古轉售組。</div>
 <table>
  <tr><th>案名</th><th>交屋潮年度</th><th>交屋潮均價</th><th>中古轉售均價</th><th>價差</th></tr>
  {wrow}
 </table>
 <div class="warn" style="margin-top:4mm">
  <span class="b">◆ 看到「某某商辦成交價才 28 萬」時要先問一句：那是哪一年？</span>
  很可能是交屋潮那批。<span class="b">同一棟樓，兩組數字可以差四成。</span>
 </div>
</div>{foot(5,"第四章 價格")}</div>"""

# ── P6 第五章 投報率 ──
YD=[d for d in D if d['y']]
ymx=5.0; YX,YW=140,380
ybar=""
for i,d in enumerate(sorted(YD,key=lambda x:-x['y'])):
    y=14+i*28; w=d['y']/ymx*YW; c=TIER[d['tier']]
    ybar+=f'<text x="{YX-8}" y="{y+13}" font-size="9.5" fill="#3A2E1C" text-anchor="end">{d["n"]}</text>'
    ybar+=f'<rect x="{YX}" y="{y+2}" width="{w:.1f}" height="15" rx="4" fill="{c}"/>'
    ybar+=f'<text x="{YX+w+7:.0f}" y="{y+13}" font-size="9.5" font-weight="700" fill="#3A2E1C">{d["y"]:.2f}%</text>'
med=st.median(YS)
ybar+=(f'<line x1="{YX+med/ymx*YW:.0f}" y1="8" x2="{YX+med/ymx*YW:.0f}" y2="{14+len(YD)*28}" '
       f'stroke="#3A2E1C" stroke-width="1.5" stroke-dasharray="4 3"/>'
       f'<text x="{YX+med/ymx*YW:.0f}" y="6" font-size="8.5" fill="#3A2E1C" text-anchor="middle">中位 {med:.2f}%</text>')

p6=f"""<div class="page"><div class="pad">
 <div class="ch">第 五 章</div><div class="ttl">投報率的真相：市場已經把它拉平了</div>
 <div class="lead">這是本報告最重要的一個發現，也是最反直覺的一個：
 <span class="b">單價差 2.25 倍的八棟商辦，毛投報率幾乎一樣。</span></div>

 <div class="kpi">
  <div><div class="v">{min(YS):.2f}–{max(YS):.2f}<span style="font-size:11pt">%</span></div><div class="l">八棟毛投報區間</div></div>
  <div><div class="v">{med:.2f}<span style="font-size:11pt">%</span></div><div class="l">中位數</div></div>
  <div><div class="v">{st.pstdev(YS):.2f}</div><div class="l">標準差（百分點）</div></div>
  <div><div class="v">2.25<span style="font-size:11pt">倍</span></div><div class="l">同期單價最大差距</div></div>
 </div>

 <svg viewBox="0 0 600 {14+len(YD)*28+18}" style="width:100%;height:53mm">{ybar}</svg>
 <div style="font-size:7.4pt;color:#8a7a60">毛投報＝年租金 ÷ 成交總價（中古轉售組）。未計管理費、稅、空置與裝修攤提，實際淨報酬低於此數。</div>

 <div class="note" style="margin-top:5mm">
  <span class="b g">◆ 為什麼會這樣？</span>因為<span class="b">租金與售價是同步反映等級的</span>。
  聯聚中雍單價是親家 T3 的 2.25 倍，租金也正好是它的 2.14 倍——兩者相除，投報率就打平了。
  這代表七期商辦的<span class="b">定價效率很高，沒有哪一棟「特別划算」</span>。
 </div>

 <div class="warn" style="margin-top:4mm">
  <span class="b">◆ 所以：想靠「選棟」拉高投報率，數據上做不到。</span><br>
  選棟要看<span class="b">產品、坪數、門面需求與自用規劃</span>，不是投報率。
  若買方拿「聽說某某棟投報率比較高」來議價——那多半是把交屋潮價格當成本、或只看單一個案。
 </div>

 <div style="margin-top:5mm" class="card">
  <div class="b" style="font-size:10pt;color:#3A2E1C">唯一的例外：豐邑市政都心廣場 4.38%</div>
  <div style="font-size:8.5pt;line-height:1.85;color:#6b5c46;margin-top:2mm">
   明顯高出其餘七棟（3.17–3.36%）。數據上看得到的原因有三：
   ① 單價 30.39 萬為全場次低，但屋齡 16 年也是全場最老；
   ② 租金 1,108 元／坪，僅次於聯聚中雍，租金相對強勢；
   ③ 樣本較少（買賣 62 筆、租賃 66 筆），統計穩定度低於其他棟。<br>
   <span class="b">收租型買方值得現場一看</span>；但屋齡與後續維護成本要一併算進去。
  </div>
 </div>
</div>{foot(6,"第五章 投報")}</div>"""

# ── P7 第六章 樓層溢價 ──
FLR=[("聯聚中維大廈",22.4,"敏感"),("聯聚中雍大廈",16.0,"敏感"),
     ("NTC國家商貿中心",11.4,"鈍感"),("CBD時代廣場",10.1,"鈍感"),("市政壹號廣場",3.4,"鈍感")]
fmx=25.0; FX,FW=130,330
fbar=""
for i,(n,v,k) in enumerate(FLR):
    y=12+i*30; w=v/fmx*FW; c="#1baf7a" if k=="敏感" else "#8a7a60"
    fbar+=f'<text x="{FX-8}" y="{y+14}" font-size="9.5" fill="#3A2E1C" text-anchor="end">{n}</text>'
    fbar+=f'<rect x="{FX}" y="{y+2}" width="{w:.1f}" height="16" rx="4" fill="{c}"/>'
    fbar+=f'<text x="{FX+w+7:.0f}" y="{y+14}" font-size="9.5" font-weight="700" fill="#3A2E1C">+{v:.1f}%</text>'

p7=f"""<div class="page"><div class="pad">
 <div class="ch">第 六 章</div><div class="ttl">樓層溢價分兩派：決定你該談什麼</div>
 <div class="lead">「高樓層一定比較貴」——在七期商辦，這句話只對一半。
 實登逐層重算後，九案清楚分成<span class="b">樓層敏感</span>與<span class="b">樓層鈍感</span>兩派，
 而這兩派<span class="b">議價時該談的東西完全不同</span>。</div>

 <svg viewBox="0 0 600 180" style="width:100%;height:40mm">{fbar}
  <text x="{FX}" y="176" font-size="9" fill="#8a7a60">高樓層相對低樓層之單價溢價（實登分層重算）</text></svg>

 <table style="margin-top:4mm">
  <tr><th style="width:18%">派別</th><th style="width:34%">標的</th><th style="width:48%">議價時該談什麼</th></tr>
  <tr><td class="b">樓層敏感</td><td>聯聚中維 +22.4%<br>聯聚中雍 +16.0%</td>
      <td>樓層、視野、地標性。<span class="b">高低樓層是兩個產品</span>，不可用同一單價換算。</td></tr>
  <tr><td class="b">樓層鈍感</td><td>NTC +11.4%<br>CBD +10.1%（非單調）<br>市政壹號 +3.4%</td>
      <td>坪數、格局、車位席數、總價。<span class="b">拿樓層要溢價站不住腳</span>，實登看得出來。</td></tr>
 </table>

 <div class="note" style="margin-top:5mm">
  <span class="b g">◆ 市政壹號廣場只有 +3.4%，是最極端的例子。</span>
  35 層樓，但樓層幾乎不影響單價——因為<span class="b">產品高度同質</span>（清一色 26 坪小單位），
  買方在意的是總價與可否公司登記，不是視野。<span class="b">這類案子，買低樓層的 CP 值最高。</span>
 </div>

 <div class="warn" style="margin-top:4mm">
  <span class="b">◆ CBD 時代廣場的「非單調」要特別注意。</span>
  它的高樓層平均較貴，但<span class="b">中間樓層出現價格倒掛</span>——
  代表個別戶的格局、面向、釋出時機影響大於樓層。
  <span class="b">這一棟不能用「幾樓 × 每坪多少」推估，必須逐戶看實登。</span>
 </div>
</div>{foot(7,"第六章 樓層")}</div>"""

# ── P8 / P9 第七章 逐案優劣 ──
CASES=[
 ("市政壹號廣場","26 坪｜80.6 萬／坪｜2,338 萬｜預售 2028",
  ["全區<b>唯一的小坪數新案</b>，26 坪即可入手","新案中<b>總價門檻最低</b>，2,338 萬","臺灣大道三段門牌，辨識度高","樓層溢價僅 +3.4%，<b>買低樓層最划算</b>"],
  ["單價 80.6 萬／坪為<b>全場最高</b>","890 戶為全區最多，<b>未來轉售與出租競爭最激烈</b>","預售案，2028 年才交屋，<b>無租金可驗證投報</b>","預售價是建商銷售成交價，不等於日後市場轉售價"]),
 ("聯聚中維大廈","132 坪｜69.3 萬／坪｜9,255 萬｜興建中",
  ["<b>42 樓為全區最高</b>，天際線地標","聯聚品牌，七期頂級商辦的既有認知","<b>81 坪小戶型與 131–161 坪大戶並存</b>，彈性高","樓層溢價 +22.4% 全場最高 → 高樓層具稀缺性"],
  ["興建中，<b>尚無租賃實績可驗證投報</b>","總價逼近一億，買方池極小","<b>高低樓層價差大</b>，議價前務必先確認樓層基準","與聯聚中雍在同一買方池中彼此替代"]),
 ("聯聚中雍大廈","220 坪｜64.9 萬／坪｜1.44 億｜屋齡 8 年｜3.20%",
  ["<b>全區唯一整層產品</b>，可兩戶合併約 441 坪","僅 73 戶，<b>出入最單純</b>，適合總部門面","租金 1,728 元／坪，<b>全區最高</b>","企業門面與地標性，無替代品"],
  ["總價 1.44 億，<b>流動性全區最低</b>","成屋轉售樣本僅 47 筆，<b>行情需逐戶判斷</b>","投報 3.20% 與中階案無異，<b>不適合純收租</b>","管理與維運成本對應頂級規格，須一併估算"]),
 ("NTC國家商貿中心","74 坪｜44.7 萬／坪｜2,690 萬｜屋齡 8 年｜3.33%",
  ["中階級距中<b>租金最強</b>（1,240 元／坪）","74 坪為最泛用的中型坪數","另有大坪數戶（實登最大 838 坪），<b>擴充彈性大</b>","屋齡 8 年，設備仍新"],
  ["<b>交屋潮與中古價差 +37.5%，全場最大</b> → 看錯年份極易誤判行情","單價 44.7 萬已是中階天花板，<b>議價空間相對小</b>","243 戶，出入較雜"]),
 ("CBD時代廣場","92 坪｜35.1 萬／坪｜3,173 萬｜屋齡 10 年｜3.17%",
  ["<b>公設比 36.17% 為全區最低</b> → 每坪實際可用最多","92 坪中大型，格局選擇多，亦有 456 坪大戶","朝馬／七期西側，周邊生活機能成熟"],
  ["租金 925 元／坪偏低，<b>投報 3.17% 全場最低</b>","255 戶，戶數偏多","<b>樓層價格非單調</b>，必須逐戶查實登，不能用樓層推估"]),
 ("鼎盛BHW","82 坪｜34.7 萬／坪｜3,068 萬｜屋齡 12 年｜3.32%",
  ["<b>一案兩棟，產品互補</b>：A 棟 82 坪壓在 3,000 萬內；B 棟 112 坪投報 3.45% 較優","車位 828 席，<b>停車最充裕</b>","基地 1,641 坪，量體完整"],
  ["屋齡 12 年，設備進入更新期","<b>實登社區名稱空白</b>、樂居地址亦有誤 → 市場資訊落差大，查價困難","公設比 38.16%，中上水準"]),
 ("親家T-POWER","69 坪｜33.3 萬／坪｜2,542 萬｜屋齡 9 年｜3.24%",
  ["<b>中階級距的最低門檻</b>，2,542 萬","69 坪是市場最好用的中型坪數","176 戶相對單純","屋齡 9 年，中階中較新"],
  ["<b>28 樓為全區偏低</b>，視野與地標性較弱","租金 901 元／坪偏低","實登登記為「親家市政廣場」，<b>極易與親家 T3 混淆</b>"]),
 ("豐邑市政都心廣場","102 坪｜30.4 萬／坪｜3,344 萬｜屋齡 16 年｜4.38%",
  ["<b>毛投報 4.38% 為全區最高</b>","租金 1,108 元／坪，全區第二高","102 坪大空間，單價僅 30.4 萬","38 樓、市政路正面，樓高有優勢"],
  ["<b>屋齡 16 年為全區最老</b>，維護與設備更新成本要估進去","樣本僅買賣 62 筆、租賃 66 筆，<b>數字穩定度低於其他棟</b>","總價 3,344 萬為中階最高"]),
 ("親家T3市政國際中心","61 坪｜28.8 萬／坪｜1,850 萬｜屋齡 13 年｜3.36%",
  ["<b>總價 1,850 萬，全區進場門檻最低</b>","單價 28.8 萬／坪，全區最低","61 坪適合 10–20 人團隊","投報 3.36%，高於全區中位"],
  ["租金 808 元／坪，<b>全區最低</b>","屋齡 13 年","29 樓、市政路末端，<b>門面感相對弱</b>","轉售時買方同樣以價格為主要訴求，<b>議價壓力大</b>"]),
]
TMAP={d["n"]:d["tier"] for d in D}
def case(n,sub,pro,con):
    c=TIER[TMAP[n]]
    P="".join(f"<li>{x}</li>" for x in pro); C="".join(f"<li>{x}</li>" for x in con)
    return (f'<div class="cs"><div class="csh">'
            f'<span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:{c};margin-right:5px"></span>'
            f'<span class="csn">{n}</span><span class="css">{sub}</span></div>'
            f'<div class="csb"><div><div class="pl">優　勢</div><ul>{P}</ul></div>'
            f'<div><div class="cl">要留意</div><ul>{C}</ul></div></div></div>')

CS="""
.cs{background:#fff;border:1px solid #e6dcc8;border-left:3px solid #B8924F;padding:3mm 4mm;margin-bottom:3mm}
.csh{display:flex;align-items:baseline;border-bottom:1px solid #efe7d6;padding-bottom:1.5mm;margin-bottom:1.5mm}
.csn{font-weight:700;font-size:10pt;color:#3A2E1C;font-family:"Noto Serif CJK TC",serif}
.css{margin-left:auto;font-size:7.6pt;color:#8a7a60;font-variant-numeric:tabular-nums}
.csb{display:flex;gap:5mm}.csb>div{flex:1}
.csb ul{margin-left:4mm}
.csb li{font-size:7.7pt;line-height:1.6;margin-bottom:.4mm;color:#4a3f2e}
.pl,.cl{font-size:7.2pt;letter-spacing:.2em;margin-bottom:1mm}
.pl{color:#1b8f66}.cl{color:#b2563a}
"""
p8=f"""<div class="page"><div class="pad">
 <div class="ch">第 七 章 ／ 上</div><div class="ttl">九案逐案優劣（一）</div>
 <div class="lead" style="margin-bottom:4mm">每一案的「要留意」欄，寫的是<span class="b">實登數據看得出來的事實</span>，
 不是缺點評價。沒有完美的案子，只有適不適合你。</div>
 {"".join(case(*c) for c in CASES[:5])}
</div>{foot(8,"第七章 逐案")}</div>"""
p9=f"""<div class="page"><div class="pad">
 <div class="ch">第 七 章 ／ 下</div><div class="ttl">九案逐案優劣（二）</div>
 <div class="lead" style="margin-bottom:4mm">以下四案總價集中在 2,500–3,400 萬，
 是<span class="b">替代性最高、議價空間也最大</span>的一層。</div>
 {"".join(case(*c) for c in CASES[5:])}
 <div class="note" style="margin-top:3mm">
  <span class="b g">◆ 中階這一層擠了六棟</span>，總價從 2,542 萬到 3,344 萬只差 800 萬。
  預算落在這個區間的買方<span class="b">有六個選擇，議價籌碼最多</span>；
  反過來說，這一層的屋主最需要把「自己這棟贏在哪」講清楚。
 </div>
</div>{foot(9,"第七章 逐案")}</div>"""

# ── P10 第八章 怎麼挑 ──
STEPS=[("①","先問坪數，不要先問預算",
        "客戶常低估「自己要的坪數在七期值多少」。先確定<b>你要幾坪</b>，九案立刻刷掉一半——"
        "25–35 坪只有市政壹號；220 坪以上只有聯聚中雍。"),
       ("②","用總價分級，不要用單價分級",
        "單價最高的市政壹號（80.6 萬）總價門檻最低（2,338 萬）。<b>決定你進不進得來的是總價</b>，"
        "單價只決定每坪成本。"),
       ("③","確認你買的是「空間」還是「門面」",
        "買空間 → 中階六棟挑公設比與坪效（CBD 公設比最低 36.17%）。"
        "買門面 → 只有聯聚雙塔，沒有替代品，別在中階裡找門面。"),
       ("④","投報率不是選棟依據",
        "八棟毛投報 3.17–4.38%，中位 3.29%，標準差僅 0.37。"
        "<b>選棟拉不高投報率</b>，唯一值得追的變數是<b>買進價格</b>。"),
       ("⑤","查行情時先確認「哪一年、扣不扣車位」",
        "交屋潮價與中古轉售價最多差 37.5%；實登原始單價欄只在車位有揭露時才扣車位。"
        "<b>兩個陷阱沒排除，行情就是錯的。</b>")]
sl="".join(f'<tr><td style="width:9%;font-size:13pt;color:#B8924F;font-weight:700;text-align:center">{a}</td>'
           f'<td style="width:30%" class="b">{b}</td><td style="width:61%;line-height:1.75">{c}</td></tr>' for a,b,c in STEPS)

SCEN=[("10–20 人自用，預算 2,000 萬內","親家 T3 市政國際中心","全區唯一總價 2,000 萬以下、61 坪的選擇"),
      ("成長期企業，30–50 人，3,000 萬上下","親家 T-POWER、NTC、鼎盛 BHW A 棟","69–82 坪；此區間選擇最多，議價空間最大"),
      ("要大空間、坪效優先","CBD 時代廣場","92 坪，公設比 36.17% 全區最低"),
      ("收租為主","豐邑市政都心廣場","毛投報 4.38% 全區最高；但屋齡 16 年，維護成本要估"),
      ("公司登記／小型事務所／新案","市政壹號廣場","26 坪、2,338 萬；但 890 戶競爭激烈，買低樓層 CP 值最高"),
      ("上市櫃總部、企業門面","聯聚中雍、聯聚中維","1 億以上，沒有替代品；中雍可整層 220 坪、合併 441 坪")]
sc="".join(f'<tr><td class="b">{a}</td><td class="b g">{b}</td><td>{c}</td></tr>' for a,b,c in SCEN)

p10=f"""<div class="page"><div class="pad">
 <div class="ch">第 八 章</div><div class="ttl">怎麼挑：五個步驟</div>
 <div class="lead">九案看完，最後把它收斂成一條可以直接走的流程。</div>
 <table style="font-size:8.6pt">{sl}</table>

 <div style="margin-top:7mm" class="ch">情 境 對 照 ： 你 是 哪 一 種 買 方</div>
 <table>
  <tr><th style="width:31%">你的情境</th><th style="width:28%">優先看</th><th style="width:41%">理由</th></tr>
  {sc}
 </table>

 <div class="note" style="margin-top:6mm">
  <span class="b g">◆ 最後一句實話：</span>七期商辦的定價效率很高，
  <span class="b">買到「便宜貨」的機會不多，但買錯產品的機會很多。</span>
  挑對坪數、挑對定位，比多殺兩萬一坪重要得多。
 </div>

 <div class="card" style="margin-top:6mm">
  <div class="b" style="font-size:10pt;color:#3A2E1C">需要逐案實登明細、或針對特定一棟做估價？</div>
  <div style="font-size:8.6pt;line-height:1.9;color:#6b5c46;margin-top:2mm">
   本報告背後是九案 2,700+ 筆實價登錄的逐筆重算資料庫，
   可依單一建案出具<b>含逐筆成交明細、分層分坪、租金對照的完整估價報告書</b>。<br>
   <span class="b" style="color:#3A2E1C">劉力助（助哥）｜永慶不動產 七期河南市政店</span>
  </div>
 </div>
</div>{foot(10,"第八章 怎麼挑")}</div>"""

# ── P11 第九章 資料來源與免責 ──
def rentf(d): return "—" if not d["rent"] else f'{d["rent"]:,.0f}'
def yf(d): return "—" if not d["y"] else f'{d["y"]:.2f}%'

sr="".join(f'<tr><td class="b">{d["n"]}</td><td>{d["src"]}</td>'
           f'<td class="num b">{d["p"]:.2f}</td>'
           f'<td class="num">{rentf(d)}</td>'
           f'<td class="num">{yf(d)}</td></tr>' for d in D)

p11=f"""<div class="page"><div class="pad">
 <div class="ch">第 九 章</div><div class="ttl">資料來源、處理方法與免責</div>
 <div class="lead">本報告不引用任何坊間網站、同業整理或媒體轉述的價格。
 所有數字皆自<span class="b">內政部不動產交易實價查詢服務網</span>下載原始檔後逐筆重算。</div>

 <div class="ch">處 理 方 法（ 四 道 修 正 ）</div>
 <table style="margin-bottom:6mm">
  <tr><th style="width:26%">修正項目</th><th>做法與理由</th></tr>
  <tr><td class="b">① 扣除車位</td><td>實登「單價」欄<span class="b">只在車位價格有揭露時才扣車位</span>，口徑不一致。
   本報告一律重算：淨單價 ＝（總價 − 車位價）÷（總面積 − 車位面積）。車位面積逐案由車位分頁加總，
   因坡道平面（約 9.63 坪）與坡道機械（約 3.47 坪）差距達 2.8 倍。</td></tr>
  <tr><td class="b">② 排除非常規交易</td><td>排除親友、員工、共有人、特殊關係人交易，以及已解約案件。</td></tr>
  <tr><td class="b">③ 分離交屋潮</td><td>新案交屋期的建商銷售成交與日後中古轉售分列統計，
   兩者最大差距達 +37.5%。<span class="b">本報告採用的行情一律為中古轉售組。</span></td></tr>
  <tr><td class="b">④ 不設查詢條件</td><td>撈取時<span class="b">不勾選樓層別、坪數區間、建物型態</span>，避免樣本偏誤。
   另：商辦認定<span class="b">只認「主要用途＝辦公用」</span>，不採建物型態欄
   （同一棟樓在買賣與租賃兩套登錄中的型態欄可能不同）。</td></tr>
 </table>

 <div class="ch">各 案 樣 本 基 準</div>
 <table>
  <tr><th>案名</th><th>單價基準樣本</th><th>淨單價<br>（萬/坪）</th><th>租金<br>（元/坪/月）</th><th>毛投報</th></tr>
  {sr}
 </table>
 <div style="font-size:7.4pt;color:#8a7a60;margin-top:1.5mm">
  合計實登逾 2,700 筆（買賣 2,000+、租賃 1,100+）。撈取日 2026-09-11。</div>

 <div class="warn" style="margin-top:6mm">
  <span class="b">◆ 免責聲明</span><br>
  本報告係依公開之實價登錄資料整理分析，僅供參考，<span class="b">不構成任何價格保證、投資建議或要約</span>。
  毛投報率為年租金除以成交總價，<span class="b">未扣除管理費、地價稅、房屋稅、空置期、裝修攤提與交易成本</span>，
  實際淨報酬將低於本表數字。個案成交條件（樓層、面向、格局、車位配置、屋況、交易時點、賣方動機）
  差異極大，實際價格應以現場查看與個案評估為準。不動產價格受政策、利率與景氣影響，
  <span class="b">過去成交紀錄不代表未來表現，本公司不保證增值或任何報酬。</span>
 </div>

 <div style="margin-top:8mm;border-top:1px solid #d9cdb4;padding-top:4mm;font-size:8.4pt;color:#6b5c46;line-height:1.9">
  <span class="b" style="font-size:10pt;color:#3A2E1C">劉力助（助哥）</span>　永慶不動產 七期河南市政店<br>
  百富國際開發有限公司｜中市地價二字第1070032073號<br>
  製表 2026-09-12
 </div>
</div>{foot(11,"第九章 資料來源")}</div>"""

# ── 組版與輸出 ──
html=("<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'>"
      f"<style>{CSS}{CS}</style></head><body>"
      f"{p1}{p2}{p3}{p4}{p5}{p6}{p7}{p8}{p9}{p10}{p11}</body></html>")
OUT=Path("/home/user/my-website/deliverables"); OUT.mkdir(exist_ok=True)
tmp=SC/"_qiqi_report9.html"; tmp.write_text(html,encoding="utf-8")

from playwright.sync_api import sync_playwright
pdf=OUT/"台中七期商辦全解析_九大建案完整比較.pdf"
with sync_playwright() as pw:
    b=pw.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg=b.new_page(); pg.goto(tmp.as_uri()); pg.wait_for_timeout(900)
    pg.pdf(path=str(pdf),format="A4",print_background=True,prefer_css_page_size=True)
    b.close()
print("OK",pdf)
