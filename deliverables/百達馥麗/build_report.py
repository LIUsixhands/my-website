"""百達馥麗 銷售報告書（給買方）：讀 summary.json / transactions.csv / listings.json → 產 HTML → Playwright 輸出 PDF。
口徑：社區全部成交皆含坡道平面車位，單價一律並列「房屋單價（已扣車位）」與「總價÷總坪數（車位一起算）」；
同型比較以扣車位面積約 88 坪的「三房＋1」為主，區域比較組為西區・屋齡 15–20 年・80–100 坪（112–115）。"""
import base64, json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
OUT_HTML = HERE / '百達馥麗_銷售報告書.html'
OUT_PDF = HERE / '百達馥麗_銷售報告書.pdf'

S = json.load(open(HERE / 'summary.json'))
LST = json.load(open(HERE / 'listings.json')) if (HERE / 'listings.json').exists() else []
df = pd.read_csv(HERE / 'transactions.csv')
df['備註'] = df['備註'].fillna('')
df['yr'] = df['交易日期'].str[:3].astype(int)
L = S['本戶']
BASE, PK = L['扣車位面積'], L['車位估價']
SAME4, SAME6 = S['同型_近四年'], S['同型_近六年']
CMP = S['比較組']
CMP3 = CMP['近三年_不含本社區']
RENT = S['租賃']
TARGET = 3750                                       # 小登推估：同型中位 39.2 與 19F 高點 43.0 之間，計入整戶精裝
T_NET = (TARGET - PK) / BASE
T_GROSS = TARGET / L['總面積']

def conv(net): return net * BASE + PK               # 不含車單價 → 本戶總價（88 坪＋1 車位）
def img(name):
    mime = 'image/png' if name.endswith('png') else 'image/jpeg'
    return f"data:{mime};base64,{base64.b64encode((HERE / name).read_bytes()).decode()}"
def f2(v): return '—' if v is None or pd.isna(v) else f'{v:.2f}'
def wan(v): return '—' if v is None or pd.isna(v) else f'{v:,.0f}'

P_HOUSE = '房屋單價（已扣車位）'
P_ALL = '總價÷總坪數（車位一起算）'
SAME = df[df['產品'].str.startswith('三房')].sort_values('交易日期')
TOP = SAME[SAME['交易日期'] == '113/01/27'].iloc[0]       # 同型 19F 最近高點
LAST = SAME[SAME['交易日期'] == '114/09/05'].iloc[0]      # 同型 28F 最新一筆

def svg_open(W, H): return [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC" font-size="10">']
def tt(d): y, m, _ = d.split('/'); return int(y) + (int(m) - .5) / 12

# ---------- 圖一：社區歷年成交（101–115，依產品分色；三房＋1 連線） ----------
W, H, Lm, R, T, B = 560, 230, 40, 16, 24, 42
X0, X1, YMIN, YMAX = 101, 116, 20, 48
def X(t): return Lm + (t - X0) * (W - Lm - R) / (X1 - X0)
def Y(v): return T + (YMAX - v) * (H - T - B) / (YMAX - YMIN)
svg = svg_open(W, H)
for v in range(YMIN, YMAX + 1, 5):
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e3e8ec"/>'
               f'<text x="{Lm-6}" y="{Y(v)+3:.1f}" text-anchor="end" fill="#7b8794">{v}</text>')
for y in range(101, 116):
    svg.append(f'<text x="{X(y+.5):.1f}" y="{H-B+14}" text-anchor="middle" fill="#7b8794" font-size="9">{y}</text>')
svg.append(f'<text x="{W-R}" y="{T-10}" text-anchor="end" fill="#7b8794" font-size="9">單位：萬元／坪（{P_HOUSE}）</text>')
for v, c, lab, dy in [(L['不含車單價'], '#C0392B', f'本戶開價 {L["不含車單價"]:.1f}', -4), (T_NET, '#2E7D4F', f'建議成交參考 {T_NET:.1f}（{TARGET:,} 萬）', 11)]:
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{c}" stroke-width="1.2" stroke-dasharray="3 3"/>'
               f'<text x="{Lm+4}" y="{Y(v)+dy:.1f}" fill="{c}" font-size="9" font-weight="700">{lab}</text>')
STY = {'三房＋1（約 88 坪）': ('#1F4E5F', 4.2), '四房（約 100–104 坪）': ('#C8963E', 3.2),
       '四房大坪（約 112–117 坪）': ('#9aa7b2', 3.2), '頂層大戶（約 214 坪）': ('#6b7d8a', 3.2)}
# 三房＋1 以年度中位連線，避免同年多點鋸齒
ym = SAME.groupby('yr')['不含車單價'].median()
svg.append(f'<path d="{" ".join(("M" if i == 0 else "L") + f"{X(y+.5):.1f},{Y(v):.1f}" for i, (y, v) in enumerate(ym.items()))}" fill="none" stroke="#1F4E5F" stroke-width="2.2" opacity=".85"/>')
for r in df.itertuples():
    c, rad = STY[r.產品]
    svg.append(f'<circle cx="{X(tt(r.交易日期)):.1f}" cy="{Y(r.不含車單價):.1f}" r="{rad}" fill="{c}" fill-opacity="{1 if r.產品.startswith("三房") else .75}" stroke="#fff" stroke-width=".8"/>')
for y, v in ym.items():
    if y >= 108:
        svg.append(f'<text x="{X(y+.5):.1f}" y="{Y(v)+13:.1f}" text-anchor="middle" fill="#1F4E5F" font-size="8.4" font-weight="700">{v:.1f}</text>')
for i, (prod, name) in enumerate([(k, k.replace('（約', ' ').replace('）', '')) for k in STY]):
    c, rad = STY[prod]; lx = Lm + 2 + i * 132
    svg.append(f'<circle cx="{lx+6}" cy="{H-10}" r="{rad}" fill="{c}"/><text x="{lx+14}" y="{H-7}" fill="#4a5560" font-size="8.4">{name}</text>')
svg.append('</svg>')
chart_comm = ''.join(svg)

comm_rows = ''
for r in df[df['yr'] >= 110].itertuples():
    cls = ' class="hl"' if r.產品.startswith('三房') else ''
    est = '*' if r.車位價來源.startswith('估算') else ''
    note = r.備註.replace(';', ' ').replace('含傢俱設備費', '含傢俱').strip()[:12]
    comm_rows += (f'<tr{cls}><td>{r.交易日期}</td><td>{r.棟別}・{r.樓層}F</td><td>{r.產品.split("（")[0]}</td><td class="num">{wan(r.總價萬)}</td>'
                  f'<td class="num">{r.總面積坪:.2f}</td><td class="num">{r.車位數}</td><td class="num">{wan(r.車位價萬)}{est}</td>'
                  f'<td class="num b">{r.不含車單價:.2f}{est}</td><td class="num">{r.含車單價:.2f}</td><td>{note}</td></tr>')

prod_rows = ''
for p in S['產品']:
    hl = ' class="hl"' if p['型'].startswith('三房') else ''
    prod_rows += (f'<tr{hl}><td>{p["型"]}</td><td class="num">{p["總面積中位"]:.2f}</td><td class="num">{p["全期n"]}</td>'
                  f'<td class="num">{p["近四年n"]}</td><td class="num b">{f2(p["近四年不含車中位"])}</td><td class="num">{f2(p["近四年含車中位"])}</td></tr>')

# ---------- 區域比較組 ----------
cmp_rows = ''
for r in CMP['明細']:
    cls = ' class="hl"' if r['本社區'] else ''
    est = '' if r['車位價'] else '*'
    cmp_rows += (f'<tr{cls}><td>{r["日期"]}</td><td>{r["社區"]}</td><td>{r["門牌"]}</td><td class="num">{r["樓層"]}</td><td class="num">{wan(r["總價"])}</td>'
                 f'<td class="num">{r["坪數"]:.2f}</td><td>{r["車位"]}・{r["車位類別"].replace("坡道", "")}</td>'
                 f'<td class="num b">{r["不含車"]:.2f}{est}</td><td class="num">{r["含車"]:.2f}</td></tr>')
EX = next(r for r in CMP['明細'] if r['社區'] == '鄉林君悅' and r['車位價'])

# ---------- 價格分析：各參考點換算本戶（扣車位 88 坪＋1 席坡道平面 160 萬） ----------
anchors = [
    ('同型 19F（B1 正上方）', f'113/01 成交 {wan(TOP["總價萬"])} 萬，含 2 車位、陽台外推', TOP['不含車單價']),
    ('同型 近四年中位', f'112–115 年 {SAME4["n"]} 筆（9F／19F／28F）', SAME4['net']),
    ('同型 28F 最新一筆', f'114/09 成交 {wan(LAST["總價萬"])} 萬，1 車位', LAST['不含車單價']),
    ('同型 近六年中位', f'110–115 年 {SAME6["n"]} 筆', SAME6['net']),
    ('西區同級大樓 近三年中位', f'屋齡 15–20 年、80–100 坪，{CMP3["n"]} 筆（不含本社區）', CMP3['net']),
]
pos_rows = (f'<tr class="hl"><td>本戶開價</td><td>B1・16F・93.16 坪・1 車位</td><td class="num">{L["不含車單價"]:.2f}</td><td class="num">{L["含車單價"]:.2f}</td><td class="num">{wan(L["開價"])}</td></tr>'
            f'<tr style="font-weight:700"><td style="background:#e4f1e8;color:#2E7D4F">建議成交參考</td><td style="background:#e4f1e8;color:#2E7D4F">同型行情＋整戶精裝、空屋</td>'
            f'<td class="num" style="background:#e4f1e8;color:#2E7D4F">{T_NET:.2f}</td><td class="num" style="background:#e4f1e8;color:#2E7D4F">{T_GROSS:.2f}</td>'
            f'<td class="num" style="background:#e4f1e8;color:#2E7D4F">{TARGET:,}</td></tr>')
for nm, why, up in anchors:
    pos_rows += f'<tr><td class="b">{nm}</td><td>{why}</td><td class="num">{up:.2f}</td><td class="num">{conv(up)/L["總面積"]:.2f}</td><td class="num">{wan(conv(up))}</td></tr>'

# ---------- 租賃 ----------
rent_rows = ''
for r in RENT['近三年整戶']:
    cls = ' class="hl"' if r['棟'] == 'B1' and r['樓層'] == 16 else ''
    rent_rows += (f'<tr{cls}><td>{r["日期"]}</td><td>{r["棟"]}・{r["樓層"]}F{"（本戶）" if cls else ""}</td><td class="num">{r["面積坪"]:.2f}</td>'
                  f'<td class="num">{r["車位"]}</td><td class="num b">{r["月租萬"]:.2f}</td><td class="num">{r["月租萬"]*10000/r["面積坪"]:,.0f}</td></tr>')
OWN_RENT = next(r for r in RENT['近三年整戶'] if r['棟'] == 'B1' and r['樓層'] == 16)
YIELD = OWN_RENT['月租萬'] * 12 / TARGET * 100

# ---------- 房貸試算 ----------
RATE, YEARS, LTV = 0.022, 30, 0.8
loan = TARGET * LTV
r_m = RATE / 12
pay = loan * 10000 * r_m / (1 - (1 + r_m) ** (-YEARS * 12))
down = TARGET - loan

DISC = '永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號'
PHONE, LINE_ID, WEB = '0925-313-570', '@080akczk', 'sixhands.tw'
CONTACT = f'助哥 {PHONE}　｜　LINE {LINE_ID}　｜　{WEB}'
def foot(n):
    return (f'<div class="foot"><div>{DISC}<br><span class="ct">{CONTACT}</span></div>'
            f'<span>百達馥麗 銷售報告書　{n}</span></div>')

SITE = (HERE / '棟別圖.svg').read_text(encoding='utf-8').split('?>')[-1]

# ---------- 市售（listings.json，有資料才出頁） ----------
lst_page = ''
if LST:
    rows = ''
    for r in LST:
        net = (r['開價'] - r.get('車位價', PK * r.get('車位數', 1))) / (r['總面積'] - r.get('車位面積', 5.16 * r.get('車位數', 1)))
        rows += (f'<tr{" class=\"hl\"" if r.get("本戶") else ""}><td>{r["棟別樓層"]}</td><td>{r.get("格局", "")}</td><td class="num">{r["總面積"]:.2f}</td>'
                 f'<td class="num">{r.get("車位數", 1)}</td><td class="num">{wan(r["開價"])}</td><td class="num b">{net:.2f}</td>'
                 f'<td class="num">{r["開價"]/r["總面積"]:.2f}</td><td>{r.get("屋況", "")}</td></tr>')
    lst_page = f'''
<div class="page"><div class="pad">
  <div class="eyebrow">08 · ON THE MARKET</div>
  <div class="ttl">社區市售比較</div>
  <div class="sub">同社區目前刊登中的物件（開價為刊登價，非成交價）。車位價未揭露者以本社區坡道平面每席 {PK:.0f} 萬換算。</div>
  <table><tr><th>棟別樓層</th><th>格局</th><th>坪數</th><th>車位</th><th>開價（萬）</th><th>{P_HOUSE}</th><th>{P_ALL}</th><th>屋況</th></tr>{rows}</table>
</div>{foot(8)}</div>'''
PN = 9 if LST else 8

html = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>百達馥麗 銷售報告書</title><style>
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
tr.me td {{ background: #C0392B !important; color: #fff; }}
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
.feat {{ display: flex; gap: 3mm; margin-bottom: 3.2mm; }}
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
  <img src="{img('外觀_林蔭街景.jpg')}" style="position:absolute;left:0;top:0;width:210mm;height:156mm;object-fit:cover;object-position:center 30%">
  <div style="position:absolute;left:0;top:116mm;width:210mm;height:40mm;background:linear-gradient(180deg,rgba(16,42,51,0),#102a33)"></div>
  <div style="position:absolute;left:16mm;top:152mm;right:16mm;color:#fff">
    <div style="font-size:8pt;letter-spacing:.5em;color:#E3B66A">PROPERTY SALES REPORT</div>
    <div style="width:46mm;height:2px;background:#E3B66A;margin:5mm 0 6mm"></div>
    <div class="serif" style="font-size:11pt;color:#E3B66A;letter-spacing:.2em">臺中市西區 · 勤美草悟道生活圈 · 興富發 34 層地標</div>
    <h1 style="font-size:40pt;line-height:1.2;margin-top:2mm">百達馥麗</h1>
    <div class="serif" style="font-size:15pt;margin-top:2mm">買方銷售報告書 · 16 樓 三房＋1 · 坐北朝南</div>
    <div style="font-size:8.8pt;color:#b9cad3;margin-top:4mm;line-height:1.9">臺中市西區中興街287號16樓之1（B1 棟）<br>開價 {wan(L["開價"])} 萬　·　權狀 {L["總面積"]} 坪（含坡道平面車位）　·　3+1房2廳3衛　·　空屋精裝</div>
    <div style="margin-top:7mm;border-top:1px solid #3b5b66;padding-top:5mm;display:flex;gap:8mm;align-items:flex-end">
      <div style="flex:1">
        <div style="font-size:7.6pt;color:#E3B66A;letter-spacing:.3em">核心結論</div>
        <div style="font-size:9.3pt;line-height:1.9;margin-top:2mm">
          同型三房＋1 近四年成交中位 <b>{SAME4["net"]:.1f} 萬/坪</b>，最高為正上方 19F 的 <b>{TOP["不含車單價"]:.1f}</b>（113/01）。<br>
          本戶整戶精裝、空屋可立即入住，三面採光、衛浴皆開窗。<br>
          <span style="color:#E3B66A">合理成交參考約 <b>{TARGET:,} 萬</b>（{P_HOUSE} {T_NET:.1f}），開價 {wan(L["開價"])} 萬。</span>
        </div>
      </div>
      <div class="qr" style="width:22mm"><img src="{img('QR_LINE.png')}"><div>加 LINE</div></div>
    </div>
  </div>
  <div style="position:absolute;left:16mm;bottom:8mm;font-size:7.2pt;color:#8fa6b1">資料：內政部實價登錄（中興街287／289號逐門牌 101/01–115/10；西區同級大樓 112/01–115/10，查詢 2026-10-16）　｜　{CONTACT}</div>
</div>

<!-- P2 物件總覽 -->
<div class="page"><div class="pad">
  <div class="eyebrow">01 · PROPERTY OVERVIEW</div>
  <div class="ttl">物件總覽</div>
  <div class="kpi">
    <div><div class="v">{wan(L["開價"])}</div><div class="u">萬元</div><div class="l">開價（含 1 車位）</div></div>
    <div><div class="v">{L["總面積"]}</div><div class="u">坪</div><div class="l">權狀總坪數（含車位）</div></div>
    <div><div class="v">61.31</div><div class="u">坪</div><div class="l">主建物＋附屬（室內可用）</div></div>
    <div><div class="v">16<span style="font-size:10pt">／34F</span></div><div class="u">樓層</div><div class="l">中高樓層・坐北朝南</div></div>
    <div><div class="v">8,500</div><div class="u">元／月</div><div class="l">管理費（物業管理）</div></div>
  </div>
  <div class="two">
    <div>
      <h3 class="h">本戶資料</h3>
      <table class="spec">
        <tr><td>地址</td><td>臺中市西區中興街287號16樓之1</td></tr>
        <tr><td>棟別</td><td>B1 棟（287 號之一）</td></tr>
        <tr><td>格局</td><td>3+1房2廳3衛（含更衣間、多功能空間）</td></tr>
        <tr><td>坪數</td><td>主建物 49.90＋附屬 11.41＋公設 31.85（含車位）＝{L["總面積"]} 坪</td></tr>
        <tr><td>車位</td><td>坡道平面 1 席・B4-146</td></tr>
        <tr><td>座向</td><td>坐北朝南・三面採光</td></tr>
        <tr><td>現況</td><td>空屋・整戶精裝</td></tr>
        <tr><td>管理費</td><td>8,500 元／月・物業管理</td></tr>
        <tr><td>建築完成</td><td>民國 99 年 2 月（屋齡約 16 年）</td></tr>
        <tr><td>合約編號</td><td>AG1948932</td></tr>
      </table>
    </div>
    <div>
      <h3 class="h">社區資料</h3>
      <table class="spec">
        <tr><td>社區</td><td>百達馥麗（興富發建設）</td></tr>
        <tr><td>規模</td><td>總戶數 191 戶・地上 34 層・3 戶／3 梯</td></tr>
        <tr><td>基地</td><td>約 985 坪・住宅區</td></tr>
        <tr><td>結構</td><td>鋼骨鋼筋混凝土（SRC）・外牆二丁掛</td></tr>
        <tr><td>公設比</td><td>30.37%（樂居登錄）</td></tr>
        <tr><td>建築設計</td><td>大容聯合建築師事務所</td></tr>
        <tr><td>營造</td><td>日商華大成營造</td></tr>
        <tr><td>學區</td><td>中正國小・忠明高中國中部（雙語）</td></tr>
      </table>
    </div>
  </div>
  <h3 class="h">棟別配置</h3>
  <div style="display:flex;gap:5mm;align-items:center">
    <div style="flex:1.25">{SITE}</div>
    <div style="flex:1;font-size:8.2pt;line-height:1.8;color:#33414c">
      兩棟雙併：<b>A 棟＝289 號</b>（美村路21巷側）、<b>B 棟＝287 號</b>（中興街285巷側），每棟每層三戶、三部電梯。<br>
      本戶為 <b style="color:#C0392B">B1（287 號之一）</b>，位於基地內側、遠離中興街車流；同型 B1／A1 的扣車位面積皆約 88 坪。
      <div class="cap" style="margin-top:2mm">依社區棟別圖重繪，非比例尺；北向朝左上。</div>
    </div>
  </div>
</div>{foot(2)}</div>

<!-- P3 格局與賣點 -->
<div class="page"><div class="pad">
  <div class="eyebrow">02 · FLOOR PLAN</div>
  <div class="ttl">格局與六大賣點</div>
  <div class="two">
    <div style="flex:1.05"><div class="photo" style="background:#fff"><img src="{img('格局圖.jpg')}" style="height:140mm;object-fit:contain"></div>
    <div class="cap">※ 示意圖，實際格局與尺寸以現場丈量為準。陽台外移／加窗部分以現況與不動產說明書為準。</div></div>
    <div>
      <div class="feat"><div class="no">01</div><div><h3>高樓層景觀</h3><p>16 樓視野越過周邊街廓，可眺望廣三 SOGO 與七期天際線。</p></div></div>
      <div class="feat"><div class="no">02</div><div><h3>坐北朝南・三面採光</h3><p>客廳、多功能空間、主臥分佔三個面，白天自然光充足，南向日照穩定。</p></div></div>
      <div class="feat"><div class="no">03</div><div><h3>三套衛浴皆開窗</h3><p>主浴有窗、雙面盆、按摩浴缸與獨立淋浴間；三套衛浴都有對外窗，通風好、不易潮濕。</p></div></div>
      <div class="feat"><div class="no">04</div><div><h3>整戶精裝・空屋</h3><p>間接照明天花、大理石中島、整面收納牆與書房系統櫃都已完成，交屋即可入住。</p></div></div>
      <div class="feat"><div class="no">05</div><div><h3>3+1 彈性空間</h3><p>多功能空間可作書房、遊戲室或第四房；主臥附更衣間，客餐廳一字排開、動線開闊。</p></div></div>
      <div class="feat"><div class="no">06</div><div><h3>物業管理・坡道平面車位</h3><p>專業物業管理，B4 坡道平面車位一席，進出不必排機械。</p></div></div>
    </div>
  </div>
  <div class="note" style="margin-top:3mm"><b>室內可用 61.31 坪。</b>主建物 49.90 坪＋陽台等附屬 11.41 坪，佔權狀 {61.31/L["總面積"]*100:.1f}%；扣掉車位後的公設約 26.7 坪，含游泳池、宴會廳、健身房等大型公設。</div>
</div>{foot(3)}</div>

<!-- P4 區位與社區 -->
<div class="page"><div class="pad">
  <div class="eyebrow">03 · LOCATION &amp; COMMUNITY</div>
  <div class="ttl">區位與社區機能</div>
  <div class="sub">位於西區中興街、美村路一段與台灣大道之間，屬勤美誠品綠園道、草悟道生活圈；步行可到廣三 SOGO、市民廣場。</div>
  <div class="photo"><img src="{img('外觀_林蔭街景.jpg')}" style="height:78mm;object-position:center 35%"></div>
  <div class="cap">社區外觀與前方林蔭人行道。</div>
  <div class="two" style="margin-top:4mm">
    <div>
      <h3 class="h">生活機能</h3>
      <table class="spec">
        <tr><td>商圈</td><td>勤美誠品綠園道、廣三 SOGO、向上市場</td></tr>
        <tr><td>綠地</td><td>草悟道、市民廣場、金典綠園道</td></tr>
        <tr><td>交通</td><td>近台灣大道、美村路，往七期、臺中車站都順</td></tr>
        <tr><td>學區</td><td>中正國小、忠明高中國中部（雙語學區）</td></tr>
        <tr><td>醫療</td><td>售屋資料表列：中國醫院；周邊診所多</td></tr>
      </table>
    </div>
    <div>
      <h3 class="h">社區公設</h3>
      <table class="spec">
        <tr><td>休閒</td><td>游泳池會館、SPA、三溫暖</td></tr>
        <tr><td>社交</td><td>宴會廳、鋼琴酒廊、交誼廳</td></tr>
        <tr><td>運動</td><td>健身房、拳擊場、撞球室</td></tr>
        <tr><td>管理</td><td>物業管理公司進駐</td></tr>
      </table>
      <div class="cap">公設依網路刊登資訊整理，實際項目與開放規定以管委會公告為準。</div>
    </div>
  </div>
  <div class="note" style="margin-top:4mm"><b>為什麼是這裡：</b>34 層大樓、地段在勤美與 SOGO 之間，生活機能步行可及。社區 101–115 年實登成交 96 筆，換手穩定，買賣都有行情可以參考。</div>
</div>{foot(4)}</div>

<!-- P5 社區成交 -->
<div class="page"><div class="pad">
  <div class="eyebrow">04 · COMMUNITY HISTORY</div>
  <div class="ttl">百達馥麗歷年成交</div>
  <div class="sub">287 號、289 號逐門牌查詢 101/01–115/10，有效成交 {S["有效筆數"]} 筆（排除特殊關係 4 筆、部分移轉與單買車位 2 筆）。
  依扣除車位後的坪數分成四種產品；<b>三房＋1（約 88 坪）即本戶同型</b>，線為年度中位數。</div>
  {chart_comm}
  <div class="note" style="margin:3mm 0">同型三房＋1 年度中位：108 年 32.8 → 110 年 36.7 → 111 年 39.2 → 113 年 <b>{TOP["不含車單價"]:.1f}</b>（19F）→ 114 年 {LAST["不含車單價"]:.1f}（28F）。
  社區全部產品近三年中位為 {S["近三年"]["net"]:.1f}，但其中 30F 兩戶為毛胚屋、2F 為低樓層大坪，拉低了整體數字，<b>看行情請以同型為準</b>。</div>
  <table class="tight xs">
    <tr><th>日期</th><th>棟別</th><th>產品</th><th>總價（萬）</th><th>總坪數</th><th>車位</th><th>車位價</th><th>{P_HOUSE}</th><th>{P_ALL}</th><th>備註</th></tr>
    {comm_rows}
  </table>
  <div class="cap">列出 110 年後成交，淡橘底為同型三房＋1。車位價未揭露者以本社區坡道平面每席中位 {PK:.0f} 萬估算（標 *）。單位：萬元／坪。</div>
</div>{foot(5)}</div>

<!-- P6 區域比較 -->
<div class="page"><div class="pad">
  <div class="eyebrow">05 · AREA COMPARISON</div>
  <div class="ttl">西區同級大樓比較</div>
  <div class="sub">條件：西區、住宅大樓、屋齡 15–20 年、總面積 80–100 坪（本戶 93.16 坪），112/01–115/10，共 {CMP["有效"]} 筆（排除特殊關係 {CMP["排除"]} 筆）。</div>
  <div class="note" style="margin-bottom:3.5mm"><b>有車位的物件，單價怎麼看？</b>總價裡含車位，所以有兩種算法：<br>
  ① <b>{P_HOUSE}</b>＝（總價－車位價）÷（總坪數－車位坪數），用來比房子本身。<br>
  ② <b>{P_ALL}</b>，車位每坪便宜，會把單價拉低，網路上常看到的是這個數字。<br>
  例：鄉林君悅 {EX["日期"]} 成交 {wan(EX["總價"])} 萬、{EX["坪數"]:.2f} 坪，含坡道平面車位 2 席 {wan(EX["車位價"])} 萬 → ① <b>{EX["不含車"]:.1f}</b>；② {EX["含車"]:.1f}。<br>
  本戶：開價 {wan(L["開價"])} 萬、{L["總面積"]} 坪、車位 1 席（以社區每席 {PK:.0f} 萬、{L["車位面積_實登"]} 坪計）→ ① ({wan(L["開價"])}－{PK:.0f})÷{BASE:.2f} 坪＝<b>{L["不含車單價"]:.2f}</b>；② {wan(L["開價"])}÷{L["總面積"]} 坪＝{L["含車單價"]:.2f}。</div>
  <div class="kpi">
    <div><div class="v">{CMP3["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">西區同級 近三年 {P_HOUSE}</div></div>
    <div><div class="v">{CMP3["gross"]:.1f}</div><div class="u">萬/坪</div><div class="l">西區同級 近三年 {P_ALL}</div></div>
    <div><div class="v">{SAME4["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">百達同型 近四年 {P_HOUSE}</div></div>
    <div><div class="v">{(SAME4["net"]/CMP3["net"]-1)*100:+.0f}%</div><div class="u">社區溢價</div><div class="l">百達同型 vs 西區同級</div></div>
  </div>
  <table class="tight">
    <tr><th>日期</th><th>社區</th><th>門牌</th><th>樓層</th><th>總價（萬）</th><th>總坪數</th><th>車位</th><th>{P_HOUSE}</th><th>{P_ALL}</th></tr>
    {cmp_rows}
  </table>
  <div class="cap">淡橘底為百達馥麗。車位價未揭露者以比較組同類別車位中位估算（標 *）。「—」為實登未填社區名。單位：萬元／坪。</div>
</div>{foot(6)}</div>

<!-- P7 價格分析 -->
<div class="page"><div class="pad">
  <div class="eyebrow">06 · PRICE ANALYSIS</div>
  <div class="ttl">價格分析：合理成交約 {TARGET:,} 萬</div>
  <div class="sub">把各參考點的「{P_HOUSE}」套到本戶（扣車位 {BASE:.2f} 坪＋車位 1 席 {PK:.0f} 萬），換算成「照這個行情，本戶值多少」。</div>
  <div class="kpi">
    <div><div class="v">{wan(L["開價"])}</div><div class="u">萬元</div><div class="l">開價（{P_HOUSE} {L["不含車單價"]:.1f}）</div></div>
    <div style="border-top-color:#2E7D4F"><div class="v" style="color:#2E7D4F">{TARGET:,}</div><div class="u">萬元</div><div class="l">建議成交參考（{T_NET:.1f}）</div></div>
    <div><div class="v">{wan(conv(TOP["不含車單價"]))}</div><div class="u">萬元</div><div class="l">照 19F 113/01 行情換算</div></div>
    <div><div class="v">{(1 - TARGET / L["開價"]) * 100:.1f}%</div><div class="u">約 {L["開價"] - TARGET} 萬</div><div class="l">開價到參考價的空間</div></div>
  </div>
  <table>
    <tr><th>參考點</th><th>說明</th><th>{P_HOUSE}</th><th>{P_ALL}</th><th>換算本戶（萬）</th></tr>
    {pos_rows}
  </table>
  <h3 class="h">怎麼解讀</h3>
  <ul>
    <li><b>同型行情 {SAME4["net"]:.1f}–{TOP["不含車單價"]:.1f}：</b>近四年同型三筆落在 38.0（28F）、39.2（9F）、43.0（19F）。換算本戶約 {wan(conv(LAST["不含車單價"]))}–{wan(conv(TOP["不含車單價"]))} 萬。</li>
    <li><b>精裝與空屋是加分：</b>本戶天花、櫃體、中島、衛浴都已完成，買方省下裝修預算與 3–6 個月工期，合理落在同型區間的中上段。</li>
    <li><b>樓層不是主要差異：</b>110 年後中樓層（12–22F）中位 {S["樓層帶_110後"][1]["不含車中位"]:.1f}，高樓層（23–34F）{S["樓層帶_110後"][2]["不含車中位"]:.1f}，本社區價格主要看產品與屋況。</li>
    <li><b>比西區同級高：</b>百達同型比西區同級大樓（{CMP3["net"]:.1f}）高約 {(SAME4["net"]/CMP3["net"]-1)*100:.0f}%，反映 34 層地標、公設與勤美生活圈。</li>
  </ul>
  <div class="warn" style="margin-top:3mm">同型近四年僅 {SAME4["n"]} 筆成交，行情帶寬較寬。建議成交參考為小登依實登推估，不是估價師的估價，也不保證成交價。</div>
</div>{foot(7)}</div>
{lst_page}
<!-- 購屋試算 -->
<div class="page"><div class="pad">
  <div class="eyebrow">{PN-1:02d} · BUYER'S GUIDE</div>
  <div class="ttl">租金參考與購屋試算</div>
  <div class="kpi">
    <div><div class="v">{TARGET:,}</div><div class="u">萬元</div><div class="l">以建議成交參考價試算</div></div>
    <div><div class="v">{wan(down)}</div><div class="u">萬元</div><div class="l">自備款（兩成）</div></div>
    <div><div class="v">{wan(loan)}</div><div class="u">萬元</div><div class="l">貸款（八成）</div></div>
    <div><div class="v">{pay/10000:.1f}</div><div class="u">萬元／月</div><div class="l">本息攤還</div></div>
  </div>
  <div class="note">試算假設：貸款八成、年利率 {RATE*100:.1f}%、{YEARS} 年本息平均攤還，每月約 {pay:,.0f} 元。另需預留契稅、代書、仲介服務費。實際成數、利率與年限依銀行鑑價與個人條件核定。</div>
  <h3 class="h">社區整戶出租（近三年實登）</h3>
  <table>
    <tr><th>日期</th><th>棟別</th><th>面積（坪）</th><th>車位</th><th>月租（萬）</th><th>每坪（元／月）</th></tr>
    {rent_rows}
  </table>
  <div class="cap">已排除分租套房、多人合租等部分出租。本戶 113/06 曾整戶出租 {OWN_RENT["月租萬"]:.1f} 萬／月；以建議成交參考價計，毛租金約 {YIELD:.1f}%（未扣管理費、稅費與空置），本社區以自住為主。</div>
  <h3 class="h">看屋重點</h3>
  <ul>
    <li><b>陽台外移／加窗：</b>格局圖標示陽台外移與加窗，請以現況與不動產說明書確認，評估是否屬增建。</li>
    <li><b>車位面積：</b>同型戶實登登載每席坡道平面約 5.16 坪；車位編號 B4-146，面積與位置以謄本、分管協議為準。</li>
    <li><b>管理費：</b>8,500 元／月，含物業管理與大型公設維護，可索取管委會收支與修繕紀錄。</li>
    <li><b>屋齡 16 年：</b>SRC 結構，可一併確認外牆、電梯與管線的保養紀錄。</li>
  </ul>
  <div style="margin-top:5mm;position:relative;background:#fff;border:1px solid #dde4e9;padding:4mm 36mm 4mm 6mm;font-size:7.6pt;line-height:1.75;color:#4a5560">
    <div class="b" style="font-size:9.4pt;color:#163a47;margin-bottom:1.2mm">資料來源與免責聲明</div>
    實價登錄：內政部不動產交易實價查詢服務網，中興街287號、289號買賣與租賃（101/01–115/10）；西區住宅大樓・屋齡15–20年・總面積80–100坪買賣（112/01–115/10）；查詢日 2026-10-16。社區介紹整理自樂居、591 等網路刊登資訊。<br>
    本報告書為不動產經紀業務之行銷參考資料，非不動產估價師出具之估價報告。行情統計與試算係依公開資料整理，不構成價格保證、投資建議或獲利承諾。實際面積、用途、產權及使用現況，以權狀、謄本、不動產說明書及買賣契約記載為準。
    <div style="position:absolute;right:7mm;top:50%;margin-top:-11mm;width:22mm;height:22mm;border:2.5px solid #b3261e;border-radius:50%;color:#b3261e;display:flex;align-items:center;justify-content:center;text-align:center;font-family:'Noto Serif CJK TC',serif;font-size:8pt;font-weight:700;line-height:1.3;transform:rotate(-12deg)">僅供<br>參考</div>
  </div>
  <div style="margin-top:5mm;display:flex;align-items:center;justify-content:center;gap:7mm;background:#163a47;padding:5mm 7mm;border-radius:2px">
    <div style="color:#fff">
      <div style="font-size:7.4pt;color:#E3B66A;letter-spacing:.3em">預約帶看・行情諮詢</div>
      <div class="serif" style="font-size:16pt;font-weight:700;margin-top:1mm">助哥　<span style="color:#F0D9A4">{PHONE}</span></div>
      <div style="font-size:8pt;color:#b9cad3;margin-top:1mm;line-height:1.7">永慶不動產 七期河南市政店<br>LINE {LINE_ID}　｜　{WEB}</div>
    </div>
    <div class="qr" style="width:24mm"><img src="{img('QR_LINE.png')}"><div>加 LINE</div></div>
    <div class="qr" style="width:24mm"><img src="{img('QR_網站.png')}"><div>看網站</div></div>
  </div>
</div>{foot(PN)}</div>

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
