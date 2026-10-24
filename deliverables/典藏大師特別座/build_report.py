"""典藏大師特別座 銷售報告書（給買方）：讀 summary.json → 產 HTML → Playwright 輸出 PDF。
口徑：透天比「總價÷建物總面積」與「總價÷土地面積」；本戶另列「房屋單價（已扣車位）」（B1 車位以 150 萬估）。
所有統計逐年呈現、不跨年合併（助哥 2026-10-24）。對外報告不放建議成交價，試算以開價計。"""
import base64, json
from pathlib import Path

HERE = Path(__file__).parent
OUT_HTML = HERE / '典藏大師特別座_銷售報告書.html'
OUT_PDF = HERE / '典藏大師特別座_銷售報告書.pdf'
S = json.load(open(HERE / 'summary.json'))
L = S['本戶']
ASK = L['開價']
CSS = (HERE / '_style.css').read_text()

def img(name):
    mime = 'image/png' if name.endswith('png') else 'image/jpeg'
    return f"data:{mime};base64,{base64.b64encode((HERE / name).read_bytes()).decode()}"
def wan(v): return '—' if v is None else f'{v:,.0f}'
def f1(v): return '—' if v is None else f'{v:.1f}'
def f2(v): return '—' if v is None else f'{v:.2f}'
def pct(a, b): return (a / b - 1) * 100

P_ALL = '總價÷建物總坪（車位一起算）'
P_HOUSE = '房屋單價（已扣車位）'
P_LAND = '總價÷土地坪'
COMM = [c for c in S['本社區'] if not c['排除']]
C108 = COMM[0]
CY = {d['年']: d for d in S['比較組逐年']}
Z7 = {d['年']: d for d in S['七期逐年']}
CMP = S['比較組']
LAND_MED = [CY[y]['地坪中位'] for y in CY]

# ---------- 圖：七期透天土地單價逐年中位（108–115）＋本社區 108 成交＋本戶開價 ----------
def svg_open(W, H): return [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC" font-size="10">']
W, H, Lm, R, T, B = 560, 230, 40, 16, 26, 34
YMAX = 140
years = list(range(108, 116))
bw = (W - Lm - R) / len(years)
def X(i): return Lm + bw * i + bw / 2
def Y(v): return T + (YMAX - v) * (H - T - B) / YMAX
svg = svg_open(W, H)
for v in range(0, YMAX + 1, 20):
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e3e8ec"/><text x="{Lm-6}" y="{Y(v)+3:.1f}" text-anchor="end" fill="#7b8794">{v}</text>')
for i, y in enumerate(years):
    v = Z7[y]['土地單價中位']
    svg.append(f'<rect x="{X(i)-bw*0.3:.1f}" y="{Y(v):.1f}" width="{bw*0.6:.1f}" height="{Y(0)-Y(v):.1f}" rx="3" fill="#1F4E5F" opacity=".85"/>'
               f'<text x="{X(i):.1f}" y="{Y(v)+22:.1f}" text-anchor="middle" fill="#fff" font-size="9" font-weight="700">{v:.1f}</text>'
               f'<text x="{X(i):.1f}" y="{H-B+14}" text-anchor="middle" fill="#7b8794" font-size="9">{y if y < 115 else "115*"}</text>'
               f'<text x="{X(i):.1f}" y="{H-B+26}" text-anchor="middle" fill="#9aa7b2" font-size="8">n={Z7[y]["n"]}</text>')
svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(L["土地單價"]):.1f}" y2="{Y(L["土地單價"]):.1f}" stroke="#C0392B" stroke-width="1.3" stroke-dasharray="4 3"/>'
           f'<text x="{Lm+4}" y="{Y(L["土地單價"])-5:.1f}" fill="#C0392B" font-size="9" font-weight="700">本戶開價 {L["土地單價"]:.1f}</text>')
svg.append(f'<circle cx="{X(0)+bw*0.36:.1f}" cy="{Y(C108["土地單價"]):.1f}" r="5" fill="#C8963E" stroke="#fff" stroke-width="1.2"/>'
           f'<text x="{X(0)+bw*0.36:.1f}" y="{Y(C108["土地單價"])-9:.1f}" text-anchor="middle" fill="#8a6a2c" font-size="8.6" font-weight="700" paint-order="stroke" stroke="#F7F9FA" stroke-width="3">本社區 {C108["土地單價"]:.1f}</text>')
svg.append(f'<text x="{W-R}" y="{T-12}" text-anchor="end" fill="#7b8794" font-size="9">單位：萬元／土地坪（{P_LAND}）・七期重劃區透天逐年中位</text></svg>')
chart_land = ''.join(svg)

# ---------- 圖：比較組逐筆（112–115）土地單價 vs 建坪單價散佈 ----------
W2, H2, L2, R2, T2, B2 = 560, 300, 40, 16, 34, 34
XMIN, XMAX, YMIN2, YMAX2 = 70, 170, 25, 65
def X2(v): return L2 + (v - XMIN) * (W2 - L2 - R2) / (XMAX - XMIN)
def Y2(v): return T2 + (YMAX2 - v) * (H2 - T2 - B2) / (YMAX2 - YMIN2)
s2 = svg_open(W2, H2)
for v in range(YMIN2, YMAX2 + 1, 10):
    s2.append(f'<line x1="{L2}" x2="{W2-R2}" y1="{Y2(v):.1f}" y2="{Y2(v):.1f}" stroke="#e3e8ec"/><text x="{L2-6}" y="{Y2(v)+3:.1f}" text-anchor="end" fill="#7b8794">{v}</text>')
for v in range(XMIN, XMAX + 1, 20):
    s2.append(f'<text x="{X2(v):.1f}" y="{H2-B2+14}" text-anchor="middle" fill="#7b8794" font-size="9">{v}</text>')
s2.append(f'<text x="{(L2+W2-R2)/2:.0f}" y="{H2-6}" text-anchor="middle" fill="#7b8794" font-size="9">{P_LAND}（萬元）→</text>'
          f'<text x="{L2}" y="{T2-10}" fill="#7b8794" font-size="9">↑ {P_ALL}（萬元）</text>')
for c in CMP:
    if '異常' in c['標記'] or not (XMIN <= c['土地單價'] <= XMAX and YMIN2 <= c['建坪單價'] <= YMAX2): continue
    col = '#C8963E' if c['標記'].startswith('同街廓') else '#1F4E5F'
    s2.append(f'<circle cx="{X2(c["土地單價"]):.1f}" cy="{Y2(c["建坪單價"]):.1f}" r="4" fill="{col}" fill-opacity=".8" stroke="#fff" stroke-width=".8"/>')
s2.append(f'<circle cx="{X2(L["土地單價"]):.1f}" cy="{Y2(L["總價除總坪"]):.1f}" r="6.5" fill="#C0392B" stroke="#fff" stroke-width="1.4"/>'
          f'<text x="{X2(L["土地單價"])-9:.1f}" y="{Y2(L["總價除總坪"])+3:.1f}" text-anchor="end" fill="#C0392B" font-size="9" font-weight="700" paint-order="stroke" stroke="#F7F9FA" stroke-width="3">本戶開價（土地 {L["土地單價"]:.1f}，建坪 {L["總價除總坪"]:.1f}）</text>')
s2.append(f'<circle cx="{W2-270}" cy="{T2-12}" r="4" fill="#1F4E5F"/><text x="{W2-262}" y="{T2-9}" fill="#4a5560" font-size="8.4">七期同齡透天</text>'
          f'<circle cx="{W2-190}" cy="{T2-12}" r="4" fill="#C8963E"/><text x="{W2-182}" y="{T2-9}" fill="#4a5560" font-size="8.4">同街廓（大通街／大川街／大觀路）</text></svg>')
chart_scatter = ''.join(s2)

# ---------- 表格 ----------
def trow(c, hl=False):
    return (f'<tr{" class=hl" if hl else ""}><td>{c["日期"]}</td><td>{c["門牌"]}</td><td>{c["社區"]}</td><td class="num">{c["屋齡"]}</td><td>{c["樓層"]}</td>'
            f'<td class="num">{wan(c["總價"])}</td><td class="num">{c["建坪"]:.2f}</td><td class="num">{c["地坪"]:.2f}</td><td class="num">{c["車位"]}</td>'
            f'<td class="num b">{c["建坪單價"]:.1f}</td><td class="num b">{c["土地單價"]:.1f}</td></tr>')
HEAD = f'<tr><th>日期</th><th>門牌</th><th>社區</th><th>屋齡</th><th>樓層</th><th>總價（萬）</th><th>建坪</th><th>地坪</th><th>車位</th><th>{P_ALL}</th><th>{P_LAND}</th></tr>'
comm_rows = ''.join(trow(c, True) for c in COMM) + ''.join(trow(c) for c in S['同街廓'])
cmp_rows = ''.join(trow(c, c['標記'].startswith('同街廓')).replace('<td class="num b">', '<td class="num b" style="color:#9aa7b2">') if '異常' in c['標記'] else trow(c, c['標記'].startswith('同街廓')) for c in reversed(CMP))
year_rows = ''.join(f'<tr><td>{y if y < 115 else "115*"}</td><td class="num">{d["n"]}</td><td class="num">{wan(d["總價中位"])}</td><td class="num">{d["建坪中位"]:.1f}</td><td class="num">{d["地坪中位"]:.1f}</td>'
                    f'<td class="num b">{d["建坪單價中位"]:.1f}</td><td class="num b">{d["土地單價中位"]:.1f}</td></tr>' for y, d in CY.items())
pos_rows = (f'<tr class="hl"><td>本戶開價</td><td class="num">{L["總價除總坪"]:.1f}</td><td class="num">{L["土地單價"]:.1f}</td><td>建坪 {L["建坪"]}、地坪 {L["土地"]}</td></tr>')
for y, d in CY.items():
    pos_rows += (f'<tr><td>七期同齡透天 {y if y < 115 else "115*"} 年中位（{d["n"]} 筆）</td><td class="num">{d["建坪單價中位"]:.1f}</td><td class="num">{d["土地單價中位"]:.1f}</td>'
                 f'<td>本戶相差 建坪 {pct(L["總價除總坪"], d["建坪單價中位"]):+.0f}%／土地 {pct(L["土地單價"], d["土地單價中位"]):+.0f}%</td></tr>')

# ---------- 房貸 ----------
RATE, YEARS, LTV = 0.022, 30, 0.8
loan = ASK * LTV; r_m = RATE / 12
pay = loan * 10000 * r_m / (1 - (1 + r_m) ** (-YEARS * 12)); down = ASK - loan

DISC = '永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號'
PHONE, LINE_ID, WEB = '0925-313-570', '@080akczk', 'sixhands.tw'
CONTACT = f'助哥 <span style="white-space:nowrap">{PHONE}</span>　｜　LINE {LINE_ID}　｜　{WEB}'
def foot(n): return f'<div class="foot"><div>{DISC}<br><span class="ct">{CONTACT}</span></div><span>典藏大師特別座 銷售報告書　{n}</span></div>'
LAND_GAP = L['土地'] - min(LAND_MED)
Z108, Z115 = Z7[108]['土地單價中位'], Z7[115]['土地單價中位']

html = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>典藏大師特別座 銷售報告書</title><style>{CSS}</style></head><body>

<!-- P1 封面 -->
<div class="page" style="background:#102a33">
  <img src="{img('外觀.jpg')}" style="position:absolute;left:0;top:0;width:210mm;height:112mm;object-fit:cover;object-position:center 55%">
  <div style="position:absolute;left:0;top:78mm;width:210mm;height:34mm;background:linear-gradient(180deg,rgba(16,42,51,0),#102a33)"></div>
  <div style="position:absolute;left:16mm;top:104mm;color:#E3B66A;font-size:8pt;letter-spacing:.5em">PROPERTY SALES REPORT</div>
  <div style="position:absolute;left:16mm;top:110mm;right:16mm;color:#fff">
    <div class="serif" style="font-size:11pt;color:#E3B66A;letter-spacing:.2em">臺中市南屯區 · 大通街85號 · 七期惠文學區</div>
    <div style="width:46mm;height:2px;background:#E3B66A;margin:5mm 0 4mm"></div>
    <h1 style="font-size:40pt;line-height:1.2">典藏大師特別座</h1>
    <div class="serif" style="font-size:15pt;margin-top:2mm">買方銷售報告書 · 鄰綠園道透天邊間 · 六房 · B1 車位</div>
    <div style="font-size:8.8pt;color:#b9cad3;margin-top:4mm;line-height:1.9">臺中市南屯區大通街85號・地上 4 層透天・{L["朝向"]}向<br>開價 {wan(ASK)} 萬　·　建坪 {L["建坪"]} 坪（含車位 {L["車位面積"]} 坪）　·　土地 {L["土地"]} 坪　·　{L["格局"]}</div>
    <div style="margin-top:7mm;border-top:1px solid #3b5b66;padding-top:5mm">
      <div style="font-size:7.6pt;color:#E3B66A;letter-spacing:.3em">核心數字</div>
      <div style="font-size:9.3pt;line-height:1.9;margin-top:2mm">
        七期重劃區內、惠文國小／惠文高中學區的社區型透天，門前綠園道，地下室有坡道平面車位。<br>
        土地 <b>{L["土地"]} 坪</b>，比七期同齡透天常見的 {min(LAND_MED):.0f}–{max(LAND_MED):.0f} 坪多出約 {LAND_GAP:.0f} 坪。<br>
        開價換算 {P_LAND} <b>{L["土地單價"]:.1f} 萬</b>，七期同齡透天 112–115 年逐年中位在 {min(d["土地單價中位"] for d in CY.values()):.0f}–{max(d["土地單價中位"] for d in CY.values()):.0f} 之間。<br>
        <span style="color:#E3B66A">開價 {wan(ASK)} 萬，{P_ALL} {L["總價除總坪"]:.1f} 萬／坪。</span>
      </div>
    </div>
    <div style="margin-top:6mm;display:flex;align-items:center;gap:6mm;background:#163a47;border:1px solid #3b5b66;padding:4mm 5mm;border-radius:2px">
      <div style="flex:1">
        <div style="font-size:7.4pt;color:#E3B66A;letter-spacing:.3em">預約帶看</div>
        <div class="serif" style="font-size:15pt;font-weight:700;margin-top:1mm">助哥　<span style="color:#F0D9A4;white-space:nowrap">{PHONE}</span></div>
        <div style="font-size:8pt;color:#b9cad3;margin-top:1mm">LINE {LINE_ID}　｜　{WEB}</div>
      </div>
      <div class="qr" style="width:21mm"><img src="{img('QR_LINE.png')}"><div>加 LINE</div></div>
      <div class="qr" style="width:21mm"><img src="{img('QR_網站.png')}"><div>看網站</div></div>
    </div>
  </div>
  <div style="position:absolute;left:16mm;right:16mm;bottom:7mm;font-size:6.8pt;color:#8fa6b1;line-height:1.7">資料：內政部實價登錄（臺中市南屯區透天厝買賣 108/01–115/10，查詢 2026-10-24）；物件資料取自刊登資訊與建物謄本<br>{DISC}</div>
</div>

<!-- P2 物件總覽 -->
<div class="page"><div class="pad">
  <div class="eyebrow">01 · PROPERTY OVERVIEW</div>
  <div class="ttl">物件總覽</div>
  <div class="kpi">
    <div><div class="v">{wan(ASK)}</div><div class="u">萬元</div><div class="l">開價（含 B1 車位 1 席）</div></div>
    <div><div class="v">{L["土地"]}</div><div class="u">坪</div><div class="l">土地坪數</div></div>
    <div><div class="v">{L["建坪"]}</div><div class="u">坪</div><div class="l">建物總坪（含車位 {L["車位面積"]}）</div></div>
    <div><div class="v">{L["主建物"]}</div><div class="u">坪</div><div class="l">主建物（1–4F 室內）</div></div>
    <div><div class="v">{L["管理費月"]:,}</div><div class="u">元／月</div><div class="l">管理費</div></div>
  </div>
  <div class="two">
    <div>
      <h3 class="h">本戶資料</h3>
      <table class="spec">
        <tr><td>地址</td><td>臺中市南屯區大通街85號</td></tr>
        <tr><td>型態</td><td>透天・地上 4 層・邊間・{L["朝向"]}向</td></tr>
        <tr><td>格局</td><td>{L["格局"]}，六房皆開窗（刊登資料）</td></tr>
        <tr><td>土地</td><td>{L["土地"]} 坪（惠義段・都市計畫住宅區）</td></tr>
        <tr><td>建物</td><td>主建物 {L["主建物"]}＋附屬（雨遮）{L["附屬"]}＋共同使用 {L["共同"]}（含車位 {L["車位面積"]}）＝{L["建坪"]} 坪</td></tr>
        <tr><td>車位</td><td>{L["車位"]}</td></tr>
        <tr><td>管理費</td><td>月繳 {L["管理費月"]:,} 元</td></tr>
        <tr><td>屋齡</td><td>約 {L["屋齡"]} 年（87 年 8 月完工，88/02/23 登記）</td></tr>
        <tr><td>登記用途</td><td>{L["用途"]}</td></tr>
        <tr><td>物件編號</td><td>{L["物件編號"]}</td></tr>
      </table>
    </div>
    <div>
      <h3 class="h">社區與學區</h3>
      <table class="spec">
        <tr><td>社區</td><td>典藏大師特別座（實登社區簡稱「大師特別座」），透天社區、有管理組織</td></tr>
        <tr><td>地下室</td><td>社區共用地下室，坡道進出、平面車位</td></tr>
        <tr><td>小學</td><td>{L["小學"]}</td></tr>
        <tr><td>國中</td><td>{L["國中"]}</td></tr>
        <tr><td>分區</td><td>七期重劃區（南屯區惠義段）</td></tr>
        <tr><td>道路</td><td>門前約 10 米路，門口無畫線可再停一部車（刊登資料）</td></tr>
        <tr><td>景觀</td><td>面綠園道，客廳面自家花圃</td></tr>
      </table>
    </div>
  </div>
  <h3 class="h">坪數怎麼看</h3>
  <div class="note">
    權狀建坪 {L["建坪"]} 坪裡，<b>主建物 {L["主建物"]} 坪</b>是 1 到 4 樓的室內空間；共同使用 {L["共同"]} 坪是社區地下室等公共部分，其中 <b>{L["車位面積"]} 坪是本戶的 B1 車位</b>。<br>
    透天的價值大半在土地。本戶土地 <b>{L["土地"]} 坪</b>，七期同齡、同坪數透天 112–115 年的地坪中位在 {min(LAND_MED):.1f}–{max(LAND_MED):.1f} 坪，本戶多出約 {LAND_GAP:.0f} 坪。
  </div>
</div>{foot(2)}</div>

<!-- P3 區位與賣點 -->
<div class="page"><div class="pad">
  <div class="eyebrow">02 · LOCATION</div>
  <div class="ttl">區位與六大賣點</div>
  <div class="photo" style="background:#fff"><img src="{img('位置圖.png')}" style="height:80mm;object-fit:cover"></div>
  <div class="cap">房屋圖示為本戶位置（大通街與綠園道轉角）。地圖取自刊登資訊，北方朝上。</div>
  <div class="two" style="margin-top:4mm">
    <div>
      <div class="feat"><div class="no">01</div><div><h3>七期・惠文學區</h3><p>位在七期重劃區南側，學區為市立惠文國小、惠文高中附設國中。</p></div></div>
      <div class="feat"><div class="no">02</div><div><h3>面綠園道</h3><p>房子在大通街與綠園道轉角，客廳面自家花圃與園道綠帶，前方沒有房子擋。</p></div></div>
      <div class="feat"><div class="no">03</div><div><h3>邊間・六房皆開窗</h3><p>邊間三面採光，6 房 2 廳 3 衛，每一房都有對外窗，適合三代同堂或要書房、孝親房的家庭。</p></div></div>
    </div>
    <div>
      <div class="feat"><div class="no">04</div><div><h3>地大・土地 {L["土地"]} 坪</h3><p>比七期同齡透天常見的地坪多約 {LAND_GAP:.0f} 坪；透天的價值主要在土地。</p></div></div>
      <div class="feat"><div class="no">05</div><div><h3>B1 車位＋門前停車</h3><p>社區地下室坡道平面車位 1 席（B1-25），門前約 10 米路、無畫線可再停一部車。</p></div></div>
      <div class="feat"><div class="no">06</div><div><h3>生活圈完整</h3><p>北邊緊鄰公益路二段；刊登資料載明鄰近 IKEA、文心森林公園、捷運綠線水安宮站。</p></div></div>
    </div>
  </div>
  <div class="note" style="margin-top:2mm"><b>社區型透天：</b>典藏大師特別座為有管理組織的透天社區，共用地下室停車；管理費月繳 {L["管理費月"]:,} 元，可向管委會索取收支與地下室維護紀錄。</div>
</div>{foot(3)}</div>

<!-- P4 本社區與同街廓成交 -->
<div class="page"><div class="pad">
  <div class="eyebrow">03 · NEARBY SALES</div>
  <div class="ttl">本社區與同街廓成交</div>
  <div class="sub">南屯區透天實登 108/01–115/10 中，本社區（實登社區簡稱「大師特別座」）成交 {len(COMM)} 筆（淡橘底），以及同一街廓（大通街、大川街、大觀路）其他透天 {len(S["同街廓"])} 筆。
  透天比較看兩個單價：<b>{P_ALL}</b>，以及 <b>{P_LAND}</b>。</div>
  <table class="tight">{HEAD}{comm_rows}</table>
  <div class="cap">單位：萬元、坪、萬元／坪。建坪含車位坪數（如有）。已排除特殊關係、持分、非住宅等交易。</div>
  <h3 class="h">同社區 108 年成交 vs 本戶</h3>
  <div class="two" style="align-items:flex-start">
    <table class="spec" style="flex:1">
      <tr><td>108/11 成交</td><td>{wan(C108["總價"])} 萬・建坪 {C108["建坪"]} 坪（含車位 2 席）・土地 {C108["地坪"]} 坪・屋齡 {C108["屋齡"]} 年</td></tr>
      <tr><td>本戶開價</td><td>{wan(ASK)} 萬・建坪 {L["建坪"]} 坪（含車位 1 席）・土地 {L["土地"]} 坪・屋齡 {L["屋齡"]} 年</td></tr>
    </table>
    <div style="flex:1;font-size:8.2pt;line-height:1.8;color:#33414c">
      兩戶土地都約 33 坪、主建物約 51–52 坪，條件接近。以 {P_LAND} 看，108 年成交 <b>{C108["土地單價"]:.1f}</b>，本戶開價 <b>{L["土地單價"]:.1f}</b>，差 {pct(L["土地單價"], C108["土地單價"]):+.0f}%；
      同期七期透天土地單價中位由 108 年 {Z108:.1f} 到 115 年 {Z115:.1f}，{pct(Z115, Z108):+.0f}%。
    </div>
  </div>
  <h3 class="h">七期透天土地單價，逐年中位</h3>
  {chart_land}
  <div class="cap">七期重劃區（南屯部分）透天有效成交，每年中位數；115* 為 115 年 1–8 月成交。橘點為本社區 108/11 成交，紅線為本戶開價。</div>
</div>{foot(4)}</div>

<!-- P5 七期同齡透天比較 -->
<div class="page"><div class="pad">
  <div class="eyebrow">04 · AREA COMPARISON</div>
  <div class="ttl">七期同齡透天比較</div>
  <div class="sub">條件：{S["比較組條件"]}，共 {len(CMP)} 筆（不含本社區）。逐年列中位，不跨年合併；單價達同年中位 1.8 倍以上的 {sum("異常" in c["標記"] for c in CMP)} 筆列出但不計入中位。</div>
  <table><tr><th>年度</th><th>筆數</th><th>總價中位（萬）</th><th>建坪中位</th><th>地坪中位</th><th>{P_ALL}</th><th>{P_LAND}</th></tr>{year_rows}
  <tr class="hl"><td>本戶開價</td><td class="num">—</td><td class="num">{wan(ASK)}</td><td class="num">{L["建坪"]:.1f}</td><td class="num">{L["土地"]:.1f}</td><td class="num b">{L["總價除總坪"]:.1f}</td><td class="num b">{L["土地單價"]:.1f}</td></tr></table>
  <div class="cap">115* 為 115 年 1–8 月。單位：萬元、坪、萬元／坪。</div>
  <h3 class="h">每一筆放在一起看</h3>
  {chart_scatter}
  <div class="cap">橫軸為{P_LAND}，縱軸為{P_ALL}；每點一筆 112–115 年成交。紅點為本戶開價。</div>
  <div class="note" style="margin-top:2mm"><b>怎麼看這張圖：</b>本戶在土地單價上落在比較組中間，建坪單價偏高。原因是本戶建坪精簡、土地較大：同樣的總價，建坪越小，「總價÷建坪」就越高。透天買的是土地，建議以土地單價為主要比較基準。</div>
</div>{foot(5)}</div>

<!-- P6 比較組明細 -->
<div class="page"><div class="pad">
  <div class="eyebrow">05 · COMPARABLES</div>
  <div class="ttl">比較組明細</div>
  <div class="sub">七期重劃區透天・屋齡 18–35 年・建物總面積 60–100 坪・112/01–115/10，新到舊排列。淡橘底為同街廓，灰字單價為異常不計。</div>
  <table class="tight xs">{HEAD}{cmp_rows}</table>
  <div class="cap">單位：萬元、坪、萬元／坪。資料：內政部實價登錄，查詢 2026-10-24。</div>
</div>{foot(6)}</div>

<!-- P7 價格分析＋購屋試算 -->
<div class="page"><div class="pad">
  <div class="eyebrow">06 · PRICE &amp; BUYER'S GUIDE</div>
  <div class="ttl">價格分析與購屋試算</div>
  <div class="kpi">
    <div><div class="v">{L["土地單價"]:.1f}</div><div class="u">萬／土地坪</div><div class="l">開價 {P_LAND}</div></div>
    <div><div class="v">{L["總價除總坪"]:.1f}</div><div class="u">萬／坪</div><div class="l">開價 {P_ALL}</div></div>
    <div><div class="v">{L["房屋單價_扣車位"]:.1f}</div><div class="u">萬／坪</div><div class="l">開價 {P_HOUSE}</div></div>
  </div>
  <table class="tight"><tr><th>參考點</th><th>{P_ALL}</th><th>{P_LAND}</th><th>說明</th></tr>{pos_rows}</table>
  <div class="note" style="margin-top:2.5mm"><b>{P_HOUSE}怎麼算：</b>（總價－車位價）÷（總坪－車位坪）。南屯透天社區 B1 坡道平面車位實登揭露 3 筆，每席 150–200 萬；本戶車位 {L["車位面積"]} 坪較小，以 {L["車位估價"]} 萬估：
  （{wan(ASK)}－{L["車位估價"]}）÷ {L["扣車位面積"]:.2f} 坪＝<b>{L["房屋單價_扣車位"]:.1f}</b>。比較組多數未分開登記車位價，所以表格以總價÷建坪與總價÷土地坪比較。</div>
  <div class="kpi" style="margin-top:4mm">
    <div><div class="v">{ASK:,}</div><div class="u">萬元</div><div class="l">以開價試算</div></div>
    <div><div class="v">{wan(down)}</div><div class="u">萬元</div><div class="l">自備款（兩成）</div></div>
    <div><div class="v">{wan(loan)}</div><div class="u">萬元</div><div class="l">貸款（八成）</div></div>
    <div><div class="v">{pay/10000:.1f}</div><div class="u">萬元／月</div><div class="l">本息攤還</div></div>
  </div>
  <div class="sub" style="margin:-1mm 0 2mm">假設貸款八成、年利率 {RATE*100:.1f}%、{YEARS} 年本息平均攤還，每月約 {pay:,.0f} 元；另需預留契稅、代書與仲介服務費。實際成數依銀行鑑價與個人條件核定。</div>
  <h3 class="h">看屋重點</h3>
  <ul>
    <li><b>屋況：</b>屋齡約 {L["屋齡"]:.0f} 年，請看屋頂防水、外牆、管線與窗框；索取歷年修繕紀錄。</li>
    <li><b>地下室與車位：</b>確認 B1-25 位置、車道坡度與地下室排水，車位使用以分管協議為準。</li>
    <li><b>管理費：</b>月繳 {L["管理費月"]:,} 元，可索取管委會收支與公共設施維護項目。</li>
    <li><b>增建與花圃：</b>花圃與門前空間的使用範圍，以現況、謄本與不動產說明書確認。</li>
  </ul>
  <div style="margin-top:3mm;position:relative;background:#fff;border:1px solid #dde4e9;padding:3.5mm 36mm 3.5mm 6mm;font-size:7.4pt;line-height:1.7;color:#4a5560">
    <div class="b" style="font-size:9.2pt;color:#163a47;margin-bottom:1mm">資料來源與免責聲明</div>
    實價登錄：內政部不動產交易實價查詢服務網，臺中市南屯區透天厝買賣 108/01–115/10（115 年成交登錄至 8 月），查詢日 2026-10-24；分區依土地地段判定。物件資料取自刊登資訊與建物謄本，地圖取自刊登頁。<br>
    本報告書為不動產經紀業務之行銷參考資料，非不動產估價師出具之估價報告。行情統計與試算係依公開資料整理，不構成價格保證、投資建議或獲利承諾。實際面積、用途、產權及使用現況，以權狀、謄本、不動產說明書及買賣契約記載為準。
    <div style="position:absolute;right:7mm;top:50%;margin-top:-11mm;width:22mm;height:22mm;border:2.5px solid #b3261e;border-radius:50%;color:#b3261e;display:flex;align-items:center;justify-content:center;text-align:center;font-family:'Noto Serif CJK TC',serif;font-size:8pt;font-weight:700;line-height:1.3;transform:rotate(-12deg)">僅供<br>參考</div>
  </div>
  <div style="margin-top:3mm;display:flex;align-items:center;justify-content:center;gap:7mm;background:#163a47;padding:4mm 7mm;border-radius:2px">
    <div style="color:#fff">
      <div style="font-size:7.4pt;color:#E3B66A;letter-spacing:.3em">預約帶看・行情諮詢</div>
      <div class="serif" style="font-size:15pt;font-weight:700;margin-top:1mm">助哥　<span style="color:#F0D9A4;white-space:nowrap">{PHONE}</span></div>
      <div style="font-size:8pt;color:#b9cad3;margin-top:1mm;line-height:1.7">永慶不動產 七期河南市政店<br>LINE {LINE_ID}　｜　{WEB}</div>
    </div>
    <div class="qr" style="width:22mm"><img src="{img('QR_LINE.png')}"><div>加 LINE</div></div>
    <div class="qr" style="width:22mm"><img src="{img('QR_網站.png')}"><div>看網站</div></div>
  </div>
</div>{foot(7)}</div>

</body></html>'''

OUT_HTML.write_text(html, encoding='utf-8')
print('HTML →', OUT_HTML)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
    pg = b.new_page()
    pg.goto(OUT_HTML.resolve().as_uri())
    pg.wait_for_timeout(500)
    pg.pdf(path=str(OUT_PDF), prefer_css_page_size=True, print_background=True)
    b.close()
print('PDF  →', OUT_PDF)
