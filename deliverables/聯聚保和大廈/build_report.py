"""聯聚保和大廈 銷售報告書（給買方）：讀 summary.json／transactions.csv／listings.json → 產 HTML → Playwright 輸出 PDF。
版型沿用 deliverables/富邦天空樹/build_report.py。不使用他家刊登照片；市售來源一律匿名為「網路刊登」。"""
import base64, json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
OUT_HTML = HERE / '聯聚保和大廈_銷售報告書.html'
OUT_PDF = HERE / '聯聚保和大廈_銷售報告書.pdf'

df = pd.read_csv(HERE / 'transactions.csv')
df['備註'] = df['備註'].fillna('')
S = json.load(open(HERE / 'summary.json'))
LS = json.load(open(HERE / 'listings.json'))['物件']
N3, N4, BU, RS = S['近三年'], S['近四年'], S['建商'], S['轉售']
PARK = S['車位']['每席價格中位']
T = {t['帶']: t for t in S['樓層帶']}
HIGH = S['樓層帶'][3]

def img(name):
    mime = 'image/png' if name.endswith('png') else 'image/jpeg'
    return f"data:{mime};base64,{base64.b64encode((HERE / name).read_bytes()).decode()}"

def wan(v):
    return f'{v:,.0f}'

def yr_frac(d):
    y, m, _ = d.split('/')
    return int(y) + (int(m) - 0.5) / 12

# ---------- 成交散點圖（每筆有效成交的不含車單價） ----------
ok = df[df['有效'] == '是'].copy()
W, H, L, R, Tp, B = 560, 250, 40, 14, 22, 30
X0, X1, Y0, Y1 = 101, 115, 38, 74
def X(y): return L + (y - X0) * (W - L - R) / (X1 - X0)
def Y(v): return Tp + (Y1 - v) * (H - Tp - B) / (Y1 - Y0)
svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC" font-size="10">']
for v in range(40, 75, 5):
    svg.append(f'<line x1="{L}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e6dcc6"/>'
               f'<text x="{L-6}" y="{Y(v)+3:.1f}" text-anchor="end" fill="#8a7d64">{v}</text>')
for y in range(101, 116):
    svg.append(f'<text x="{X(y):.1f}" y="{H-B+15}" text-anchor="middle" fill="#8a7d64">{y}</text>')
svg.append(f'<text x="{W-R}" y="{Tp-8}" text-anchor="end" fill="#8a7d64" font-size="9">X：民國年　Y：不含車單價 萬元/坪</text>')
yl = Y(N3['net'])
svg.append(f'<line x1="{X(112.8):.1f}" x2="{W-R}" y1="{yl:.1f}" y2="{yl:.1f}" stroke="#a8382e" stroke-width="1.4" stroke-dasharray="5 3"/>'
           f'<text x="{X(112.8)-3:.1f}" y="{yl+3:.1f}" text-anchor="end" fill="#a8382e" font-size="8.5" font-weight="700">近三年中位 {N3["net"]:.1f}</text>')
for r in ok.itertuples():
    x, yv = X(yr_frac(r.交易日期)), Y(r.不含車單價)
    if r.期別 == '建商':
        svg.append(f'<circle cx="{x:.1f}" cy="{yv:.1f}" r="3.6" fill="none" stroke="#C9A055" stroke-width="1.6"/>')
    else:
        svg.append(f'<circle cx="{x:.1f}" cy="{yv:.1f}" r="4" fill="#8B5E1A"/>')
svg.append('</svg>')
chart = ''.join(svg)

# ---------- 樓層帶 ----------
tier_rows = ''
for t in S['樓層帶']:
    a, b = t['建商'], t['轉售']
    tier_rows += (f'<tr><td>{t["帶"]}</td><td class="num">{a["n"]}</td><td class="num">{a["含車中位"]:.2f}</td><td class="num b">{a["不含車中位"]:.2f}</td>'
                  f'<td class="num">{b["n"]}</td><td class="num">{b["含車中位"]:.2f}</td><td class="num b">{b["不含車中位"]:.2f}</td>'
                  f'<td class="num">{wan(t["總價中位"])}</td></tr>')

# ---------- 108 年後成交明細 ----------
rec = ok[ok['交易日期'] >= '108/01/01'].sort_values('交易日期', ascending=False)
rec_rows = ''
for i, r in enumerate(rec.itertuples()):
    note = '；'.join(n for n in ['毛胚屋' if '毛胚' in r.備註 else '', '建商餘屋' if r.期別 == '建商' else ''] if n)
    cls = ' class="hl"' if i < 2 else ''
    rec_rows += (f'<tr{cls}><td>{r.交易日期}</td><td>{r.樓層}F {r.戶別}</td><td class="num">{wan(r.總價萬)}</td>'
                 f'<td class="num">{r.總面積坪:.2f}</td><td class="num">{r.車位數}</td><td class="num">{wan(r.車位價萬)}*</td>'
                 f'<td class="num b">{r.含車單價:.2f}</td><td class="num b">{r.不含車單價:.2f}*</td><td>{note}</td></tr>')

# ---------- 市售 7 戶 ----------
def calc(o):
    pv = o['車位數'] * PARK
    base = o['建坪'] - o['車位坪']
    return o['開價'] / o['建坪'], (o['開價'] - pv) / base, base, pv
def band(fl):
    return S['樓層帶'][0 if fl <= 9 else 1 if fl <= 17 else 2 if fl <= 25 else 3]
list_rows, bid_rows, fee_rows = '', '', ''
for o in sorted(LS, key=lambda o: o['開價'] / o['合理'][1]):
    g, n, base, pv = calc(o)
    t = band(o['樓層'])
    ref = t['轉售']['不含車中位']
    lo, hi = o['合理']
    prem_lo, prem_hi = (o['開價'] / hi - 1) * 100, (o['開價'] / lo - 1) * 100
    col = '#a8382e' if prem_lo > 15 else '#3d6b2c' if prem_hi < 14 else '#8B5E1A'
    list_rows += (f'<tr><td class="b">#{o["代號"]}<br>{o["樓層"]}F {o["戶別"]}</td><td class="num">{o["建坪"]:.2f}</td><td class="num">{o["主建物"]:.2f}</td>'
                  f'<td class="num">{o["車位數"]} 席</td><td class="num b">{wan(o["開價"])}</td><td class="num">{g:.1f}</td><td class="num b">{n:.1f}</td>'
                  f'<td class="num">{ref:.1f}</td><td class="num">{o["同戶"]["日期"]}<br>{wan(o["同戶"]["總價"])}</td>'
                  f'<td class="num">{wan(lo)}–<br>{wan(hi)}</td><td class="num b" style="color:{col}">+{prem_lo:.0f}～{prem_hi:.0f}%</td></tr>')
    bid_rows += (f'<tr><td class="b">#{o["代號"]} {o["樓層"]}F {o["戶別"]}</td><td class="num">{wan(o["開價"])}</td><td class="num">{wan(lo)}–{wan(hi)}</td>'
                 f'<td class="num b">{wan(o["起點"])}</td><td class="num b">{o["目標"]}</td><td>{o["重點"]}</td></tr>')
    if o['管理費月']:
        fee_rows += (f'<tr><td>#{o["代號"]} {o["樓層"]}F {o["戶別"]}</td><td class="num">{o["建坪"]:.2f}</td><td class="num">{o["管理費月"]:,}</td>'
                     f'<td class="num">{o["管理費月"]/o["建坪"]:.0f}</td><td class="num">{o["管理費月"]*12/10000:.1f}</td></tr>')

spec_rows = ''
for o in sorted(LS, key=lambda o: o['代號']):
    spec_rows += (f'<tr><td class="b">#{o["代號"]} {o["樓層"]}F {o["戶別"]}</td><td class="num">{o["建坪"]:.2f}</td><td class="num">{o["主建物"]:.2f}</td>'
                  f'<td class="num">{o["附屬"]:.2f}</td><td class="num">{o["共有"]:.2f}</td><td class="num">{o["車位數"]}／{o["車位坪"]:.2f}</td>'
                  f'<td class="num">{o["地坪"]:.2f}</td><td>{o["屋況"]}</td></tr>')

# ---------- 主推兩戶 ----------
P1 = next(o for o in LS if o['代號'] == 1)
P5 = next(o for o in LS if o['代號'] == 5)
g1, n1, *_ = calc(P1)
g5, n5, *_ = calc(P5)

# ---------- 棟別示意（自繪） ----------
site = '''<svg viewBox="0 0 300 190" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC">
<rect width="300" height="190" fill="#f5eedd"/>
<line x1="10" y1="34" x2="290" y2="34" stroke="#C9A055" stroke-width="10"/>
<text x="150" y="22" text-anchor="middle" font-size="11" fill="#8B5E1A" font-weight="700">市政路（60 米）</text>
<rect x="20" y="44" width="260" height="34" fill="#dfe8d3"/>
<text x="150" y="65" text-anchor="middle" font-size="9.5" fill="#3d6b2c">退縮約 27 米・香樟花園・落羽松步道・保和池</text>
<rect x="40" y="96" width="96" height="54" rx="6" fill="#fff" stroke="#8B5E1A" stroke-width="1.5"/>
<text x="88" y="120" text-anchor="middle" font-size="15" font-weight="700" fill="#3a2c12">A</text>
<text x="88" y="138" text-anchor="middle" font-size="8.5" fill="#75684f">之2・約 163–177 坪</text>
<rect x="140" y="96" width="20" height="54" fill="#C9A055"/>
<text x="150" y="127" text-anchor="middle" font-size="8" fill="#fff" writing-mode="tb">梯間</text>
<rect x="164" y="96" width="96" height="54" rx="6" fill="#fff" stroke="#8B5E1A" stroke-width="1.5"/>
<text x="212" y="120" text-anchor="middle" font-size="15" font-weight="700" fill="#3a2c12">B</text>
<text x="212" y="138" text-anchor="middle" font-size="8.5" fill="#75684f">之1・約 153–182 坪</text>
<text x="150" y="172" text-anchor="middle" font-size="8.5" fill="#8a7d64">一層兩戶・雙併・南北向（37F、38F 為一層一戶）</text>
<path d="M282 168 L282 146" stroke="#3a2c12" stroke-width="2"/><polygon points="276,152 288,152 282,140" fill="#3a2c12"/>
<text x="282" y="182" text-anchor="middle" font-size="9" fill="#3a2c12">北</text>
</svg>'''

DISC = '永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號'
PHONE, LINE_ID, WEB = '0925-313-570', '@080akczk', 'sixhands-studio.netlify.app'
CONTACT = f'助哥 {PHONE}　｜　LINE {LINE_ID}　｜　{WEB}'

def foot(n):
    return (f'<div class="foot"><div>{DISC}<br><span class="ct">{CONTACT}</span></div>'
            f'<span>聯聚保和大廈 銷售報告書　{n}</span></div>')

html = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>聯聚保和大廈 銷售報告書</title><style>
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: "Noto Sans CJK TC", sans-serif; color: #2b2418; -webkit-print-color-adjust: exact; print-color-adjust: exact; background: #ddd; }}
.page {{ width: 210mm; height: 297mm; position: relative; overflow: hidden; page-break-after: always; background: #FBF7EE; margin: 0 auto; }}
.page:last-child {{ page-break-after: auto; }}
h1, h2, h3, .serif {{ font-family: "Noto Serif CJK TC", serif; }}
.pad {{ padding: 15mm 15mm 0 15mm; }}
.eyebrow {{ font-size: 7.6pt; letter-spacing: .45em; color: #A47A35; margin-bottom: 2mm; }}
.ttl {{ font-family: "Noto Serif CJK TC", serif; font-size: 19pt; color: #3a2c12; font-weight: 700; border-left: 5px solid #B8893E; padding-left: 9px; margin-bottom: 3mm; }}
.sub {{ font-size: 8.8pt; color: #75684f; margin-bottom: 5mm; line-height: 1.7; }}
table {{ width: 100%; border-collapse: collapse; font-size: 8.2pt; }}
th {{ background: #5A4318; color: #FBF7EE; padding: 4.5px 5px; text-align: left; font-weight: 500; font-size: 7.8pt; }}
td {{ padding: 4.3px 5px; border-bottom: 1px solid #e8dfcb; vertical-align: top; }}
tr:nth-child(even) td {{ background: #f5eedd; }}
tr.hl td {{ background: #B8893E !important; color: #fff; }}
.num {{ font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }}
.b {{ font-weight: 700; }}
.foot {{ position: absolute; bottom: 0; left: 0; right: 0; height: 11mm; background: #3a2c12; color: #d9c9a3; font-size: 6.4pt; line-height: 1.6; display: flex; align-items: center; justify-content: space-between; padding: 0 15mm; }}
.foot .ct {{ color: #F0D9A4; font-weight: 700; letter-spacing: .03em; }}
.qr {{ background: #fff; padding: 1.6mm; border-radius: 2px; text-align: center; }}
.qr img {{ display: block; width: 100%; }}
.qr div {{ font-size: 6.6pt; color: #3a2c12; margin-top: .8mm; font-weight: 700; }}
.kpi {{ display: flex; gap: 3.5mm; margin-bottom: 5mm; }}
.kpi > div {{ flex: 1; background: #fff; border: 1px solid #e6dcc6; border-top: 3px solid #B8893E; padding: 3.5mm 2mm; text-align: center; }}
.kpi .v {{ font-family: "Noto Serif CJK TC", serif; font-size: 19pt; color: #3a2c12; font-weight: 700; line-height: 1.1; }}
.kpi .u {{ font-size: 7.6pt; color: #A47A35; }}
.kpi .l {{ font-size: 7.2pt; color: #7d7058; margin-top: 1.5mm; }}
.note {{ background: #f7ecd4; border-left: 4px solid #B8893E; padding: 3.5mm 4.5mm; font-size: 8.3pt; line-height: 1.75; }}
.warn {{ background: #fbeceb; border-left: 4px solid #a8382e; padding: 3.5mm 4.5mm; font-size: 8.3pt; line-height: 1.75; }}
.feat {{ display: flex; gap: 4mm; margin-bottom: 4mm; }}
.feat .no {{ font-family: "Noto Serif CJK TC", serif; font-size: 22pt; color: #C9A055; line-height: 1; min-width: 11mm; }}
.feat h3 {{ font-size: 11.5pt; color: #3a2c12; margin-bottom: 1.3mm; }}
.feat p {{ font-size: 8.6pt; line-height: 1.8; color: #3d3423; }}
ul {{ margin-left: 4.5mm; }} li {{ font-size: 8.4pt; line-height: 1.8; margin-bottom: .6mm; }}
.photo {{ background: #efe5cf; padding: 2mm; border-radius: 2px; }}
.photo img {{ display: block; width: 100%; object-fit: contain; }}
.cap {{ font-size: 7pt; color: #8a7d64; margin-top: 1.2mm; line-height: 1.65; }}
.spec td:first-child {{ color: #8a6a2c; width: 24mm; white-space: nowrap; }}
.spec td {{ background: transparent !important; padding: 3.4px 4px; font-size: 8.3pt; }}
.chip {{ display: inline-block; border: 1px solid #C9A055; color: #8B5E1A; font-size: 7.4pt; padding: .5mm 2.2mm; border-radius: 10px; margin: 0 1.2mm 1.2mm 0; }}
.card {{ background: #fff; border: 1px solid #e6dcc6; border-top: 3px solid #B8893E; padding: 4.5mm 5mm; }}
</style></head><body>

<!-- P1 封面 -->
<div class="page" style="background:#182a21">
  <img src="{img('位置圖_七期三分區.png')}" style="position:absolute;right:4mm;top:34mm;width:116mm;opacity:.95">
  <div style="position:absolute;left:14mm;top:30mm;width:84mm;color:#FBF7EE">
    <div style="font-size:8pt;letter-spacing:.5em;color:#D8B26A">PROPERTY SALES REPORT</div>
    <div style="width:46mm;height:2px;background:#D8B26A;margin:6mm 0 9mm"></div>
    <div style="font-size:11pt;color:#D8B26A;letter-spacing:.2em" class="serif">七期 · 市政路香樟花園</div>
    <h1 style="font-size:38pt;line-height:1.2;margin-top:3mm">聯聚<br>保和大廈</h1>
    <div style="font-size:15pt;margin-top:5mm" class="serif">買方銷售報告書</div>
    <div style="font-size:8.8pt;color:#c7cfc0;margin-top:5mm;line-height:1.9">臺中市西屯區市政路 25 號<br>39 層 · 一層兩戶 · SRC · 762 坪基地</div>
    <div style="margin-top:14mm;border-top:1px solid #4d6655;padding-top:6mm;width:84mm">
      <div style="font-size:7.6pt;color:#D8B26A;letter-spacing:.3em">核心結論</div>
      <div style="font-size:9.4pt;line-height:1.9;margin-top:2.5mm">
        近三年（113–115）成交中位：<b>不含車 {N3['net']:.1f}</b>、<b>含車 {N3['gross']:.1f}</b> 萬／坪（{N3['n']} 筆）。<br>
        目前市售 {len(LS)} 戶，開價高出實登參考區間約 6%～32%。<br>
        <span style="color:#D8B26A">先看成交，再看開價——同款戶的成交價就是你的出價依據。</span>
      </div>
    </div>
  </div>
  <div style="position:absolute;left:14mm;bottom:22mm;width:84mm;color:#FBF7EE">
    <div style="font-size:7.4pt;color:#D8B26A;letter-spacing:.3em">預約帶看</div>
    <div style="white-space:nowrap;margin-top:1.5mm"><span class="serif" style="font-size:17pt;font-weight:700">助哥</span>
      <span style="font-size:15pt;font-weight:700;letter-spacing:.04em;color:#F0D9A4;margin-left:2.5mm">{PHONE}</span></div>
    <div style="display:flex;gap:3mm;align-items:flex-end;margin-top:3mm">
      <div class="qr" style="width:20mm"><img src="{img('QR_LINE.png')}"><div>LINE</div></div>
      <div class="qr" style="width:20mm"><img src="{img('QR_網站.png')}"><div>網站</div></div>
      <div style="font-size:7.2pt;color:#c7cfc0;line-height:1.8;white-space:nowrap">LINE {LINE_ID}<br>{WEB}</div>
    </div>
  </div>
  <div style="position:absolute;left:14mm;bottom:9mm;font-size:6.2pt;color:#9fb3a6;width:90mm;line-height:1.7">資料基準：內政部實價登錄 101/01–115/10（查詢 2026-10-06）<br>{DISC}</div>
</div>

<!-- P2 建案檔案 -->
<div class="page"><div class="pad">
  <div class="eyebrow">01 · PROFILE</div>
  <div class="ttl">建案檔案</div>
  <div class="sub">聯聚建設在 60 米市政路上的新古典超高層住宅：一層兩戶、毛胚交屋、退縮約 27 米留給香樟花園。位於七期「公益向上（南七期）」次分區，學區為惠文國小（雙語）。</div>
  <div style="display:flex;gap:6mm">
    <div style="flex:1.1">
      <table class="spec">
        <tr><td>地址</td><td>臺中市西屯區市政路 25 號</td></tr>
        <tr><td>區位</td><td>七期重劃區 ③ 公益向上（市政路南側，面市政路）</td></tr>
        <tr><td>屋齡</td><td>約 10 年（105/07 建築完成）</td></tr>
        <tr><td>使用分區</td><td>第四之一種商業區（商4-1）</td></tr>
        <tr><td>基地面積</td><td>約 762 坪（惠順段 7 地號）</td></tr>
        <tr><td>樓層</td><td>地上 39 層／地下 6 層</td></tr>
        <tr><td>總戶數</td><td>69 戶（一層兩戶；37F、38F 一層一戶）</td></tr>
        <tr><td>戶型坪數</td><td>約 131–262 坪（含車位）；雙併三梯、南北向</td></tr>
        <tr><td>公設比</td><td>34.89%</td></tr>
        <tr><td>結構</td><td>SRC 鋼骨鋼筋混凝土；外牆石材</td></tr>
        <tr><td>交屋</td><td>毛胚交屋；樓層淨高約 3.6 米</td></tr>
        <tr><td>車位</td><td>坡道平面為主，社區 225 位，每席約 9.93 坪；每戶配 2–5 席</td></tr>
        <tr><td>國小學區</td><td>惠文國小（雙語）</td></tr>
        <tr><td>國中學區</td><td>惠文高中國中部</td></tr>
        <tr><td>建設公司</td><td>聯聚建設</td></tr>
        <tr><td>建築設計</td><td>張德昌建築師事務所</td></tr>
        <tr><td>營造</td><td>安鼎營造</td></tr>
      </table>
      <div class="cap" style="margin-top:2mm">註：雙語學區依各縣市政府教育局處資料，入學資格請以當年度公告為準。戶數、車位數依建物謄本與公開社區資料整理。</div>
    </div>
    <div style="flex:.9">
      <div class="photo">{site}</div>
      <div class="cap">棟別配置示意（小登依公開資料自繪，非比例）。A＝門牌「之2」、B＝「之1」。</div>
      <div class="photo" style="margin-top:4mm"><img src="{img('位置圖_七期三分區.png')}"></div>
      <div class="cap">七期三分區位置示意：保和位於市政路南側，屬 ③ 公益向上。</div>
    </div>
  </div>
  <div style="margin-top:4mm">
    <span class="chip">一層兩戶</span><span class="chip">SRC 鋼骨</span><span class="chip">毛胚交屋</span><span class="chip">退縮 27 米香樟花園</span><span class="chip">9.5 米挑高大廳</span><span class="chip">惠文雙語學區</span>
  </div>
</div>{foot(2)}</div>

<!-- P3 建築與公設 -->
<div class="page"><div class="pad">
  <div class="eyebrow">02 · ARCHITECTURE</div>
  <div class="ttl">新古典外觀・博物館式公設</div>
  <div class="sub">建案公開時，全版廣告只放了四個字「無以尚之」（語出《論語・里仁》），不搭樣品屋，只帶客戶看聯聚過去的完工作品。「保和」取自《易經》「保合太和」，意為萬物和諧。</div>
  <div style="display:flex;gap:6mm">
    <div style="flex:1">
      <div class="feat"><div class="no">01</div><div><h3>把 27 米留給一座花園</h3>
        <p>臨 60 米市政路退縮約 27 米，種下 6 棵老樟樹成為「香樟花園」，與落羽松夾出林蔭步道；門前設「保和池」水景，基地一隅另有義大利造型的「奉茶」飲水柱，供路人取用。</p></div></div>
      <div class="feat"><div class="no">02</div><div><h3>新古典的建築語彙</h3>
        <p>圓形列柱、拾級而上的石階門廊、拜占庭十字花紋家徽，外牆鑲嵌 20 隻台灣藍鵲石雕；後院植生牆與泳池旁置一座古井，與前院保和池呼應。</p></div></div>
      <div class="feat"><div class="no">03</div><div><h3>空間尺度</h3>
        <p>標準層一層兩戶、雙併三梯，戶戶三面採光；坪數約 131–262 坪，室內毛胚交屋，標準格局可做 2 廳 3 房 3 衛＋傭人房。客廳約 10 米面寬落地窗。</p></div></div>
    </div>
    <div style="flex:1">
      <div class="card">
        <h3 style="font-size:12pt;color:#3a2c12;margin-bottom:2.5mm">公設配置（集中 1–3F 與頂樓）</h3>
        <table class="spec">
          <tr><td>1F</td><td>挑高 9.5 米大廳（3 盞威尼斯手工水晶吊燈、17 世紀畫作）、半開放交誼廳、戶外泳池、villa 式 SPA</td></tr>
          <tr><td>2F</td><td>舒壓室、健身房、瑜伽室、劇院</td></tr>
          <tr><td>3F</td><td>中西式宴會廳、戶外 120 米環景步道</td></tr>
          <tr><td>39F</td><td>Sky Lounge（降板式吧台、旋轉梯、俯瞰七期夜景）</td></tr>
          <tr><td>其他</td><td>牌藝室、兒童遊戲室、室內籃球場（地下層）</td></tr>
          <tr><td>地下室</td><td>車道紅銅圓拱天花；地坪與牆面皆石材，柱上人偶雕塑；展示一部 1933 年古董勞斯萊斯</td></tr>
        </table>
      </div>
      <div class="note" style="margin-top:4mm">買方觀點：公設集中在低樓層與頂樓，<b>住戶動線與公設分離</b>；戶數少、坪數大，住戶組成單純。大面積公設與藝術品維護，反映在管理費上（見第 7 頁）。</div>
    </div>
  </div>
  <div class="cap" style="margin-top:3mm">建築與公設說明依建設公司公開資料與媒體報導整理（2016–2017 年前後），實際設施與使用規範以現況與管委會規約為準。</div>
</div>{foot(3)}</div>

<!-- P4 行情 -->
<div class="page"><div class="pad">
  <div class="eyebrow">03 · MARKET</div>
  <div class="ttl">社區行情：含車 vs 不含車</div>
  <div class="sub">資料：內政部實價登錄，市政路 25 號，101/01–115/10，共 {S['原始筆數']} 筆，全數住家用。排除特殊關係與債務抵償 {len(S['排除'])} 筆，有效 <b>{S['有效筆數']}</b> 筆。以下單價一律為<b>中位數</b>。</div>
  <div class="kpi">
    <div><div class="v">{N3['net']:.1f}</div><div class="l">近三年 不含車中位<br>萬／坪（113–115，{N3['n']} 筆）</div></div>
    <div><div class="v">{N3['gross']:.1f}</div><div class="l">近三年 含車中位<br>萬／坪（113–115，{N3['n']} 筆）</div></div>
    <div style="border-top-color:#8B5E1A"><div class="v">{N4['net']:.1f}</div><div class="l">112–115 不含車中位<br>萬／坪（{N4['n']} 筆，全為轉售）</div></div>
    <div style="border-top-color:#8B5E1A"><div class="v">{N4['gross']:.1f}</div><div class="l">112–115 含車中位<br>萬／坪（{N4['n']} 筆）</div></div>
  </div>
  <div style="background:#fff;border:1px solid #e6dcc6;padding:3mm 3mm 1mm">
    <div style="font-size:9pt;font-weight:700;color:#3a2c12;margin:0 0 1mm 2mm">每一筆成交的不含車單價
      <span style="font-weight:400;font-size:7.6pt;color:#C9A055;margin-left:4mm">○ 建商首售／餘屋</span>
      <span style="font-weight:400;font-size:7.6pt;color:#8B5E1A;margin-left:3mm">● 轉售（中古）</span></div>
    {chart}
  </div>
  <div class="cap">⚠ 近三年僅 {N3['n']} 筆成交，行情帶寬較寬，議價前請逐戶核對。101–102 年為預售簽約期；103 年兩筆約 70 萬為 37F、38F 一層一戶；111 年仍有建商餘屋出清。108 年後成交車位價未揭露，以本棟已揭露之坡道平面每席中位 {PARK:.0f} 萬估算。</div>
  <div style="margin-top:4mm"><table>
    <tr><th>樓層區段</th><th class="num">建商筆數</th><th class="num">建商 含車</th><th class="num">建商 不含車</th><th class="num">轉售筆數</th><th class="num">轉售 含車</th><th class="num">轉售 不含車</th><th class="num">總價中位(萬)</th></tr>
    {tier_rows}
  </table></div>
  <div class="note" style="margin-top:4mm">
    <b>兩個重點：</b>①<b>25 樓以下價差小、26 樓以上跳一級</b>——高樓層轉售不含車中位 {HIGH['轉售']['不含車中位']:.1f}，比中高樓層高約兩成五，比價一定要對照同一區段。②<b>轉售價與建商首售價大致持平</b>（轉售全期中位 {RS['net']:.1f}、建商 {BU['net']:.1f}），本社區不是只漲不跌的產品。<br>
    <b>單價怎麼看？</b>含車單價＝總價 ÷ 總面積；不含車單價＝(總價 − 車位價) ÷ (總面積 − 車位面積)。每戶配 2–5 席車位，兩種口徑差約 {N3['gap_pct']:.0f}%，比價時務必用同一口徑。
  </div>
</div>{foot(4)}</div>

<!-- P5 成交明細 -->
<div class="page"><div class="pad">
  <div class="eyebrow">04 · TRANSACTIONS</div>
  <div class="ttl">近年成交明細（108 年後）</div>
  <div class="sub">金色列為最新兩筆成交。* 為車位價未揭露、以每席 {PARK:.0f} 萬估算。戶別：A＝之2、B＝之1。單價單位：萬元／坪；總價、車位價單位：萬元。</div>
  <table>
    <tr><th>交易日</th><th>樓層戶別</th><th class="num">總價</th><th class="num">總面積(坪)</th><th class="num">車位</th><th class="num">車位價</th><th class="num">含車單價</th><th class="num">不含車單價</th><th>註記</th></tr>
    {rec_rows}
  </table>
  <div class="ttl" style="font-size:13pt;margin-top:6mm">市售各戶的同一戶前次成交</div>
  <table>
    <tr><th>市售物件</th><th>同一戶前次成交</th><th class="num">當時總價(萬)</th><th class="num">當時不含車</th><th class="num">現開價(萬)</th><th class="num">開價／前次</th></tr>
    {''.join(f'<tr><td class="b">#{o["代號"]} {o["樓層"]}F {o["戶別"]}</td><td>{o["同戶"]["日期"]} {o["同戶"]["性質"]}</td><td class="num">{wan(o["同戶"]["總價"])}</td><td class="num">{o["同戶"]["不含車"]:.2f}</td><td class="num">{wan(o["開價"])}</td><td class="num b">{(o["開價"]/o["同戶"]["總價"]-1)*100:+.1f}%</td></tr>' for o in sorted(LS, key=lambda o: o["代號"]))}
  </table>
  <div class="cap" style="margin-top:2mm">前次成交為實價登錄公開資料。預售期價格與今日屋況、車位數相同時才可直接比較；#7 前次成交已含室內隔間與廚衛。#6 同一戶於 114/05 才以 6,868 萬成交，是本表最直接的比價依據。</div>
</div>{foot(5)}</div>

<!-- P6 市售物件 -->
<div class="page"><div class="pad">
  <div class="eyebrow">05 · LISTINGS</div>
  <div class="ttl">目前市售物件 vs 實登行情</div>
  <div class="sub">2026-10 市場上刊登中的 {len(LS)} 戶，坪數皆以<b>建物謄本</b>校正。用同一把尺（含車／不含車）和實價登錄比較，依「開價高出參考區間」由低到高排列。開價是屋主的期待，成交價才是市場的答案。</div>
  <table>
    <tr><th>物件</th><th class="num">建坪(含車)</th><th class="num">主建物</th><th class="num">車位</th><th class="num">開價(萬)</th><th class="num">含車單價</th><th class="num">不含車單價</th><th class="num">同樓層帶<br>轉售中位</th><th class="num">同一戶<br>前次成交</th><th class="num">參考總價<br>區間(萬)</th><th class="num">開價高出<br>參考區間</th></tr>
    {list_rows}
  </table>
  <div class="cap" style="margin-top:2mm">單位：萬元／坪。不含車單價＝(開價 − 車位數 × {PARK:.0f} 萬) ÷ (建坪 − 謄本車位坪)。「參考總價區間」為小登依同款戶近年成交、同層對戶與樓層區段推算的參考值，<b>不是估價</b>，也不代表屋主願意成交的價格；#4 一層一戶無轉售可比、#7 含裝修殘值假設，區間不確定性較高。</div>

  <div class="ttl" style="font-size:13pt;margin-top:6mm">謄本坪數一覽</div>
  <table>
    <tr><th>物件</th><th class="num">總坪數</th><th class="num">主建物</th><th class="num">附屬(陽台＋雨遮)</th><th class="num">共有(不含車位)</th><th class="num">車位 席／坪</th><th class="num">地坪</th><th>屋況（依刊登）</th></tr>
    {spec_rows}
  </table>
  <div class="cap" style="margin-top:2mm">B 戶（之1）主建物皆 70.43 坪，152.59／162.53 坪的差別在車位 2 席或 3 席；A 戶（之2）低樓層主建物 72.44 坪。地坪＝惠順段 7 地號持分 × 基地面積。</div>
</div>{foot(6)}</div>

<!-- P7 出價參考 -->
<div class="page"><div class="pad">
  <div class="eyebrow">06 · BUYER'S VIEW</div>
  <div class="ttl">給買方的出價參考</div>
  <div class="sub">把行情轉成你出價時用得到的數字。以下為依實登推算的參考，實際仍應依屋況、樓層、車位與屋主條件個別調整。</div>
  <table>
    <tr><th>物件</th><th class="num">開價(萬)</th><th class="num">參考區間(萬)</th><th class="num">建議出價起點</th><th class="num">成交目標</th><th>關鍵依據</th></tr>
    {bid_rows}
  </table>
  <div style="display:flex;gap:5mm;margin-top:5mm">
    <div style="flex:1" class="note">
      <div class="b" style="font-size:10pt;margin-bottom:1.5mm">議價時拿得出來的數字</div>
      <ul>
        <li><b>同款戶成交</b>：B 戶 152.59 坪、2 車位，17F（114/05）與 21F（112/06）都在 6,870 萬左右成交。</li>
        <li><b>同層對戶</b>：27F A 戶 114/05 成交 8,200 萬（不含車 57.5），是高樓層最新的價格錨點。</li>
        <li><b>樓層區段</b>：25F 以下轉售不含車約 46–51；26F 以上約 57–64。</li>
      </ul>
    </div>
    <div style="flex:1" class="warn">
      <div class="b" style="font-size:10pt;margin-bottom:1.5mm">總預算要另外算的</div>
      <ul>
        <li><b>裝修</b>：多數戶為毛胚或僅隔間，130 坪級室內裝修需另編預算並申請室內裝修許可。</li>
        <li><b>車位</b>：每戶 2–5 席綁售，總價差異有相當比例來自車位數，比價先對齊車位數。</li>
        <li><b>稅費</b>：契稅、代書、仲介服務費、貸款相關費用另計。</li>
      </ul>
    </div>
  </div>
  <div class="ttl" style="font-size:13pt;margin-top:6mm">持有成本：管理費</div>
  <table>
    <tr><th>物件</th><th class="num">建坪</th><th class="num">月管理費(元)</th><th class="num">每坪／月(元)</th><th class="num">年管理費(萬)</th></tr>
    {fee_rows}
  </table>
  <div class="cap" style="margin-top:1.5mm">依市售刊登資訊（車位管理費含在大樓管理費內），約每坪每月 133–150 元（以刊登建坪計）；未刊登管理費的物件未列。實際收費標準與公基金請向管委會確認；另有房屋稅、地價稅與保險。</div>
</div>{foot(7)}</div>

<!-- P8 推薦 -->
<div class="page"><div class="pad">
  <div class="eyebrow">07 · FEATURED</div>
  <div class="ttl">優先帶看：兩戶最貼近行情</div>
  <div class="sub">市售 {len(LS)} 戶裡，開價與實登參考區間差距最小的兩戶，一戶高樓層、一戶低樓層，預算與需求不同各有適合的人。</div>
  <div style="display:flex;gap:5mm">
    <div style="flex:1" class="card">
      <div class="eyebrow" style="margin-bottom:1mm">高樓層首選</div>
      <h3 style="font-size:15pt;color:#3a2c12">#1　27F B 戶</h3>
      <div class="kpi" style="margin:3mm 0">
        <div><div class="v">{wan(P1['開價'])}</div><div class="l">開價（萬）</div></div>
        <div><div class="v">{n1:.1f}</div><div class="l">不含車單價</div></div>
      </div>
      <table class="spec">
        <tr><td>建坪</td><td>{P1['建坪']:.2f} 坪（謄本）</td></tr>
        <tr><td>主建物</td><td>{P1['主建物']:.2f} 坪；陽台 {P1['陽台']:.2f}、雨遮 {P1['雨遮']:.2f}</td></tr>
        <tr><td>車位</td><td>{P1['車位數']} 席坡道平面（{P1['車位坪']:.2f} 坪）</td></tr>
        <tr><td>含車單價</td><td>{g1:.1f} 萬／坪</td></tr>
        <tr><td>參考區間</td><td>{wan(P1['合理'][0])}–{wan(P1['合理'][1])} 萬</td></tr>
      </table>
      <ul style="margin-top:3mm">
        <li>同層 A 戶 114/05 剛以不含車 57.5 成交，比價依據最直接。</li>
        <li>邊間、26F 以上高樓層區段（轉售中位 {HIGH['轉售']['不含車中位']:.1f}）。</li>
        <li>開價高出參考區間約 6–9%，是市售各戶中最小。</li>
      </ul>
    </div>
    <div style="flex:1" class="card">
      <div class="eyebrow" style="margin-bottom:1mm">入門總價首選</div>
      <h3 style="font-size:15pt;color:#3a2c12">#5　5F A 戶</h3>
      <div class="kpi" style="margin:3mm 0">
        <div><div class="v">{wan(P5['開價'])}</div><div class="l">開價（萬）</div></div>
        <div><div class="v">{n5:.1f}</div><div class="l">不含車單價</div></div>
      </div>
      <table class="spec">
        <tr><td>建坪</td><td>{P5['建坪']:.2f} 坪（謄本）</td></tr>
        <tr><td>主建物</td><td>{P5['主建物']:.2f} 坪；陽台 {P5['陽台']:.2f}、雨遮 {P5['雨遮']:.2f}</td></tr>
        <tr><td>車位</td><td>{P5['車位數']} 席坡道平面（{P5['車位坪']:.2f} 坪）</td></tr>
        <tr><td>含車單價</td><td>{g5:.1f} 萬／坪</td></tr>
        <tr><td>參考區間</td><td>{wan(P5['合理'][0])}–{wan(P5['合理'][1])} 萬</td></tr>
      </table>
      <ul style="margin-top:3mm">
        <li>市售最低總價；不含車單價與近三年中位 {N3['net']:.1f} 只差約 2%。</li>
        <li>正下方 4F 同款戶 113/03 成交 6,813 萬，可直接比價。</li>
        <li>與 #3（8F A，同款 8,100 萬）可同日看屋比較。</li>
      </ul>
    </div>
  </div>
  <div class="note" style="margin-top:5mm"><b>怎麼選？</b>要高樓景觀、預算 8,000 萬以上 → 先看 #1；要同一座社區、總價壓在 7,000 萬級 → 先看 #5。想要現成裝潢、不想自己施工 → 可加看 #7，但要評估裝修風格是否符合需求，價差約 2,600 萬主要在裝修。</div>
</div>{foot(8)}</div>

<!-- P9 揭露 + 免責 -->
<div class="page"><div class="pad">
  <div class="eyebrow">08 · DISCLOSURE</div>
  <div class="ttl">誠實揭露：購買前請一併評估</div>
  <div class="warn">
    <ul>
      <li><b>成交稀少：</b>112 年後每年僅約 2 筆成交，近三年中位只有 {N3['n']} 筆樣本，行情帶寬較寬；轉手可能需要較長時間。</li>
      <li><b>價格並非只漲不跌：</b>轉售價與 101–107 年建商首售價大致持平；部分戶別轉售價低於首售價。</li>
      <li><b>商業區住宅：</b>土地使用分區為商4-1，登記用途為集合住宅；相關稅負與使用限制請依個案謄本與主管機關規定確認。</li>
      <li><b>公設比 34.89%：</b>比價時請一併比較主建物坪數與陽台面積。</li>
      <li><b>車位價估算：</b>108 年後成交車位價未揭露，不含車單價以本棟坡道平面每席中位 {PARK:.0f} 萬估算，表中以 * 標示。</li>
      <li><b>毛胚與裝修：</b>多數戶為毛胚交屋或僅隔間，裝修需申請室內裝修許可，預算與工期另估。</li>
      <li><b>市售資訊：</b>開價、管理費、屋況依 2026-10 網路刊登資訊整理，坪數以建物謄本校正；開價可能隨時調整，以實際委託與謄本為準。</li>
      <li><b>學區：</b>雙語學區資訊依教育局處資料，學籍與入學資格以學校當年度公告為準。</li>
    </ul>
  </div>
  <div class="ttl" style="font-size:13pt;margin-top:6mm">資料來源與方法</div>
  <ul>
    <li>成交資料：內政部不動產交易實價查詢服務網，市政路 25 號，101 年 1 月至 115 年 10 月，查詢時間 2026-10-06；查詢時未設樓層、坪數、型態篩選。</li>
    <li>清洗規則：備註含親友、員工、共有人、特殊關係者，以及債權債務抵償者排除（{len(S['排除'])} 筆）；備註「建物第一次登記後移轉」者歸為建商首售／餘屋，其餘為轉售。</li>
    <li>統計：一律採<b>中位數</b>；行情以<b>近三年（113–115）</b>為準，其他期間僅作脈絡參考。</li>
    <li>含車單價＝總價 ÷ 總面積；不含車單價＝(總價 − 車位價) ÷ (總面積 − 車位面積)。</li>
    <li>建案資料：建設公司與公開社區資料、媒體報導；圖面為小登自繪示意。</li>
  </ul>
  <div style="margin-top:8mm;position:relative;background:#fff;border:1px solid #e6dcc6;padding:6mm 38mm 6mm 7mm;font-size:8pt;line-height:1.85;color:#55493a">
    <div class="b" style="font-size:10pt;color:#3a2c12;margin-bottom:2mm">免責聲明</div>
    本報告書為不動產經紀業務之行銷參考資料，非不動產估價師出具之估價報告。報告中之行情統計、參考區間、出價參考與情境分析，係依公開實價登錄資料整理推算，不構成任何價格保證、投資建議或獲利承諾。實際交易價格、面積、車位、產權及使用現況，以權狀、謄本、不動產說明書及買賣契約記載為準。建案特色說明引用公開資料，實際設施以現況為準。買方應自行或委託專業人士查證後再做決定。
    <div style="position:absolute;right:8mm;top:50%;margin-top:-12mm;width:24mm;height:24mm;border:2.5px solid #b3261e;border-radius:50%;color:#b3261e;display:flex;align-items:center;justify-content:center;text-align:center;font-family:'Noto Serif CJK TC',serif;font-size:8.4pt;font-weight:700;line-height:1.3;transform:rotate(-12deg)">僅供<br>參考</div>
  </div>
  <div style="margin-top:7mm;display:flex;align-items:center;justify-content:center;gap:7mm;background:#3a2c12;padding:5mm 7mm;border-radius:2px">
    <div style="color:#FBF7EE">
      <div style="font-size:7.4pt;color:#D8B26A;letter-spacing:.3em">預約帶看・行情諮詢</div>
      <div class="serif" style="font-size:16pt;font-weight:700;margin-top:1mm">助哥　<span style="color:#F0D9A4">{PHONE}</span></div>
      <div style="font-size:8pt;color:#cdbf9f;margin-top:1mm;line-height:1.7">永慶不動產 七期河南市政店<br>LINE {LINE_ID}　｜　{WEB}</div>
    </div>
    <div class="qr" style="width:24mm"><img src="{img('QR_LINE.png')}"><div>加 LINE</div></div>
    <div class="qr" style="width:24mm"><img src="{img('QR_網站.png')}"><div>看網站</div></div>
  </div>
</div>{foot(9)}</div>

</body></html>'''

OUT_HTML.write_text(html, encoding='utf-8')
print('HTML →', OUT_HTML)

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    pg = b.new_page()
    pg.goto(OUT_HTML.resolve().as_uri())
    pg.wait_for_timeout(500)
    pg.pdf(path=str(OUT_PDF), prefer_css_page_size=True, print_background=True)
    b.close()
print('PDF  →', OUT_PDF)
