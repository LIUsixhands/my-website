"""寶鴻大白 銷售報告書（給買方）：讀 summary.json / transactions.csv → 產 HTML → Playwright 輸出 PDF。
口徑：社區成交幾乎全含坡道平面車位，單價一律並列「房屋單價（已扣車位）」與「總價÷總坪數（車位一起算）」；
同型比較以扣車位約 62 坪的「三房四衛」為主；區域比較組為西區・屋齡 5–10 年・扣車位面積 本戶 ±5 坪（112–115）。
室內照片為 3D 設計示意圖，一律標示「設計示意，非現況照片」。"""
import base64, json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
OUT_HTML = HERE / '寶鴻大白_銷售報告書.html'
OUT_PDF = HERE / '寶鴻大白_銷售報告書.pdf'

S = json.load(open(HERE / 'summary.json'))
df = pd.read_csv(HERE / 'transactions.csv')
df['備註'] = df['備註'].fillna('')
df['yr'] = df['交易日期'].str[:3].astype(int)
L = S['本戶']
BASE, PKV, PK1 = L['扣車位面積'], L['車位估價'], S['車位']['每席價格中位_110後']
SAME4, SAME5 = S['同型_近四年'], S['同型_近五年']
CMP = S['比較組']
BAND = CMP['同級距']
CY = {r['年']: r for r in CMP['年度_不含本社區']}
FB = {b['帶'][:2]: b for b in S['樓層帶_同型_110後']}
ASK = L['開價']                                       # ⛔ 對外報告不放建議成交價，試算以開價計

def conv(net): return net * BASE + PKV               # 房屋單價 → 本戶總價（扣車位 62.44 坪＋2 席）
def img(name):
    mime = 'image/png' if name.endswith('png') else 'image/jpeg'
    return f"data:{mime};base64,{base64.b64encode((HERE / name).read_bytes()).decode()}"
def f2(v): return '—' if v is None or pd.isna(v) else f'{v:.2f}'
def wan(v): return '—' if v is None or pd.isna(v) else f'{v:,.0f}'

P_HOUSE = '房屋單價（已扣車位）'
P_ALL = '總價÷總坪數（車位一起算）'
SAME = df[df['產品'].str.startswith('三房')].sort_values('交易日期')
S4 = SAME[SAME['yr'] >= 112]
TOP = S4.loc[S4['不含車單價'].idxmax()]
LAST = SAME.iloc[-1]
HI = SAME[SAME['樓層'] >= 7]
CDET = [r for r in CMP['明細'] if r['同級距']]
CTOP = max(CDET, key=lambda r: r['不含車'])
MARK = '設計示意，非現況照片'
Z2H = str.maketrans('０１２３４５６７８９', '0123456789')

def svg_open(W, H): return [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC" font-size="10">']
def tt(d): y, m, _ = d.split('/'); return int(y) + (int(m) - .5) / 12

# ---------- 圖一：社區歷年成交（106–115，依產品分色；三房四衛年度中位連線） ----------
W, H, Lm, R, T, B = 560, 236, 40, 16, 24, 42
X0, X1, YMIN, YMAX = 106, 116, 30, 60
def X(t): return Lm + (t - X0) * (W - Lm - R) / (X1 - X0)
def Y(v): return T + (YMAX - v) * (H - T - B) / (YMAX - YMIN)
svg = svg_open(W, H)
for v in range(YMIN, YMAX + 1, 5):
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e3e8ec"/>'
               f'<text x="{Lm-6}" y="{Y(v)+3:.1f}" text-anchor="end" fill="#7b8794">{v}</text>')
for y in range(106, 116):
    svg.append(f'<text x="{X(y+.5):.1f}" y="{H-B+14}" text-anchor="middle" fill="#7b8794" font-size="9">{y}</text>')
svg.append(f'<text x="{W-R}" y="{T-10}" text-anchor="end" fill="#7b8794" font-size="9">單位：萬元／坪（{P_HOUSE}）</text>')
v = L['不含車單價']
svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#C0392B" stroke-width="1.2" stroke-dasharray="3 3"/>'
           f'<text x="{Lm+4}" y="{Y(v)-4:.1f}" fill="#C0392B" font-size="9" font-weight="700">本戶開價 {v:.1f}</text>')
STY = {'三房四衛（約 62 坪）': ('#1F4E5F', 4.2), '頂樓層小坪（約 40–50 坪）': ('#C8963E', 3.4), '2F 五車位（特例）': ('#9aa7b2', 3.4)}
ym = SAME.groupby('yr')['不含車單價'].median()
svg.append(f'<path d="{" ".join(("M" if i == 0 else "L") + f"{X(y+.5):.1f},{Y(v):.1f}" for i, (y, v) in enumerate(ym.items()))}" fill="none" stroke="#1F4E5F" stroke-width="2.2" opacity=".85"/>')
for r in df.itertuples():
    c, rad = STY[r.產品]
    svg.append(f'<circle cx="{X(tt(r.交易日期)):.1f}" cy="{Y(r.不含車單價):.1f}" r="{rad}" fill="{c}" fill-opacity="{1 if r.產品.startswith("三房") else .8}" stroke="#fff" stroke-width=".8"/>')
for y, v in ym.items():
    svg.append(f'<text x="{X(y+.5):.1f}" y="{Y(v)+14:.1f}" text-anchor="middle" fill="#1F4E5F" font-size="8.4" font-weight="700">{v:.1f}</text>')
for i, (prod, name) in enumerate([(k, k.replace('（約', ' ').replace('）', '').replace('（', ' ')) for k in STY]):
    c, rad = STY[prod]; lx = Lm + 2 + i * 150
    svg.append(f'<circle cx="{lx+6}" cy="{H-10}" r="{rad}" fill="{c}"/><text x="{lx+14}" y="{H-7}" fill="#4a5560" font-size="8.4">{name}</text>')
svg.append('</svg>')
chart_comm = ''.join(svg)

comm_rows = ''
for r in df[df['yr'] >= 110].itertuples():
    cls = ' class="hl"' if r.產品.startswith('三房') else ''
    est = '*' if r.車位價來源.startswith('估算') else ''
    note = r.備註.replace(';', ' ').strip()
    note = '車位另計 630 萬' if '陸佰參拾' in note else ('土地建物分列' if '土地價格' in note else note[:10])
    comm_rows += (f'<tr{cls}><td>{r.交易日期}</td><td>{r.門牌}・{r.樓層}F</td><td>{r.產品.split("（")[0]}</td><td class="num">{wan(r.總價萬)}</td>'
                  f'<td class="num">{r.總面積坪:.2f}</td><td class="num">{r.車位數}</td><td class="num">{wan(r.車位價萬)}{est}</td>'
                  f'<td class="num b">{r.不含車單價:.2f}{est}</td><td class="num">{r.含車單價:.2f}</td><td>{note}</td></tr>')

# ---------- 區域比較組（同級距） ----------
cmp_rows = ''
for r in CDET:
    est = '' if r['揭露'] else '*'
    cmp_rows += (f'<tr><td>{r["日期"]}</td><td>{r["社區"]}</td><td>{r["門牌"].translate(Z2H)}</td><td class="num">{r["屋齡"]}</td><td class="num">{r["樓層"]}</td><td class="num">{wan(r["總價"])}</td>'
                 f'<td class="num">{r["坪數"]:.2f}</td><td class="num">{r["扣車位坪數"]:.1f}</td><td class="num">{r["車位"]}</td>'
                 f'<td class="num b">{r["不含車"]:.2f}{est}</td><td class="num">{r["含車"]:.2f}</td></tr>')
EX = next(r for r in CDET if r['揭露'] and r['社區'] != '—' and r['車位'] == 2)

# ---------- 價格分析 ----------
anchors = [
    ('社區同型 最新一筆', f'{LAST["交易日期"][:6]} {LAST["門牌"]} {LAST["樓層"]}F 成交 {wan(LAST["總價萬"])} 萬', LAST['不含車單價']),
    ('社區同型 近四年中位', f'112–115 年 {SAME4["n"]} 筆，2–8F', SAME4['net']),
    ('社區同型 7–8F 歷年中位', f'本戶同層與下一層，110–112 年 {len(HI[HI["yr"]>=110])} 筆', HI[HI['yr'] >= 110]['不含車單價'].median()),
    ('社區同型 近四年最高', f'{TOP["交易日期"][:6]} {TOP["門牌"]} {TOP["樓層"]}F（{TOP["車位數"]} 車位）', TOP['不含車單價']),
    ('西區同齡同坪數 中位', f'屋齡 5–10 年、扣車位 {BAND["扣車位面積"]} 坪，112–115 年 {BAND["n"]} 筆', BAND['net']),
    ('西區同齡 115 年中位', f'屋齡 5–10 年、70–100 坪，115 年 {CY[115]["n"]} 筆（不分坪數級距）', CY[115]['不含車中位']),
    ('西區同齡同坪數 最高', f'{CTOP["日期"][:6]} {CTOP["門牌"].translate(Z2H).split('號')[0]}號 {CTOP["樓層"]}F，屋齡 {CTOP["屋齡"]} 年', CTOP['不含車']),
]
pos_rows = (f'<tr class="hl"><td>本戶開價</td><td>3號 8F・{L["總面積"]} 坪・2 車位</td><td class="num">{L["不含車單價"]:.2f}</td>'
            f'<td class="num">{L["含車單價"]:.2f}</td><td class="num">{wan(ASK)}</td></tr>')
for nm, why, up in anchors:
    pos_rows += f'<tr><td class="b">{nm}</td><td>{why}</td><td class="num">{up:.2f}</td><td class="num">{conv(up)/L["總面積"]:.2f}</td><td class="num">{wan(conv(up))}</td></tr>'
GAP_SAME = (L['不含車單價'] / SAME4['net'] - 1) * 100
GAP_BAND = (L['不含車單價'] / BAND['net'] - 1) * 100

# ---------- 房貸試算 ----------
RATE, YEARS, LTV = 0.022, 30, 0.8
loan = ASK * LTV
r_m = RATE / 12
pay = loan * 10000 * r_m / (1 - (1 + r_m) ** (-YEARS * 12))
down = ASK - loan

DISC = '永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號'
PHONE, LINE_ID, WEB = '0925-313-570', '@080akczk', 'sixhands.tw'
CONTACT = f'助哥 {PHONE}　｜　LINE {LINE_ID}　｜　{WEB}'
def foot(n):
    return (f'<div class="foot"><div>{DISC}<br><span class="ct">{CONTACT}</span></div>'
            f'<span>寶鴻大白 銷售報告書　{n}</span></div>')

SITE = (HERE / '棟別圖.svg').read_text(encoding='utf-8').split('?>')[-1]
def ph(name, h, cap, mark=True, pos='center'):
    m = f'<span class="mk">{MARK}</span>' if mark else ''
    return (f'<div><div class="photo" style="position:relative"><img src="{img(name)}" style="height:{h}mm;object-position:{pos}">{m}</div>'
            f'<div class="cap">{cap}</div></div>')

html = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>寶鴻大白 銷售報告書</title><style>
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
.feat {{ display: flex; gap: 3mm; margin-bottom: 3mm; }}
.feat .no {{ font-family: "Noto Serif CJK TC", serif; font-size: 20pt; color: #C8963E; line-height: 1; min-width: 10mm; }}
.feat h3 {{ font-size: 10.4pt; color: #163a47; margin-bottom: .8mm; }}
.feat p {{ font-size: 8.3pt; line-height: 1.7; color: #33414c; }}
ul {{ margin-left: 4.5mm; }} li {{ font-size: 8.4pt; line-height: 1.8; margin-bottom: .5mm; }}
.photo {{ background: #e3eaef; padding: 1.8mm; border-radius: 2px; }}
.photo img {{ display: block; width: 100%; object-fit: cover; }}
.mk {{ position: absolute; right: 3.5mm; bottom: 3.5mm; background: rgba(22,58,71,.82); color: #fff; font-size: 6.4pt; padding: .8mm 2mm; border-radius: 2px; letter-spacing: .05em; }}
.cap {{ font-size: 7pt; color: #7b8794; margin-top: 1.2mm; }}
.spec td:first-child {{ color: #8a6a2c; width: 22mm; white-space: nowrap; }}
.spec td {{ background: transparent !important; padding: 3px 4px; font-size: 8.2pt; }}
.two {{ display: flex; gap: 5mm; }} .two > div {{ flex: 1; min-width: 0; }}
.three {{ display: flex; gap: 4mm; }} .three > div {{ flex: 1; min-width: 0; }}
.quote {{ font-family: "Noto Serif CJK TC", serif; font-size: 9pt; line-height: 2; color: #33414c; }}
</style></head><body>

<!-- P1 封面 -->
<div class="page" style="background:#F3F1EC">
  <img src="{img('外觀_透視.jpg')}" style="position:absolute;right:0;top:0;width:112mm;height:206mm;object-fit:cover;object-position:center 30%">
  <div style="position:absolute;right:112mm;top:0;width:30mm;height:206mm;background:linear-gradient(90deg,#F3F1EC 10%,rgba(243,241,236,0))"></div>
  <img src="{img('書法_大白.jpg')}" style="position:absolute;left:10mm;top:20mm;width:88mm;mix-blend-mode:multiply">
  <div style="position:absolute;left:16mm;top:118mm;width:80mm">
    <div style="font-size:8pt;letter-spacing:.5em;color:#a07a30">PROPERTY SALES REPORT</div>
    <div style="width:40mm;height:2px;background:#C8963E;margin:4mm 0 5mm"></div>
    <h1 style="font-size:36pt;line-height:1.15;color:#163a47">寶鴻大白</h1>
    <div class="serif" style="font-size:13pt;margin-top:2mm;color:#163a47">買方銷售報告書</div>
    <div class="serif" style="font-size:10.5pt;margin-top:4mm;color:#5d6b76;letter-spacing:.25em;line-height:1.9">大白若辱<br>盛德若不足</div>
    <div style="font-size:8.4pt;color:#5d6b76;margin-top:5mm;line-height:1.8">臺中市西區・美術館綠園道生活圈<br>寶鴻建設・10 層・全社區 18 戶</div>
  </div>
  <div style="position:absolute;left:0;right:0;top:206mm;bottom:0;background:#163a47;color:#fff;padding:7mm 16mm 0">
    <div class="serif" style="font-size:13pt">8 樓・三房四衛・朝東・B1 連號雙平面車位</div>
    <div style="font-size:8.6pt;color:#b9cad3;margin-top:1.5mm">臺中市西區五權三街55巷3號8樓　·　開價 {wan(ASK)} 萬　·　權狀 {L["總面積"]} 坪（含車位 {L["車位面積"]} 坪）　·　空屋</div>
    <div style="margin-top:4.5mm;border-top:1px solid #3b5b66;padding-top:4mm;display:flex;gap:8mm;align-items:flex-end">
      <div style="flex:1;font-size:8.8pt;line-height:1.85">
        <span style="font-size:7.4pt;color:#E3B66A;letter-spacing:.3em">重點摘要</span><br>
        三房四衛是社區主力產品，只做到 8 樓，<b>本戶就在同型的最高一層</b>；一層兩戶。<br>
        社區同型近四年成交中位 <b>{SAME4["net"]:.1f} 萬/坪</b>；西區屋齡 5–10 年、同坪數大樓中位 <b>{BAND["net"]:.1f}</b>。<br>
        <span style="color:#E3B66A">開價 {wan(ASK)} 萬，{P_HOUSE} {L["不含車單價"]:.1f} 萬/坪。</span>
      </div>
      <div class="qr" style="width:21mm"><img src="{img('QR_LINE.png')}"><div>加 LINE</div></div>
    </div>
    <div style="position:absolute;left:16mm;bottom:7mm;font-size:7pt;color:#8fa6b1">資料：內政部實價登錄（社區逐門牌 101/01–115/10；西區同齡大樓 112/01–115/10；查詢 2026-10-23）</div>
  </div>
</div>

<!-- P2 物件總覽 -->
<div class="page"><div class="pad">
  <div class="eyebrow">01 · PROPERTY OVERVIEW</div>
  <div class="ttl">物件總覽</div>
  <div class="kpi">
    <div><div class="v">{wan(ASK)}</div><div class="u">萬元</div><div class="l">開價（含 2 車位）</div></div>
    <div><div class="v">{L["總面積"]}</div><div class="u">坪</div><div class="l">權狀總坪數（含車位）</div></div>
    <div><div class="v">{L["主建物"]+L["附屬"]:.2f}</div><div class="u">坪</div><div class="l">主建物＋附屬（室內可用）</div></div>
    <div><div class="v">8<span style="font-size:10pt">／10F</span></div><div class="u">樓層</div><div class="l">同型最高樓層・朝東</div></div>
    <div><div class="v">8,400</div><div class="u">元／月</div><div class="l">管理費（物業管理）</div></div>
  </div>
  <div class="two">
    <div>
      <h3 class="h">本戶資料</h3>
      <table class="spec">
        <tr><td>地址</td><td>臺中市西區五權三街55巷3號8樓</td></tr>
        <tr><td>格局</td><td>3房2廳4衛・三房皆為套房規劃</td></tr>
        <tr><td>坪數</td><td>主建物 {L["主建物"]:.2f}＋附屬 {L["附屬"]:.2f}＋公設 {L["公設"]:.2f}（含車位 {L["車位面積"]}）＝{L["總面積"]} 坪</td></tr>
        <tr><td>車位</td><td>坡道平面 2 席・B1 連號（B1-34A、35）</td></tr>
        <tr><td>座向</td><td>朝東・前後陽台</td></tr>
        <tr><td>現況</td><td>空屋・屋主裝潢、獨立廚房</td></tr>
        <tr><td>管理費</td><td>8,400 元／月・物業管理</td></tr>
        <tr><td>建築完成</td><td>民國 106 年 9 月（屋齡約 9 年）</td></tr>
        <tr><td>合約編號</td><td>{L["合約"]}</td></tr>
      </table>
    </div>
    <div>
      <h3 class="h">社區資料</h3>
      <table class="spec">
        <tr><td>社區</td><td>寶鴻大白（寶鴻建設）</td></tr>
        <tr><td>規模</td><td>地上 10 層／地下 3 層・總戶數 18 戶・一層兩戶</td></tr>
        <tr><td>基地</td><td>約 231 坪・住三</td></tr>
        <tr><td>結構</td><td>鋼筋混凝土（RC）・外牆二丁掛</td></tr>
        <tr><td>公設比</td><td>33.07%（樂居登錄）</td></tr>
        <tr><td>建築設計</td><td>王銘鴻建築師事務所</td></tr>
        <tr><td>營造</td><td>瑞助營造</td></tr>
        <tr><td>車位</td><td>全為坡道平面，共 37 席</td></tr>
        <tr><td>學區</td><td>忠信國小・崇倫國中（雙語學區）</td></tr>
      </table>
    </div>
  </div>
  <h3 class="h">棟別配置</h3>
  <div style="display:flex;gap:5mm;align-items:center">
    <div style="flex:1">{SITE}</div>
    <div style="flex:1.2;font-size:8.2pt;line-height:1.8;color:#33414c">
      單棟一層兩戶：<b>3 號在北、5 號在南</b>，中間為梯間，東側臨五權三街55巷。<br>
      本戶為 <b style="color:#C0392B">3 號 8 樓</b>。兩戶共用一座梯廳，全棟只有 18 戶，純住家、沒有店面。
      <div class="cap" style="margin-top:2mm">依社區棟別圖重繪，非比例尺。</div>
    </div>
  </div>
  <div class="two" style="margin-top:4mm">
    {ph('公設_交誼廳泳池.jpg', 50, '公設閱覽／交誼空間，落地窗外為戶外水景庭園。', False)}
    {ph('公設_大廳沙發.jpg', 50, '公設交誼廳：石材牆面與皮革沙發。', False)}
  </div>
</div>{foot(2)}</div>

<!-- P3 建築 -->
<div class="page"><div class="pad">
  <div class="eyebrow">02 · ARCHITECTURE</div>
  <div class="ttl">「大白」之名，明白其志</div>
  <div class="two">
    <div style="flex:.95">{ph('外觀_透視_題字.jpg', 64, '建案外觀透視（建商銷售資料）。', False)}</div>
    <div class="quote">
      案名取自《道德經》「大白若辱，盛德若不足」：最潔白的東西看起來反而像有缺點，最高的德行看起來反而像不夠。<br>
      純白的外觀不張揚，用來襯托美術館園道的綠意。<br>
      <span style="font-size:7.6pt;color:#7b8794">— 整理自寶鴻建設建案文案</span>
    </div>
  </div>
  <div class="two" style="margin-top:3mm">
    <div>
      <h3 class="h">建築設計</h3>
      <ul>
        <li><b>有機表皮：</b>從樹葉的組織發想，用大小圓孔的白色表皮包覆立面，兼顧通風與綠化。</li>
        <li><b>層疊景觀陽台：</b>大尺度陽台上種樹，一層層往上疊，把園道的綠延伸進建築。</li>
        <li><b>夜間「水樹沐光」：</b>表皮透出低量的光暈，不靠浮誇的燈飾。</li>
        <li><b>公設設計：</b>大廳與公設由設計師王勝正規劃，以「森．美術館」為設計概念。</li>
      </ul>
    </div>
    <div>
      <h3 class="h">建案原始建材規劃</h3>
      <table class="spec">
        <tr><td>玄關門</td><td>義大利「敵銳」裝甲玄關門</td></tr>
        <tr><td>室內門</td><td>義大利 BRAGA 實木門</td></tr>
        <tr><td>電子鎖</td><td>義大利 TORTEROLO &amp; RE</td></tr>
        <tr><td>窗</td><td>日本 YKK 氣密窗＋LOW-E 玻璃</td></tr>
        <tr><td>空調</td><td>大金冷暖</td></tr>
        <tr><td>衛浴</td><td>KOHLER 智能馬桶、面盆、獨立浴缸</td></tr>
        <tr><td>廚具</td><td>德國 NOBLESSA 廚具・移動式中島</td></tr>
        <tr><td>插座</td><td>Panasonic</td></tr>
      </table>
      <div class="cap">依建案銷售資料整理；本戶現況（含屋主裝修更換項目）以現場與不動產說明書為準。</div>
    </div>
  </div>
  <div style="margin-top:3.5mm">{ph('外觀_透視.jpg', 56, '立面細部：圓孔表皮與層疊景觀陽台（建商透視圖）。', False, 'center 22%')}</div>
</div>{foot(3)}</div>

<!-- P4 賣點 -->
<div class="page"><div class="pad">
  <div class="eyebrow">03 · HIGHLIGHTS</div>
  <div class="ttl">六大賣點</div>
  <div class="two">
    <div>
      <div class="feat"><div class="no">01</div><div><h3>同型最高樓層</h3><p>社區的三房四衛只做到 8 樓（9、10 樓是較小的戶型），本戶就是這個產品的最高一層，視野越過周邊街廓。</p></div></div>
      <div class="feat"><div class="no">02</div><div><h3>一層兩戶・18 戶</h3><p>單棟一層只有兩戶、全社區 18 戶，純住家、沒有店面，住戶單純、梯廳安靜。</p></div></div>
      <div class="feat"><div class="no">03</div><div><h3>三套房・四衛浴</h3><p>三間房都是套房規劃，另有客用衛浴。格局方正，室內動線順暢，適合三代同住或家有青少年。</p></div></div>
    </div>
    <div>
      <div class="feat"><div class="no">04</div><div><h3>朝東採光・前後陽台</h3><p>東向迎接晨光，前後陽台形成對流，通風良好。</p></div></div>
      <div class="feat"><div class="no">05</div><div><h3>美術館綠園道生活圈</h3><p>美術館、美術園道就在附近，生活節奏安靜；全聯、第五市場、向上市場、好市多都在生活圈內。</p></div></div>
      <div class="feat"><div class="no">06</div><div><h3>B1 連號雙平面車位</h3><p>兩席坡道平面車位在 B1、連號相鄰，出入最快，不用排機械。</p></div></div>
    </div>
  </div>
  <div class="note" style="margin-top:1mm"><b>室內可用 {L["主建物"]+L["附屬"]:.2f} 坪。</b>主建物 {L["主建物"]:.2f} 坪＋陽台等附屬 {L["附屬"]:.2f} 坪；權狀 {L["總面積"]} 坪中有 {L["車位面積"]} 坪是兩席車位，扣掉車位後的公設約 {L["公設"]-L["車位面積"]:.1f} 坪（公設比 33%）。</div>
  <div style="margin-top:3.5mm">{ph('示意_客廳全景.jpg', 84, '客廳望向餐廳與中島：木紋天花、間接照明，電視牆整合收納與展示櫃。')}</div>
  <div class="two" style="margin-top:3.5mm">
    {ph('示意_玄關.jpg', 50, '玄關：整面鞋櫃與弧形端景牆。')}
    {ph('示意_客廳落地窗.jpg', 50, '客廳：落地窗面向陽台，沙發背牆木紋飾條。')}
  </div>
</div>{foot(4)}</div>

<!-- P5 室內：公領域 -->
<div class="page"><div class="pad">
  <div class="eyebrow">04 · INTERIOR · LIVING</div>
  <div class="ttl">室內設計示意：客餐廚</div>
  <div class="warn" style="margin-bottom:4mm">以下室內圖均為 <b>3D 設計示意圖，不是本戶現況照片</b>。本戶為空屋，實際裝修、家具與設備以現場為準。</div>
  <div class="two">
    {ph('示意_電視牆展示櫃.jpg', 56, '電視牆：石材主牆＋黑框玻璃展示櫃。')}
    {ph('示意_餐廳.jpg', 56, '餐廳：大理石餐桌與中島相接，上方木紋天花。')}
  </div>
  <div class="two" style="margin-top:3.5mm">
    {ph('示意_中島餐桌.jpg', 56, '中島：嵌入式水槽，餐桌與中島一體。')}
    {ph('示意_廚房電器櫃.jpg', 56, '廚房：嵌入式烤箱、蒸爐高櫃與咖啡吧台。')}
  </div>
  <div class="two" style="margin-top:3.5mm">
    {ph('示意_中島望客廳.jpg', 56, '從中島望向客廳，客、餐、廚一路相連。')}
    {ph('示意_客餐廳.jpg', 56, '客廳與餐廳：大理石紋地坪、整面背牆。')}
  </div>
</div>{foot(5)}</div>

<!-- P6 室內：私領域 -->
<div class="page"><div class="pad">
  <div class="eyebrow">04 · INTERIOR · BEDROOMS</div>
  <div class="ttl">室內設計示意：三套房</div>
  <div class="sub">主臥附更衣室；次臥可兼書房；第三間適合作小孩房。圖均為 3D 設計示意，非現況照片。</div>
  <div class="two">
    {ph('示意_主臥.jpg', 56, '主臥：金屬色床頭背板與燈帶，整面衣櫃。')}
    {ph('示意_主臥電視牆.jpg', 56, '主臥：木紋電視牆。')}
  </div>
  <div class="two" style="margin-top:3.5mm">
    {ph('示意_更衣室.jpg', 56, '主臥更衣室：開放吊掛、層板與化妝台。')}
    {ph('示意_次臥書桌.jpg', 56, '次臥：床頭延伸懸浮書桌，可兼書房。')}
  </div>
  <div class="two" style="margin-top:3.5mm">
    {ph('示意_小孩房.jpg', 56, '小孩房：軟包牆板、整面衣櫃。')}
    {ph('示意_小孩房遊戲.jpg', 56, '小孩房：地板留出遊戲空間。')}
  </div>
</div>{foot(6)}</div>

<!-- P7 區位 -->
<div class="page"><div class="pad">
  <div class="eyebrow">05 · LOCATION</div>
  <div class="ttl">區位與生活機能</div>
  <div class="sub">位於西區五權三街55巷，國立臺灣美術館、美術園道生活圈；巷弄住宅區，遠離主幹道車流。</div>
  <div class="photo"><img src="{img('外觀_入口.jpg')}" style="height:100mm;object-position:center 60%"></div>
  <div class="cap">社區入口：門廳、植栽與右側坡道車道入口。</div>
  <div class="two" style="margin-top:4mm">
    <div>
      <h3 class="h">生活機能</h3>
      <table class="spec">
        <tr><td>市場賣場</td><td>全聯、超商、第五市場、向上市場、好市多</td></tr>
        <tr><td>綠地</td><td>美術園道</td></tr>
        <tr><td>文化</td><td>國立臺灣美術館</td></tr>
        <tr><td>學區</td><td>忠信國小・崇倫國中（雙語學區）</td></tr>
        <tr><td>鄰近學校</td><td>大勇國小、向上國中</td></tr>
        <tr><td>醫療</td><td>友仁醫院</td></tr>
      </table>
      <div class="cap">學區依教育局公告學區（樂居登錄）；入學仍以設籍與當年度分發規定為準。</div>
    </div>
    <div>
      <h3 class="h">社區公設</h3>
      <table class="spec">
        <tr><td>大廳</td><td>門廳・王勝正設計</td></tr>
        <tr><td>交誼</td><td>交誼廳、閱覽空間</td></tr>
        <tr><td>庭園</td><td>戶外水景庭園</td></tr>
        <tr><td>管理</td><td>物業管理公司進駐</td></tr>
      </table>
      <div class="cap">依現場照片與售屋資料表整理，實際公設項目與開放規定以管委會公告為準。</div>
    </div>
  </div>
  <div class="note" style="margin-top:4mm"><b>為什麼是這裡：</b>全社區只有 18 戶、一層兩戶，在美術館生活圈的靜巷裡。社區 106–115 年實登 {S["有效筆數"]} 筆，有行情可以比對。</div>
</div>{foot(7)}</div>

<!-- P8 社區成交 -->
<div class="page"><div class="pad">
  <div class="eyebrow">06 · COMMUNITY HISTORY</div>
  <div class="ttl">寶鴻大白歷年成交</div>
  <div class="sub">3 號、5 號逐門牌查詢 101/01–115/10，有效成交 {S["有效筆數"]} 筆（無特殊關係交易）。依扣除車位後的坪數分型；
  <b>三房四衛（扣車位約 62 坪）即本戶同型</b>，線為年度中位數。</div>
  {chart_comm}
  <div class="note" style="margin:3mm 0">同型三房四衛年度中位：109 年 {ym[109]:.1f} → 110 年 {ym[110]:.1f} → 111 年 {ym[111]:.1f} → 112 年 {ym[112]:.1f} → 113 年 {ym[113]:.1f} → 115 年 {ym[115]:.1f}。
  110 年後大致在 <b>44–47 萬/坪</b>；同型 5–8F 中位 {FB["中高"]["不含車中位"]:.1f}、2–4F {FB["低樓"]["不含車中位"]:.1f}，樓層價差不大。114 年無同型成交。</div>
  <table class="tight xs">
    <tr><th>日期</th><th>門牌</th><th>產品</th><th>總價（萬）</th><th>總坪數</th><th>車位</th><th>車位價</th><th>{P_HOUSE}</th><th>{P_ALL}</th><th>備註</th></tr>
    {comm_rows}
  </table>
  <div class="cap">列出 110 年後成交，淡橘底為同型三房四衛。車位價未揭露者以本社區 110 年後揭露之坡道平面每席中位 {PK1:.1f} 萬估算（標 *）。單位：萬元／坪。</div>
</div>{foot(8)}</div>

<!-- P9 區域比較 -->
<div class="page"><div class="pad">
  <div class="eyebrow">07 · AREA COMPARISON</div>
  <div class="ttl">西區同齡、同坪數大樓比較</div>
  <div class="sub">條件：西區、華廈與住宅大樓、屋齡 5–10 年、總面積 70–100 坪，112/01–115/10。排除特殊關係、1 樓店面與樓中樓後，再取<b>扣車位面積 {BAND["扣車位面積"]} 坪</b>（本戶 {BASE:.2f} 坪 ±5 坪），共 {BAND["n"]} 筆（不含本社區）。</div>
  <div class="note" style="margin-bottom:3.5mm"><b>有車位的物件，單價怎麼看？</b>總價裡含車位，所以有兩種算法：<br>
  ① <b>{P_HOUSE}</b>＝（總價－車位價）÷（總坪數－車位坪數），用來比房子本身。<br>
  ② <b>{P_ALL}</b>，車位每坪便宜，會把單價拉低，網路上常看到的是這個數字。<br>
  例：{EX["社區"]} {EX["日期"]} 成交 {wan(EX["總價"])} 萬、{EX["坪數"]:.2f} 坪，含坡道平面車位 {EX["車位"]} 席 {wan(EX["車位價"])} 萬 → ① <b>{EX["不含車"]:.1f}</b>；② {EX["含車"]:.1f}。<br>
  本戶：開價 {wan(ASK)} 萬、{L["總面積"]} 坪、車位 2 席 {L["車位面積"]} 坪（以社區每席 {PK1:.1f} 萬計）→ ① ({wan(ASK)}－{PKV:.0f})÷{BASE:.2f} 坪＝<b>{L["不含車單價"]:.2f}</b>；② {wan(ASK)}÷{L["總面積"]} 坪＝{L["含車單價"]:.2f}。</div>
  <div class="kpi">
    <div><div class="v">{BAND["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">西區同齡同坪數 {P_HOUSE}</div></div>
    <div><div class="v">{BAND["gross"]:.1f}</div><div class="u">萬/坪</div><div class="l">西區同齡同坪數 {P_ALL}</div></div>
    <div><div class="v">{SAME4["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">寶鴻大白同型 近四年 {P_HOUSE}</div></div>
    <div><div class="v">{CY[112]["不含車中位"]:.0f}→{CY[115]["不含車中位"]:.0f}</div><div class="u">萬/坪</div><div class="l">西區同齡大樓 112→115 年中位</div></div>
  </div>
  <table class="tight xs">
    <tr><th>日期</th><th>社區</th><th>門牌</th><th style="white-space:nowrap">屋齡</th><th style="white-space:nowrap">樓層</th><th>總價（萬）</th><th style="white-space:nowrap">總坪數</th><th style="white-space:nowrap">扣車位</th><th>車位</th><th>{P_HOUSE}</th><th>{P_ALL}</th></tr>
    {cmp_rows}
  </table>
  <div class="cap">車位價未揭露者以比較組坡道平面每席中位 {CMP["車位每席中位"]:.1f} 萬估算（標 *）。「—」為實登未填社區名。屋齡為交易當時（年）。單位：萬元／坪。
  西區同齡大樓（不分坪數級距、不含本社區）年度中位：112 年 {CY[112]["不含車中位"]:.1f}（{CY[112]["n"]} 筆）、113 年 {CY[113]["不含車中位"]:.1f}（{CY[113]["n"]}）、114 年 {CY[114]["不含車中位"]:.1f}（{CY[114]["n"]}）、115 年 {CY[115]["不含車中位"]:.1f}（{CY[115]["n"]}）。</div>
</div>{foot(9)}</div>

<!-- P10 價格分析 -->
<div class="page"><div class="pad">
  <div class="eyebrow">08 · PRICE ANALYSIS</div>
  <div class="ttl">價格分析：開價放進行情看</div>
  <div class="sub">把各參考點的「{P_HOUSE}」套到本戶（扣車位 {BASE:.2f} 坪＋車位 2 席 {PKV:.0f} 萬），換算成「照這個行情，本戶是多少」。</div>
  <div class="kpi">
    <div><div class="v">{wan(ASK)}</div><div class="u">萬元</div><div class="l">開價（{P_HOUSE} {L["不含車單價"]:.1f}）</div></div>
    <div><div class="v">{L["含車單價"]:.1f}</div><div class="u">萬/坪</div><div class="l">開價 {P_ALL}</div></div>
    <div><div class="v">{SAME4["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">社區同型近四年中位（{SAME4["n"]} 筆）</div></div>
    <div><div class="v">{BAND["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">西區同齡同坪數中位（{BAND["n"]} 筆）</div></div>
  </div>
  <table>
    <tr><th>參考點</th><th>說明</th><th>{P_HOUSE}</th><th>{P_ALL}</th><th>換算本戶（萬）</th></tr>
    {pos_rows}
  </table>
  <h3 class="h">怎麼解讀</h3>
  <ul>
    <li><b>社區成交行情 44–47：</b>110 年後同型多數落在 44–47 萬/坪，近四年中位 {SAME4["net"]:.1f}，換算本戶約 {wan(conv(SAME4["net"]))} 萬；近四年最高 {TOP["不含車單價"]:.1f}，換算約 {wan(conv(TOP["不含車單價"]))} 萬。</li>
    <li><b>開價高於社區過往成交：</b>本戶開價換算 {L["不含車單價"]:.1f}，比社區同型近四年中位高約 {GAP_SAME:.0f}%、比西區同齡同坪數中位高約 {GAP_BAND:.0f}%；與西區同級距最高一筆（{CTOP["不含車"]:.1f}）相近。</li>
    <li><b>社區成交多在中低樓層：</b>近四年同型 {SAME4["n"]} 筆中，只有 1 筆在 8 樓（112/02，5 號）。本戶是同型最高樓層，同層、高樓層的成交參考點少。</li>
    <li><b>西區同齡大樓 115 年成交較高：</b>西區屋齡 5–10 年大樓 115 年中位 {CY[115]["不含車中位"]:.1f}，高於 112 年的 {CY[112]["不含車中位"]:.1f}；社區最近一筆同型成交在 115/01（{LAST["不含車單價"]:.1f}）。</li>
    <li><b>車位價值：</b>兩席 B1 坡道平面，以社區揭露行情每席約 {PK1:.0f} 萬計，車位合計約 {PKV:.0f} 萬，已含在開價內。</li>
  </ul>
  <div class="warn" style="margin-top:3mm">社區 18 戶、成交樣本少（近四年同型 {SAME4["n"]} 筆），行情帶寬較寬。以上換算是依實價登錄推估，不是不動產估價師的估價；實際成交以買賣雙方議價為準，過去成交不代表未來價格。</div>
</div>{foot(10)}</div>

<!-- P11 購屋試算 -->
<div class="page"><div class="pad">
  <div class="eyebrow">09 · BUYER'S GUIDE</div>
  <div class="ttl">購屋試算與看屋重點</div>
  <div class="kpi">
    <div><div class="v">{ASK:,}</div><div class="u">萬元</div><div class="l">以開價試算</div></div>
    <div><div class="v">{wan(down)}</div><div class="u">萬元</div><div class="l">自備款（兩成）</div></div>
    <div><div class="v">{wan(loan)}</div><div class="u">萬元</div><div class="l">貸款（八成）</div></div>
    <div><div class="v">{pay/10000:.1f}</div><div class="u">萬元／月</div><div class="l">本息攤還</div></div>
  </div>
  <div class="note">試算假設：貸款八成、年利率 {RATE*100:.1f}%、{YEARS} 年本息平均攤還，每月約 {pay:,.0f} 元。另需預留契稅、代書、仲介服務費。實際成數、利率與年限依銀行鑑價與個人條件核定。</div>
  <h3 class="h">看屋重點</h3>
  <ul>
    <li><b>坪數：</b>權狀 {L["總面積"]} 坪（主建物 {L["主建物"]:.2f}、附屬 {L["附屬"]:.2f}、公設 {L["公設"]:.2f}，其中車位 {L["車位面積"]} 坪），以建物謄本與權狀為準。</li>
    <li><b>車位：</b>B1 坡道平面 2 席（B1-34A、35），車位位置與使用方式以分管協議、管委會規約為準。</li>
    <li><b>裝修：</b>本報告室內圖為 3D 設計示意；屋主裝潢項目、留下的家具家電，請以現場與點交清單確認。</li>
    <li><b>管理費：</b>8,400 元／月，可索取管委會收支、修繕紀錄與規約。</li>
    <li><b>屋齡 9 年：</b>RC 結構，可一併確認外牆、防水、電梯保養紀錄。</li>
  </ul>
  <div style="margin-top:5mm;position:relative;background:#fff;border:1px solid #dde4e9;padding:4mm 36mm 4mm 6mm;font-size:7.6pt;line-height:1.75;color:#4a5560">
    <div class="b" style="font-size:9.4pt;color:#163a47;margin-bottom:1.2mm">資料來源與免責聲明</div>
    實價登錄：內政部不動產交易實價查詢服務網，五權三街55巷3號、5號買賣（101/01–115/10）；西區華廈・住宅大樓・屋齡5–10年・總面積70–100坪買賣（112/01–115/10）；查詢日 2026-10-23。社區與建案介紹整理自樂居、建商銷售資料與售屋資料表；室內圖為 3D 設計示意。<br>
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
</div>{foot(11)}</div>

</body></html>'''

OUT_HTML.write_text(html, encoding='utf-8')
print('HTML →', OUT_HTML)

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    pg = b.new_page()
    pg.goto(OUT_HTML.resolve().as_uri())
    pg.wait_for_timeout(800)
    pg.pdf(path=str(OUT_PDF), prefer_css_page_size=True, print_background=True)
    b.close()
print('PDF  →', OUT_PDF)
