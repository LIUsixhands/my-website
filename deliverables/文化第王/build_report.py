"""文化第王 銷售報告書（給買方）：讀 summary.json / transactions.csv → 產 HTML → Playwright 輸出 PDF。
比較口徑：板橋區・屋齡 25–35 年・3房2廳2衛（＝本戶售屋條件），一律分【無車位】【有車位】，有車位並列含車／不含車。"""
import base64, json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
OUT_HTML = HERE / '文化第王_銷售報告書.html'
OUT_PDF = HERE / '文化第王_銷售報告書.pdf'

S = json.load(open(HERE / 'summary.json'))
df = pd.read_csv(HERE / 'transactions.csv')
df['備註'] = df['備註'].fillna('')
df['yr'] = df['交易日期'].str[:3].astype(int)
L = S['本戶']
JZ3, BQ3 = S['江子翠_近三年'], S['板橋_近三年']
JZN, JZP = JZ3['無車位'], JZ3['有車位']
SIM = S['江子翠_無車位30-40坪_近三年']
TWIN = next(r for r in S['同社區'] if '1弄10號七樓' in r['門牌'])

def img(name):
    mime = 'image/png' if name.endswith('png') else 'image/jpeg'
    return f"data:{mime};base64,{base64.b64encode((HERE / name).read_bytes()).decode()}"
def f1(v): return '—' if v is None or pd.isna(v) else f'{v:.1f}'
def f2(v): return '—' if v is None or pd.isna(v) else f'{v:.2f}'
def wan(v): return '—' if v is None or pd.isna(v) else f'{v:,.0f}'
def pct(a, b): return f'{(a / b - 1) * 100:+.1f}%'

# ---------- 年度趨勢圖（江子翠：無車位／有車位不含車／有車位含車；板橋無車位作背景線） ----------
W, H, Lm, R, T, B = 560, 240, 40, 16, 26, 40
YMIN, YMAX = 40, 90
def X(y): return Lm + (y - 111) * (W - Lm - R) / 4
def Y(v): return T + (YMAX - v) * (H - T - B) / (YMAX - YMIN)
svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC" font-size="10">']
for v in range(YMIN, YMAX + 1, 10):
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e3e8ec" stroke-width="1"/>'
               f'<text x="{Lm-6}" y="{Y(v)+3:.1f}" text-anchor="end" fill="#7b8794">{v}</text>')
for y in range(111, 116):
    svg.append(f'<text x="{X(y):.1f}" y="{H-B+15}" text-anchor="middle" fill="#7b8794">{y}年</text>')
svg.append(f'<text x="{W-R}" y="{T-10}" text-anchor="end" fill="#7b8794" font-size="9">單位：萬元／坪（年度中位數）</text>')
# 本戶開價參考線
svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(L["單價"]):.1f}" y2="{Y(L["單價"]):.1f}" stroke="#C0392B" stroke-width="1.2" stroke-dasharray="2 3"/>'
           f'<text x="{Lm+4}" y="{Y(L["單價"])-4:.1f}" fill="#C0392B" font-size="9" font-weight="700">本戶開價 {L["單價"]:.1f}</text>')
series = [('江子翠_年度', '無車位中位', '#1F4E5F', '', '江子翠 無車位'),
          ('江子翠_年度', '不含車中位', '#C8963E', '', '江子翠 有車位（不含車）'),
          ('江子翠_年度', '含車中位', '#C8963E', '5 3', '江子翠 有車位（含車）'),
          ('板橋_年度', '無車位中位', '#9aa7b2', '2 3', '板橋全區 無車位')]
for i, (grp, col, color, dash, name) in enumerate(series):
    pts = [(r['年'], r[col]) for r in S[grp] if r[col] is not None]
    path = ' '.join(f'{"M" if j == 0 else "L"}{X(y):.1f},{Y(v):.1f}' for j, (y, v) in enumerate(pts))
    svg.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{2.4 if i < 3 else 1.6}" stroke-dasharray="{dash}"/>')
    for y, v in pts:
        svg.append(f'<circle cx="{X(y):.1f}" cy="{Y(v):.1f}" r="{3.2 if i < 3 else 2.2}" fill="{color}"/>')
        if i == 0:
            dy = -7 if i == 0 else 13
            svg.append(f'<text x="{X(y):.1f}" y="{Y(v)+dy:.1f}" text-anchor="middle" fill="{color}" font-size="9" font-weight="700">{v:.1f}</text>')
    lx = Lm + 6 + i * 128
    svg.append(f'<line x1="{lx}" x2="{lx+18}" y1="{H-9}" y2="{H-9}" stroke="{color}" stroke-width="2.4" stroke-dasharray="{dash}"/>'
               f'<text x="{lx+22}" y="{H-6}" fill="#4a5560" font-size="8.6">{name}</text>')
svg.append('</svg>')
chart = ''.join(svg)

# ---------- 年度表 ----------
def year_rows(grp):
    out = ''
    for r in S[grp]:
        out += (f'<tr><td>{r["年"]} 年{"（至10月）" if r["年"] == 115 else ""}</td>'
                f'<td class="num">{r["無車位n"]}</td><td class="num b">{f2(r["無車位中位"])}</td><td class="num">{wan(r["無車位總價"])}</td>'
                f'<td class="num">{r["有車位n"]}</td><td class="num">{f2(r["含車中位"])}</td><td class="num b">{f2(r["不含車中位"])}</td><td class="num">{wan(r["有車位總價"])}</td></tr>')
    return out
jz_rows, bq_rows = year_rows('江子翠_年度'), year_rows('板橋_年度')

# ---------- 本戶定位：同條件換算 ----------
A = L['建坪']
anchors = [
    ('同社區 10號7F（115/06）', '同棟正上方一層、同坪數、無車位', TWIN['單價'], TWIN['總價']),
    ('江子翠 無車位 30–40坪', f'近三年 {SIM["n"]} 筆，與本戶坪數最接近', SIM['單價中位'], SIM['單價中位'] * A),
    ('江子翠 無車位 全部', f'近三年 {JZN["n"]} 筆', JZN['net'], JZN['net'] * A),
    ('江子翠 有車位（不含車）', f'近三年 {JZP["n"]} 筆，扣除車位價後', JZP['net'], JZP['net'] * A),
    ('板橋全區 無車位', f'近三年 {BQ3["無車位"]["n"]} 筆', BQ3['無車位']['net'], BQ3['無車位']['net'] * A),
]
pos_rows = (f'<tr class="hl"><td>本戶 10號6F 開價</td><td>無車位・34.39 坪・主建物 27.65 坪</td>'
            f'<td class="num">{L["單價"]:.2f}</td><td class="num">{wan(L["總價"])}</td><td class="num">—</td></tr>')
for nm, why, up, tot in anchors:
    pos_rows += (f'<tr><td class="b">{nm}</td><td>{why}</td><td class="num">{up:.2f}</td>'
                 f'<td class="num">{wan(tot)}</td><td class="num b">{pct(L["總價"], tot)}</td></tr>')

# 坪效：主建物單價
MAIN_L = L['主建物單價']
MAIN_TWIN = TWIN['總價'] / L['主建物']
MAIN_JZ = JZ3['無車位主建物單價中位']
MAIN_BQ = BQ3['無車位主建物單價中位']

# ---------- 近三年江子翠明細 ----------
jz = df[(df['江子翠'] == 1) & (df['yr'] >= 113)].sort_values('交易日期', ascending=False)
def detail(g, park):
    out = ''
    for r in g.itertuples():
        same = r.同社區 == 1
        cls = ' class="hl"' if same else ''
        addr = r.門牌.replace('文化路二段', '文化路2段').replace('十', '十')
        if park:
            est = '*' if str(r.車位價來源).startswith('估算') else ''
            out += (f'<tr{cls}><td>{r.交易日期}</td><td>{addr}</td><td class="num">{r.屋齡}</td><td class="num">{wan(r.總價萬)}</td>'
                    f'<td class="num">{r.總面積坪:.2f}</td><td>{r.車位類別}</td><td class="num">{wan(r.車位價萬)}{est}</td>'
                    f'<td class="num">{r.含車單價:.2f}</td><td class="num b">{r.不含車單價:.2f}{est}</td></tr>')
        else:
            out += (f'<tr{cls}><td>{r.交易日期}</td><td>{addr}{"（同社區）" if same else ""}</td><td class="num">{r.屋齡}</td>'
                    f'<td class="num">{wan(r.總價萬)}</td><td class="num">{r.總面積坪:.2f}</td><td class="num">{r.主建物佔比*100:.1f}%</td>'
                    f'<td class="num b">{r.不含車單價:.2f}</td></tr>')
    return out
np_rows = detail(jz[jz['車位數'] == 0], False)
pk_rows = detail(jz[jz['車位數'] > 0], True)

# ---------- 房貸試算 ----------
RATE, YEARS, LTV = 0.022, 30, 0.8
loan = L['總價'] * LTV
r_m = RATE / 12
pay = loan * 10000 * r_m / (1 - (1 + r_m) ** (-YEARS * 12))
down = L['總價'] - loan

DISC = '永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號'
PHONE, LINE_ID, WEB = '0925-313-570', '@080akczk', 'sixhands-studio.netlify.app'
CONTACT = f'助哥 {PHONE}　｜　LINE {LINE_ID}　｜　{WEB}'
def foot(n):
    return (f'<div class="foot"><div>{DISC}<br><span class="ct">{CONTACT}</span></div>'
            f'<span>文化第王 銷售報告書　{n}</span></div>')

# 棟別配置示意（依樂居棟別圖重繪；本戶 10 號標示）
def block(x, y, t, me=False):
    fill, col = ('#C0392B', '#fff') if me else ('#fff', '#4a5560')
    return (f'<rect x="{x}" y="{y}" width="64" height="40" rx="6" fill="{fill}" stroke="#cfd8df"/>'
            f'<text x="{x+32}" y="{y+25}" text-anchor="middle" font-size="11" fill="{col}" font-weight="{700 if me else 400}">{t}</text>')
site = ['<svg viewBox="0 0 470 210" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC">',
        '<rect x="0" y="0" width="470" height="210" fill="#eef3f6"/>',
        '<rect x="20" y="22" width="440" height="8" fill="#e9c46a"/><text x="240" y="16" text-anchor="middle" font-size="10" fill="#4a5560">文化路二段182巷1弄</text>',
        '<rect x="20" y="178" width="440" height="8" fill="#e9c46a"/><text x="240" y="202" text-anchor="middle" font-size="10" fill="#4a5560">文化路二段182巷3弄</text>',
        '<rect x="8" y="22" width="8" height="164" fill="#e9c46a"/><text x="4" y="110" font-size="9" fill="#4a5560" writing-mode="tb">182巷</text>']
for x, top, bot in [(30, '2號', '3弄1號'), (100, '4號', '3弄3號'), (190, '8號', '6號／3弄5號'), (260, '10號', '3弄7・9號'), (380, '12號', '3弄11號')]:
    site.append(block(x, 44, top, top == '10號'))
    site.append(block(x, 124, bot))
site.append('<text x="292" y="100" text-anchor="middle" font-size="9" fill="#C0392B" font-weight="700">▲ 本戶棟別</text>')
site.append('</svg>')
site = ''.join(site)

html = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>文化第王 銷售報告書</title><style>
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
th.g2 {{ background: #8a6a2c; }}
td {{ padding: 4px 5px; border-bottom: 1px solid #e1e7eb; vertical-align: top; }}
tr:nth-child(even) td {{ background: #eef3f6; }}
tr.hl td {{ background: #C0392B !important; color: #fff; }}
.tight td, .tight th {{ padding: 2.6px 4px; font-size: 7.3pt; }}
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
.feat {{ display: flex; gap: 3.5mm; margin-bottom: 3.6mm; }}
.feat .no {{ font-family: "Noto Serif CJK TC", serif; font-size: 22pt; color: #C8963E; line-height: 1; min-width: 11mm; }}
.feat h3 {{ font-size: 11pt; color: #163a47; margin-bottom: 1mm; }}
.feat p {{ font-size: 8.5pt; line-height: 1.75; color: #33414c; }}
ul {{ margin-left: 4.5mm; }} li {{ font-size: 8.4pt; line-height: 1.8; margin-bottom: .5mm; }}
.photo {{ background: #e3eaef; padding: 1.8mm; border-radius: 2px; }}
.photo img {{ display: block; width: 100%; object-fit: cover; }}
.cap {{ font-size: 7pt; color: #7b8794; margin-top: 1.2mm; }}
.spec td:first-child {{ color: #8a6a2c; width: 24mm; white-space: nowrap; }}
.spec td {{ background: transparent !important; padding: 3.2px 4px; font-size: 8.3pt; }}
.two {{ display: flex; gap: 5mm; }} .two > div {{ flex: 1; min-width: 0; }}
</style></head><body>

<!-- P1 封面 -->
<div class="page" style="background:#102a33">
  <img src="{img('客廳.jpg')}" style="position:absolute;left:0;top:0;width:210mm;height:150mm;object-fit:cover">
  <div style="position:absolute;left:0;top:110mm;width:210mm;height:40mm;background:linear-gradient(180deg,rgba(16,42,51,0),#102a33)"></div>
  <div style="position:absolute;left:16mm;top:150mm;right:16mm;color:#fff">
    <div style="font-size:8pt;letter-spacing:.5em;color:#E3B66A">PROPERTY SALES REPORT</div>
    <div style="width:46mm;height:2px;background:#E3B66A;margin:5mm 0 6mm"></div>
    <div class="serif" style="font-size:11pt;color:#E3B66A;letter-spacing:.2em">新北市議會旁 · 捷運江子翠站步行圈</div>
    <h1 style="font-size:40pt;line-height:1.2;margin-top:2mm">文化第王</h1>
    <div class="serif" style="font-size:15pt;margin-top:2mm">買方銷售報告書 · 6 樓 三房兩衛</div>
    <div style="font-size:8.8pt;color:#b9cad3;margin-top:4mm;line-height:1.9">新北市板橋區文化路二段182巷1弄10號6樓<br>開價 {wan(L["總價"])} 萬　·　建坪 {A} 坪　·　公設比 9.2%　·　無車位</div>
    <div style="margin-top:8mm;border-top:1px solid #3b5b66;padding-top:5mm;display:flex;gap:8mm;align-items:flex-end">
      <div style="flex:1">
        <div style="font-size:7.6pt;color:#E3B66A;letter-spacing:.3em">核心結論</div>
        <div style="font-size:9.4pt;line-height:1.9;margin-top:2mm">
          同棟 7F 同坪數 115/06 成交 <b>{wan(TWIN["總價"])} 萬（{TWIN["單價"]:.1f} 萬/坪）</b>，本戶開價高出 {pct(L["總價"], TWIN["總價"])}。<br>
          江子翠無車位近三年中位 {JZN["net"]:.1f} 萬/坪；本戶公設僅 9.2%，<b>換算主建物單價只高 {pct(MAIN_L, MAIN_JZ)}</b>。<br>
          <span style="color:#E3B66A">同樣 34 坪權狀，主建物比一般大樓多約 {A*(L['主建物佔比']-JZ3['主建物佔比中位']):.0f} 坪。</span>
        </div>
      </div>
      <div class="qr" style="width:22mm"><img src="{img('QR_LINE.png')}"><div>加 LINE</div></div>
    </div>
  </div>
  <div style="position:absolute;left:16mm;bottom:8mm;font-size:7.2pt;color:#8fa6b1">資料：內政部實價登錄（板橋區・屋齡25–35年・3房2廳2衛，111/01–115/10，查詢 2026-10-09）　｜　{CONTACT}</div>
</div>

<!-- P2 物件總覽 -->
<div class="page"><div class="pad">
  <div class="eyebrow">01 · PROPERTY OVERVIEW</div>
  <div class="ttl">物件總覽</div>
  <div class="kpi">
    <div><div class="v">{wan(L["總價"])}</div><div class="u">萬元</div><div class="l">開價（無車位）</div></div>
    <div><div class="v">{A}</div><div class="u">坪</div><div class="l">權狀建坪</div></div>
    <div><div class="v">31.22</div><div class="u">坪</div><div class="l">主建物＋附屬（室內可用）</div></div>
    <div><div class="v">{L["單價"]:.2f}</div><div class="u">萬/坪</div><div class="l">建坪單價</div></div>
    <div><div class="v">9.2%</div><div class="u">公設比</div><div class="l">社區登錄 9.10%</div></div>
  </div>
  <div class="two">
    <div>
      <h3 class="h">本戶資料</h3>
      <table class="spec">
        <tr><td>地址</td><td>新北市板橋區文化路二段182巷1弄10號6樓</td></tr>
        <tr><td>樓層／格局</td><td>6F／19F・3房2廳2衛・座向朝南</td></tr>
        <tr><td>坪數</td><td>主建物 27.65＋附屬 3.57＋公設 3.17＝{A} 坪</td></tr>
        <tr><td>車位</td><td>無</td></tr>
        <tr><td>管理費</td><td>2,380 元／月（約 69 元／坪）・管理員（警衛）</td></tr>
        <tr><td>建築完成</td><td>1995/10/05（屋齡約 31 年）</td></tr>
        <tr><td>結構</td><td>鋼筋混凝土（RC）</td></tr>
        <tr><td>面前道路</td><td>12 米</td></tr>
        <tr><td>現況</td><td>自用</td></tr>
        <tr><td>合約編號</td><td>YA0023949</td></tr>
      </table>
    </div>
    <div>
      <h3 class="h">社區資料</h3>
      <table class="spec">
        <tr><td>社區</td><td>文化第王（實登簡稱「文化遠見」）</td></tr>
        <tr><td>規模</td><td>總戶數 209 戶・19 層・2 梯 6 戶</td></tr>
        <tr><td>土地分區</td><td>商業區</td></tr>
        <tr><td>建設／營造</td><td>至合建設／合興建設</td></tr>
        <tr><td>建築設計</td><td>翁清源建築師事務所</td></tr>
        <tr><td>學區</td><td>莒光國小・江翠國中</td></tr>
      </table>
      <h3 class="h">棟別配置示意</h3>
      {site}
      <div class="cap">依社區棟別圖重繪，非比例尺；北向約朝左。</div>
    </div>
  </div>
  <div class="note" style="margin-top:4mm"><b>低公設是本戶最大的價值。</b>近三年江子翠同條件大樓的主建物佔比中位約 {JZ3["主建物佔比中位"]*100:.0f}%，本戶為 {L["主建物佔比"]*100:.1f}%。同樣 {A} 坪權狀，一般大樓主建物約 {A*JZ3['主建物佔比中位']:.1f} 坪，本戶有 {L['主建物']} 坪，多出約 {A*(L['主建物佔比']-JZ3['主建物佔比中位']):.1f} 坪；加上陽台，室內可用 31.22 坪。</div>
</div>{foot(2)}</div>

<!-- P3 格局 -->
<div class="page"><div class="pad">
  <div class="eyebrow">02 · FLOOR PLAN</div>
  <div class="ttl">格局與室內</div>
  <div class="sub">方正三房，客廳與兩間臥室分處兩側，兩套衛浴；前後雙陽台，廚房有對外窗。</div>
  <div class="photo" style="background:#fff"><img src="{img('格局圖.png')}" style="height:118mm;object-fit:contain"></div>
  <div class="cap">※ 示意圖，實際格局與尺寸以現場丈量為準。</div>
  <div class="photo" style="margin-top:4mm"><img src="{img('客廳.jpg')}" style="height:70mm"></div>
  <div class="cap">客廳現況：大面落地窗通陽台，採光良好；吊扇燈、分離式冷氣。</div>
  <div class="two" style="margin-top:3mm">
    <div class="feat"><div class="no">01</div><div><h3>大客廳</h3><p>客餐廳整併成一個大空間，家具好擺，也能隔出書房或工作區。</p></div></div>
    <div class="feat"><div class="no">02</div><div><h3>雙衛浴・雙陽台</h3><p>兩套衛浴減少早上排隊；前陽台曬衣、後陽台接廚房。</p></div></div>
  </div>
</div>{foot(3)}</div>

<!-- P4 區位 -->
<div class="page"><div class="pad">
  <div class="eyebrow">03 · LOCATION</div>
  <div class="ttl">區位與生活機能</div>
  <div class="sub">位於文化路二段與 182 巷口內側，新北市議會正後方；步行約 3 分鐘到捷運板南線江子翠站。</div>
  <div class="photo"><img src="{img('空拍_區位.jpg')}" style="height:84mm"></div>
  <div class="cap">空拍示意：紅色標記為本社區，文化路二段（藍線為捷運板南線）。</div>
  <div class="two" style="margin-top:4mm">
    <div><div class="photo"><img src="{img('地圖_位置.jpg')}" style="height:62mm"></div><div class="cap">位置圖：北側為江子翠站，西側為板橋石雕公園。</div></div>
    <div>
      <table class="spec">
        <tr><td>捷運</td><td>板南線江子翠站，步行約 3 分鐘</td></tr>
        <tr><td>地標</td><td>新北市議會旁，位置好找</td></tr>
        <tr><td>學校</td><td>莒光國小、江翠國中</td></tr>
        <tr><td>醫療</td><td>板橋聯合醫院</td></tr>
        <tr><td>公園</td><td>板橋石雕公園、農村公園</td></tr>
        <tr><td>生活</td><td>江子翠商圈、市場、圖書館</td></tr>
        <tr><td>使用彈性</td><td>商業區・登記用途商業用，可自住或作工作室、事務所（依謄本與相關法規）</td></tr>
      </table>
    </div>
  </div>
</div>{foot(4)}</div>

<!-- P5 年度行情 -->
<div class="page"><div class="pad">
  <div class="eyebrow">04 · MARKET TREND</div>
  <div class="ttl">年度行情：有車位 vs 無車位</div>
  <div class="sub">條件與本戶相同：板橋區、屋齡 25–35 年、3房2廳2衛、住宅大樓（排除 1 樓、頂樓加蓋、夾層戶與特殊關係交易）。
  「江子翠」只取捷運站步行圈路段：文化路二段、莊敬路、雙十路二／三段、文聖街、民生路三段百號內等。</div>
  {chart}
  <h3 class="h">江子翠生活圈（{S["江子翠母體"]} 筆）</h3>
  <table>
    <tr><th rowspan="2">年度</th><th colspan="3">無車位（同本戶）</th><th class="g2" colspan="4">有車位</th></tr>
    <tr><th>筆數</th><th>單價中位</th><th>總價中位</th><th class="g2">筆數</th><th class="g2">含車單價</th><th class="g2">不含車單價</th><th class="g2">總價中位</th></tr>
    {jz_rows}
  </table>
  <h3 class="h">板橋全區（{S["大樓母體"]} 筆）</h3>
  <table>
    <tr><th rowspan="2">年度</th><th colspan="3">無車位</th><th class="g2" colspan="4">有車位</th></tr>
    <tr><th>筆數</th><th>單價中位</th><th>總價中位</th><th class="g2">筆數</th><th class="g2">含車單價</th><th class="g2">不含車單價</th><th class="g2">總價中位</th></tr>
    {bq_rows}
  </table>
  <div class="note" style="margin-top:3.5mm">江子翠無車位單價從 111–112 年約 62 萬，113 年起站上 72–76 萬，比板橋全區高約三成，捷運站步行圈的價差明顯。
  江子翠單一年度筆數僅 4–15 筆，判斷行情以近三年合計中位為準（無車位 {JZN['n']} 筆、有車位 {JZP['n']} 筆）。單價單位：萬元／坪；不含車＝（總價－車位價）÷（總面積－車位面積）。</div>
</div>{foot(5)}</div>

<!-- P6 本戶定位 -->
<div class="page"><div class="pad">
  <div class="eyebrow">05 · PRICE POSITIONING</div>
  <div class="ttl">本戶價格定位</div>
  <div class="sub">把各組成交單價乘上本戶建坪 {A} 坪，換算成「如果照這個行情，本戶值多少」，再跟開價比較。全部取近三年（113–115）中位數。</div>
  <table>
    <tr><th>比較對象</th><th>說明</th><th>單價（萬/坪）</th><th>換算本戶總價（萬）</th><th>開價差距</th></tr>
    {pos_rows}
  </table>
  <h3 class="h">換算主建物單價：低公設的價差</h3>
  <div class="kpi">
    <div><div class="v">{MAIN_L:.1f}</div><div class="u">萬／主建物坪</div><div class="l">本戶開價</div></div>
    <div><div class="v">{MAIN_TWIN:.1f}</div><div class="u">萬／主建物坪</div><div class="l">同棟 7F 成交</div></div>
    <div><div class="v">{MAIN_JZ:.1f}</div><div class="u">萬／主建物坪</div><div class="l">江子翠 無車位中位</div></div>
    <div><div class="v">{MAIN_BQ:.1f}</div><div class="u">萬／主建物坪</div><div class="l">板橋 無車位中位</div></div>
  </div>
  <div class="note">江子翠同條件大樓的權狀裡，主建物以外的公設與附屬約佔三成，本戶公設只有 9.2%。用建坪算，本戶開價比江子翠無車位中位高 {pct(L["單價"], JZN["net"])}；
  改用主建物算，差距只剩 {pct(MAIN_L, MAIN_JZ)}。買的是室內空間，這個差距才是真正的價差。</div>
  <h3 class="h">同社區成交紀錄（111–115）</h3>
  <table>
    <tr><th>日期</th><th>門牌</th><th>總價（萬）</th><th>坪數</th><th>單價</th><th>車位</th><th>說明</th></tr>
    {''.join(f'<tr><td>{r["日期"]}</td><td>{r["門牌"].replace("板橋區", "")}</td><td class="num">{wan(r["總價"])}</td><td class="num">{r["坪數"]:.2f}</td><td class="num">{r["單價"]:.2f}</td><td class="num">{r["車位"]}</td><td>{"特殊關係交易，不列入行情" if "特殊關係" in r["備註"] else r["備註"].rstrip(";").replace(";", "、")}</td></tr>' for r in S["同社區"])}
  </table>
  <div class="warn" style="margin-top:3.5mm">樣本提醒：符合 3房2廳2衛條件的同社區成交，五年內只有 1 筆有效紀錄（10號7F）。同社區其他格局的成交未納入本次查詢，議價前可再補查。</div>
</div>{foot(6)}</div>

<!-- P7 明細 -->
<div class="page"><div class="pad">
  <div class="eyebrow">06 · TRANSACTIONS</div>
  <div class="ttl">江子翠近三年成交明細</div>
  <div class="sub">113/01–115/10，條件同前。紅底為同社區；* 為車位價未拆分，以同類別車位中位數估算。</div>
  <h3 class="h" style="margin-top:0">無車位（{len(jz[jz["車位數"] == 0])} 筆）</h3>
  <table class="tight">
    <tr><th>日期</th><th>門牌</th><th>屋齡</th><th>總價</th><th>坪數</th><th>主建物佔比</th><th>單價</th></tr>
    {np_rows}
  </table>
</div>{foot(7)}</div>

<div class="page"><div class="pad">
  <div class="eyebrow">06 · TRANSACTIONS</div>
  <div class="ttl">江子翠近三年成交明細（有車位）</div>
  <div class="sub">有車位物件並列含車與不含車單價；* 為車位價未拆分，以同類別車位中位數估算。</div>
  <h3 class="h" style="margin-top:0">有車位（{len(jz[jz["車位數"] > 0])} 筆）</h3>
  <table class="tight">
    <tr><th class="g2">日期</th><th class="g2">門牌</th><th class="g2">屋齡</th><th class="g2">總價</th><th class="g2">坪數</th><th class="g2">車位</th><th class="g2">車位價</th><th class="g2">含車單價</th><th class="g2">不含車單價</th></tr>
    {pk_rows}
  </table>
</div>{foot(8)}</div>

<!-- P8 購屋試算 -->
<div class="page"><div class="pad">
  <div class="eyebrow">07 · BUYER'S GUIDE</div>
  <div class="ttl">購屋試算與注意事項</div>
  <div class="kpi">
    <div><div class="v">{wan(L["總價"])}</div><div class="u">萬元</div><div class="l">開價</div></div>
    <div><div class="v">{wan(down)}</div><div class="u">萬元</div><div class="l">自備款（兩成）</div></div>
    <div><div class="v">{wan(loan)}</div><div class="u">萬元</div><div class="l">貸款（八成）</div></div>
    <div><div class="v">{pay/10000:.1f}</div><div class="u">萬元／月</div><div class="l">本息攤還</div></div>
  </div>
  <div class="note">試算假設：貸款八成、年利率 {RATE*100:.1f}%、{YEARS} 年本息平均攤還，每月約 {pay:,.0f} 元。另需預留契稅、代書、仲介服務費與裝修預算。實際成數、利率與年限依銀行鑑價與個人條件核定。</div>
  <h3 class="h">買方看屋重點</h3>
  <ul>
    <li><b>用途登記：</b>土地為商業區，同社區實登用途為「商業用」。請以建物謄本為準，並向銀行確認貸款成數、年限與房屋稅率。</li>
    <li><b>屋齡 31 年：</b>部分銀行會依屋齡縮短貸款年限，建議先送件預審。可索取管委會修繕紀錄（外牆、管線、電梯）。</li>
    <li><b>無車位：</b>附近可租月租車位，看屋時可一併詢問社區或周邊行情。</li>
    <li><b>增建與現況：</b>同棟 7F 成交備註有陽台外推與增建。本戶現況以現場與不動產說明書為準。</li>
    <li><b>管理費：</b>2,380 元／月，約 69 元／坪，在江子翠大樓中屬偏低。</li>
  </ul>
  <h3 class="h">為什麼值得看</h3>
  <ul>
    <li>捷運江子翠站步行約 3 分鐘，雙北通勤方便。</li>
    <li>公設比 9.2%，34 坪權狀有 31 坪主建物＋陽台，坪效佳。</li>
    <li>同棟 7F 剛在 115/06 以 {wan(TWIN["總價"])} 萬成交，價格有清楚依據。</li>
    <li>商業區，可自住也可作工作室或事務所。</li>
  </ul>
  <div style="margin-top:6mm;position:relative;background:#fff;border:1px solid #dde4e9;padding:5mm 36mm 5mm 6mm;font-size:7.8pt;line-height:1.8;color:#4a5560">
    <div class="b" style="font-size:9.6pt;color:#163a47;margin-bottom:1.5mm">免責聲明</div>
    本報告書為不動產經紀業務之行銷參考資料，非不動產估價師出具之估價報告。行情統計與試算係依公開實價登錄資料整理，不構成價格保證、投資建議或獲利承諾。實際面積、用途、產權及使用現況，以權狀、謄本、不動產說明書及買賣契約記載為準。買方應自行或委託專業人士查證後再做決定。
    <div style="position:absolute;right:7mm;top:50%;margin-top:-11mm;width:22mm;height:22mm;border:2.5px solid #b3261e;border-radius:50%;color:#b3261e;display:flex;align-items:center;justify-content:center;text-align:center;font-family:'Noto Serif CJK TC',serif;font-size:8pt;font-weight:700;line-height:1.3;transform:rotate(-12deg)">僅供<br>參考</div>
  </div>
  <div style="margin-top:6mm;display:flex;align-items:center;justify-content:center;gap:7mm;background:#163a47;padding:5mm 7mm;border-radius:2px">
    <div style="color:#fff">
      <div style="font-size:7.4pt;color:#E3B66A;letter-spacing:.3em">預約帶看・行情諮詢</div>
      <div class="serif" style="font-size:16pt;font-weight:700;margin-top:1mm">助哥　<span style="color:#F0D9A4">{PHONE}</span></div>
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
    b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    pg = b.new_page()
    pg.goto(OUT_HTML.resolve().as_uri())
    pg.wait_for_timeout(500)
    pg.pdf(path=str(OUT_PDF), prefer_css_page_size=True, print_background=True)
    b.close()
print('PDF  →', OUT_PDF)
