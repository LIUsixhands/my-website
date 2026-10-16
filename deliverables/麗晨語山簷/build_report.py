"""麗晨語山簷 7F之3 銷售報告書（給買方）：讀 summary.json → 產 HTML → Playwright 輸出 PDF。
口徑：房屋單價一律扣車位（車位價、車位坪數逐案取自實登車位分頁）；本戶車位以 115 年交屋後每席中位估。
對外聯絡只放助哥（同事案件，售資專員姓名不上）。棟別圖、樓層配置圖皆依原圖重繪（SVG）。"""
import base64, json
from pathlib import Path

HERE = Path(__file__).parent
OUT_HTML = HERE / '麗晨語山簷_銷售報告書.html'
OUT_PDF = HERE / '麗晨語山簷_銷售報告書.pdf'
S = json.load(open(HERE / 'summary.json'))
L, TX = S['本戶'], S['成交']
H3, AF, PRE, TY, PK = S['近三年'], S['交屋後'], S['預售'], S['戶型'], S['車位每席']
SAME_C = next(r for r in TX if r['戶型'] == 'C' and r['波段'] == '交屋後')          # 13F之3 115/01
NEAR_A = next(r for r in TX if r['日期'] == '115/06/26')                         # 8F之1
SELF = next(r for r in TX if r['戶型'] == 'C' and r['樓層'] == 7)
C_PRE_WAVE = [r for r in TX if r['戶型'] == 'C' and r['日期'][:6] in ('110/08', '110/09', '110/10')]
TARGET = 4450
T_UP = (TARGET - L['車位估']) / L['房屋坪']
YT = 'https://www.youtube.com/shorts/UrZ5fMJqZtA'

def img(name):
    mime = 'image/png' if name.endswith('png') else 'image/jpeg'
    return f"data:{mime};base64,{base64.b64encode((HERE / name).read_bytes()).decode()}"
def wan(v): return '—' if v is None else f'{v:,.0f}'
def house(up): return up * L['房屋坪'] + L['車位估']

DISC = '永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號'
PHONE, LINE_ID, WEB = '0925-313-570', '@080akczk', 'sixhands.tw'
CONTACT = f'助哥 {PHONE}　｜　LINE {LINE_ID}　｜　{WEB}'
def foot(n):
    return (f'<div class="foot"><div>{DISC}<br><span class="ct">{CONTACT}</span></div>'
            f'<span>麗晨語山簷 銷售報告書　{n}</span></div>')

# ---------- 棟別配置圖（依樂居棟別圖重繪，北朝上） ----------
def bk(x, y, w, h, t, sub, fill='#fff', col='#163a47', stroke='#cfd8df'):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
            f'<text x="{x+w/2}" y="{y+h/2-2}" text-anchor="middle" font-size="17" font-weight="700" fill="{col}">{t}</text>'
            f'<text x="{x+w/2}" y="{y+h/2+15}" text-anchor="middle" font-size="9.5" fill="{col}">{sub}</text>')
site = ['<svg viewBox="0 0 420 300" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC">',
        '<rect width="420" height="300" fill="#eef3f6"/>',
        '<rect x="42" y="14" width="10" height="276" fill="#e9c46a"/>',
        '<text x="30" y="150" font-size="10.5" fill="#4a5560" writing-mode="tb" letter-spacing="3">河南路四段</text>',
        '<path d="M42 262 L410 276 L410 286 L42 272 Z" fill="#e9c46a"/>',
        '<text x="250" y="296" text-anchor="middle" font-size="10.5" fill="#4a5560">大業路</text>',
        bk(222, 22, 92, 66, 'B 戶', '63 坪・556號-2'),
        '<rect x="222" y="94" width="92" height="66" rx="8" fill="#e9c46a" stroke="#d9b24f"/>',
        '<text x="268" y="124" text-anchor="middle" font-size="12" font-weight="700" fill="#163a47">梯廳</text>',
        '<text x="268" y="140" text-anchor="middle" font-size="9" fill="#163a47">雙梯・無走廊</text>',
        bk(222, 166, 92, 66, 'A 戶', '70 坪・556號-1'),
        bk(110, 94, 106, 66, 'C 戶', '55 坪・556號-3', '#C0392B', '#fff', '#C0392B'),
        '<text x="163" y="178" text-anchor="middle" font-size="9.5" font-weight="700" fill="#C0392B">▲ 本戶 7 樓之 3</text>',
        '<g transform="translate(372,48)"><circle r="20" fill="#fff" stroke="#C8963E" stroke-width="2"/>'
        '<path d="M0 -14 L6 6 L0 2 L-6 6 Z" fill="#163a47"/><text y="16" text-anchor="middle" font-size="9" fill="#163a47">北</text></g>',
        '</svg>']
site = ''.join(site)

# ---------- 樓層配置圖（依建商樓層平面重繪，北朝上；示意） ----------
plan = ['<svg viewBox="0 0 520 400" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC">',
        '<rect width="520" height="400" fill="#f4f7f2"/>',
        '<defs><pattern id="g" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#dfeedd"/>'
        '<circle cx="4" cy="4" r="1.3" fill="#9cc49a"/></pattern></defs>',
        # 外圈綠帶（複層植生牆＋維護通道）
        '<rect x="70" y="20" width="400" height="340" rx="10" fill="url(#g)" stroke="#9cc49a"/>',
        # B（北）
        '<rect x="250" y="36" width="200" height="98" fill="#f1dcd9" stroke="#b9a29e"/>',
        '<text x="350" y="82" text-anchor="middle" font-size="18" font-weight="700" fill="#8a5b55">B</text>',
        '<text x="350" y="100" text-anchor="middle" font-size="10" fill="#8a5b55">63 坪・3 房</text>',
        # 梯廳
        '<rect x="250" y="140" width="200" height="88" fill="#e6e1d5" stroke="#b8ae96"/>',
        '<text x="350" y="178" text-anchor="middle" font-size="12" font-weight="700" fill="#6b5f45">梯廳</text>',
        '<text x="350" y="195" text-anchor="middle" font-size="9.5" fill="#6b5f45">雙電梯・雙安全梯</text>',
        # A（南）
        '<rect x="250" y="234" width="200" height="110" fill="#f6efc9" stroke="#c9bc80"/>',
        '<text x="350" y="284" text-anchor="middle" font-size="18" font-weight="700" fill="#7a6a22">A</text>',
        '<text x="350" y="302" text-anchor="middle" font-size="10" fill="#7a6a22">70 坪・4 房</text>',
        # C（西）本戶
        '<rect x="88" y="96" width="156" height="178" fill="#C0392B" stroke="#8e2a20" stroke-width="2"/>',
        '<text x="166" y="170" text-anchor="middle" font-size="22" font-weight="700" fill="#fff">C</text>',
        '<text x="166" y="190" text-anchor="middle" font-size="10.5" fill="#fff">本戶・55 坪・3 房</text>',
        '<text x="166" y="206" text-anchor="middle" font-size="9.5" fill="#fbd9d4">室內 37.05 坪</text>',
        '<path d="M244 184 L250 184" stroke="#8e2a20" stroke-width="6"/>',
        # 環繞走道（虛線）
        '<rect x="78" y="86" width="176" height="198" fill="none" stroke="#2E7D4F" stroke-width="2" stroke-dasharray="5 4"/>',
        '<text x="166" y="298" text-anchor="middle" font-size="9.5" fill="#2E7D4F" font-weight="700">綠廊環繞（權狀外維護通道）</text>',
        # 三面採光箭頭
        '<g fill="#C8963E" font-size="9.5" font-weight="700">'
        '<path d="M166 52 L160 66 L172 66 Z"/><text x="166" y="46" text-anchor="middle">北面採光</text>'
        '<path d="M30 185 L44 179 L44 191 Z"/><text x="22" y="170" text-anchor="middle">西面</text><text x="22" y="182" text-anchor="middle" font-size="8.5">（河南路）</text>'
        '<path d="M166 330 L160 316 L172 316 Z"/><text x="166" y="344" text-anchor="middle">南面採光</text></g>',
        '<g transform="translate(486,40)"><circle r="18" fill="#fff" stroke="#C8963E" stroke-width="2"/>'
        '<path d="M0 -12 L5 5 L0 2 L-5 5 Z" fill="#163a47"/><text y="14" text-anchor="middle" font-size="8.5" fill="#163a47">北</text></g>',
        '<text x="270" y="388" text-anchor="middle" font-size="9" fill="#7b8794">每層三戶・C 戶三面臨綠帶；示意圖非比例尺，實際以使照竣工圖及現場為準</text>',
        '</svg>']
plan = ''.join(plan)

# ---------- 本戶格局圖（依售屋格局圖重繪，北朝上；示意） ----------
def room(x, y, w, h, t, fill='#fff', fs=13, col='#163a47'):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="#4a5560" stroke-width="2"/>'
            f'<text x="{x+w/2}" y="{y+h/2+4}" text-anchor="middle" font-size="{fs}" font-weight="700" fill="{col}">{t}</text>')
def door(x, y, w, h): return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fff"/>'
unit = ['<svg viewBox="0 0 500 470" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC">',
        '<rect width="500" height="470" fill="#fff"/>',
        '<defs><pattern id="wd" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(90)">'
        '<rect width="6" height="6" fill="#e4efe0"/><line x1="0" y1="0" x2="0" y2="6" stroke="#9cc49a" stroke-width="1.4"/></pattern></defs>',
        # 環繞綠廊（北、西、南）
        '<path d="M50 40 H410 V70 H80 V410 H410 V440 H50 Z" fill="url(#wd)" stroke="#7aa978" stroke-width="1.2"/>',
        '<rect x="18" y="200" width="32" height="96" fill="url(#wd)" stroke="#7aa978" stroke-width="1.2"/>',
        '<text x="34" y="252" text-anchor="middle" font-size="11" fill="#2E7D4F" font-weight="700" writing-mode="tb">陽台</text>',
        room(80, 70, 150, 110, '臥室'), room(230, 70, 120, 110, '臥室'), room(350, 70, 90, 110, '浴廁', '#eef3f6', 12),
        room(80, 180, 190, 140, '客廳', '#fbf3e2', 17), room(270, 180, 100, 140, '餐廳', '#fbf3e2', 14),
        room(370, 180, 70, 70, '玄關', '#fff', 12), room(370, 250, 70, 90, '廚房', '#fff', 12),
        room(80, 320, 180, 90, '主臥室', '#fff', 14), room(260, 320, 70, 90, '浴廁', '#eef3f6', 12),
        room(330, 320, 40, 90, '', '#fff'), room(370, 340, 70, 70, '陽台', '#e4efe0', 11, '#2E7D4F'),
        # 開口（門）
        door(140, 178, 34, 4), door(290, 178, 30, 4), door(368, 120, 4, 30), door(230, 318, 30, 4),
        door(268, 318, 26, 4), door(78, 222, 4, 52), door(388, 338, 30, 4),
        # 入口
        '<path d="M488 215 L462 205 L462 225 Z" fill="#C0392B"/><text x="476" y="245" text-anchor="middle" font-size="10" fill="#C0392B" font-weight="700">入口</text>',
        '<rect x="438" y="196" width="4" height="36" fill="#fff"/>',
        '<text x="245" y="58" text-anchor="middle" font-size="10" fill="#2E7D4F">環繞綠廊（權狀外維護通道）</text>',
        '<text x="245" y="430" text-anchor="middle" font-size="10" fill="#2E7D4F">環繞綠廊</text>',
        '<g transform="translate(466,40)"><circle r="16" fill="#fff" stroke="#C8963E" stroke-width="2"/>'
        '<path d="M0 -11 L5 5 L0 2 L-5 5 Z" fill="#163a47"/><text y="13" text-anchor="middle" font-size="8" fill="#163a47">北</text></g>',
        '<text x="250" y="462" text-anchor="middle" font-size="9" fill="#7b8794">3房2廳2衛・示意圖非比例尺，實際以現況及竣工圖為準</text>',
        '</svg>']
unit = ''.join(unit)

# ---------- 社區歷年成交圖（房屋單價，依戶型分色） ----------
W, H, Lm, R, T, B = 560, 290, 40, 16, 24, 40
X0, X1, YMIN, YMAX = 110.5, 116.6, 40, 82
def X(t): return Lm + (t - X0) * (W - Lm - R) / (X1 - X0)
def Y(v): return T + (YMAX - v) * (H - T - B) / (YMAX - YMIN)
def tt(d): y, m, _ = d.split('/'); return int(y) + (int(m) - .5) / 12
svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC" font-size="10">']
for v in range(YMIN, YMAX + 1, 10):
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e3e8ec"/>'
               f'<text x="{Lm-6}" y="{Y(v)+3:.1f}" text-anchor="end" fill="#7b8794">{v}</text>')
for y in range(111, 116):
    svg.append(f'<text x="{X(y):.1f}" y="{H-B+14}" text-anchor="middle" fill="#7b8794" font-size="9">{y}</text>')
svg.append(f'<rect x="{X(113+6.5/12):.1f}" y="{T}" width="1" height="{H-T-B}" fill="#9aa7b2"/>'
           f'<text x="{X(113+6.5/12)+4:.1f}" y="{T+10}" fill="#7b8794" font-size="8.6">113/07 使照・交屋</text>')
svg.append(f'<text x="{W-R}" y="{T-10}" text-anchor="end" fill="#7b8794" font-size="9">單位：萬元／坪（房屋單價，已扣車位）</text>')
for v, c, lab, dy in [(L['單價'], '#C0392B', f'本戶開價 {L["單價"]:.1f}', -4), (T_UP, '#2E7D4F', f'建議成交參考 {T_UP:.1f}（{TARGET:,} 萬）', 11)]:
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{c}" stroke-width="1.2" stroke-dasharray="3 3"/>'
               f'<text x="{Lm+4}" y="{Y(v)+dy:.1f}" fill="{c}" font-size="9" font-weight="700">{lab}</text>')
STY = {'A': ('#C8963E', 'A 戶 70 坪・4 房'), 'B': ('#9aa7b2', 'B 戶 63 坪・3 房'), 'C': ('#1F4E5F', 'C 戶 55 坪・3 房（同本戶）')}
for r in TX:
    c, _ = STY[r['戶型']]
    svg.append(f'<circle cx="{X(tt(r["日期"])):.1f}" cy="{Y(r["單價"]):.1f}" r="{4.4 if r["戶型"] == "C" else 3.6}" fill="{c}" stroke="#fff" stroke-width="1"/>')
# 交屋後逐筆標註：右側一欄，依單價排序、拉開間距，避免重疊
lab, last = [], None
for r in sorted([r for r in TX if r['波段'] == '交屋後'], key=lambda r: -r['單價']):
    y = Y(r['單價']) + 3 if last is None else max(Y(r['單價']) + 3, last + 11)
    lab.append((r, y)); last = y
LX = X(116.05)
for r, y in lab:
    c, _ = STY[r['戶型']]
    svg.append(f'<line x1="{X(tt(r["日期"])) + 4:.1f}" y1="{Y(r["單價"]):.1f}" x2="{LX - 2:.1f}" y2="{y - 3:.1f}" stroke="{c}" stroke-width=".6"/>'
               f'<text x="{LX:.1f}" y="{y:.1f}" fill="{c}" font-size="8.4" font-weight="700">{r["戶型"]} {r["樓層"]}F {r["單價"]:.1f}</text>')
for i, k in enumerate('CAB'):
    c, name = STY[k]; lx = Lm + 4 + i * 160
    svg.append(f'<circle cx="{lx+6}" cy="{H-10}" r="4" fill="{c}"/><text x="{lx+14}" y="{H-7}" fill="#4a5560" font-size="8.6">{name}</text>')
svg.append('</svg>')
chart = ''.join(svg)

tx_rows = ''
for r in reversed(TX):
    cls = ' class="hl"' if r is SAME_C else ''
    tx_rows += (f'<tr{cls}><td>{r["日期"]}</td><td>{r["戶型"]}</td><td class="num">{r["樓層"]}F</td><td class="num">{wan(r["總價"])}</td>'
                f'<td class="num">{r["坪數"]:.2f}</td><td class="num">{r["車位"] or "—"}</td><td class="num">{wan(r["車位價"]) if r["車位"] else "—"}</td>'
                f'<td class="num b">{r["單價"]:.2f}</td><td class="num">{r["含車單價"]:.2f}</td><td>{r["波段"]}{"・" + r["備註"] if r["備註"] else ""}</td></tr>')
yr_rows = ''.join(f'<tr><td>{r["年"]} 年{"（至10月）" if r["年"] == 115 else ""}</td><td class="num">{r["n"]}</td>'
                  f'<td class="num b">{r["不含車中位"]:.2f}</td><td class="num">{r["含車中位"]:.2f}</td></tr>' for r in S['年度'])
def after(t): return f'{t["交屋後中位"]:.2f}（n={t["交屋後n"]}）' if t['交屋後n'] else '尚無'
ty_rows = ''.join(f'<tr{" class=hl" if k == "C" else ""}><td>{k} 戶</td><td class="num">{TY[k]["房屋坪"]:.2f}</td><td class="num">{TY[k]["n"]}</td>'
                  f'<td class="num">{TY[k]["預售中位"]:.2f}</td><td class="num b">{after(TY[k])}</td></tr>'
                  for k in 'CAB')

# ---------- 價格分析 ----------
anchors = [
    ('同型 C 戶 13F', f'115/01 交屋後成交 {wan(SAME_C["總價"])} 萬（無車位），同為 55.96 坪房屋', SAME_C['單價']),
    ('近鄰 A 戶 8F', f'115/06 成交 {wan(NEAR_A["總價"])} 萬（1 車），樓層與本戶相近', NEAR_A['單價']),
    ('115 年交屋後中位', f'{AF["n"]} 筆（A 戶 5 筆、C 戶 1 筆）', AF['net']),
    ('近三年中位（113–115）', f'{H3["n"]} 筆，含 113/05 預售末段 2 筆', H3['net']),
]
pos_rows = (f'<tr class="hl"><td>本戶開價</td><td>7F・C 戶・房屋 {L["房屋坪"]} 坪＋雙坡道平面</td><td class="num">{L["單價"]:.2f}</td><td class="num">{wan(L["總價"])}</td></tr>'
            f'<tr style="font-weight:700"><td style="background:#e4f1e8;color:#2E7D4F">建議成交參考</td><td style="background:#e4f1e8;color:#2E7D4F">同型 13F 再依樓層差修正</td>'
            f'<td class="num" style="background:#e4f1e8;color:#2E7D4F">{T_UP:.2f}</td><td class="num" style="background:#e4f1e8;color:#2E7D4F">{TARGET:,}</td></tr>')
for nm, why, up in anchors:
    pos_rows += f'<tr><td class="b">{nm}</td><td>{why}</td><td class="num">{up:.2f}</td><td class="num">{wan(house(up))}</td></tr>'
lo_f, hi_f = C_PRE_WAVE[0], C_PRE_WAVE[-1]
c_wave = sorted(C_PRE_WAVE, key=lambda r: r['樓層'])

RATE, YEARS, LTV = 0.022, 30, 0.8
loan = TARGET * LTV
r_m = RATE / 12
pay = loan * 10000 * r_m / (1 - (1 + r_m) ** (-YEARS * 12))
down = TARGET - loan

html = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>麗晨語山簷 銷售報告書</title><style>
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
tr.hl td {{ background: #C0392B !important; color: #fff; }}
.xs td, .xs th {{ padding: 2.2px 4px; font-size: 7.2pt; }}
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
.feat {{ display: flex; gap: 3.5mm; margin-bottom: 3.2mm; }}
.feat .no {{ font-family: "Noto Serif CJK TC", serif; font-size: 20pt; color: #C8963E; line-height: 1; min-width: 10mm; }}
.feat h3 {{ font-size: 10.6pt; color: #163a47; margin-bottom: .8mm; }}
.feat p {{ font-size: 8.3pt; line-height: 1.7; color: #33414c; }}
ul {{ margin-left: 4.5mm; }} li {{ font-size: 8.4pt; line-height: 1.8; margin-bottom: .5mm; }}
.photo {{ background: #e3eaef; padding: 1.5mm; border-radius: 2px; }}
.photo img {{ display: block; width: 100%; object-fit: cover; }}
.cap {{ font-size: 7pt; color: #7b8794; margin-top: 1.2mm; }}
.spec td:first-child {{ color: #8a6a2c; width: 22mm; white-space: nowrap; }}
.spec td {{ background: transparent !important; padding: 3px 4px; font-size: 8.2pt; }}
.two {{ display: flex; gap: 5mm; }} .two > div {{ flex: 1; min-width: 0; }}
.grid3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 2.5mm; }}
.grid3 .photo img {{ height: 34mm; }}
</style></head><body>

<!-- P1 封面 -->
<div class="page" style="background:#102a33">
  <img src="{img('photos/外觀.jpg')}" style="position:absolute;left:0;top:0;width:210mm;height:160mm;object-fit:cover;object-position:center 30%">
  <div style="position:absolute;left:0;top:115mm;width:210mm;height:45mm;background:linear-gradient(180deg,rgba(16,42,51,0),#102a33)"></div>
  <div style="position:absolute;left:16mm;top:156mm;right:16mm;color:#fff">
    <div style="font-size:8pt;letter-spacing:.5em;color:#E3B66A">PROPERTY SALES REPORT</div>
    <div style="width:46mm;height:2px;background:#E3B66A;margin:5mm 0 5mm"></div>
    <div class="serif" style="font-size:11pt;color:#E3B66A;letter-spacing:.2em">南七期 · 惠文學區第一排</div>
    <h1 style="font-size:40pt;line-height:1.2;margin-top:2mm">麗晨語山簷</h1>
    <div class="serif" style="font-size:15pt;margin-top:2mm">把透天的庭院，搬上七樓 · 三房雙平車</div>
    <div style="font-size:8.8pt;color:#b9cad3;margin-top:4mm;line-height:1.9">台中市南屯區大業路556號 7樓之3（C 戶）<br>開價 {wan(L["總價"])} 萬　·　權狀 {L["坪數"]} 坪（含車位 {L["車位坪"]} 坪）　·　3房2廳2衛　·　坡道平面車位 ×2</div>
    <div style="margin-top:7mm;border-top:1px solid #3b5b66;padding-top:5mm;display:flex;gap:6mm;align-items:flex-end">
      <div style="flex:1">
        <div style="font-size:7.6pt;color:#E3B66A;letter-spacing:.3em">核心結論</div>
        <div style="font-size:9.3pt;line-height:1.9;margin-top:2mm">
          扣除兩個車位後，本戶房屋單價約 <b>{L["單價"]:.1f} 萬/坪</b>，低於社區 115 年交屋後成交中位 {AF["net"]:.1f}。<br>
          同型 C 戶 13F 在 115/01 成交房屋單價 {SAME_C["單價"]:.1f} 萬/坪，是最直接的比價依據。<br>
          <span style="color:#E3B66A">合理成交參考約 <b>{TARGET:,} 萬</b>（房屋 {T_UP:.1f} 萬/坪＋雙車位）。</span>
        </div>
      </div>
      <div class="qr" style="width:21mm"><img src="{img('QR_影片.png')}"><div>看影片</div></div>
      <div class="qr" style="width:21mm"><img src="{img('QR_LINE.png')}"><div>加 LINE</div></div>
    </div>
  </div>
  <div style="position:absolute;left:16mm;bottom:8mm;font-size:7.2pt;color:#8fa6b1">資料：內政部實價登錄（社區名稱「麗晨語山簷」，101/01–115/10，查詢 2026-10-16）　｜　{CONTACT}</div>
</div>

<!-- P2 物件總覽 -->
<div class="page"><div class="pad">
  <div class="eyebrow">01 · PROPERTY OVERVIEW</div>
  <div class="ttl">物件總覽</div>
  <div class="kpi">
    <div><div class="v">{wan(L["總價"])}</div><div class="u">萬元</div><div class="l">開價（含 2 車位）</div></div>
    <div><div class="v">{L["坪數"]}</div><div class="u">坪</div><div class="l">權狀總坪數（含車位）</div></div>
    <div><div class="v">37.05</div><div class="u">坪</div><div class="l">主建物＋附屬（室內可用）</div></div>
    <div><div class="v">{L["單價"]:.1f}</div><div class="u">萬/坪</div><div class="l">房屋單價（已扣車位）</div></div>
    <div><div class="v">2</div><div class="u">坡道平面</div><div class="l">B3 獨立・B4 柱邊</div></div>
  </div>
  <div class="two">
    <div>
      <h3 class="h" style="margin-top:0">本戶資料</h3>
      <table class="spec">
        <tr><td>地址</td><td>台中市南屯區大業路556號7樓之3</td></tr>
        <tr><td>樓層／格局</td><td>7F／15F・3房2廳2衛・座向朝西</td></tr>
        <tr><td>坪數</td><td>主建物 {L["主建物"]}＋附屬 {L["附屬"]}＋公設 {L["公設"]}＝{L["房屋坪"]} 坪；車位 {L["車位坪"]} 坪；合計 {L["坪數"]} 坪</td></tr>
        <tr><td>土地持分</td><td>{L["地坪"]} 坪（第二種住宅區）</td></tr>
        <tr><td>車位</td><td>坡道平面 2 位：B3 獨立車位、B4 柱邊車位</td></tr>
        <tr><td>管理費</td><td>8,934 元／月（社區 140 元／坪）</td></tr>
        <tr><td>建築完成</td><td>113/07/07（屋齡約 2 年）・RC・外牆二丁掛</td></tr>
        <tr><td>現況</td><td>空屋，隨時可看</td></tr>
      </table>
    </div>
    <div>
      <h3 class="h" style="margin-top:0">社區資料</h3>
      <table class="spec">
        <tr><td>建設／營造</td><td>麗晨建設／晨祥營造</td></tr>
        <tr><td>建築設計</td><td>凡工建築師事務所</td></tr>
        <tr><td>規模</td><td>基地 495 坪・地上 15 層・42 戶・每層 3 戶</td></tr>
        <tr><td>車位</td><td>98 位，坡道平面，私有充電車位</td></tr>
        <tr><td>公設比</td><td>33.80%</td></tr>
        <tr><td>學區</td><td>惠文國小（雙語）・惠文高中國中部</td></tr>
      </table>
      <h3 class="h">棟別配置</h3>
      {site}
      <div class="cap">依社區棟別圖重繪，非比例尺。C 戶面向河南路四段（西）。</div>
    </div>
  </div>
</div>{foot(2)}</div>

<!-- P3 平面配置 -->
<div class="page"><div class="pad">
  <div class="eyebrow">02 · FLOOR PLAN</div>
  <div class="ttl">格局：三房兩衛、三面環綠</div>
  <div class="sub">東側入戶，玄關、餐廳、廚房一線；客廳朝西接陽台，兩間臥室在北、主臥室帶衛浴在南。北、西、南三面都被綠廊包住，每個房間都有對外窗。</div>
  <div class="two" style="gap:4mm">
    <div style="flex:1.45"><div class="photo" style="background:#fff">{unit}</div>
      <div class="cap">本戶格局圖，依售屋格局圖重繪。</div></div>
    <div><div class="photo" style="background:#fff">{plan}</div>
      <div class="cap">樓層配置：每層 A、B、C 三戶，出電梯即入戶、零走廊；依建商樓層平面重繪，北朝上。</div>
      <div class="note" style="margin-top:3mm;font-size:7.8pt"><b>權狀外多出的一圈：</b>C 戶外圍有一圈不計入權狀的寬走道（植栽維護通道），沿著住家繞一圈，看得到也走得到。</div></div>
  </div>
  <div class="grid3" style="margin-top:4mm">
    <div><div class="photo"><img src="{img('photos/客廳.jpg')}"></div><div class="cap">客廳：整面落地窗通陽台</div></div>
    <div><div class="photo"><img src="{img('photos/廚具.jpg')}"></div><div class="cap">廚房：中島、嵌入式烤箱、IH 爐</div></div>
    <div><div class="photo"><img src="{img('photos/臥室.jpg')}"></div><div class="cap">臥室：窗外就是綠廊植栽</div></div>
  </div>
</div>{foot(3)}</div>

<!-- P4 建築特色 -->
<div class="page"><div class="pad">
  <div class="eyebrow">03 · ARCHITECTURE</div>
  <div class="ttl">空中三合院：把合院簷廊搬上高樓</div>
  <div class="sub">語山簷以傳統花窗、合院簷廊為構想，依台中市宜居建築規定做雙層外牆（Double Skin）：外層植生牆＋金屬擴張網，內層才是住家。簷廊遮陽、避雨、隔熱，植栽在外牆一路往上長。</div>
  <div class="grid3">
    <div><div class="photo"><img src="{img('photos/外觀2.jpg')}"></div><div class="cap">外觀：傳統花窗 × 合院簷廊</div></div>
    <div><div class="photo"><img src="{img('photos/植生牆.jpg')}"></div><div class="cap">Double Skin 複層植生牆</div></div>
    <div><div class="photo"><img src="{img('photos/圖書館.jpg')}"></div><div class="cap">1F 圖書館（敦煌書店選書）</div></div>
    <div><div class="photo"><img src="{img('photos/書香水景.jpg')}"></div><div class="cap">書香、天光與水景</div></div>
    <div><div class="photo"><img src="{img('photos/空中花園.jpg')}"></div><div class="cap">頂樓空中花園・開心農場</div></div>
    <div><div class="photo"><img src="{img('photos/健身房.jpg')}"></div><div class="cap">頂樓健身房，遠眺七期天際線</div></div>
  </div>
  <div class="two" style="margin-top:4mm">
    <div>
      <div class="feat"><div class="no">01</div><div><h3>戶戶三面採光、零走廊</h3><p>一層三戶，出電梯就入戶，沒有虛坪走廊。客廳、臥室都有對外窗，270 度視野。</p></div></div>
      <div class="feat"><div class="no">02</div><div><h3>零瓦斯、全電設計</h3><p>全社區不接瓦斯；德國鑄鐵排水管、全室隔音墊，住起來安靜。</p></div></div>
      <div class="feat"><div class="no">03</div><div><h3>衛浴全開窗・全平面無障礙</h3><p>每間衛浴都有窗，室內無高低差，長輩、推車都好走。</p></div></div>
    </div>
    <div>
      <div class="feat"><div class="no">04</div><div><h3>全社區 42 戶</h3><p>基地近 500 坪只蓋 42 戶，出入單純；公設有圖書館、琴房、交誼廳、健身房、空中花園。</p></div></div>
      <div class="feat"><div class="no">05</div><div><h3>惠文學區第一排</h3><p>惠文國小（雙語）、惠文高中國中部；惠來公園、文心森林公園；黎明市場、小康市場、全聯，公益路・黎明路商圈。</p></div></div>
      <div style="display:flex;gap:3mm;align-items:center;background:#163a47;color:#fff;padding:3mm;border-radius:2px">
        <div class="qr" style="width:19mm;flex:none"><img src="{img('QR_影片.png')}"></div>
        <div style="font-size:8pt;line-height:1.7"><span style="color:#E3B66A;font-weight:700">看 90 秒影片導覽</span><br>{YT}</div>
      </div>
    </div>
  </div>
</div>{foot(4)}</div>

<!-- P5 社區行情 -->
<div class="page"><div class="pad">
  <div class="eyebrow">04 · COMMUNITY PRICE</div>
  <div class="ttl">麗晨語山簷歷年成交</div>
  <div class="sub">社區 101/01–115/10 實登共 {S["原始筆數"]} 筆，排除 1F 店面 1 筆，住宅有效 {S["有效筆數"]} 筆。113/07 使照前為預售（建商首售），115 年起為交屋後成交。
  單價一律為<b>房屋單價（已扣車位）</b>＝（總價－車位價）÷（總坪數－車位坪數），車位價、車位坪數都取自實登揭露。</div>
  {chart}
  <div class="note" style="margin:3mm 0">交屋後的 {AF["n"]} 筆成交，房屋單價落在 {min(r["單價"] for r in TX if r["波段"] == "交屋後"):.1f}–{max(r["單價"] for r in TX if r["波段"] == "交屋後"):.1f} 萬/坪，中位 <b>{AF["net"]:.1f}</b>；
  本戶開價換算 <b>{L["單價"]:.1f}</b>，低於中位。車位交屋後每席成交 {wan(min(PK["交屋後"]))}–{wan(max(PK["交屋後"]))} 萬（中位 {wan(PK["交屋後中位"])} 萬），比預售時（中位 {wan(PK["預售中位"])} 萬）高。</div>
  <div class="two">
    <div>
      <h3 class="h" style="margin-top:0">依戶型</h3>
      <table class="xs">
        <tr><th>戶型</th><th>房屋坪</th><th>筆數</th><th>預售中位</th><th>交屋後中位</th></tr>
        {ty_rows}
      </table>
    </div>
    <div>
      <h3 class="h" style="margin-top:0">依年度</h3>
      <table class="xs">
        <tr><th>年度</th><th>筆數</th><th>房屋單價<br>（已扣車位）</th><th>總價÷總坪數<br>（車位一起算）</th></tr>
        {yr_rows}
      </table>
    </div>
  </div>
  <div class="cap">單位：萬元／坪，中位數。近三年（113–115）合計 {H3["n"]} 筆：房屋單價 {H3["net"]:.2f}、總價÷總坪數 {H3["gross"]:.2f}；樣本少，行情帶較寬。</div>
</div>{foot(5)}</div>

<!-- P6 成交明細 -->
<div class="page"><div class="pad">
  <div class="eyebrow">05 · TRANSACTIONS</div>
  <div class="ttl">社區成交明細</div>
  <div class="sub">全部 {S["有效筆數"]} 筆住宅成交（新到舊）。紅底為同型 C 戶交屋後成交。<b>有車位的物件有兩種單價：</b>
  ① 房屋單價（已扣車位），可以和無車位物件直接比；② 總價÷總坪數（車位一起算），車位坪數便宜會把單價拉低，網路上常看到的是這個。
  例：本戶 {wan(L["總價"])} 萬、{L["坪數"]} 坪 → ② {L["含車單價"]:.1f}；扣兩個車位（約 {wan(L["車位估"])} 萬、{L["車位坪"]} 坪）→ ① ({wan(L["總價"])}－{wan(L["車位估"])})÷{L["房屋坪"]} 坪＝{L["單價"]:.1f}。</div>
  <table class="xs">
    <tr><th>日期</th><th>戶型</th><th>樓層</th><th>總價（萬）</th><th>總坪數</th><th>車位</th><th>車位價</th><th>房屋單價<br>（已扣車位）</th><th>總價÷<br>總坪數</th><th>波段</th></tr>
    {tx_rows}
  </table>
  <div class="cap">紅單轉讓：該戶預售合約於 112/10 以 3,330 萬轉讓。另 110/10 一筆門牌記「十樓之1」、樓別記「四層」，以樓別為準。</div>
</div>{foot(6)}</div>

<!-- P7 價格分析 -->
<div class="page"><div class="pad">
  <div class="eyebrow">06 · PRICE ANALYSIS</div>
  <div class="ttl">價格分析：合理成交約 {TARGET:,} 萬</div>
  <div class="sub">把各參考點的房屋單價乘上本戶房屋 {L["房屋坪"]} 坪，再加上兩個車位（以交屋後每席中位 {wan(PK["交屋後中位"])} 萬計，共 {wan(L["車位估"])} 萬），換算成「照這個行情，本戶值多少」。</div>
  <div class="kpi">
    <div><div class="v">{wan(L["總價"])}</div><div class="u">萬元</div><div class="l">開價（房屋 {L["單價"]:.1f} 萬/坪）</div></div>
    <div style="border-top-color:#2E7D4F"><div class="v" style="color:#2E7D4F">{TARGET:,}</div><div class="u">萬元</div><div class="l">建議成交參考（{T_UP:.1f} 萬/坪）</div></div>
    <div><div class="v">{SAME_C["單價"]:.1f}</div><div class="u">萬/坪</div><div class="l">同型 C 戶 13F 115/01</div></div>
    <div><div class="v">{AF["net"]:.1f}</div><div class="u">萬/坪</div><div class="l">115 年交屋後中位</div></div>
  </div>
  <table>
    <tr><th>參考點</th><th>說明</th><th>房屋單價（萬/坪）</th><th>換算本戶總價（萬）</th></tr>
    {pos_rows}
  </table>
  <h3 class="h">為什麼是 {TARGET:,} 萬</h3>
  <div class="feat"><div class="no">01</div><div><h3>同型 C 戶剛成交 {SAME_C["單價"]:.1f} 萬/坪</h3><p>13F 之 3 在 115/01 成交，房屋坪數和本戶完全一樣（55.96 坪），是最直接的比價依據。照這個單價，本戶連兩個車位約 {wan(house(SAME_C["單價"]))} 萬。</p></div></div>
  <div class="feat"><div class="no">02</div><div><h3>7 樓比 13 樓略低一些</h3><p>同一批 C 戶預售（110/08–10）從 {c_wave[0]["樓層"]}F {c_wave[0]["單價"]:.1f} 到 {c_wave[-1]["樓層"]}F {c_wave[-1]["單價"]:.1f}，每高一層約多 1%。交屋後的 A 戶 8F 與 12–14F 只差約 2%。本戶 7F 取同型 13F 再打 1–2 折扣，約 {T_UP:.1f} 萬/坪。</p></div></div>
  <div class="feat"><div class="no">03</div><div><h3>開價已經低於社區交屋後中位</h3><p>交屋後 {AF["n"]} 筆房屋單價中位 {AF["net"]:.1f}，本戶開價換算 {L["單價"]:.1f}。三房雙車位 {wan(L["總價"])} 萬，比同社區四房 A 戶 115 年成交（5,300–6,360 萬）低一個級距，是進入這個社區門檻最低的產品。</p></div></div>
  <div class="warn">提醒：社區交屋後成交只有 {AF["n"]} 筆（其中 C 戶 1 筆），樣本少、行情帶較寬。B4 車位為柱邊車位，實際價值以現場停車條件為準。建議成交參考價為依實登推估，不代表屋主同意的售價，實際以雙方議價為準。</div>
</div>{foot(7)}</div>

<!-- P8 購屋試算 -->
<div class="page"><div class="pad">
  <div class="eyebrow">07 · BUYER'S GUIDE</div>
  <div class="ttl">購屋試算與看屋重點</div>
  <div class="kpi">
    <div><div class="v">{TARGET:,}</div><div class="u">萬元</div><div class="l">以建議成交參考價試算</div></div>
    <div><div class="v">{wan(down)}</div><div class="u">萬元</div><div class="l">自備款（兩成）</div></div>
    <div><div class="v">{wan(loan)}</div><div class="u">萬元</div><div class="l">貸款（八成）</div></div>
    <div><div class="v">{pay/10000:.1f}</div><div class="u">萬元／月</div><div class="l">本息攤還</div></div>
  </div>
  <div class="note">試算假設：貸款八成、年利率 {RATE*100:.1f}%、{YEARS} 年本息平均攤還，每月約 {pay:,.0f} 元。第二戶以上房貸成數依央行規定與銀行核定；另需預留契稅、代書、仲介服務費。</div>
  <h3 class="h">看屋重點</h3>
  <ul>
    <li><b>三面採光：</b>C 戶北、西、南三面開窗，看屋時建議下午走一趟，感受西側日照與遮陽格柵的效果。</li>
    <li><b>權狀外的綠廊：</b>環繞住家的維護通道不在權狀內，使用方式以社區規約為準。</li>
    <li><b>車位：</b>兩個坡道平面車位，B3 為獨立車位、B4 為柱邊車位，看屋可一併下樓確認。</li>
    <li><b>全電設計：</b>無瓦斯管線，廚具、熱水皆用電，可詢問社區電費經驗。</li>
    <li><b>新成屋：</b>屋齡約 2 年，空屋可直接規劃裝潢；保固範圍與期限請向建商與管委會確認。</li>
  </ul>
  <h3 class="h">為什麼值得看</h3>
  <ul>
    <li>七期惠文學區第一排，全社區 42 戶、一層三戶零走廊。</li>
    <li>雙平車三房，房屋單價換算低於社區交屋後成交中位。</li>
    <li>空中三合院建築，植生牆、圖書館、頂樓花園與健身房。</li>
  </ul>
  <div style="margin-top:5mm;position:relative;background:#fff;border:1px solid #dde4e9;padding:4.5mm 36mm 4.5mm 6mm;font-size:7.7pt;line-height:1.8;color:#4a5560">
    <div class="b" style="font-size:9.4pt;color:#163a47;margin-bottom:1.2mm">免責聲明</div>
    本報告書為不動產經紀業務之行銷參考資料，非不動產估價師出具之估價報告。行情統計與試算係依公開實價登錄資料整理，不構成價格保證、投資建議或獲利承諾。建築特色依建商公開資料與現場拍攝整理。實際面積、用途、產權及使用現況，以權狀、謄本、不動產說明書及買賣契約記載為準。
    <div style="position:absolute;right:7mm;top:50%;margin-top:-11mm;width:22mm;height:22mm;border:2.5px solid #b3261e;border-radius:50%;color:#b3261e;display:flex;align-items:center;justify-content:center;text-align:center;font-family:'Noto Serif CJK TC',serif;font-size:8pt;font-weight:700;line-height:1.3;transform:rotate(-12deg)">僅供<br>參考</div>
  </div>
  <div style="margin-top:5mm;display:flex;align-items:center;justify-content:center;gap:6mm;background:#163a47;padding:5mm 6mm;border-radius:2px">
    <div style="color:#fff">
      <div style="font-size:7.4pt;color:#E3B66A;letter-spacing:.3em">預約帶看・行情諮詢</div>
      <div class="serif" style="font-size:16pt;font-weight:700;margin-top:1mm">助哥　<span style="color:#F0D9A4">{PHONE}</span></div>
      <div style="font-size:8pt;color:#b9cad3;margin-top:1mm;line-height:1.7">永慶不動產 七期河南市政店<br>LINE {LINE_ID}　｜　{WEB}</div>
    </div>
    <div class="qr" style="width:22mm"><img src="{img('QR_LINE.png')}"><div>加 LINE</div></div>
    <div class="qr" style="width:22mm"><img src="{img('QR_影片.png')}"><div>看影片</div></div>
    <div class="qr" style="width:22mm"><img src="{img('QR_網站.png')}"><div>看網站</div></div>
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
