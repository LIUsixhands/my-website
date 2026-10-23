"""赫里翁 銷售報告書（給買方）：讀 summary.json / transactions.csv → 產 HTML → Playwright 輸出 PDF。
口徑：單價一律並列「房屋單價（已扣車位）」與「總價÷總坪數（車位一起算）」；不使用主建物單價。
同型＝三房中坪（之3／之6／之7，扣車位約 84 坪）；區域比較組卡扣車位面積 ±5 坪（鐵律 8）。
本社區每席車位約 6 坪、180 萬，車位每坪價與房屋單價接近，兩個口徑幾乎相同（headline 的 gross>net 提示屬此情形，非類別配錯）。"""
import base64, json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
OUT_HTML = HERE / '赫里翁_銷售報告書.html'
OUT_PDF = HERE / '赫里翁_銷售報告書.pdf'

S = json.load(open(HERE / 'summary.json'))
df = pd.read_csv(HERE / 'transactions.csv')
df['備註'] = df['備註'].fillna('')
df['yr'] = df['交易日期'].str[:3].astype(int)
L = S['本戶']
BASE, PK = L['扣車位面積'], L['車位估價']
SAME3, SAME5, R3 = S['同型_近三年'], S['同型_近五年'], S['近三年']
CMP = S['比較組']
CB, CA = CMP['同級距'], CMP['全部_不含本社區']
HI = S['樓層帶_110後'][2]
ASK = L['開價']                                       # ⛔ 對外報告不放建議成交價，試算以開價計
MGMT = L['管理費季'] / 3

def conv(net): return net * BASE + PK               # 房屋單價（已扣車位）→ 本戶總價（扣車位 83.41 坪＋1 車位）
def img(name):
    mime = 'image/png' if name.endswith('png') else 'image/jpeg'
    return f"data:{mime};base64,{base64.b64encode((HERE / name).read_bytes()).decode()}"
def f2(v): return '—' if v is None or pd.isna(v) else f'{v:.2f}'
def wan(v): return '—' if v is None or pd.isna(v) else f'{v:,.0f}'
def pct(a, b): return (a / b - 1) * 100

PHOTOS = [('室內_客廳.jpg', '客廳：水晶燈、線板天花與間接照明，整面書櫃與展示櫃。'),
          ('室內_餐廳.jpg', '餐廳：圓桌區連開放式廚房中島，牆面整排收納櫃。'),
          ('室內_廚房.jpg', '廚房：一字型廚具、洗碗機與電器櫃，門外為工作陽台。'),
          ('室內_主臥.jpg', '主臥：繃布床頭牆、窗邊臥榻收納，木地板。'),
          ('室內_主衛浴.jpg', '主衛浴：乾濕分離、淋浴間加浴缸，浴缸旁開窗、暖風機。'),
          ('外觀_雙塔.jpg', '社區外觀：雙塔新古典石材立面，拱門門廳。')]
PHOTOS = [(f, c) for f, c in PHOTOS if (HERE / f).exists()]

P_HOUSE = '房屋單價（已扣車位）'
P_ALL = '總價÷總坪數（車位一起算）'
MID = df[df['產品'].str.startswith('三房')].sort_values('交易日期')
B2 = df[df['戶別'] == 'B2'].sort_values('交易日期')
B2_LAST = B2.iloc[-1]
TOP = df[(df['yr'] >= 113) & df['產品'].str.startswith('三房')].sort_values('不含車單價').iloc[-1]   # 同型近三年最高
YR = {d['年']: d for d in S['年度']}

def svg_open(W, H): return [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC" font-size="10">']
def tt(d): y, m, _ = d.split('/'); return int(y) + (int(m) - .5) / 12

# ---------- 棟別配置（依樂居棟別圖重繪：A、B 兩棟各一層 3 戶 2 梯） ----------
def site_svg(hl='B2'):
    W, H = 380, 220
    s = svg_open(W, H)
    s.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#fff"/>')
    s.append('<rect x="20" y="8" width="320" height="16" fill="#e8edf0"/><text x="180" y="20" text-anchor="middle" fill="#5d6b76" font-size="9">西屯路二段 249-9 巷</text>')
    s.append('<rect x="20" y="194" width="340" height="18" fill="#e8edf0"/><text x="190" y="207" text-anchor="middle" fill="#5d6b76" font-size="9.5">青海路二段</text>')
    s.append('<rect x="346" y="8" width="16" height="186" fill="#e8edf0"/><text x="354" y="100" text-anchor="middle" fill="#5d6b76" font-size="9" writing-mode="tb">弘孝路</text>')
    units = {'B2': (30, 40, '之6'), 'B3': (108, 40, '之7'), 'A3': (186, 40, '之3'), 'A2': (264, 40, '之2'),
             'B1': (30, 112, '之5'), 'A1': (264, 112, '之1')}
    for k, (x, y, no) in units.items():
        me = k == hl
        s.append(f'<rect x="{x}" y="{y}" width="74" height="66" rx="3" fill="{"#C0392B" if me else "#eef3f6"}" stroke="{"#8e2a1f" if me else "#9fb3bf"}"/>'
                 f'<text x="{x+37}" y="{y+30}" text-anchor="middle" font-size="17" font-weight="700" fill="{"#fff" if me else "#1F4E5F"}">{k}</text>'
                 f'<text x="{x+37}" y="{y+48}" text-anchor="middle" font-size="9" fill="{"#fff" if me else "#5d6b76"}">188號{no}{"・本戶" if me else ""}</text>')
    for x in (108, 186):
        s.append(f'<rect x="{x}" y="112" width="24" height="66" fill="#d8e0e5"/><text x="{x+12}" y="150" text-anchor="middle" font-size="8.5" fill="#5d6b76" writing-mode="tb">梯間</text>')
    s.append('<text x="74" y="186" text-anchor="middle" font-size="8.5" fill="#7b8794">B 棟</text><text x="300" y="186" text-anchor="middle" font-size="8.5" fill="#7b8794">A 棟</text>')
    s.append('<text x="2" y="36" font-size="8.5" fill="#7b8794">↖北</text></svg>')
    return ''.join(s)
SITE = site_svg()

# ---------- 圖一：社區歷年成交（依產品分色；同型以年度中位連線） ----------
W, H, Lm, R, T, B = 560, 236, 40, 16, 24, 42
X0, X1, YMIN, YMAX = 102, 116, 16, 48
def X(t): return Lm + (t - X0) * (W - Lm - R) / (X1 - X0)
def Y(v): return T + (YMAX - v) * (H - T - B) / (YMAX - YMIN)
svg = svg_open(W, H)
for v in range(YMIN, YMAX + 1, 4):
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e3e8ec"/>'
               f'<text x="{Lm-6}" y="{Y(v)+3:.1f}" text-anchor="end" fill="#7b8794">{v}</text>')
for y in range(102, 116):
    svg.append(f'<text x="{X(y+.5):.1f}" y="{H-B+14}" text-anchor="middle" fill="#7b8794" font-size="9">{y}</text>')
svg.append(f'<text x="{W-R}" y="{T-10}" text-anchor="end" fill="#7b8794" font-size="9">單位：萬元／坪（{P_HOUSE}）</text>')
for v, c, lab, dy in [(L['不含車單價'], '#C0392B', f'本戶開價 {L["不含車單價"]:.1f}', -4), (CB['net'], '#C8963E', f'西屯同級距中位 {CB["net"]:.1f}', 11)]:
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{c}" stroke-width="1.2" stroke-dasharray="3 3"/>'
               f'<text x="{Lm+4}" y="{Y(v)+dy:.1f}" fill="{c}" font-size="9" font-weight="700">{lab}</text>')
STY = {'三房中坪（之3・之6・之7）': ('#1F4E5F', 4.0), '四房大坪（之1・之2・之5）': ('#9aa7b2', 3.4)}
for prod, (c, _) in STY.items():
    ym_p = df[df['產品'] == prod].groupby('yr')['不含車單價'].median()
    svg.append(f'<path d="{" ".join(("M" if i == 0 else "L") + f"{X(y+.5):.1f},{Y(v):.1f}" for i, (y, v) in enumerate(ym_p.items()))}" fill="none" stroke="{c}" stroke-width="{2.2 if prod.startswith("三房") else 1.4}" opacity=".85"/>')
for r in df.itertuples():
    c, rad = STY[r.產品]
    me = r.戶別 == 'B2'
    svg.append(f'<circle cx="{X(tt(r.交易日期)):.1f}" cy="{Y(r.不含車單價):.1f}" r="{rad}" fill="{c}" fill-opacity="{1 if r.產品.startswith("三房") else .75}" stroke="{"#C0392B" if me else "#fff"}" stroke-width="{1.4 if me else .8}"/>')
ym = MID.groupby('yr')['不含車單價'].median()
for y, v in ym.items():
    if y >= 106:
        svg.append(f'<text x="{X(y+.5):.1f}" y="{Y(v)+13:.1f}" text-anchor="middle" fill="#1F4E5F" font-size="8.4" font-weight="700">{v:.1f}</text>')
for i, prod in enumerate(STY):
    c, rad = STY[prod]; lx = Lm + 2 + i * 170
    svg.append(f'<circle cx="{lx+6}" cy="{H-10}" r="{rad}" fill="{c}"/><text x="{lx+14}" y="{H-7}" fill="#4a5560" font-size="8.4">{prod}</text>')
svg.append(f'<circle cx="{Lm+350}" cy="{H-10}" r="4" fill="#1F4E5F" stroke="#C0392B" stroke-width="1.4"/><text x="{Lm+358}" y="{H-7}" fill="#4a5560" font-size="8.4">紅框＝B2（之6，本戶同戶型）</text>')
svg.append('</svg>')
chart_comm = ''.join(svg)

comm_rows = ''
for r in df[df['yr'] >= 110].itertuples():
    cls = ' class="hl"' if r.戶別 == 'B2' else ''
    est = '*' if r.車位價來源.startswith('估算') else ''
    note = str(r.備註).replace(';', ' ').replace('。', '').strip()[:10]
    comm_rows += (f'<tr{cls}><td>{r.交易日期}</td><td>{r.戶別}・{r.樓層}F</td><td>{r.產品[:4]}</td><td>{r.格局 if isinstance(r.格局, str) else ""}</td><td class="num">{wan(r.總價萬)}</td>'
                  f'<td class="num">{r.總面積坪:.2f}</td><td class="num">{r.車位數}</td><td class="num">{wan(r.車位價萬)}{est}</td>'
                  f'<td class="num b">{r.不含車單價:.2f}{est}</td><td class="num">{r.含車單價:.2f}</td><td>{note}</td></tr>')

prod_rows = ''
for p in S['產品']:
    hl = ' class="hl"' if p['型'].startswith('三房') else ''
    prod_rows += (f'<tr{hl}><td>{p["型"]}</td><td class="num">{p["總面積中位"]:.2f}</td><td class="num">{p["扣車位面積中位"]:.2f}</td><td class="num">{p["全期n"]}</td>'
                  f'<td class="num">{p["近五年n"]}</td><td class="num b">{f2(p["近五年不含車中位"])}</td><td class="num">{p["近三年n"]}</td><td class="num b">{f2(p["近三年不含車中位"])}</td><td class="num">{f2(p["近三年含車中位"])}</td></tr>')
floor_rows = ''.join(f'<tr{" class=hl" if b["帶"].startswith("高") else ""}><td>{b["帶"]}</td><td class="num">{b["n"]}</td><td class="num b">{b["不含車中位"]:.2f}</td><td class="num">{b["含車中位"]:.2f}</td></tr>'
                     for b in S['樓層帶_110後'])

# ---------- 區域比較組（同級距，依社區彙整） ----------
cmp_rows = ''.join(f'<tr><td>{c["社區"]}</td><td class="num">{c["n"]}</td><td class="num b">{c["不含車中位"]:.2f}</td><td class="num">{c["含車中位"]:.2f}</td></tr>'
                   for c in CMP['同級距_社區'])
EX = next((r for r in CMP['明細'] if r['同級距'] and r['車位價']), None)

# ---------- 價格分析 ----------
anchors = [
    ('同型三房 近三年中位', f'113–115 年 {SAME3["n"]} 筆（之3／之7），扣車位約 84 坪', SAME3['net']),
    ('同型三房 近五年中位', f'111–115 年 {SAME5["n"]} 筆（含 B2 三筆）', SAME5['net']),
    ('同型近三年最高', f'{TOP["交易日期"]} {TOP["戶別"]}・{TOP["樓層"]}F，成交 {wan(TOP["總價萬"])} 萬', TOP['不含車單價']),
    ('B2 最近一筆', f'{B2_LAST["交易日期"]} {B2_LAST["樓層"]}F，成交 {wan(B2_LAST["總價萬"])} 萬、1 車位', B2_LAST['不含車單價']),
    ('高樓層 18–25F 中位', f'110 年後 {HI["n"]} 筆（不分戶型）', HI['不含車中位']),
    ('全社區 近三年中位', f'113–115 年 {R3["n"]} 筆（含四房大坪）', R3['net']),
    ('西屯同級距 中位', f'扣車位 {BASE-5:.0f}–{BASE+5:.0f} 坪、屋齡 10–20 年，{CB["n"]} 筆', CB['net']),
]
pos_rows = (f'<tr class="hl"><td>本戶開價</td><td>B2・20F・{L["總面積"]} 坪・1 車位</td><td class="num">{L["不含車單價"]:.2f}</td><td class="num">{L["含車單價"]:.2f}</td><td class="num">{wan(ASK)}</td></tr>')
for nm, why, up in anchors:
    pos_rows += f'<tr><td class="b">{nm}</td><td>{why}</td><td class="num">{up:.2f}</td><td class="num">{conv(up)/L["總面積"]:.2f}</td><td class="num">{wan(conv(up))}</td></tr>'

# ---------- 租賃 ----------
RENT = S['租賃']
def rent_note(r):
    t = []
    if r['每坪元'] >= 2000: t.append('單價異常，不列入參考')
    if '含管理費' in r['備註']: t.append('含管理費等')
    if '他戶產權' in r['備註']: t.append('含他戶車位')
    return '・'.join(t) or '—'
rent_rows = ''.join(f'<tr{" class=hl" if r["戶"] == "B2" else ""}><td>{r["日期"]}</td><td>{r["戶"]}・{r["樓層"]}F</td><td class="num">{r["面積坪"]:.2f}</td><td class="num">{r["車位"]}</td>'
                    f'<td class="num b">{r["月租萬"]:.2f}</td><td class="num">{r["每坪元"]:,}</td><td>{rent_note(r)}</td></tr>' for r in RENT['明細'])

# ---------- 房貸試算 ----------
RATE, YEARS, LTV = 0.022, 30, 0.8
loan = ASK * LTV
r_m = RATE / 12
pay = loan * 10000 * r_m / (1 - (1 + r_m) ** (-YEARS * 12))
down = ASK - loan

DISC = '永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號'
PHONE, LINE_ID, WEB = '0925-313-570', '@080akczk', 'sixhands.tw'
CONTACT = f'助哥 <span style="white-space:nowrap">{PHONE}</span>　｜　LINE {LINE_ID}　｜　{WEB}'
def foot(n):
    return (f'<div class="foot"><div>{DISC}<br><span class="ct">{CONTACT}</span></div>'
            f'<span>赫里翁 銷售報告書　{n}</span></div>')

def photo_block(items, h):
    cells = ''.join(f'<div><div class="photo"><img src="{img(f)}" style="height:{h}mm"></div><div class="cap">{c}</div></div>' for f, c in items)
    return f'<div class="two" style="margin-top:3mm">{cells}</div>'
photo_rows = ''.join(photo_block(PHOTOS[i:i + 2], 64) for i in range(0, len(PHOTOS), 2))

html = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>赫里翁 銷售報告書</title><style>
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: "Noto Sans CJK TC", sans-serif; color: #1e2a33; -webkit-print-color-adjust: exact; print-color-adjust: exact; background: #ddd; }}
.page {{ width: 210mm; height: 297mm; position: relative; overflow: hidden; page-break-after: always; background: #F7F9FA; margin: 0 auto; }}
.page:last-child {{ page-break-after: auto; }}
h1, h2, h3, .serif {{ font-family: "Noto Serif CJK TC", serif; }}
.pad {{ padding: 14mm 14mm 0 14mm; }}
.eyebrow {{ font-size: 7.6pt; letter-spacing: .45em; color: #C8963E; margin-bottom: 2mm; }}
.ttl {{ font-family: "Noto Serif CJK TC", serif; font-size: 18pt; color: #163a47; font-weight: 700; border-left: 5px solid #C8963E; padding-left: 9px; margin-bottom: 3mm; }}
.sub {{ font-size: 8.6pt; color: #5d6b76; margin-bottom: 4.5mm; line-height: 1.7; }}
h3.h {{ font-size: 11pt; color: #163a47; margin: 4mm 0 2mm; }}
table {{ width: 100%; border-collapse: collapse; font-size: 8.2pt; }}
th {{ background: #1F4E5F; color: #fff; padding: 4px 5px; text-align: left; font-weight: 500; font-size: 7.8pt; }}
td {{ padding: 4px 5px; border-bottom: 1px solid #e1e7eb; vertical-align: top; }}
tr:nth-child(even) td {{ background: #eef3f6; }}
tr.hl td {{ background: #fbeee0 !important; }}
.tight td, .tight th {{ padding: 2.6px 4px; font-size: 7.3pt; }}
.xs td, .xs th {{ padding: 1.8px 4px; font-size: 6.9pt; }}
.num {{ font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }}
.b {{ font-weight: 700; }}
.foot {{ position: absolute; bottom: 0; left: 0; right: 0; height: 11mm; background: #163a47; color: #b9cad3; font-size: 6.4pt; line-height: 1.6; display: flex; align-items: center; justify-content: space-between; padding: 0 14mm; }}
.foot .ct {{ color: #F0D9A4; font-weight: 700; letter-spacing: .03em; }}
.qr {{ background: #fff; padding: 1.6mm; border-radius: 2px; text-align: center; }}
.qr img {{ display: block; width: 100%; }}
.qr div {{ font-size: 6.6pt; color: #163a47; margin-top: .8mm; font-weight: 700; }}
.kpi {{ display: flex; gap: 3mm; margin-bottom: 4.5mm; }}
.kpi > div {{ flex: 1; background: #fff; border: 1px solid #dde4e9; border-top: 3px solid #C8963E; padding: 3mm 1.5mm; text-align: center; }}
.kpi .v {{ font-family: "Noto Serif CJK TC", serif; font-size: 17pt; color: #163a47; font-weight: 700; line-height: 1.1; }}
.kpi .u {{ font-size: 7.4pt; color: #C8963E; }}
.kpi .l {{ font-size: 7pt; color: #5d6b76; margin-top: 1.3mm; }}
.note {{ background: #fbf3e2; border-left: 4px solid #C8963E; padding: 3mm 4mm; font-size: 8.2pt; line-height: 1.75; }}
.warn {{ background: #fbeceb; border-left: 4px solid #C0392B; padding: 3mm 4mm; font-size: 8.2pt; line-height: 1.75; }}
.feat {{ display: flex; gap: 3mm; margin-bottom: 3.4mm; }}
.feat .no {{ font-family: "Noto Serif CJK TC", serif; font-size: 20pt; color: #C8963E; line-height: 1; min-width: 10mm; }}
.feat h3 {{ font-size: 10.4pt; color: #163a47; margin-bottom: .8mm; }}
.feat p {{ font-size: 8.3pt; line-height: 1.7; color: #33414c; }}
ul {{ margin-left: 4.5mm; }} li {{ font-size: 8.4pt; line-height: 1.8; margin-bottom: .5mm; }}
.photo {{ background: #e3eaef; padding: 1.8mm; border-radius: 2px; }}
.photo img {{ display: block; width: 100%; object-fit: cover; }}
.cap {{ font-size: 7pt; color: #7b8794; margin-top: 1.2mm; }}
.spec td:first-child {{ color: #8a6a2c; width: 22mm; white-space: nowrap; }}
.spec td {{ background: transparent !important; padding: 3px 4px; font-size: 8.2pt; }}
.two {{ display: flex; gap: 5mm; }} .two > div {{ flex: 1; min-width: 0; }}
</style></head><body>

<!-- P1 封面 -->
<div class="page" style="background:#102a33">
  <img src="{img('外觀_雙塔.jpg')}" style="position:absolute;left:0;top:0;width:210mm;height:128mm;object-fit:cover;object-position:center 30%">
  <div style="position:absolute;left:0;top:92mm;width:210mm;height:36mm;background:linear-gradient(180deg,rgba(16,42,51,0),#102a33)"></div>
  <div style="position:absolute;left:16mm;top:112mm;color:#E3B66A;font-size:8pt;letter-spacing:.5em">PROPERTY SALES REPORT</div>
  <div style="position:absolute;left:16mm;top:118mm;right:16mm;color:#fff">
    <div class="serif" style="font-size:11pt;color:#E3B66A;letter-spacing:.2em">臺中市西屯區 · 青海路二段 × 弘孝路 · 逢甲／七期生活圈</div>
    <div style="width:46mm;height:2px;background:#E3B66A;margin:5mm 0 4mm"></div>
    <h1 style="font-size:42pt;line-height:1.2">赫里翁</h1>
    <div class="serif" style="font-size:15pt;margin-top:2mm">買方銷售報告書 · 20 樓高樓邊間 · 三房 · 坡道平面車位</div>
    <div style="font-size:8.8pt;color:#b9cad3;margin-top:4mm;line-height:1.9">臺中市西屯區青海路二段188號20樓之6（B2 戶，B 棟端戶）<br>開價 {wan(ASK)} 萬　·　權狀 {L["總面積"]} 坪（含車位 {L["車位面積"]} 坪）　·　{L["格局"]}　·　{L["朝向"]}向　·　精裝修</div>
    <div style="margin-top:7mm;border-top:1px solid #3b5b66;padding-top:5mm">
      <div style="font-size:7.6pt;color:#E3B66A;letter-spacing:.3em">核心數字</div>
      <div style="font-size:9.3pt;line-height:1.9;margin-top:2mm">
        興富發 2011 年完工的 25 層雙塔，143 戶、一層三戶兩梯、一樓無店面；本戶在 20 樓 B 棟端戶。<br>
        社區同型三房近五年成交中位 <b>{SAME5["net"]:.1f} 萬/坪</b>，高樓層（18–25F）<b>{HI["不含車中位"]:.1f}</b>；西屯同坪數大樓 <b>{CB["net"]:.1f}</b>。<br>
        本社區車位每席約 6 坪，兩種單價口徑幾乎相同，比較起來直觀。<br>
        <span style="color:#E3B66A">開價 {wan(ASK)} 萬，{P_HOUSE} {L["不含車單價"]:.1f} 萬/坪（含精裝修與 1 席平面車位）。</span>
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
  <div style="position:absolute;left:16mm;right:16mm;bottom:7mm;font-size:6.8pt;color:#8fa6b1;line-height:1.7">資料：內政部實價登錄（青海路二段188號逐門牌 101/01–115/10；西屯區大樓／華廈 屋齡10–20年 70–100坪 113/01–115/10，查詢 2026-10-23）<br>{DISC}</div>
</div>

<!-- P2 物件總覽 -->
<div class="page"><div class="pad">
  <div class="eyebrow">01 · PROPERTY OVERVIEW</div>
  <div class="ttl">物件總覽</div>
  <div class="kpi">
    <div><div class="v">{wan(ASK)}</div><div class="u">萬元</div><div class="l">開價（含 1 車位）</div></div>
    <div><div class="v">{L["總面積"]}</div><div class="u">坪</div><div class="l">權狀總坪數（含車位）</div></div>
    <div><div class="v">{L["主建物"]+L["附屬"]:.2f}</div><div class="u">坪</div><div class="l">主建物＋附屬（室內可用）</div></div>
    <div><div class="v">20<span style="font-size:10pt">／25F</span></div><div class="u">樓層</div><div class="l">高樓層・B 棟端戶</div></div>
    <div><div class="v">{MGMT:,.0f}</div><div class="u">元／月</div><div class="l">管理費（季繳 {L["管理費季"]:,} 元）</div></div>
  </div>
  <div class="two">
    <div>
      <h3 class="h">本戶資料</h3>
      <table class="spec">
        <tr><td>地址</td><td>臺中市西屯區青海路二段188號20樓之6</td></tr>
        <tr><td>戶別</td><td>B2 戶（之6），B 棟端戶</td></tr>
        <tr><td>格局</td><td>{L["格局"]}・{L["朝向"]}向</td></tr>
        <tr><td>坪數</td><td>主建物 {L["主建物"]}＋附屬 {L["附屬"]}（陽台 {L["陽台"]}／雨遮 {L["雨遮"]}）＋共同使用 {L["共同"]}（含車位 {L["車位面積"]}）＝{L["總面積"]} 坪</td></tr>
        <tr><td>土地</td><td>{L["土地"]} 坪</td></tr>
        <tr><td>車位</td><td>坡道平面 1 席（編號 155）</td></tr>
        <tr><td>現況</td><td>精裝修，系統櫃收納、廚具家電齊全（見實景照片）</td></tr>
        <tr><td>管理費</td><td>季繳 {L["管理費季"]:,} 元（約 {MGMT:,.0f} 元／月）</td></tr>
        <tr><td>屋齡</td><td>約 {L["屋齡"]} 年（建築完成 100/01）</td></tr>
        <tr><td>物件編號</td><td>{L["物件編號"]}</td></tr>
      </table>
    </div>
    <div>
      <h3 class="h">社區資料</h3>
      <table class="spec">
        <tr><td>社區</td><td>赫里翁（興富發建設）</td></tr>
        <tr><td>規模</td><td>總戶數 143 戶・地上 25 層／地下 4 層・A、B 雙塔</td></tr>
        <tr><td>配置</td><td>每棟一層 3 戶、2 部電梯・一樓無店面</td></tr>
        <tr><td>基地</td><td>約 1,125 坪・商業區</td></tr>
        <tr><td>結構</td><td>鋼筋混凝土（RC）</td></tr>
        <tr><td>公設比</td><td>32.04%（樂居）</td></tr>
        <tr><td>車位</td><td>坡道平面，每席登記約 5.3–6.1 坪</td></tr>
        <tr><td>建築設計</td><td>大容聯合建築師事務所</td></tr>
        <tr><td>營造</td><td>齊裕營造</td></tr>
        <tr><td>學區</td><td>上石國小・至善國中（雙語）</td></tr>
      </table>
    </div>
  </div>
  <h3 class="h">棟別配置</h3>
  <div style="display:flex;gap:5mm;align-items:center">
    <div style="flex:1.25">{SITE}</div>
    <div style="flex:1;font-size:8.2pt;line-height:1.8;color:#33414c">
      基地臨青海路二段、弘孝路與西屯路二段 249-9 巷，分 A、B 兩棟，<b>每棟一層 3 戶、2 部電梯</b>。<br>
      本戶為 <b style="color:#C0392B">B2（188號之6）</b>，位在 B 棟角落的端戶，兩面採光；主臥外有八角窗陽台。
      <div class="cap" style="margin-top:2mm">依樂居棟別圖重繪，非比例尺。</div>
    </div>
  </div>
</div>{foot(2)}</div>

<!-- P3 格局與賣點 -->
<div class="page"><div class="pad">
  <div class="eyebrow">02 · FLOOR PLAN</div>
  <div class="ttl">格局與六大賣點</div>
  <div class="photo" style="background:#fff"><img src="{img('格局圖.png')}" style="height:92mm;object-fit:contain"></div>
  <div class="cap">※ 室內裝修平面配置圖（設計參考用），實際格局與尺寸以現場丈量及合約圖說為準。</div>
  <div class="two" style="margin-top:4mm">
    <div>
      <div class="feat"><div class="no">01</div><div><h3>20 樓高樓・端戶邊間</h3><p>25 層雙塔的 20 樓，B 棟角落端戶、兩面採光；主臥八角窗陽台與主衛浴開窗都看得到西屯市景。</p></div></div>
      <div class="feat"><div class="no">02</div><div><h3>三房兩衛・空間寬</h3><p>扣車位 {BASE:.1f} 坪做三房，主建物＋附屬 {L["主建物"]+L["附屬"]:.1f} 坪；客廳、餐廳、開放式廚房連成一線，主臥附衛浴。</p></div></div>
      <div class="feat"><div class="no">03</div><div><h3>歐式精裝・收納到位</h3><p>水晶燈、線板天花、整面書櫃與展示櫃；廚房含洗碗機與電器櫃，主衛浴乾濕分離加浴缸。</p></div></div>
    </div>
    <div>
      <div class="feat"><div class="no">04</div><div><h3>一層三戶兩梯・一樓無店面</h3><p>每棟一層只有 3 戶共用 2 部電梯；一樓沒有店面，出入只有住戶，單純安靜。</p></div></div>
      <div class="feat"><div class="no">05</div><div><h3>飯店式公設</h3><p>實登共有部分登載社區游泳池；網路資料另列 SPA、健身房、宴會廳、交誼廳、會議室，挑高門廳。</p></div></div>
      <div class="feat"><div class="no">06</div><div><h3>坡道平面車位・交通順</h3><p>坡道平面 1 席不必排機械；開車約 3 分鐘接 74 號快速道路與國道一號，雙語學區上石國小／至善國中。</p></div></div>
    </div>
  </div>
  <div class="note" style="margin-top:2mm"><b>室內可用 {L["主建物"]+L["附屬"]:.2f} 坪。</b>主建物 {L["主建物"]} 坪＋陽台 {L["陽台"]}＋雨遮 {L["雨遮"]} 坪；權狀 {L["總面積"]} 坪中車位佔 {L["車位面積"]} 坪，扣掉車位後的公設約 {L["共同"]-L["車位面積"]:.1f} 坪。</div>
</div>{foot(3)}</div>

<!-- P4 實景照片 -->
<div class="page"><div class="pad">
  <div class="eyebrow">03 · INTERIOR</div>
  <div class="ttl">實景照片</div>
  <div class="sub">本戶現況照片，裝潢、家具與家電依實際點交為準。</div>
  {photo_rows}
</div>{foot(4)}</div>

<!-- P5 區位 -->
<div class="page"><div class="pad">
  <div class="eyebrow">04 · LOCATION &amp; COMMUNITY</div>
  <div class="ttl">區位與生活機能</div>
  <div class="sub">位於西屯區青海路二段與弘孝路口，<b>不在第七期重劃區內</b>；往東接七期市政商圈，往西接逢甲商圈，兩邊都在短車程內。</div>
  <table class="spec" style="margin-bottom:4mm">
    <tr><td>商圈</td><td>逢甲商圈、萬家福青海店；車程約 5 分鐘到七期新光三越、大遠百</td></tr>
    <tr><td>交通</td><td>開車約 3 分鐘接 74 號快速道路與中山高速公路（國道一號）；社區旁有「青海弘孝路口」公車站</td></tr>
    <tr><td>學區</td><td>市立上石國小、市立至善國中（雙語學區）</td></tr>
    <tr><td>綠地</td><td>福星公園</td></tr>
    <tr><td>社區</td><td>2011 年（民國 100 年 1 月）完工；歐式新古典石材立面、挑高門廳；一樓圓柱環廊、無店面</td></tr>
  </table>
  <div class="note"><b>為什麼是這裡：</b>同樣在西屯、去七期與逢甲都方便，但價格比七期重劃區內的大樓低一截。社區 101–115 年實登成交 {S["有效筆數"]} 筆，各戶型都有成交可以比。</div>

  <h3 class="h" style="margin-top:5mm">社區產品分型</h3>
  <div class="sub" style="margin-bottom:2mm">實登總坪數含 1–3 席車位，直接比會失準；依門牌「之幾」分型，比較扣除車位後的坪數。本戶 B2 屬三房中坪。</div>
  <table>
    <tr><th>產品</th><th>總坪數中位</th><th>扣車位中位</th><th>全期筆數</th><th>111–115 筆數</th><th>111–115 {P_HOUSE}</th><th>113–115 筆數</th><th>113–115 {P_HOUSE}</th><th>113–115 {P_ALL}</th></tr>
    {prod_rows}
  </table>
  <div class="cap">淡橘底為本戶同型。單位：坪、萬元／坪。</div>
  <h3 class="h" style="margin-top:5mm">樓層：高樓層有溢價</h3>
  <div class="two" style="align-items:flex-start">
    <div><table><tr><th>樓層帶（110 年後）</th><th>筆數</th><th>{P_HOUSE}</th><th>{P_ALL}</th></tr>{floor_rows}</table></div>
    <div style="font-size:8.2pt;line-height:1.8;color:#33414c">25 層的社區，110 年後 18–25 樓成交中位 <b>{HI["不含車中位"]:.1f}</b>，比 2–17 樓高約 {pct(HI["不含車中位"], max(S["樓層帶_110後"][0]["不含車中位"], S["樓層帶_110後"][1]["不含車中位"])):.0f}%。本戶 20 樓，屬高樓層帶。<div class="cap" style="margin-top:2mm">不分戶型；高樓層樣本 {HI["n"]} 筆。</div></div>
  </div>
</div>{foot(5)}</div>

<!-- P6 社區成交 -->
<div class="page"><div class="pad">
  <div class="eyebrow">05 · COMMUNITY HISTORY</div>
  <div class="ttl">赫里翁歷年成交</div>
  <div class="sub">青海路二段188號逐門牌查詢 101/01–115/10，買賣 {S["原始筆數"]} 筆，排除特殊關係、債務抵償與資料異常 {len(S["排除"])} 筆，有效 {S["有效筆數"]} 筆。
  <b>深色點與線為本戶同型（三房中坪）</b>，線為年度中位數；紅框為 B2（之6）。</div>
  {chart_comm}
  <div class="note" style="margin:3mm 0">同型三房年度中位：106 年 {ym.get(106, float("nan")):.1f} → 110 年 {ym.get(110):.1f} → 112 年 {ym.get(112):.1f} → 114 年 <b>{ym.get(114):.1f}</b>。
  B2 最近一筆為 {B2_LAST["交易日期"]} {B2_LAST["樓層"]}F {B2_LAST["不含車單價"]:.1f}；113 年後 B2 尚無成交。</div>
  <table class="tight xs">
    <tr><th>日期</th><th>戶別</th><th>產品</th><th>格局</th><th>總價（萬）</th><th>總坪數</th><th>車位</th><th>車位價</th><th>{P_HOUSE}</th><th>{P_ALL}</th><th>備註</th></tr>
    {comm_rows}
  </table>
  <div class="cap">列出 110 年後成交，淡橘底為 B2。車位價未揭露者以本社區坡道平面每席中位 {PK} 萬估算（標 *）。單位：萬元／坪。</div>
</div>{foot(6)}</div>

<!-- P7 區域比較 -->
<div class="page"><div class="pad">
  <div class="eyebrow">06 · AREA COMPARISON</div>
  <div class="ttl">西屯同坪數大樓比較</div>
  <div class="sub">條件：西屯區、大樓／華廈、屋齡 10–20 年、總面積 70–100 坪，113/01–115/10，共 {CMP["有效"]} 筆有效（排除特殊關係 {CMP["排除特殊關係"]} 筆、一樓 {CMP["一樓排除"]} 筆）。
  再依本戶扣車位面積 {BASE:.2f} 坪，取 <b>扣車位 {BASE-5:.1f}–{BASE+5:.1f} 坪</b>的 {CB["n"]} 筆為同級距（不含本社區）。</div>
  <div class="note" style="margin-bottom:3.5mm"><b>有車位的物件，單價怎麼看？</b>總價裡含車位，所以有兩種算法：<br>
  ① <b>{P_HOUSE}</b>＝（總價－車位價）÷（總坪數－車位坪數），用來比房子本身。<br>
  ② <b>{P_ALL}</b>，網路上常看到的是這個數字。<br>
  {f'例：{EX["社區"]} {EX["日期"]} 成交 {wan(EX["總價"])} 萬、{EX["坪數"]:.2f} 坪，含車位 {EX["車位"]} 席 {wan(EX["車位價"])} 萬（{EX["坪數"]-EX["扣車位"]:.2f} 坪）→ ① <b>{EX["不含車"]:.1f}</b>；② {EX["含車"]:.1f}。<br>' if EX else ''}
  本戶：開價 {wan(ASK)} 萬、{L["總面積"]} 坪、車位 1 席（以社區每席 {PK} 萬、{L["車位面積"]} 坪計）→ ① ({wan(ASK)}－{PK})÷{BASE:.2f} 坪＝<b>{L["不含車單價"]:.2f}</b>；② {wan(ASK)}÷{L["總面積"]} 坪＝{L["含車單價"]:.2f}。<br>
  赫里翁車位每席約 6 坪、180 萬，每坪價和房屋差不多，所以 ① 與 ② 很接近；比較組多為兩席車位，② 會比 ① 低一些。</div>
  <div class="kpi">
    <div><div class="v">{CB["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">西屯同級距 {P_HOUSE}</div></div>
    <div><div class="v">{CB["gross"]:.1f}</div><div class="u">萬/坪</div><div class="l">西屯同級距 {P_ALL}</div></div>
    <div><div class="v">{CA["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">比較組全部 {CA["n"]} 筆 {P_HOUSE}</div></div>
    <div><div class="v">{SAME5["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">赫里翁同型近五年 {P_HOUSE}</div></div>
  </div>
  <div class="two">
    <div style="flex:1.3">
      <table class="tight"><tr><th>同級距社區（{CB["n"]} 筆）</th><th>筆數</th><th>{P_HOUSE}</th><th>{P_ALL}</th></tr>{cmp_rows}</table>
      <div class="cap">依社區彙整之中位數；逐筆明細見網站行情頁。「未填社區名」為實登空白。單位：萬元／坪。</div>
    </div>
    <div style="font-size:8.2pt;line-height:1.8;color:#33414c">
      <b>怎麼看這張表：</b><br>同級距 {CB["n"]} 筆中位 {CB["net"]:.1f}；成交最多的國家一號院、鄉林皇居、市政愛敦閣，中位都在 42 上下。<br><br>
      同樣坪數，如來、世紀之頂、百達富裔、市政文華等社區多在 33–39 之間；西屯範圍大，社區條件差很多，價差可到 10 萬/坪以上。<br><br>
      赫里翁同型三房近五年 {SAME5["net"]:.1f}，比西屯同級距中位低約 {abs(pct(SAME5["net"], CB["net"])):.0f}%。
    </div>
  </div>
</div>{foot(7)}</div>

<!-- P8 價格分析 -->
<div class="page"><div class="pad">
  <div class="eyebrow">07 · PRICE ANALYSIS</div>
  <div class="ttl">價格分析：開價放進行情看</div>
  <div class="sub">把各參考點的「{P_HOUSE}」套到本戶（扣車位 {BASE:.2f} 坪＋車位 1 席 {PK} 萬），換算成「照這個行情，本戶值多少」。</div>
  <div class="kpi">
    <div><div class="v">{wan(ASK)}</div><div class="u">萬元</div><div class="l">開價（{P_HOUSE} {L["不含車單價"]:.1f}）</div></div>
    <div><div class="v">{L["含車單價"]:.1f}</div><div class="u">萬/坪</div><div class="l">開價 {P_ALL}</div></div>
    <div><div class="v">{wan(conv(HI["不含車中位"]))}</div><div class="u">萬元</div><div class="l">照社區高樓層中位換算</div></div>
    <div><div class="v">{wan(conv(CB["net"]))}</div><div class="u">萬元</div><div class="l">照西屯同級距中位換算</div></div>
  </div>
  <table>
    <tr><th>參考點</th><th>說明</th><th>{P_HOUSE}</th><th>{P_ALL}</th><th>換算本戶（萬）</th></tr>
    {pos_rows}
  </table>
  <h3 class="h">怎麼解讀</h3>
  <ul>
    <li><b>跟西屯同坪數大樓比：</b>本戶 {P_HOUSE} {L["不含車單價"]:.1f}，比西屯同級距中位 {CB["net"]:.1f} 高約 {pct(L["不含車單價"], CB["net"]):.0f}%，與同級距中較高的一群社區相當。</li>
    <li><b>跟社區自己的成交比：</b>開價高於社區過往成交。同型三房近五年中位 {SAME5["net"]:.1f}、高樓層中位 {HI["不含車中位"]:.1f}，同型近三年最高一筆為 {TOP["交易日期"]} {TOP["戶別"]} {TOP["樓層"]}F 的 {TOP["不含車單價"]:.1f}。</li>
    <li><b>趨勢往上：</b>同型年度中位從 110 年 {ym.get(110):.1f} 到 114 年 {ym.get(114):.1f}；但 115 年社區尚無成交，最新行情要以下一筆成交確認。</li>
    <li><b>差額看什麼：</b>20 樓高樓層、端戶兩面採光、整套精裝修與系統櫃，是本戶與社區過往成交（含毛胚屋、低樓層）的主要差異；看屋時可把裝修內容、景觀與屋況一併比較。</li>
    <li><b>車位口徑單純：</b>本社區車位每席約 6 坪，兩種單價幾乎相同，網路上看到的「總價÷總坪數」可以直接拿來比社區行情。</li>
  </ul>
  <div class="warn" style="margin-top:3mm">社區近三年僅 {R3["n"]} 筆成交、同型近三年 {SAME3["n"]} 筆，行情帶寬較寬。以上換算依實登推估，不是估價師的估價，實際成交以雙方議價為準。</div>
</div>{foot(8)}</div>

<!-- P9 購屋試算 -->
<div class="page"><div class="pad">
  <div class="eyebrow">08 · BUYER'S GUIDE</div>
  <div class="ttl">購屋試算與租金參考</div>
  <div class="kpi">
    <div><div class="v">{ASK:,}</div><div class="u">萬元</div><div class="l">以開價試算</div></div>
    <div><div class="v">{wan(down)}</div><div class="u">萬元</div><div class="l">自備款（兩成）</div></div>
    <div><div class="v">{wan(loan)}</div><div class="u">萬元</div><div class="l">貸款（八成）</div></div>
    <div><div class="v">{pay/10000:.1f}</div><div class="u">萬元／月</div><div class="l">本息攤還</div></div>
  </div>
  <div class="note">試算假設：貸款八成、年利率 {RATE*100:.1f}%、{YEARS} 年本息平均攤還，每月約 {pay:,.0f} 元。另需預留契稅、代書、仲介服務費。實際成數、利率與年限依銀行鑑價與個人條件核定。</div>
  <h3 class="h">社區出租實登（101–115，共 {RENT["筆數"]} 筆）</h3>
  <table class="tight">
    <tr><th>日期</th><th>戶別</th><th>面積（坪）</th><th>車位</th><th>月租（萬）</th><th>元／坪／月</th><th>說明</th></tr>
    {rent_rows}
  </table>
  <div class="cap">最新一筆為 {RENT["最新"]}，近三年無租賃實登；淡橘底為 B2（103 年 5F、{RENT["明細"][-1]["月租萬"]:.2f} 萬）。面積依實登登記，部分未含車位。本社區以自住為主。</div>
  <h3 class="h">看屋重點</h3>
  <ul>
    <li><b>裝修內容：</b>請索取裝修項目與保固資料，確認哪些家具、家電與燈具隨屋點交。</li>
    <li><b>景觀與座向：</b>{L["朝向"]}向，建議下午看一次西曬與隔熱，晚上看一次夜景。</li>
    <li><b>增建：</b>社區部分成交備註陽台外推或其他增建，請以現況與不動產說明書確認。</li>
    <li><b>車位：</b>坡道平面 1 席（編號 155），{L["車位面積"]} 坪含於權狀總坪數；位置與使用以分管協議為準。</li>
    <li><b>管理費與公設：</b>季繳 {L["管理費季"]:,} 元（約 {MGMT/L["總面積"]:.0f} 元／坪／月），可索取管委會收支、泳池等公設的開放時間與修繕紀錄。</li>
  </ul>
  <div style="margin-top:4mm;position:relative;background:#fff;border:1px solid #dde4e9;padding:4mm 36mm 4mm 6mm;font-size:7.6pt;line-height:1.75;color:#4a5560">
    <div class="b" style="font-size:9.4pt;color:#163a47;margin-bottom:1.2mm">資料來源與免責聲明</div>
    實價登錄：內政部不動產交易實價查詢服務網，青海路二段188號買賣與租賃（101/01–115/10）；西屯區住宅大樓／華廈・屋齡10–20年・總面積70–100坪買賣（113/01–115/10）；查詢日 2026-10-23。社區資料整理自樂居、信義房屋等網路公開資訊與售屋資料表；公設與建築特色部分取自建案介紹，以現況為準。<br>
    本報告書為不動產經紀業務之行銷參考資料，非不動產估價師出具之估價報告。行情統計與試算係依公開資料整理，不構成價格保證、投資建議或獲利承諾。實際面積、用途、產權及使用現況，以權狀、謄本、不動產說明書及買賣契約記載為準。
    <div style="position:absolute;right:7mm;top:50%;margin-top:-11mm;width:22mm;height:22mm;border:2.5px solid #b3261e;border-radius:50%;color:#b3261e;display:flex;align-items:center;justify-content:center;text-align:center;font-family:'Noto Serif CJK TC',serif;font-size:8pt;font-weight:700;line-height:1.3;transform:rotate(-12deg)">僅供<br>參考</div>
  </div>
  <div style="margin-top:4mm;display:flex;align-items:center;justify-content:center;gap:7mm;background:#163a47;padding:5mm 7mm;border-radius:2px">
    <div style="color:#fff">
      <div style="font-size:7.4pt;color:#E3B66A;letter-spacing:.3em">預約帶看・行情諮詢</div>
      <div class="serif" style="font-size:16pt;font-weight:700;margin-top:1mm">助哥　<span style="color:#F0D9A4;white-space:nowrap">{PHONE}</span></div>
      <div style="font-size:8pt;color:#b9cad3;margin-top:1mm;line-height:1.7">永慶不動產 七期河南市政店<br>LINE {LINE_ID}　｜　{WEB}</div>
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
    b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
    pg = b.new_page()
    pg.goto(OUT_HTML.resolve().as_uri())
    pg.wait_for_timeout(500)
    pg.pdf(path=str(OUT_PDF), prefer_css_page_size=True, print_background=True)
    b.close()
print('PDF  →', OUT_PDF)
