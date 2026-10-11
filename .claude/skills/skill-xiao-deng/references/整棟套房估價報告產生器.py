#!/usr/bin/env python3
"""整棟套房估價報告產生器（屋主版・單套均價法）— 小登

用法：python3 整棟套房估價報告產生器.py <案件資料夾>/case.json
  case.json 放案件資料（標的、租金表、參數、判讀文字），實登 .xls 放同一個資料夾。
  換案件只換 case.json，不改本檔。範例：deliverables/一中透套/case.json

輸出（寫在 case.json 同資料夾）：
  <輸出檔名>.html / .pdf   屋主版估價報告
  整棟套房_篩選明細.csv     全部套房型物件（含房數級距）與排除原因
  估價計算.json             計算結果（給內部 md 或複核用）

方法（細節見 整棟套房估價方法.md）——⛔ 不用地坪估價（助哥 2026-10-11：買方不認同）
  篩選：房 ≥6（4–5 房多為透天別墅）、衛 ≥ 房 × 房衛比下限；排除旅館、無隔間、
        住家格局（6–9 房廳 >1、10 房以上廳 >3，但登記成廳≈房者保留）、每房建坪 >15 坪；依房數分級距（10 房以下／10–19／20–29／30 以上）
  行情表：各級距「每間套房平均總價」（總價 ÷ 房數）中位數，近三年全屋齡＋近五年新屋兩種口徑
  法一 單套均價法：同級距、同區、最新一筆新屋成交的每間價 × (1 + 新屋修正)
                   第一棟標的直接套用；其他棟再乘「本棟平均月租 ÷ 第一棟平均月租」（房間大小、租金等級差）
  法二 收益法：滿租年租 ÷ 買方要求的毛投報率（買方看的就是毛投報）
  加權：單套 × 權重 + 收益 × 權重 → 試算中值；最終合理價、建議價由分析師填在 case.json（判斷值），本檔檢查是否偏離
依賴：xlrd、playwright（Chromium 在 /opt/pw-browsers）、字型 WenQuanYi Zen Hei。
"""
import base64, csv, glob, json, re, statistics as st, sys
from pathlib import Path

import xlrd

CASE = Path(sys.argv[1]).resolve()
DIR = CASE.parent
C = json.load(open(CASE, encoding='utf-8'))
BRAND = Path(__file__).resolve().parents[2] / 'skill-sixhands-brand'
TIERS = C.get('級距', [[1, 9, '10 房以下'], [10, 19, '10–19 房'], [20, 29, '20–29 房'], [30, 9999, '30 房以上']])


# ---------- 1. 讀實登 ----------
def num(s):
    s = str(s).replace(',', '').strip()
    return float(s) if s else 0.0


def ym(s):
    y, m = s.split('/')[:2]
    return int(y) + int(m) / 12


def tier_of(n):
    return next(t[2] for t in TIERS if t[0] <= n <= t[1])


def load(path):
    b = xlrd.open_workbook(path)
    s = b.sheet_by_name('案件列表')
    dist = re.search(r'臺中市(\S+?區)', s.cell_value(0, 0)).group(1)
    bld = {}
    sh = b.sheet_by_name('建物')
    for r in range(1, sh.nrows):
        v = sh.row_values(r)
        bld.setdefault(v[0].split('-')[0], []).append(v)
    out = []
    for r in range(2, s.nrows):
        v = s.row_values(r)
        m = re.match(r'(\d+)房', v[14])
        if not m:
            continue
        rooms = int(m.group(1))
        if rooms < C.get('最少房數', 6):
            continue
        bm = re.search(r'(\d+)衛', v[14])
        baths = int(bm.group(1)) if bm else 0
        hm = re.search(r'(\d+)廳', v[14])
        halls = int(hm.group(1)) if hm else 0
        blds = bld.get(v[0], [])
        price = num(v[4])
        nt = re.search(r'實際成交價為([\d,]+)元', v[18])  # 備註載明實際成交價時以備註為準
        if nt:
            price = num(nt.group(1)) / 10000
        age = v[9]
        done = [x[6] for x in blds if x[6]]
        if age == '' and done:
            age = int(v[3].split('/')[0]) - int(done[0].split('/')[0])
        age = int(age) if age != '' else None
        use = '|'.join(x[4] for x in blds)
        ex = ''
        area = num(v[6])
        hall_max = 1 if rooms < 10 else 3  # 套房透天：廳很少；登記把每間都算廳（廳≈房）也算套房
        if baths < rooms * C['房衛比下限']:
            ex = '房衛比低（非套房）'
        elif '旅' in use:
            ex = '旅館'
        elif '無隔間' in v[14]:
            ex = '無隔間'
        elif halls > hall_max and halls < rooms * 0.8:
            ex = '住家格局（透天別墅等，廳數多）'
        elif area / rooms > C.get('每房建坪上限', 15):
            ex = '每房建坪過大（非套房）'
        addr = v[1].translate(str.maketrans('０１２３４５６７８９－', '0123456789-'))
        addr = re.sub(r'^(北區|中區|南區|西區|西屯區|東區|南屯區|北屯區)', '', addr)
        out.append(dict(區=dist, 門牌=addr, 日期=v[3], t=ym(v[3]), 總價=price, 房=rooms, 衛=baths, 屋齡=age,
                        樓高=v[10], 建坪=num(v[6]), 排除=ex, 每間=price / rooms, 級距=tier_of(rooms)))
    return out


rows, seen = [], set()
for f in C['實登檔']:
    for r in load(DIR / f):
        key = (r['門牌'], r['日期'], round(r['總價']))
        if key not in seen:  # 分批撈的檔案可能重疊
            seen.add(key)
            rows.append(r)
rows.sort(key=lambda r: (r['房'], -r['t']))
ok = [r for r in rows if not r['排除']]
win3, win5 = ym(C['近三年起']), ym(C['新屋行情起'])
NEW = C['新屋門檻']
isnew = lambda r: r['屋齡'] is not None and r['屋齡'] <= NEW
dists = sorted({r['區'] for r in rows})

tiers = []
for lo, hi, lab in TIERS:
    a = [r for r in ok if r['級距'] == lab and r['t'] >= win3]
    b = [r for r in ok if r['級距'] == lab and r['t'] >= win5 and isnew(r)]
    tiers.append(dict(級距=lab, n3=len(a), m3=st.median(x['每間'] for x in a) if a else None,
                      tot3=st.median(x['總價'] for x in a) if a else None,
                      n5=len(b), m5=st.median(x['每間'] for x in b) if b else None))

with open(DIR / '整棟套房_篩選明細.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['區', '門牌', '交易日期', '總價(萬)', '房', '衛', '房數級距', '屋齡', '樓高', '建坪', '每間套房均價(萬)', '排除原因'])
    for r in rows:
        w.writerow([r['區'], r['門牌'], r['日期'], round(r['總價']), r['房'], r['衛'], r['級距'], r['屋齡'], r['樓高'],
                    r['建坪'], round(r['每間']), r['排除']])

# ---------- 2. 估價 ----------
A = C['標的']
base = None
for S in A:
    S['月租'] = sum(S['租金'].values())
    S['年租'] = S['月租'] * 12 / 10000
    S['均租'] = S['月租'] / len(S['租金'])
    S['級距'] = tier_of(S['房'])
    cand = [r for r in ok if r['級距'] == S['級距'] and isnew(r) and r['t'] >= win5]
    same = [r for r in cand if r['區'] == S['區']] or cand
    if not same:
        sys.exit(f'{S["名稱"]}：{S["級距"]}沒有近年新屋成交，請放寬撈取範圍')
    S['同級案例'] = sorted(cand, key=lambda r: -r['t'])
    ref = max(same, key=lambda r: r['t'])
    S['參考'] = ref
    S['租金比'] = 1.0 if base is None else S['均租'] / base['均租']
    base = base or S
    S['每間'] = ref['每間'] * (1 + C['新屋修正'] / 100) * S['租金比']
    band = C.get('單套區間', 3.5) / 100
    S['法一'] = (S['每間'] * (1 - band) * S['房'], S['每間'] * (1 + band) * S['房'])
    y_lo, y_hi = C['毛投報']
    S['法二'] = (S['年租'] / (y_hi / 100), S['年租'] / (y_lo / 100))
    wt = C['權重']
    S['試算中值'] = sum(S['法一']) / 2 * wt['單套'] + sum(S['法二']) / 2 * wt['收益']
    S['中值'] = sum(S['合理價']) / 2
    if abs(S['中值'] / S['試算中值'] - 1) > 0.03:
        print(f'⚠️ {S["名稱"]} 合理價中值 {S["中值"]:.0f} 與加權試算 {S["試算中值"]:.0f} 差超過 3%，請確認判斷依據')
    S['毛投報_開'] = S['年租'] / S['開價'] * 100
    S['毛投報_底'] = S['年租'] / S['底價'] * 100

json.dump(dict(級距行情=tiers, 標的=[{k: v for k, v in S.items() if k not in ('租金', '同級案例')} for S in A]),
          open(DIR / '估價計算.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
for t in tiers:
    print(t)
for S in A:
    print(f"{S['名稱']}：每間 {S['每間']:.0f}（參考 {S['參考']['門牌']} {S['參考']['每間']:.0f}，租金比 {S['租金比']:.3f}）｜"
          f"法一 {S['法一'][0]:.0f}–{S['法一'][1]:.0f}｜法二 {S['法二'][0]:.0f}–{S['法二'][1]:.0f}｜加權 {S['試算中值']:.0f}｜判斷 {S['合理價']}")


# ---------- 3. HTML ----------
def img(p):
    p = Path(p)
    mime = 'image/png' if p.suffix == '.png' else 'image/jpeg'
    return f'data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}'


def w(v):
    return '—' if v is None else f'{v:,.0f}'


NAME = C['案名']
DISC = '永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號'
CONTACT = '助哥 <span class="nw">0925-313-570</span>　｜　LINE @080akczk　｜　sixhands.tw'
QR = (f'<div class="qrs"><div class="qr"><img src="{img(BRAND / "qr_line.png")}"><div>LINE 諮詢</div></div>'
      f'<div class="qr"><img src="{img(BRAND / "qr_web.png")}"><div>官網</div></div></div>')
pages = []


def page(body, n):
    pages.append(f'<section class="page"><div class="pad">{body}</div>'
                 f'<div class="foot"><div>{DISC}<br><span class="ct">{CONTACT}</span></div>'
                 f'<span>{NAME} 屋主估價報告　{n}</span></div></section>')


# 長條圖：各級距每間均價（近三年）＋標的每間價
bars = [(f"{t['級距']}（{t['n3']} 筆）", t['m3'], 'c') for t in tiers if t['m3'] and not t['級距'].startswith('10 房以下')]
for S in A:
    bars.append((f"{S['名稱']} 現行開價", S['開價'] / S['房'], 'o'))
    bars.append((f"{S['名稱']} 建議心理價", S['建議底價'] / S['房'], 's'))
BW, BH, LW = 640, 24 * len(bars) + 14, 200
mx = max(b[1] for b in bars) * 1.15
colors = {'c': '#8a97ab', 'o': '#B8893E', 's': '#1A2942'}
svg = [f'<svg viewBox="0 0 {BW} {BH}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="WenQuanYi Zen Hei" font-size="10.5">']
for i, (lab, v, k) in enumerate(bars):
    y = 6 + i * 24
    ww = v / mx * (BW - LW - 40)
    svg.append(f'<text x="{LW - 8}" y="{y + 13}" text-anchor="end" fill="#333">{lab}</text>'
               f'<rect x="{LW}" y="{y + 2}" width="{ww:.1f}" height="16" rx="2" fill="{colors[k]}"/>'
               f'<text x="{LW + ww + 5:.1f}" y="{y + 14}" fill="#222" font-weight="700">{v:.0f} 萬</text>')
svg.append('</svg>')
chart = ''.join(svg)

# P1 封面
res = ''.join(f'<div class="cbox"><div class="cl">{S["名稱"]}</div><div class="cv">{w(S["合理價"][0])}–{w(S["合理價"][1])}</div>'
              f'<div class="cu">萬元　合理價區間（每間約 {S["合理價"][0] / S["房"]:.0f}–{S["合理價"][1] / S["房"]:.0f} 萬）</div>'
              f'<div class="cs">建議開價 {w(S["建議開價"])}　｜　心理價 {w(S["建議底價"])}</div></div>' for S in A)
pages.append(f'''<section class="page cover">
<img class="logo" src="{img(BRAND / 'logo_full_white.png')}">
<div class="ceyebrow">WHOLE-BUILDING SUITE VALUATION</div>
<h1>{NAME}</h1>
<div class="csub">{C['副標']}</div>
<div class="ctitle">市場行情分析暨建議售價報告<span>屋主版</span></div>
<div class="cres">{res}</div>
<div class="cmeta">報告日期 {C['報告日']}　｜　資料來源 內政部實價登錄（撈取日 {C['撈取日']}）</div>
<div class="ccontact"><div><div class="cct">預約洽談</div><div class="ccn">助哥 <span class="nw">0925-313-570</span></div>
<div class="ccs">永慶不動產 七期河南市政店<br>LINE @080akczk　｜　sixhands.tw</div></div>{QR}</div>
</section>''')

# P2 物件概要
spec = ''
for lab, fn in [('地址', lambda S: S['地址'].replace('臺中市', '')), ('格局', lambda S: f"{S['房']} 房 {S['衛']} 衛（{S['級距']}級距）"),
                ('樓層', lambda S: S['樓層']), ('屋齡', lambda S: S['屋齡']), ('建坪', lambda S: f"{S['建坪']:.2f} 坪"),
                ('地坪', lambda S: f"{S['地坪']:.2f} 坪"), ('車位', lambda S: S['車位'])]:
    spec += f'<tr><td>{lab}</td>' + ''.join(f'<td>{fn(S)}</td>' for S in A) + '</tr>'
rent_rows = [
    ('現行開價／心理價', lambda S: f"{w(S['開價'])}／{w(S['底價'])} 萬"),
    ('換算每間套房', lambda S: f"{S['開價'] / S['房']:.0f}／{S['底價'] / S['房']:.0f} 萬"),
    ('滿租月租金', lambda S: f"{S['月租'] / 10000:.2f} 萬"),
    ('滿租年租金', lambda S: f"{S['年租']:.1f} 萬"),
    ('平均每間月租', lambda S: f"{S['均租']:,.0f} 元"),
    ('每間月租範圍', lambda S: f"{min(S['租金'].values()) / 10000:.1f}–{max(S['租金'].values()) / 10000:.1f} 萬"),
    ('滿租毛投報（開價／心理價）', lambda S: f"{S['毛投報_開']:.2f}%／{S['毛投報_底']:.2f}%"),
]
rent = ''.join(f'<tr><td>{lab}</td>' + ''.join(f'<td class="num">{fn(S)}</td>' for S in A) + '</tr>' for lab, fn in rent_rows)
head = '<tr><th></th>' + ''.join(f'<th>{S["名稱"]}</th>' for S in A) + '</tr>'
photo = f'<div class="photo"><img src="{img(DIR / C["照片"])}"><div class="cap">標的套房室內實景</div></div>' if C.get('照片') else ''
page(f'''<div class="eyebrow">01　PROPERTY</div><div class="ttl">物件概要</div>
<table class="spec">{head}{spec}</table>
<div class="ttl2">租金收益現況</div>
<table class="spec">{head}{rent}</table>
<div class="sub" style="margin-top:2mm">{C.get('租金說明', '租金以屋主提供之租金表、每間最新一期租金計算。')}</div>
{photo}''', 2)

# P3 市場行情：房數級距 ＋ 各區單套均價折線圖
trow = ''
for t in tiers:
    hl = ' class="hl"' if t['級距'] == A[0]['級距'] else ''
    trow += (f'<tr{hl}><td>{t["級距"]}</td><td class="num">{t["n3"]}</td><td class="num b">{w(t["m3"])} 萬</td><td class="num">{w(t["tot3"])} 萬</td>'
             f'<td class="num">{t["n5"]}</td><td class="num b">{w(t["m5"])} 萬</td></tr>')
y3, y5 = C['近三年起'], C['新屋行情起']

# 各區 × 房數級距 每間均價中位數（y5 起、全屋齡）
DCOL = ['#1A2942', '#B8893E', '#3d7a5a', '#a8382e', '#6b5fa8', '#2f7fa8', '#8a6a2c']
dline = []
for i, d in enumerate(dists):
    pts = []
    for j, (lo, hi, lab) in enumerate(TIERS):
        s = [r['每間'] for r in ok if r['區'] == d and r['級距'] == lab and r['t'] >= win5]
        pts.append((j, st.median(s), len(s)) if s else None)
    dline.append((d, DCOL[i % len(DCOL)], pts))
LW2, LH2, PL, PR, PT, PB = 640, 300, 50, 20, 20, 46
ymax = max(p[1] for _, _, ps in dline for p in ps if p) * 1.12
ymax = (int(ymax / 200) + 1) * 200
X = lambda j: PL + (j + .5) * (LW2 - PL - PR) / len(TIERS)
Y = lambda v: PT + (1 - v / ymax) * (LH2 - PT - PB)
g = [f'<svg viewBox="0 0 {LW2} {LH2}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="WenQuanYi Zen Hei" font-size="10">']
for v in range(0, ymax + 1, 200):
    g.append(f'<line x1="{PL}" x2="{LW2 - PR}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e5e7eb"/>'
             f'<text x="{PL - 6}" y="{Y(v) + 3:.1f}" text-anchor="end" fill="#888">{v}</text>')
for j, (lo, hi, lab) in enumerate(TIERS):
    g.append(f'<text x="{X(j):.1f}" y="{LH2 - PB + 16}" text-anchor="middle" fill="#333" font-size="10.5">{lab}</text>')
g.append(f'<text x="{PL}" y="{PT - 6}" fill="#888" font-size="9">萬元／間</text>')
for d, col, pts in dline:
    seg, path = [p for p in pts if p], ''
    path = ' '.join(f'{"M" if k == 0 else "L"}{X(p[0]):.1f},{Y(p[1]):.1f}' for k, p in enumerate(seg))
    g.append(f'<path d="{path}" fill="none" stroke="{col}" stroke-width="2.2"/>')
    for p in seg:
        g.append(f'<circle cx="{X(p[0]):.1f}" cy="{Y(p[1]):.1f}" r="3.6" fill="{col}"/>')
lx = PL
for d, col, _ in dline:
    g.append(f'<rect x="{lx}" y="{LH2 - 16}" width="14" height="4" fill="{col}"/><text x="{lx + 18}" y="{LH2 - 11}" fill="#333" font-size="10">{d}</text>')
    lx += 80
g.append('</svg>')
dchart = ''.join(g)
dtab = ('<table class="mini"><tr><th>區</th>' + ''.join(f'<th class="num">{lab}</th>' for _, _, lab in TIERS) + '</tr>' +
        ''.join(f'<tr><td><span style="color:{col}">●</span> {d}</td>' +
                ''.join(f'<td class="num">{p[1]:.0f} 萬（{p[2]}）</td>' if p else '<td class="num">—</td>' for p in pts) + '</tr>'
                for d, col, pts in dline) + '</table>')

page(f'''<div class="eyebrow">02　MARKET</div><div class="ttl">市場行情：每間套房平均總價</div>
<div class="sub">撈取 {'、'.join(dists)} 實價登錄（{C['撈取條件']}），篩出 6 房以上、衛浴數 ≥ 房數 × {C['房衛比下限']} 的整棟套房；
排除 4–5 房透天別墅、住家格局（廳數多）、旅館、無隔間、每房坪數過大等非套房物件，有效樣本 <b>{len(ok)} 筆</b>。每間套房平均總價 ＝ 成交總價 ÷ 房數。</div>
<table><tr><th>房數級距</th><th class="num">{y3} 起 筆數</th><th class="num">每間均價中位數</th><th class="num">總價中位數</th>
<th class="num">{y5} 起新屋（≤{NEW} 年）筆數</th><th class="num">每間均價中位數</th></tr>{trow}</table>
<div class="ttl2">各區每間套房均價（{y5} 起成交、全屋齡，中位數；括號為筆數）</div>{dchart}{dtab}
<div class="note" style="margin-top:2mm"><b>房數越多，每間越便宜。</b>　房數越多總價越高，買得起的人越少，每間得讓價才賣得掉；各區都是同樣的走勢。<br>{C['市場觀察']}<br>
<span class="gr">10 房以下樣本少，且多為店面住家混合；30 房以上每間明顯低一截。</span></div>''', 3)

# P4 同級距成交案例
cases = A[0]['同級案例'][:C.get('案例表上限', 18)]
allv = sorted(r['每間'] for r in A[0]['同級案例'])
q = st.quantiles(allv, n=4) if len(allv) >= 4 else [allv[0], st.median(allv), allv[-1]]
HL = ' class="hl"'
crow = ''.join(f'<tr{HL if r is A[0]["參考"] else ""}><td>{r["區"]}</td><td>{r["門牌"]}</td><td>{r["日期"]}</td><td class="num">{w(r["總價"])}</td>'
               f'<td class="num">{r["房"]}</td><td class="num">{r["屋齡"]}</td><td class="num b">{w(r["每間"])}</td></tr>' for r in cases)
page(f'''<div class="eyebrow">03　COMPARABLES</div><div class="ttl">同級距成交案例</div>
<div class="sub">{A[0]['級距']}、{y5} 起成交、屋齡 ≤{NEW} 年，共 {len(A[0]['同級案例'])} 筆（列出最新 {len(cases)} 筆）。每間均價：最低 {w(min(allv))} 萬，四分之一在 {w(q[0])} 萬以下，中位數 {w(q[1])} 萬，四分之一在 {w(q[2])} 萬以上，最高 {w(max(allv))} 萬。<br>
同一棟套房常有大小間，難以用房間坪數比較；本報告以<b>租金等級</b>反映房間大小與裝修差異。</div>
<table><tr><th>區</th><th>門牌</th><th>成交</th><th class="num">總價(萬)</th><th class="num">房</th><th class="num">屋齡</th><th class="num">每間均價(萬)</th></tr>{crow}</table>
<div class="ttl2">每間套房均價比較（萬元／間）</div>{chart}''', 4)


# P4/P5 各棟估價
def val_page(S, n):
    ref = S['參考']
    rent_adj = '' if S['租金比'] == 1 else f"<br>× 租金等級 {S['租金比'] * 100:.1f}%（本棟平均月租 {S['均租']:,.0f} 元 ÷ {base['名稱']} {base['均租']:,.0f} 元）"
    m = f'''<table><tr><th>方法</th><th>計算</th><th class="num">結果（萬）</th></tr>
<tr><td class="b">法一　單套均價法<br><span class="gr">權重 {C['權重']['單套'] * 100:.0f}%</span></td>
<td>參考 {ref['區']}{ref['門牌']}（{ref['日期']} 成交，{ref['房']} 房、屋齡 {ref['屋齡']} 年，每間 {w(ref['每間'])} 萬）<br>
<span class="gr">× 新屋修正 +{C['新屋修正']}%{rent_adj}<br>→ 每間約 {w(S['每間'])} 萬（±{C.get('單套區間', 3.5)}%）× {S['房']} 間</span></td>
<td class="num b">{w(S['法一'][0])}–{w(S['法一'][1])}</td></tr>
<tr><td class="b">法二　收益法<br><span class="gr">權重 {C['權重']['收益'] * 100:.0f}%</span></td>
<td>滿租年租 {S['年租']:.1f} 萬 ÷ 買方要求毛投報 {C['毛投報'][0]}%–{C['毛投報'][1]}%</td>
<td class="num b">{w(S['法二'][0])}–{w(S['法二'][1])}</td></tr>
<tr><td class="b">加權試算</td><td>{w(sum(S['法一']) / 2)} × {C['權重']['單套']:g} ＋ {w(sum(S['法二']) / 2)} × {C['權重']['收益']:g}</td>
<td class="num b">{w(S['試算中值'])}</td></tr>
<tr class="hl"><td colspan="2">合理價判斷（每間約 {S['合理價'][0] / S['房']:.0f}–{S['合理價'][1] / S['房']:.0f} 萬）</td>
<td class="num">{w(S['合理價'][0])}–{w(S['合理價'][1])}</td></tr></table>'''
    k = f'''<div class="kpi">
<div><div class="v">{w(S['合理價'][0])}–{w(S['合理價'][1])}</div><div class="u">萬元</div><div class="l">合理價區間</div></div>
<div><div class="v">{w(S['建議開價'])}</div><div class="u">萬元（每間 {S['建議開價'] / S['房']:.0f}）</div><div class="l">建議開價（現行 {w(S['開價'])}）</div></div>
<div><div class="v">{w(S['建議底價'])}</div><div class="u">萬元（每間 {S['建議底價'] / S['房']:.0f}）</div><div class="l">建議心理價（現行 {w(S['底價'])}）</div></div>
<div><div class="v">{S['年租'] / S['建議底價'] * 100:.2f}%</div><div class="u">滿租毛投報</div><div class="l">以建議心理價計</div></div></div>'''
    extra = ''
    if S is not base:
        cmp_rows = [
            ('現行開價', lambda X: f"{w(X['開價'])} 萬"),
            ('每間（現行開價）', lambda X: f"{X['開價'] / X['房']:.0f} 萬"),
            ('平均每間月租', lambda X: f"{X['均租'] / 10000:.2f} 萬"),
            ('滿租毛投報（現行開價）', lambda X: f"{X['毛投報_開']:.2f}%"),
            ('每間（建議心理價）', lambda X: f"{X['建議底價'] / X['房']:.0f} 萬"),
            ('滿租毛投報（建議心理價）', lambda X: f"{X['年租'] / X['建議底價'] * 100:.2f}%"),
        ]
        extra = ('<div class="ttl2">買方會怎麼比：與隔壁 ' + base['名稱'] + '</div><table><tr><th></th>' +
                 ''.join(f'<th class="num">{X["名稱"]}</th>' for X in (base, S)) + '</tr>' +
                 ''.join(f'<tr><td>{lab}</td>' + ''.join(f'<td class="num">{fn(X)}</td>' for X in (base, S)) + '</tr>' for lab, fn in cmp_rows) + '</table>')
    judg = ''.join(f'<li>{t}</li>' for t in S['判讀'])
    page(f'''<div class="eyebrow">0{n - 1}　VALUATION</div><div class="ttl">{S['名稱']} 估價</div>
<div class="sub">{S['地址']}｜{S['房']} 房 {S['衛']} 衛（{S['級距']}）｜{S['屋齡']}｜現行開價 {w(S['開價'])} 萬、心理價 {w(S['底價'])} 萬</div>
{k}{m}{extra}<div class="ttl2">判讀</div><ul>{judg}</ul>''', n)


for i, S in enumerate(A):
    val_page(S, 5 + i)

# 末頁：售價策略 + 限制 + 聯絡
N = 5 + len(A)
plan = ''.join(f'<tr><td class="b">{S["名稱"]}</td><td class="num">{w(S["開價"])}／{w(S["底價"])}</td><td class="num">{w(S["合理價"][0])}–{w(S["合理價"][1])}</td>'
               f'<td class="num b">{w(S["建議開價"])}／{w(S["建議底價"])}</td><td class="num">{S["建議開價"] / S["房"]:.0f}／{S["建議底價"] / S["房"]:.0f}</td>'
               f'<td class="num">{(S["開價"] / S["中值"] - 1) * 100:+.0f}%</td></tr>' for S in A)
adv = ''.join(f'<li>{t}</li>' for t in C['銷售建議'])
lim = ''.join(f'<li>{t}</li>' for t in C['限制'])
page(f'''<div class="eyebrow">0{N - 1}　STRATEGY</div><div class="ttl">售價策略建議</div>
<table><tr><th>棟別</th><th class="num">現行 開價／心理價</th><th class="num">合理價區間</th><th class="num">建議 開價／心理價</th><th class="num">建議價每間</th><th class="num">現行開價 vs 合理中值</th></tr>{plan}</table>
<ul style="margin-top:3mm">{adv}</ul>
<div class="ttl2">分析限制</div><ul class="small">{lim}</ul>
<div class="warn">本報告為市場行情分析，非不動產估價師法之估價報告，僅供屋主訂價參考；實際成交價受買方條件、市場變化與議價過程影響。<br>
資料來源：內政部不動產交易實價查詢服務網（撈取日 {C['撈取日']}）；租金資料由屋主提供。分析由 Sixhands Studio AI 數字員工「小登」協助整理，經助哥審閱。</div>
<div class="card"><div><div class="cct" style="color:#B8893E">委託銷售・預約洽談</div><div class="ccn" style="color:#1A2942">助哥 <span class="nw">0925-313-570</span></div>
<div class="ccs" style="color:#555">永慶不動產 七期河南市政店<br>LINE @080akczk　｜　sixhands.tw</div></div>{QR}</div>''', N)

CSS = '''
@page { size: A4; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "WenQuanYi Zen Hei", sans-serif; color: #222; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.page { width: 210mm; height: 297mm; position: relative; overflow: hidden; page-break-after: always; background: #fff; }
.page:last-child { page-break-after: auto; }
.pad { padding: 14mm 15mm 0 15mm; }
.nw { white-space: nowrap; }
.eyebrow { font-size: 7.5pt; letter-spacing: .4em; color: #B8893E; margin-bottom: 1.5mm; }
.ttl { font-size: 18pt; font-weight: 700; color: #1A2942; border-left: 5px solid #B8893E; padding-left: 9px; margin-bottom: 3mm; }
.ttl2 { font-size: 11.5pt; font-weight: 700; color: #1A2942; margin: 5mm 0 2mm; padding-bottom: 1mm; border-bottom: 1.5px solid #B8893E; }
.sub { font-size: 8.6pt; color: #666; line-height: 1.7; margin-bottom: 3mm; }
table { width: 100%; border-collapse: collapse; font-size: 8.4pt; }
th { background: #1A2942; color: #fff; padding: 4.5px 6px; text-align: left; font-weight: 400; }
td { padding: 4.5px 6px; border-bottom: 1px solid #e5e7eb; vertical-align: top; line-height: 1.55; }
tr:nth-child(even) td { background: #f6f7f9; }
tr.hl td { background: #B8893E !important; color: #fff; font-weight: 700; }
.num { text-align: right; white-space: nowrap; }
th.num { text-align: right; }
.b { font-weight: 700; }
.gr { color: #777; font-size: 7.8pt; }
.spec td:first-child { color: #8a6a2c; width: 34mm; white-space: nowrap; }
.note { background: #f7f1e3; border-left: 4px solid #B8893E; padding: 3mm 4mm; font-size: 8.4pt; line-height: 1.75; }
.warn { background: #f3f4f6; border-left: 4px solid #9ca3af; padding: 3mm 4mm; font-size: 7.6pt; line-height: 1.7; color: #555; margin-top: 4mm; }
ul { margin-left: 5mm; } li { font-size: 8.8pt; line-height: 1.8; margin-bottom: 1mm; }
table.mini td, table.mini th { padding: 2.5px 6px; font-size: 7.8pt; }
ul.small li { font-size: 7.9pt; line-height: 1.65; }
.kpi { display: flex; gap: 3mm; margin: 2mm 0 4mm; }
.kpi > div { flex: 1; border: 1px solid #e5e7eb; border-top: 3px solid #B8893E; padding: 3mm 2mm; text-align: center; }
.kpi .v { font-size: 15pt; font-weight: 700; color: #1A2942; line-height: 1.15; }
.kpi .u { font-size: 7.4pt; color: #B8893E; }
.kpi .l { font-size: 7.3pt; color: #666; margin-top: 1mm; }
.photo { margin-top: 4mm; } .photo img { width: 100%; height: 82mm; object-fit: cover; border-radius: 2px; }
.cap { font-size: 7pt; color: #888; margin-top: 1mm; }
.foot { position: absolute; bottom: 0; left: 0; right: 0; height: 11mm; background: #1A2942; color: #c9d1de; font-size: 6.3pt; line-height: 1.6;
  display: flex; align-items: center; justify-content: space-between; padding: 0 15mm; }
.foot .ct { color: #E7CF96; font-weight: 700; }
.qrs { display: flex; gap: 3mm; }
.qr { background: #fff; padding: 1.5mm; width: 25mm; text-align: center; border: 1px solid #e5e7eb; }
.qr img { width: 100%; display: block; } .qr div { font-size: 6.6pt; color: #1A2942; font-weight: 700; margin-top: .6mm; }
.cover { background: linear-gradient(150deg, #1A2942 0%, #24385a 65%, #1A2942 100%); color: #fff; padding: 22mm 20mm; }
.cover .logo { width: 52mm; display: block; margin-bottom: 24mm; }
.ceyebrow { font-size: 8pt; letter-spacing: .45em; color: #C9A961; }
.cover h1 { font-size: 40pt; margin: 4mm 0 2mm; letter-spacing: .08em; }
.csub { font-size: 12pt; color: #d9dfe8; }
.ctitle { font-size: 15pt; margin-top: 9mm; padding-top: 5mm; border-top: 1px solid #C9A96166; color: #fff; }
.ctitle span { font-size: 9pt; color: #1A2942; background: #C9A961; padding: .6mm 2.5mm; margin-left: 3mm; border-radius: 2px; vertical-align: middle; }
.cres { display: flex; gap: 5mm; margin-top: 10mm; }
.cbox { flex: 1; border: 1px solid #C9A96188; padding: 5mm; background: rgba(255,255,255,.04); }
.cl { font-size: 10pt; color: #C9A961; } .cv { font-size: 22pt; font-weight: 700; margin-top: 2mm; }
.cu { font-size: 8pt; color: #b9c3d3; } .cs { font-size: 8.6pt; margin-top: 3mm; color: #e8ecf2; }
.cmeta { font-size: 7.8pt; color: #9fb0c8; margin-top: 8mm; }
.ccontact, .card { position: absolute; left: 20mm; right: 20mm; bottom: 18mm; display: flex; justify-content: space-between; align-items: center;
  border-top: 1px solid #C9A96166; padding-top: 6mm; }
.card { position: static; margin-top: 6mm; border-top: 1.5px solid #B8893E; padding-top: 5mm; }
.cct { font-size: 9pt; letter-spacing: .3em; color: #C9A961; } .ccn { font-size: 18pt; font-weight: 700; margin: 1.5mm 0; }
.ccs { font-size: 8.6pt; color: #d9dfe8; line-height: 1.7; }
'''
OUT = DIR / C['輸出檔名']
html = f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>{NAME} 屋主估價報告</title><style>{CSS}</style></head><body>{"".join(pages)}</body></html>'
OUT.with_suffix('.html').write_text(html, encoding='utf-8')

from playwright.sync_api import sync_playwright
exe = sorted(glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome'))
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exe[-1] if exe else None)
    pg = b.new_page()
    pg.goto(OUT.with_suffix('.html').as_uri())
    pg.wait_for_timeout(400)
    over = pg.evaluate('''[...document.querySelectorAll('.page')].map((p,i)=>{const pad=p.querySelector('.pad');
        if(!pad) return null; const f=p.querySelector('.foot').getBoundingClientRect().top; const last=[...pad.children].pop().getBoundingClientRect().bottom;
        return last>f-4 ? i+1 : null}).filter(x=>x)''')
    if over:
        print('⚠️ 內容溢出頁尾的頁碼：', over)
    pg.pdf(path=str(OUT.with_suffix('.pdf')), prefer_css_page_size=True, print_background=True)
    b.close()
print('PDF →', OUT.with_suffix('.pdf'))
