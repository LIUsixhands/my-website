"""百達艷麗 銷售報告書（給買方）：讀 summary.json / transactions.csv → 產 HTML → Playwright 輸出 PDF。
口徑：單價一律並列「房屋單價（已扣車位）」與「總價÷總坪數（車位一起算）」；不使用主建物單價。
同型＝臨臺灣大道端戶（之1／之2）；區域比較組卡扣車位面積 ±5 坪（鐵律 8）。
室內照為選配：檔案放進本資料夾即自動上版（見 PHOTOS）。"""
import base64, json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
OUT_HTML = HERE / '百達艷麗_銷售報告書.html'
OUT_PDF = HERE / '百達艷麗_銷售報告書.pdf'

S = json.load(open(HERE / 'summary.json'))
df = pd.read_csv(HERE / 'transactions.csv')
df['備註'] = df['備註'].fillna('')
df['yr'] = df['交易日期'].str[:3].astype(int)
L = S['本戶']
BASE, PK = L['扣車位面積'], L['車位估價']
PK1 = PK / L['車位數']
SAME3, R3 = S['同型_近三年'], S['近三年']
CMP = S['比較組']
CB, CA = CMP['同級距'], CMP['全部_不含本社區']
ASK = L['開價']                                       # ⛔ 對外報告不放建議成交價，試算以開價計
MGMT = L['管理費季'] / 3

def conv(net): return net * BASE + PK               # 不含車單價 → 本戶總價（扣車位 75.89 坪＋2 車位）
def img(name):
    mime = 'image/png' if name.endswith('png') else 'image/jpeg'
    return f"data:{mime};base64,{base64.b64encode((HERE / name).read_bytes()).decode()}"
def f2(v): return '—' if v is None or pd.isna(v) else f'{v:.2f}'
def wan(v): return '—' if v is None or pd.isna(v) else f'{v:,.0f}'

# 室內／外觀照：助哥提供後放進資料夾即自動上版
PHOTOS = [('室內_客餐廳.jpg', '客餐廳：亮面地磚、茶鏡隔屏與整面收納櫃，客廳大面落地窗。'),
          ('室內_主臥.jpg', '主臥：兩面落地窗、雙層窗簾，木地板。'),
          ('景觀_臺灣大道.jpg', '臺灣大道街景（刊登照片）：主幹道林蔭、商辦大樓林立。'),
          ('車位_B2-40-41.jpg', '車位：B2 坡道平面 40、41 號，兩席相鄰。')]
PHOTOS = [(f, c) for f, c in PHOTOS if (HERE / f).exists()]

P_HOUSE = '房屋單價（已扣車位）'
P_ALL = '總價÷總坪數（車位一起算）'
SAME = df[df['產品'].str.startswith('端戶')].sort_values('交易日期')
CD = df[df['產品'].str.startswith('內側')]
TOP = SAME[SAME['交易日期'] == '113/04/08'].iloc[0]        # 同型 9F 最近高點
LAST_CD = CD[CD['yr'] == 115]

def svg_open(W, H): return [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC" font-size="10">']
def tt(d): y, m, _ = d.split('/'); return int(y) + (int(m) - .5) / 12

# ---------- 棟別配置（依 591 刊登之樓層平面重繪：每層 4 戶、2 梯） ----------
def site_svg(hl='B'):
    W, H = 360, 190
    s = svg_open(W, H)
    s.append('<rect x="0" y="0" width="360" height="190" fill="#fff"/>')
    s.append('<rect x="6" y="20" width="26" height="150" fill="#e8edf0"/><text x="19" y="95" text-anchor="middle" fill="#5d6b76" font-size="10" writing-mode="tb">臺灣大道</text>')
    units = {'A': (44, 20, '之1', '79.82P'), 'B': (44, 100, '之2', '79.82P'), 'D': (232, 20, '之5', '74.94P'), 'C': (232, 100, '之3', '74.94P')}
    for k, (x, y, no, p) in units.items():
        me = k == hl
        s.append(f'<rect x="{x}" y="{y}" width="114" height="70" rx="3" fill="{"#C0392B" if me else "#eef3f6"}" stroke="{"#8e2a1f" if me else "#9fb3bf"}"/>'
                 f'<text x="{x+57}" y="{y+32}" text-anchor="middle" font-size="20" font-weight="700" fill="{"#fff" if me else "#1F4E5F"}">{k}</text>'
                 f'<text x="{x+57}" y="{y+52}" text-anchor="middle" font-size="9.5" fill="{"#fff" if me else "#5d6b76"}">{no}・{p}{"・本戶" if me else ""}</text>')
    s.append('<rect x="164" y="60" width="62" height="70" fill="#d8e0e5"/><text x="195" y="92" text-anchor="middle" font-size="9" fill="#5d6b76">梯廳</text><text x="195" y="105" text-anchor="middle" font-size="9" fill="#5d6b76">2 部電梯</text>')
    s.append('<text x="354" y="14" text-anchor="end" font-size="9" fill="#7b8794">北 ↗</text></svg>')
    return ''.join(s)
SITE = site_svg()

# ---------- 圖一：社區歷年成交（依產品分色；端戶以年度中位連線） ----------
W, H, Lm, R, T, B = 560, 230, 40, 16, 24, 42
X0, X1, YMIN, YMAX = 102, 116, 15, 55
def X(t): return Lm + (t - X0) * (W - Lm - R) / (X1 - X0)
def Y(v): return T + (YMAX - v) * (H - T - B) / (YMAX - YMIN)
svg = svg_open(W, H)
for v in range(YMIN, YMAX + 1, 5):
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e3e8ec"/>'
               f'<text x="{Lm-6}" y="{Y(v)+3:.1f}" text-anchor="end" fill="#7b8794">{v}</text>')
for y in range(102, 116):
    svg.append(f'<text x="{X(y+.5):.1f}" y="{H-B+14}" text-anchor="middle" fill="#7b8794" font-size="9">{y}</text>')
svg.append(f'<text x="{W-R}" y="{T-10}" text-anchor="end" fill="#7b8794" font-size="9">單位：萬元／坪（{P_HOUSE}）</text>')
for v, c, lab, dy in [(L['不含車單價'], '#C0392B', f'本戶開價 {L["不含車單價"]:.1f}', -4), (CB['net'], '#C8963E', f'西區同級距中位 {CB["net"]:.1f}', -4)]:
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{c}" stroke-width="1.2" stroke-dasharray="3 3"/>'
               f'<text x="{Lm+4}" y="{Y(v)+dy:.1f}" fill="{c}" font-size="9" font-weight="700">{lab}</text>')
STY = {'端戶 A／B（之1・之2）': ('#1F4E5F', 4.2), '內側戶 C／D（之3・之5）': ('#9aa7b2', 3.4), '頂樓大戶': ('#6b7d8a', 3.4)}
ym = SAME.groupby('yr')['不含車單價'].median()
svg.append(f'<path d="{" ".join(("M" if i == 0 else "L") + f"{X(y+.5):.1f},{Y(v):.1f}" for i, (y, v) in enumerate(ym.items()))}" fill="none" stroke="#1F4E5F" stroke-width="2.2" opacity=".85"/>')
for r in df.itertuples():
    c, rad = STY[r.產品]
    svg.append(f'<circle cx="{X(tt(r.交易日期)):.1f}" cy="{Y(r.不含車單價):.1f}" r="{rad}" fill="{c}" fill-opacity="{1 if r.產品.startswith("端戶") else .8}" stroke="#fff" stroke-width=".8"/>')
for y, v in ym.items():
    if y >= 106:
        svg.append(f'<text x="{X(y+.5):.1f}" y="{Y(v)+13:.1f}" text-anchor="middle" fill="#1F4E5F" font-size="8.4" font-weight="700">{v:.1f}</text>')
for i, prod in enumerate(STY):
    c, rad = STY[prod]; lx = Lm + 2 + i * 165
    svg.append(f'<circle cx="{lx+6}" cy="{H-10}" r="{rad}" fill="{c}"/><text x="{lx+14}" y="{H-7}" fill="#4a5560" font-size="8.4">{prod}</text>')
svg.append('</svg>')
chart_comm = ''.join(svg)

comm_rows = ''
for r in df[df['yr'] >= 109].itertuples():
    cls = ' class="hl"' if r.產品.startswith('端戶') else ''
    est = '*' if r.車位價來源.startswith('估算') else ''
    note = r.備註.replace(';', ' ').replace('。', '').strip()[:12]
    comm_rows += (f'<tr{cls}><td>{r.交易日期}</td><td>{r.棟別}・{r.樓層}F</td><td>{r.產品.split("（")[0]}</td><td class="num">{wan(r.總價萬)}</td>'
                  f'<td class="num">{r.總面積坪:.2f}</td><td class="num">{r.車位數}</td><td class="num">{wan(r.車位價萬)}{est}</td>'
                  f'<td class="num b">{r.不含車單價:.2f}{est}</td><td class="num">{r.含車單價:.2f}</td><td>{note}</td></tr>')

prod_rows = ''
for p in S['產品']:
    hl = ' class="hl"' if p['型'].startswith('端戶') else ''
    prod_rows += (f'<tr{hl}><td>{p["型"]}</td><td class="num">{p["總面積中位"]:.2f}</td><td class="num">{p["扣車位面積中位"]:.2f}</td><td class="num">{p["全期n"]}</td>'
                  f'<td class="num">{p["近三年n"]}</td><td class="num b">{f2(p["近三年不含車中位"])}</td><td class="num">{f2(p["近三年含車中位"])}</td></tr>')

# ---------- 區域比較組（同級距） ----------
cmp_rows = ''
for r in CMP['明細']:
    if not r['同級距']: continue
    est = '' if r['車位價'] else '*'
    cmp_rows += (f'<tr><td>{r["日期"]}</td><td>{r["社區"]}</td><td>{r["門牌"]}</td><td class="num">{r["屋齡"]}</td><td class="num">{r["樓層"]}</td><td class="num">{wan(r["總價"])}</td>'
                 f'<td class="num">{r["坪數"]:.2f}</td><td class="num">{r["扣車位"]:.2f}</td><td>{r["車位"]}・{r["車位類別"].replace("坡道", "")}</td>'
                 f'<td class="num b">{r["不含車"]:.2f}{est}</td><td class="num">{r["含車"]:.2f}</td></tr>')
EX = next((r for r in CMP['明細'] if r['同級距'] and r['車位價']), None)

# ---------- 價格分析 ----------
cd115 = LAST_CD['不含車單價'].median()
anchors = [
    ('同型端戶 近三年中位', f'113 年 {SAME3["n"]} 筆（9F／10F／11F 之1），扣車位約 79–81 坪', SAME3['net']),
    ('同型端戶 9F（113/04）', f'成交 {wan(TOP["總價萬"])} 萬，含 2 車位', TOP['不含車單價']),
    ('全社區 近三年中位', f'113–115 年 {R3["n"]} 筆（含內側戶）', R3['net']),
    ('內側戶 115 年中位', f'115 年 {len(LAST_CD)} 筆（4F／5F／9F 之3・之5），坪數較小', cd115),
    ('西區同級距 中位', f'扣車位 {BASE-5:.0f}–{BASE+5:.0f} 坪、屋齡 10–20 年，{CB["n"]} 筆', CB['net']),
]
pos_rows = (f'<tr class="hl"><td>本戶開價</td><td>B・11F・{L["總面積"]} 坪・2 車位</td><td class="num">{L["不含車單價"]:.2f}</td><td class="num">{L["含車單價"]:.2f}</td><td class="num">{wan(ASK)}</td></tr>')
for nm, why, up in anchors:
    pos_rows += f'<tr><td class="b">{nm}</td><td>{why}</td><td class="num">{up:.2f}</td><td class="num">{conv(up)/L["總面積"]:.2f}</td><td class="num">{wan(conv(up))}</td></tr>'

# ---------- 租賃 ----------
RENT = S['租賃']
def rent_note(r):
    t = '整戶' if r['整戶'] else '面積僅 47.6 坪，非整戶'
    if '含管理費' in r['備註']: t += '・含管理費等'
    if '共同承租' in r['備註']: t += '・2 人共同承租'
    return t
rent_rows = ''.join(f'<tr{" class=hl" if int(r["日期"][:3]) >= 113 else ""}><td>{r["日期"]}</td><td>{r["戶"]}・{r["樓層"]}F</td><td class="num">{r["面積坪"]:.2f}</td><td class="num">{r["車位"]}</td>'
                    f'<td class="num b">{r["月租萬"]:.2f}</td><td class="num">{r["每坪元"]:,}</td><td>{rent_note(r)}</td></tr>' for r in RENT['明細'])
R_LAST = RENT['近三年整戶'][0]
YIELD = R_LAST['月租萬'] * 12 / ASK * 100

# ---------- 房貸試算 ----------
RATE, YEARS, LTV = 0.022, 30, 0.8
loan = ASK * LTV
r_m = RATE / 12
pay = loan * 10000 * r_m / (1 - (1 + r_m) ** (-YEARS * 12))
down = ASK - loan

DISC = '永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號'
PHONE, LINE_ID, WEB = '0925-313-570', '@080akczk', 'sixhands.tw'
CONTACT = f'助哥 <span style="white-space:nowrap">{PHONE}</span>　｜　LINE {LINE_ID}　｜　{WEB}'
SHIFT = 1 if PHOTOS else 0
def foot(n, raw=False):
    n = n if raw or n <= 3 else n + SHIFT
    return (f'<div class="foot"><div>{DISC}<br><span class="ct">{CONTACT}</span></div>'
            f'<span>百達艷麗 銷售報告書　{n}</span></div>')

def photo_block(items, h):
    if not items: return ''
    cells = ''.join(f'<div><div class="photo"><img src="{img(f)}" style="height:{h}mm"></div><div class="cap">{c}</div></div>' for f, c in items)
    return f'<div class="two" style="margin-top:3.5mm">{cells}</div>'

photo_page = ''
if PHOTOS:
    rows_html = ''.join(photo_block(PHOTOS[i:i + 2], 78 if len(PHOTOS) <= 2 else 74) for i in range(0, len(PHOTOS), 2))
    photo_page = f'''
<div class="page"><div class="pad">
  <div class="eyebrow">02 · INTERIOR</div>
  <div class="ttl">實景照片</div>
  <div class="sub">本戶現況照片，裝潢、家具與家電依實際點交為準。</div>
  {rows_html}
</div>{foot(4, raw=True)}</div>'''

html = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>百達艷麗 銷售報告書</title><style>
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
  <img src="{img('室內_客餐廳.jpg')}" style="position:absolute;left:0;top:0;width:210mm;height:128mm;object-fit:cover">
  <div style="position:absolute;left:0;top:92mm;width:210mm;height:36mm;background:linear-gradient(180deg,rgba(16,42,51,0),#102a33)"></div>
  <div style="position:absolute;left:16mm;top:112mm;color:#E3B66A;font-size:8pt;letter-spacing:.5em">PROPERTY SALES REPORT</div>
  <div style="position:absolute;left:16mm;top:118mm;right:16mm;color:#fff">
    <div class="serif" style="font-size:11pt;color:#E3B66A;letter-spacing:.2em">臺中市西區 · 臺灣大道二段 · 廣三 SOGO／勤美生活圈</div>
    <div style="width:46mm;height:2px;background:#E3B66A;margin:5mm 0 4mm"></div>
    <h1 style="font-size:42pt;line-height:1.2">百達艷麗</h1>
    <div class="serif" style="font-size:15pt;margin-top:2mm">買方銷售報告書 · 11 樓 四房雙主臥 · 雙坡道平面車位</div>
    <div style="font-size:8.8pt;color:#b9cad3;margin-top:4mm;line-height:1.9">臺中市西區臺灣大道二段419號11樓之2（B 戶，臨臺灣大道端）<br>開價 {wan(ASK)} 萬　·　權狀 {L["總面積"]} 坪（含車位 {L["車位面積"]} 坪）　·　4房2廳3衛　·　精裝修</div>
    <div style="margin-top:7mm;border-top:1px solid #3b5b66;padding-top:5mm">
      <div style="font-size:7.6pt;color:#E3B66A;letter-spacing:.3em">核心數字</div>
      <div style="font-size:9.3pt;line-height:1.9;margin-top:2mm">
        43 戶、12 層、每層 4 戶的低密度社區；本戶位在 11 樓、臨臺灣大道的端戶。<br>
        社區近三年成交中位 <b>{R3["net"]:.1f} 萬/坪</b>（{P_HOUSE}），西區同坪數大樓 <b>{CB["net"]:.1f}</b>。<br>
        本戶以「{P_ALL}」計為 <b>{L["含車單價"]:.1f}</b>，與西區同坪數大樓 {CB["gross"]:.1f} 相當。<br>
        <span style="color:#E3B66A">開價 {wan(ASK)} 萬，{P_HOUSE} {L["不含車單價"]:.1f} 萬/坪（含精裝修與 2 席平面車位）。</span>
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
  <div style="position:absolute;left:16mm;right:16mm;bottom:7mm;font-size:6.8pt;color:#8fa6b1;line-height:1.7">資料：內政部實價登錄（臺灣大道二段419號逐門牌 101/01–115/10；西區大樓／華廈 屋齡10–20年 80–110坪 112/10–115/10，查詢 2026-10-23）<br>{DISC}</div>
</div>

<!-- P2 物件總覽 -->
<div class="page"><div class="pad">
  <div class="eyebrow">01 · PROPERTY OVERVIEW</div>
  <div class="ttl">物件總覽</div>
  <div class="kpi">
    <div><div class="v">{wan(ASK)}</div><div class="u">萬元</div><div class="l">開價（含 2 車位）</div></div>
    <div><div class="v">{L["總面積"]}</div><div class="u">坪</div><div class="l">權狀總坪數（含車位）</div></div>
    <div><div class="v">{L["主建物"]+L["附屬"]:.2f}</div><div class="u">坪</div><div class="l">主建物＋附屬（室內可用）</div></div>
    <div><div class="v">11<span style="font-size:10pt">／12F</span></div><div class="u">樓層</div><div class="l">次頂樓・臨臺灣大道端戶</div></div>
    <div><div class="v">{MGMT:,.0f}</div><div class="u">元／月</div><div class="l">管理費（季繳 {L["管理費季"]:,} 元）</div></div>
  </div>
  <div class="two">
    <div>
      <h3 class="h">本戶資料</h3>
      <table class="spec">
        <tr><td>地址</td><td>臺中市西區臺灣大道二段419號11樓之2</td></tr>
        <tr><td>戶別</td><td>B 戶（之2），臨臺灣大道端</td></tr>
        <tr><td>格局</td><td>4房2廳3衛・雙主臥（各附衛浴，其一附更衣室）</td></tr>
        <tr><td>坪數</td><td>主建物 {L["主建物"]}＋附屬 {L["附屬"]}（陽台）＋共同使用 {L["共同"]}（含車位 {L["車位面積"]}）＝{L["總面積"]} 坪</td></tr>
        <tr><td>土地</td><td>{L["土地"]} 坪</td></tr>
        <tr><td>車位</td><td>坡道平面 2 席・B2-40、41（相鄰）</td></tr>
        <tr><td>現況</td><td>精裝修（刊登標示「百萬精裝」）</td></tr>
        <tr><td>管理費</td><td>季繳 {L["管理費季"]:,} 元（約 {MGMT:,.0f} 元／月）</td></tr>
        <tr><td>屋齡</td><td>約 17.2 年</td></tr>
        <tr><td>物件編號</td><td>0396845</td></tr>
      </table>
    </div>
    <div>
      <h3 class="h">社區資料</h3>
      <table class="spec">
        <tr><td>社區</td><td>百達艷麗（興富發建設）</td></tr>
        <tr><td>規模</td><td>總戶數 43 戶・地上 12 層／地下 4 層・每層 4 戶</td></tr>
        <tr><td>基地</td><td>約 365 坪・商三</td></tr>
        <tr><td>結構</td><td>鋼筋混凝土（RC）</td></tr>
        <tr><td>公設比</td><td>32.10–36.60%（網路刊登）</td></tr>
        <tr><td>車位</td><td>坡道平面・共 75 席</td></tr>
        <tr><td>建築設計</td><td>大容聯合建築師事務所</td></tr>
        <tr><td>營造</td><td>齊裕營造</td></tr>
        <tr><td>學區</td><td>中正國小・忠明高中國中部（雙語）</td></tr>
      </table>
    </div>
  </div>
  <h3 class="h">樓層配置</h3>
  <div style="display:flex;gap:5mm;align-items:center">
    <div style="flex:1.2">{SITE}</div>
    <div style="flex:1;font-size:8.2pt;line-height:1.8;color:#33414c">
      每層 4 戶、2 部電梯。<b>A（之1）、B（之2）</b>臨臺灣大道，權狀約 80 坪（不含車位）；<b>C（之3）、D（之5）</b>在內側，約 75 坪。<br>
      本戶為 <b style="color:#C0392B">B 戶（之2）</b>，位於臨臺灣大道的端部。
      <div class="cap" style="margin-top:2mm">依網路刊登之樓層平面重繪，非比例尺；坪數為刊登標示。</div>
    </div>
  </div>
</div>{foot(2)}</div>

<!-- P3 格局與賣點 -->
<div class="page"><div class="pad">
  <div class="eyebrow">02 · FLOOR PLAN</div>
  <div class="ttl">格局與六大賣點</div>
  <div class="photo" style="background:#fff"><img src="{img('格局圖.png')}" style="height:82mm;object-fit:contain"></div>
  <div class="cap">※ 示意圖，實際格局與尺寸以現場丈量為準。陽台外推等增建部分以現況與不動產說明書為準。</div>
  <div class="two" style="margin-top:4mm">
    <div>
      <div class="feat"><div class="no">01</div><div><h3>雙主臥・四房</h3><p>兩間主臥各在一端、各有衛浴，其一附更衣室；適合兩代同住或長輩同住，彼此有獨立動線。</p></div></div>
      <div class="feat"><div class="no">02</div><div><h3>雙坡道平面車位</h3><p>B2-40、41 兩席相鄰，坡道平面進出不必排機械；兩席合計 {L["車位面積"]} 坪。</p></div></div>
      <div class="feat"><div class="no">03</div><div><h3>精裝修</h3><p>刊登標示「百萬精裝」：亮面地磚、茶鏡隔屏、整面收納櫃與間接照明，現況可入住。</p></div></div>
    </div>
    <div>
      <div class="feat"><div class="no">04</div><div><h3>11 樓・臨臺灣大道端戶</h3><p>12 層社區的次頂樓，B 戶位在臨臺灣大道一端，客廳與主臥大面落地窗。</p></div></div>
      <div class="feat"><div class="no">05</div><div><h3>每層 4 戶・43 戶低密度</h3><p>全社區 43 戶、每層 4 戶 2 梯，住戶單純、等梯時間短。</p></div></div>
      <div class="feat"><div class="no">06</div><div><h3>SOGO・勤美生活圈</h3><p>臺灣大道二段上，廣三 SOGO、勤美誠品綠園道、草悟道、科博館都在附近；雙語學區。</p></div></div>
    </div>
  </div>
  <div class="note" style="margin-top:3mm"><b>室內可用 {L["主建物"]+L["附屬"]:.2f} 坪。</b>主建物 {L["主建物"]} 坪＋陽台 {L["附屬"]} 坪；權狀 {L["總面積"]} 坪中車位佔 {L["車位面積"]} 坪，扣掉車位後的公設約 {L["共同"]-L["車位面積"]:.1f} 坪。</div>
</div>{foot(3)}</div>
{photo_page}
<!-- P4 區位 -->
<div class="page"><div class="pad">
  <div class="eyebrow">03 · LOCATION &amp; COMMUNITY</div>
  <div class="ttl">區位與生活機能</div>
  <div class="sub">位於西區臺灣大道二段、忠明里，屬廣三 SOGO 與勤美誠品綠園道之間的生活圈；臺灣大道往七期、往臺中車站皆為直線。</div>
  <table class="spec" style="margin-bottom:4mm">
    <tr><td>商圈</td><td>廣三 SOGO、勤美誠品綠園道、草悟道商圈、向上市場</td></tr>
    <tr><td>綠地</td><td>科博館、草悟道、經國園道</td></tr>
    <tr><td>交通</td><td>臨臺灣大道（BRT／公車路網），往七期市政中心、臺中車站皆順；捷運藍線「科博館站」規劃中</td></tr>
    <tr><td>學區</td><td>市立中正國小、市立忠明高中國中部（雙語學區）</td></tr>
    <tr><td>醫療</td><td>周邊診所多；中國醫藥大學附設醫院、中山醫院車程可及</td></tr>
  </table>
  <div class="note"><b>為什麼是這裡：</b>臺灣大道主幹道、生活機能步行可及，但社區只有 43 戶、每層 4 戶，比周邊 20–30 層大樓單純。社區 101–115 年實登成交 {S["有效筆數"]} 筆，買賣都有行情可參考。</div>
  <div class="warn" style="margin-top:3mm">捷運藍線為規劃中路線，站位與時程以主管機關公告為準，本報告不以未來建設推估價格。</div>

  <h3 class="h" style="margin-top:6mm">社區產品分型</h3>
  <div class="sub" style="margin-bottom:2mm">實登總坪數含 1–3 席車位，直接比會失準；依門牌「之幾」分型，比較扣除車位後的坪數。</div>
  <table>
    <tr><th>產品</th><th>總坪數中位</th><th>扣車位中位</th><th>全期筆數</th><th>113–115 筆數</th><th>{P_HOUSE}</th><th>{P_ALL}</th></tr>
    {prod_rows}
  </table>
  <div class="cap">淡橘底為本戶同型。內側戶坪數較小、單價較高；看行情請分型比較。單位：坪、萬元／坪。</div>
</div>{foot(4)}</div>

<!-- P5 社區成交 -->
<div class="page"><div class="pad">
  <div class="eyebrow">04 · COMMUNITY HISTORY</div>
  <div class="ttl">百達艷麗歷年成交</div>
  <div class="sub">臺灣大道二段419號逐門牌查詢 101/01–115/10，買賣 {S["原始筆數"]} 筆，排除特殊關係 {len(S["排除"])} 筆，有效 {S["有效筆數"]} 筆。
  <b>深色點與線為本戶同型（端戶 A／B）</b>，線為年度中位數。</div>
  {chart_comm}
  <div class="note" style="margin:3mm 0">同型端戶年度中位：106 年 {ym.get(106, float("nan")):.1f} → 110 年 {ym.get(110):.1f} → 113 年 <b>{ym.get(113):.1f}</b>。
  113 年後端戶尚無成交；內側戶 115 年 {len(LAST_CD)} 筆中位 {cd115:.1f}，社區近三年整體中位 {R3["net"]:.1f}。</div>
  <table class="tight xs">
    <tr><th>日期</th><th>戶別</th><th>產品</th><th>總價（萬）</th><th>總坪數</th><th>車位</th><th>車位價</th><th>{P_HOUSE}</th><th>{P_ALL}</th><th>備註</th></tr>
    {comm_rows}
  </table>
  <div class="cap">列出 109 年後成交，淡橘底為同型端戶。車位價未揭露者以本社區坡道平面每席中位 {PK1:.0f} 萬估算（標 *）。單位：萬元／坪。</div>
</div>{foot(5)}</div>

<!-- P6 區域比較 -->
<div class="page"><div class="pad">
  <div class="eyebrow">05 · AREA COMPARISON</div>
  <div class="ttl">西區同坪數大樓比較</div>
  <div class="sub">條件：西區、大樓／華廈、屋齡 10–20 年、總面積 80–110 坪，112/10–115/10，共 {CMP["有效"]} 筆有效（排除特殊關係 {CMP["排除特殊關係"]} 筆、一樓店面 {CMP["一樓排除"]} 筆）。
  再依本戶扣車位面積 {BASE:.2f} 坪，取 <b>扣車位 {BASE-5:.1f}–{BASE+5:.1f} 坪</b>的 {CB["n"]} 筆為同級距（不含本社區）。</div>
  <div class="note" style="margin-bottom:3.5mm"><b>有車位的物件，單價怎麼看？</b>總價裡含車位，所以有兩種算法：<br>
  ① <b>{P_HOUSE}</b>＝（總價－車位價）÷（總坪數－車位坪數），用來比房子本身。<br>
  ② <b>{P_ALL}</b>，車位每坪便宜，會把單價拉低，網路上常看到的是這個數字。<br>
  {f'例：{EX["社區"]} {EX["日期"]} 成交 {wan(EX["總價"])} 萬、{EX["坪數"]:.2f} 坪，含車位 {EX["車位"]} 席 {wan(EX["車位價"])} 萬（{EX["坪數"]-EX["扣車位"]:.2f} 坪）→ ① <b>{EX["不含車"]:.1f}</b>；② {EX["含車"]:.1f}。<br>' if EX else ''}
  本戶：開價 {wan(ASK)} 萬、{L["總面積"]} 坪、車位 2 席（以社區每席 {PK1:.0f} 萬、合計 {L["車位面積"]} 坪計）→ ① ({wan(ASK)}－{PK})÷{BASE:.2f} 坪＝<b>{L["不含車單價"]:.2f}</b>；② {wan(ASK)}÷{L["總面積"]} 坪＝{L["含車單價"]:.2f}。<br>
  本戶兩席車位合計 {L["車位面積"]} 坪、佔權狀 {L["車位面積"]/L["總面積"]*100:.0f}%，所以 ① 與 ② 的差距比一般物件大。</div>
  <div class="kpi">
    <div><div class="v">{CB["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">西區同級距 {P_HOUSE}</div></div>
    <div><div class="v">{CB["gross"]:.1f}</div><div class="u">萬/坪</div><div class="l">西區同級距 {P_ALL}</div></div>
    <div><div class="v">{CA["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">比較組全部 {CA["n"]} 筆 {P_HOUSE}</div></div>
    <div><div class="v">{R3["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">百達艷麗 近三年 {P_HOUSE}</div></div>
  </div>
  <table class="tight">
    <tr><th>日期</th><th>社區</th><th>門牌</th><th style="white-space:nowrap">屋齡</th><th style="white-space:nowrap">樓層</th><th>總價（萬）</th><th style="white-space:nowrap">總坪數</th><th style="white-space:nowrap">扣車位</th><th>車位</th><th>{P_HOUSE}</th><th>{P_ALL}</th></tr>
    {cmp_rows}
  </table>
  <div class="cap">車位價未揭露者以比較組同類別車位中位估算（標 *）。「—」為實登未填社區名。屋齡為交易當時（年）。單位：萬元／坪。</div>
</div>{foot(6)}</div>

<!-- P7 價格分析 -->
<div class="page"><div class="pad">
  <div class="eyebrow">06 · PRICE ANALYSIS</div>
  <div class="ttl">價格分析：開價放進行情看</div>
  <div class="sub">把各參考點的「{P_HOUSE}」套到本戶（扣車位 {BASE:.2f} 坪＋車位 2 席 {PK} 萬），換算成「照這個行情，本戶值多少」。</div>
  <div class="kpi">
    <div><div class="v">{wan(ASK)}</div><div class="u">萬元</div><div class="l">開價（{P_HOUSE} {L["不含車單價"]:.1f}）</div></div>
    <div><div class="v">{L["含車單價"]:.1f}</div><div class="u">萬/坪</div><div class="l">開價 {P_ALL}</div></div>
    <div><div class="v">{wan(conv(CB["net"]))}</div><div class="u">萬元</div><div class="l">照西區同級距中位換算</div></div>
    <div><div class="v">{wan(conv(R3["net"]))}</div><div class="u">萬元</div><div class="l">照社區近三年中位換算</div></div>
  </div>
  <table>
    <tr><th>參考點</th><th>說明</th><th>{P_HOUSE}</th><th>{P_ALL}</th><th>換算本戶（萬）</th></tr>
    {pos_rows}
  </table>
  <h3 class="h">怎麼解讀</h3>
  <ul>
    <li><b>車位一起算，與西區同坪數相當：</b>本戶「{P_ALL}」{L["含車單價"]:.1f}，西區同級距中位 {CB["gross"]:.1f}。本戶兩席車位面積大，這個口徑對本戶較有利，比較時請兩個口徑一起看。</li>
    <li><b>只看房屋，開價高於成交行情：</b>{P_HOUSE} {L["不含車單價"]:.1f}，比西區同級距中位 {CB["net"]:.1f} 高約 {(L["不含車單價"]/CB["net"]-1)*100:.0f}%，比社區近三年中位 {R3["net"]:.1f} 高約 {(L["不含車單價"]/R3["net"]-1)*100:.0f}%。</li>
    <li><b>同型端戶最近成交在 113 年：</b>9F／10F／11F 之1 三筆 {SAME[SAME["yr"]==113]["不含車單價"].min():.1f}–{SAME[SAME["yr"]==113]["不含車單價"].max():.1f}，之後兩年社區只有內側戶成交（115 年中位 {cd115:.1f}）。</li>
    <li><b>差額看什麼：</b>精裝修、雙主臥格局、11 樓、兩席相鄰平面車位，是本戶與社區過往成交的主要差異；看屋時可把裝修內容、車位使用與屋況一併納入比較。</li>
    <li><b>樓層不是主要差異：</b>110 年後低樓層（2–6F）中位 {S["樓層帶_110後"][0]["不含車中位"]:.1f}、中高樓層（7–12F）{S["樓層帶_110後"][1]["不含車中位"]:.1f}；本社區價格主要看產品與成交年度。</li>
  </ul>
  <div class="warn" style="margin-top:3mm">同型端戶近三年僅 {SAME3["n"]} 筆成交、社區近三年 {R3["n"]} 筆，行情帶寬較寬。以上換算依實登推估，不是估價師的估價，實際成交以雙方議價為準。</div>
</div>{foot(7)}</div>

<!-- P8 購屋試算 -->
<div class="page"><div class="pad">
  <div class="eyebrow">07 · BUYER'S GUIDE</div>
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
  <div class="cap">近三年僅 114/11 一筆整戶出租（10F 之1、{R_LAST["月租萬"]:.1f} 萬、不含車位），淡橘底。以本戶開價計，毛租金約 {YIELD:.1f}%（未扣管理費、稅費與空置），本社區以自住為主。</div>
  <h3 class="h">看屋重點</h3>
  <ul>
    <li><b>裝修內容：</b>請索取裝修項目與保固資料，確認哪些家具、家電隨屋點交。</li>
    <li><b>陽台外推／增建：</b>社區多筆成交備註陽台外推，請以現況與不動產說明書確認是否屬增建。</li>
    <li><b>車位：</b>坡道平面 B2-40、41 兩席，合計 {L["車位面積"]} 坪（含於權狀總坪數）；位置與使用以分管協議為準。</li>
    <li><b>管理費：</b>季繳 {L["管理費季"]:,} 元，可索取管委會收支與修繕紀錄。</li>
    <li><b>臨臺灣大道：</b>主幹道車流與噪音因人而異，建議平日與假日、白天與晚上各看一次。</li>
  </ul>
  <div style="margin-top:5mm;position:relative;background:#fff;border:1px solid #dde4e9;padding:4mm 36mm 4mm 6mm;font-size:7.6pt;line-height:1.75;color:#4a5560">
    <div class="b" style="font-size:9.4pt;color:#163a47;margin-bottom:1.2mm">資料來源與免責聲明</div>
    實價登錄：內政部不動產交易實價查詢服務網，臺灣大道二段419號買賣與租賃（101/01–115/10）；西區住宅大樓／華廈・屋齡10–20年・總面積80–110坪買賣（112/10–115/10）；查詢日 2026-10-23。社區與物件資料、照片整理自網路刊登與售屋資料表。<br>
    本報告書為不動產經紀業務之行銷參考資料，非不動產估價師出具之估價報告。行情統計與試算係依公開資料整理，不構成價格保證、投資建議或獲利承諾。實際面積、用途、產權及使用現況，以權狀、謄本、不動產說明書及買賣契約記載為準。
    <div style="position:absolute;right:7mm;top:50%;margin-top:-11mm;width:22mm;height:22mm;border:2.5px solid #b3261e;border-radius:50%;color:#b3261e;display:flex;align-items:center;justify-content:center;text-align:center;font-family:'Noto Serif CJK TC',serif;font-size:8pt;font-weight:700;line-height:1.3;transform:rotate(-12deg)">僅供<br>參考</div>
  </div>
  <div style="margin-top:5mm;display:flex;align-items:center;justify-content:center;gap:7mm;background:#163a47;padding:5mm 7mm;border-radius:2px">
    <div style="color:#fff">
      <div style="font-size:7.4pt;color:#E3B66A;letter-spacing:.3em">預約帶看・行情諮詢</div>
      <div class="serif" style="font-size:16pt;font-weight:700;margin-top:1mm">助哥　<span style="color:#F0D9A4;white-space:nowrap">{PHONE}</span></div>
      <div style="font-size:8pt;color:#b9cad3;margin-top:1mm;line-height:1.7">永慶不動產 七期河南市政店<br>LINE {LINE_ID}　｜　{WEB}</div>
    </div>
    <div class="qr" style="width:24mm"><img src="{img('QR_LINE.png')}"><div>加 LINE</div></div>
    <div class="qr" style="width:24mm"><img src="{img('QR_網站.png')}"><div>看網站</div></div>
  </div>
</div>{foot(8)}</div>

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
