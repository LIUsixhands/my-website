#!/usr/bin/env python3
"""整棟套房估價報告產生器（屋主版）— 小登

用法：python3 整棟套房估價報告產生器.py <案件資料夾>/case.json
  case.json 放案件資料（標的、租金表、參數、判讀文字），實登 .xls 放同一個資料夾。
  換案件只換 case.json，不改本檔。範例：deliverables/一中透套/case.json

輸出（寫在 case.json 同資料夾）：
  <輸出檔名>.html / .pdf   屋主版估價報告
  整棟套房_篩選明細.csv     全部 ≥N 房物件與排除原因
  估價計算.json             三法計算結果（給 md 報告或複核用）

方法（細節見 整棟套房估價方法.md）：
  篩選：格局 ≥ 最少房數，且 衛 ≥ 房 × 房衛比下限（排除旅館、宿舍、醫院、教室）
  核心案例：近三年 + 屋齡 ≤ 新屋門檻，中位數
  法一 地單價法：地坪 × 核心案例每坪地價（取值區間）
  法二 每房價法：同區、房數最接近的核心案例每房價 × (標的每房地坪 ÷ 案例每房地坪) × 房數
  法三 收益法：滿租年租 × (1 − 空置率 − 費用率) ÷ 資本化率
  最終合理價、建議開價／底價由分析師填在 case.json（判斷值），本檔檢查是否落在三法區間內。
依賴：xlrd、playwright（Chromium 在 /opt/pw-browsers）、字型 WenQuanYi Zen Hei。
"""
import base64, csv, glob, json, re, statistics as st, sys
from pathlib import Path

import xlrd

CASE = Path(sys.argv[1]).resolve()
DIR = CASE.parent
C = json.load(open(CASE, encoding='utf-8'))
BRAND = Path(__file__).resolve().parents[2] / 'skill-sixhands-brand'


# ---------- 1. 讀實登 ----------
def num(s):
    s = str(s).replace(',', '').strip()
    return float(s) if s else 0.0


def ym(s):
    y, m = s.split('/')[:2]
    return int(y) + int(m) / 12


def load(path):
    b = xlrd.open_workbook(path)
    s = b.sheet_by_name('案件列表')
    dist = re.search(r'臺中市(\S+?區)', s.cell_value(0, 0)).group(1)
    land, bld = {}, {}
    for name, store in (('土地', land), ('建物', bld)):
        sh = b.sheet_by_name(name)
        for r in range(1, sh.nrows):
            v = sh.row_values(r)
            store.setdefault(v[0].split('-')[0], []).append(v)
    out = []
    for r in range(2, s.nrows):
        v = s.row_values(r)
        n = v[0]
        m = re.match(r'(\d+)房', v[14])
        if not m:
            continue
        rooms = int(m.group(1))
        bm = re.search(r'(\d+)衛', v[14])
        baths = int(bm.group(1)) if bm else 0
        lands = land.get(n, [])
        blds = bld.get(n, [])
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
        if rooms < C['最少房數']:
            continue
        if baths < rooms * C['房衛比下限']:
            ex = '房衛比低（非套房）'
        elif '旅' in use:
            ex = '旅館'
        la = sum(num(x[2].replace('坪', '')) for x in lands)
        addr = v[1].translate(str.maketrans('０１２３４５６７８９－', '0123456789-'))
        out.append(dict(區=dist, 門牌=addr, 日期=v[3], t=ym(v[3]), 總價=price, 房=rooms, 衛=baths,
                        屋齡=age, 樓高=v[10], 地坪=round(la, 2), 建坪=num(v[6]), 排除=ex,
                        每房=price / rooms, 地每房=la / rooms, 地單價=price / la if la else 0))
    return out


rows = [r for f in C['實登檔'] for r in load(DIR / f)]
rows.sort(key=lambda r: (r['區'], -r['t']))
ok = [r for r in rows if not r['排除']]
win = ym(C['近三年起'])
core = sorted([r for r in ok if r['t'] >= win and r['屋齡'] is not None and r['屋齡'] <= C['新屋門檻']],
              key=lambda r: -r['地單價'])
if not core:
    sys.exit('近三年沒有符合屋齡門檻的新套房成交，請放寬撈取範圍或新屋門檻')
dists = sorted({r['區'] for r in rows})

with open(DIR / '整棟套房_篩選明細.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['區', '門牌', '交易日期', '總價(萬)', '房', '衛', '屋齡', '樓高', '地坪', '建坪', '每房價(萬)', '地坪/房', '地單價(萬/坪)', '核心案例', '排除原因'])
    for r in rows:
        w.writerow([r['區'], r['門牌'], r['日期'], round(r['總價']), r['房'], r['衛'], r['屋齡'], r['樓高'], r['地坪'], r['建坪'],
                    round(r['每房']), round(r['地每房'], 2), round(r['地單價']), '是' if r in core else '', r['排除']])


def band(a):
    if a is None:
        return None
    return '新（≤5 年）' if a <= 5 else '中（6–15 年）' if a <= 15 else '舊（>15 年）'


bands = []
for b in ['新（≤5 年）', '中（6–15 年）', '舊（>15 年）']:
    s = [r for r in ok if band(r['屋齡']) == b]
    if s:
        bands.append((b, len(s), st.median(x['每房'] for x in s), st.median(x['地每房'] for x in s)))

LU = st.median(r['地單價'] for r in core)
lu_lo, lu_hi = C['地單價取值']

# ---------- 2. 三法估價 ----------
for S in C['標的']:
    S['地每房'] = S['地坪'] / S['房']
    S['月租'] = sum(S['租金'].values())
    S['年租'] = S['月租'] * 12 / 10000
    S['均租'] = S['月租'] / len(S['租金'])
    S['淨收'] = S['年租'] * (1 - (C['空置率'] + C['費用率']) / 100)
    S['法一'] = (S['地坪'] * lu_lo, S['地坪'] * lu_hi)
    same = [r for r in core if r['區'] == S['區']] or core
    ref = min(same, key=lambda r: abs(r['房'] - S['房']))
    S['法二參考'] = ref
    S['法二每房'] = ref['每房'] * S['地每房'] / ref['地每房']
    S['法二'] = S['法二每房'] * S['房']
    c_lo, c_hi = C['資本化率']
    S['法三'] = (S['淨收'] / (c_hi / 100), S['淨收'] / (c_lo / 100))
    lo = min(S['法一'][0], S['法二'], S['法三'][0])
    hi = max(S['法一'][1], S['法二'], S['法三'][1])
    S['三法區間'] = (lo, hi)
    S['中值'] = sum(S['合理價']) / 2
    for k in ('合理價',):
        a, b = S[k]
        if a < lo * 0.98 or b > hi * 1.02:
            print(f'⚠️ {S["名稱"]} {k} {a}–{b} 超出三法區間 {lo:.0f}–{hi:.0f}，請確認判斷依據')
    S['毛投報_開'] = S['年租'] / S['開價'] * 100
    S['毛投報_底'] = S['年租'] / S['底價'] * 100
    if S.get('實收'):
        S['實收率'] = S['實收'] / 10000 / S['年租'] * 100

json.dump(dict(地單價中位=LU, 核心案例=[{k: r[k] for k in ('區', '門牌', '日期', '總價', '房', '屋齡', '地坪', '每房', '地每房', '地單價')} for r in core],
               標的=[{k: v for k, v in S.items() if k != '租金'} for S in C['標的']]),
          open(DIR / '估價計算.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
for S in C['標的']:
    print(f"{S['名稱']}：法一 {S['法一'][0]:.0f}–{S['法一'][1]:.0f}｜法二 {S['法二']:.0f}（參考 {S['法二參考']['門牌']}）｜"
          f"法三 {S['法三'][0]:.0f}–{S['法三'][1]:.0f}｜判斷合理價 {S['合理價'][0]}–{S['合理價'][1]}")


# ---------- 3. HTML ----------
def img(p):
    p = Path(p)
    mime = 'image/png' if p.suffix == '.png' else 'image/jpeg'
    return f'data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}'


def w(v):
    return f'{v:,.0f}'


A = C['標的']
NAME = C['案名']
DISC = '永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號'
CONTACT = '助哥 <span class="nw">0925-313-570</span>　｜　LINE @080akczk　｜　sixhands.tw'
QR = (f'<div class="qrs"><div class="qr"><img src="{img(BRAND / "qr_line.png")}"><div>LINE 諮詢</div></div>'
      f'<div class="qr"><img src="{img(BRAND / "qr_web.png")}"><div>官網</div></div></div>')
pages = []


def page(body, n, title=''):
    pages.append(f'<section class="page"><div class="pad">{body}</div>'
                 f'<div class="foot"><div>{DISC}<br><span class="ct">{CONTACT}</span></div>'
                 f'<span>{NAME} 屋主估價報告　{n}</span></div></section>')


# 長條圖：核心案例每坪地價 vs 標的開價／底價
bars = [(f"{r['區']} {re.sub(r'^(北區|中區|南區|西屯區)', '', r['門牌'])[:12]}（{r['房']}房）", r['地單價'], 'c') for r in core]
for S in A:
    bars.append((f"{S['名稱']} 開價", S['開價'] / S['地坪'], 'o'))
    bars.append((f"{S['名稱']} 底價", S['底價'] / S['地坪'], 's'))
bars.sort(key=lambda b: -b[1])
BW, BH, LW = 640, 24 * len(bars) + 34, 210
mx = max(b[1] for b in bars) * 1.12
colors = {'c': '#8a97ab', 'o': '#B8893E', 's': '#1A2942'}
svg = [f'<svg viewBox="0 0 {BW} {BH}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="WenQuanYi Zen Hei" font-size="10.5">']
x_med = LW + LU / mx * (BW - LW - 40)
for i, (lab, v, k) in enumerate(bars):
    y = 8 + i * 24
    ww = v / mx * (BW - LW - 40)
    svg.append(f'<text x="{LW - 8}" y="{y + 13}" text-anchor="end" fill="#333">{lab}</text>'
               f'<rect x="{LW}" y="{y + 2}" width="{ww:.1f}" height="16" rx="2" fill="{colors[k]}"/>'
               f'<text x="{LW + ww + 5:.1f}" y="{y + 14}" fill="#222" font-weight="700">{v:.0f}</text>')
svg.append(f'<line x1="{x_med:.1f}" x2="{x_med:.1f}" y1="4" y2="{BH - 24}" stroke="#a8382e" stroke-dasharray="4 3" stroke-width="1.4"/>'
           f'<text x="{x_med:.1f}" y="{BH - 10}" text-anchor="middle" fill="#a8382e" font-size="10">新套房成交中位數 {LU:.0f} 萬／坪</text></svg>')
chart = ''.join(svg)

# P1 封面
res = ''.join(f'<div class="cbox"><div class="cl">{S["名稱"]}</div><div class="cv">{w(S["合理價"][0])}–{w(S["合理價"][1])}</div>'
              f'<div class="cu">萬元　合理價區間</div><div class="cs">建議開價 {w(S["建議開價"])}　｜　心理價 {w(S["建議底價"])}</div></div>' for S in A)
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
spec_keys = [('地址', '地址'), ('地坪', '地坪'), ('建坪', '建坪'), ('格局', None), ('樓層', '樓層'), ('屋齡', '屋齡'), ('車位', '車位')]
spec = ''
for lab, k in spec_keys:
    vals = []
    for S in A:
        if k is None:
            vals.append(f"{S['房']} 房 {S['衛']} 衛")
        elif k in ('地坪', '建坪'):
            vals.append(f'{S[k]:.2f} 坪')
        else:
            vals.append(str(S[k]).replace('臺中市', ''))
    spec += f'<tr><td>{lab}</td>' + ''.join(f'<td>{v}</td>' for v in vals) + '</tr>'
rent_rows = [
    ('現行開價／心理價', lambda S: f"{w(S['開價'])}／{w(S['底價'])} 萬"),
    ('滿租月租金', lambda S: f"{S['月租'] / 10000:.2f} 萬"),
    ('滿租年租金', lambda S: f"{S['年租']:.1f} 萬"),
    ('平均每間月租', lambda S: f"{S['均租']:,.0f} 元"),
    ('每間月租範圍', lambda S: f"{min(S['租金'].values()) / 10000:.1f}–{max(S['租金'].values()) / 10000:.1f} 萬"),
    ('每房分到的土地', lambda S: f"{S['地每房']:.2f} 坪"),
]
if all(S.get('實收') for S in A):
    rent_rows.insert(-1, ('去年實收', lambda S: f"{S['實收'] / 10000:.1f} 萬"))
rent = ''.join(f'<tr><td>{lab}</td>' + ''.join(f'<td class="num">{fn(S)}</td>' for S in A) + '</tr>' for lab, fn in rent_rows)
head = '<tr><th></th>' + ''.join(f'<th>{S["名稱"]}</th>' for S in A) + '</tr>'
photo = f'<div class="photo"><img src="{img(DIR / C["照片"])}"><div class="cap">標的套房室內實景</div></div>' if C.get('照片') else ''
page(f'''<div class="eyebrow">01　PROPERTY</div><div class="ttl">物件概要</div>
<table class="spec">{head}{spec}</table>
<div class="ttl2">租金收益現況</div>
<table class="spec">{head}{rent}</table>
<div class="sub" style="margin-top:2mm">{C.get('租金說明', '租金以屋主提供之租金表、每間最新一期租金計算。')}</div>
{photo}''', 2)

# P3 市場行情
band_rows = ''.join(f'<tr><td>{b}</td><td class="num">{n}</td><td class="num b">{w(m)} 萬</td><td class="num">{l:.2f} 坪</td></tr>' for b, n, m, l in bands)
core_rows = ''.join(
    f'<tr><td>{r["區"]}</td><td>{re.sub(r"^(北區|中區|南區|西屯區)", "", r["門牌"])}</td><td>{r["日期"]}</td><td class="num">{w(r["總價"])}</td>'
    f'<td class="num">{r["房"]}</td><td class="num">{r["屋齡"]}</td><td class="num">{r["地坪"]:.2f}</td><td class="num">{w(r["每房"])}</td>'
    f'<td class="num">{r["地每房"]:.2f}</td><td class="num b">{w(r["地單價"])}</td></tr>' for r in core)
core_rows += (f'<tr class="hl"><td colspan="7">中位數（{len(core)} 筆）</td><td class="num">{w(st.median(r["每房"] for r in core))}</td>'
              f'<td></td><td class="num">{LU:.0f}</td></tr>')
page(f'''<div class="eyebrow">02　MARKET</div><div class="ttl">市場行情：同類整棟套房成交</div>
<div class="sub">撈取 {'、'.join(dists)} 實價登錄（{C['撈取條件']}），篩出格局 ≥{C['最少房數']} 房、且衛浴數 ≥ 房數 × {C['房衛比下限']} 的整棟套房，
排除旅館、宿舍、醫院等非套房物件，有效樣本 <b>{len(ok)} 筆</b>（全部 ≥{C['最少房數']} 房物件 {len(rows)} 筆）。</div>
<table><tr><th>屋齡</th><th class="num">筆數</th><th class="num">每房價中位數</th><th class="num">每房地坪中位數</th></tr>{band_rows}</table>
<div class="note" style="margin-top:3mm"><b>為什麼不能只看「總價 ÷ 房數」？</b>　舊樓的每房價反而比新樓高，因為舊樓房數少、每房分到的土地多，
整棟透天的價值大部分在土地。所以本報告以<b>每坪土地價</b>為主要比較基準，每房價則依「每房分到幾坪地」校正。</div>
<div class="ttl2">核心比較案例（{C['近三年起']} 以後成交、屋齡 ≤{C['新屋門檻']} 年）</div>
<table><tr><th>區</th><th>門牌</th><th>成交</th><th class="num">總價(萬)</th><th class="num">房</th><th class="num">屋齡</th><th class="num">地坪</th>
<th class="num">每房(萬)</th><th class="num">地/房</th><th class="num">每坪地價</th></tr>{core_rows}</table>
<div class="ttl2">每坪土地價比較（萬元／坪）</div>{chart}''', 3)


# P4/P5 各棟估價
def val_page(S, n):
    ref = S['法二參考']
    m = f'''<table><tr><th>方法</th><th>計算</th><th class="num">結果（萬）</th></tr>
<tr><td class="b">法一　每坪地價法</td><td>地坪 {S['地坪']:.2f} 坪 × 每坪地價 {lu_lo}–{lu_hi} 萬<br><span class="gr">取近三年新套房成交中位數 {LU:.0f} 萬附近</span></td>
<td class="num b">{w(S['法一'][0])}–{w(S['法一'][1])}</td></tr>
<tr><td class="b">法二　每房價法</td><td>參考 {ref['區']}{re.sub(r"^(北區|中區|南區|西屯區)", "", ref['門牌'])}（{ref['日期']}，{ref['房']} 房，每房 {w(ref['每房'])} 萬，每房地坪 {ref['地每房']:.2f}）<br>
<span class="gr">本棟每房地坪 {S['地每房']:.2f} → 校正 {(S['地每房'] / ref['地每房'] - 1) * 100:+.0f}% → 每房約 {w(S['法二每房'])} 萬 × {S['房']} 房</span></td>
<td class="num b">{w(S['法二'])}</td></tr>
<tr><td class="b">法三　收益法</td><td>滿租年租 {S['年租']:.1f} 萬 × (1 − {'空置 ' + str(C['空置率']) + '% − ' if C['空置率'] else ''}費用 {C['費用率']}%) = 淨收 {S['淨收']:.0f} 萬<br>
<span class="gr">÷ 資本化率 {C['資本化率'][0]}%–{C['資本化率'][1]}%（推估值）</span></td>
<td class="num b">{w(S['法三'][0])}–{w(S['法三'][1])}</td></tr>
<tr class="hl"><td colspan="2">三法區間　→　合理價判斷</td><td class="num">{w(S['合理價'][0])}–{w(S['合理價'][1])}</td></tr></table>'''
    k = f'''<div class="kpi">
<div><div class="v">{w(S['合理價'][0])}–{w(S['合理價'][1])}</div><div class="u">萬元</div><div class="l">合理價區間</div></div>
<div><div class="v">{w(S['建議開價'])}</div><div class="u">萬元</div><div class="l">建議開價（現行 {w(S['開價'])}）</div></div>
<div><div class="v">{w(S['建議底價'])}</div><div class="u">萬元</div><div class="l">建議心理價（現行 {w(S['底價'])}）</div></div>
<div><div class="v">{S['年租'] / S['建議底價'] * 100:.2f}%</div><div class="u">滿租毛投報</div><div class="l">以建議心理價計</div></div></div>'''
    extra = ''
    if S is A[-1] and len(A) > 1:
        o = A[0]
        cmp_rows = [
            ('心理價', lambda X: f"{w(X['底價'])} 萬"),
            ('每坪地價（心理價）', lambda X: f"{X['底價'] / X['地坪']:.0f} 萬"),
            ('每房價（心理價）', lambda X: f"{X['底價'] / X['房']:.0f} 萬"),
            ('每房分到的土地', lambda X: f"{X['地每房']:.2f} 坪"),
            ('平均每間月租', lambda X: f"{X['均租'] / 10000:.2f} 萬"),
            ('滿租毛投報（心理價）', lambda X: f"{X['毛投報_底']:.2f}%"),
        ]
        extra = ('<div class="ttl2">買方會怎麼比：與隔壁 ' + o['名稱'] + '</div><table><tr><th></th>' +
                 ''.join(f'<th class="num">{X["名稱"]}</th>' for X in (o, S)) + '</tr>' +
                 ''.join(f'<tr><td>{lab}</td>' + ''.join(f'<td class="num">{fn(X)}</td>' for X in (o, S)) + '</tr>' for lab, fn in cmp_rows) + '</table>')
    judg = ''.join(f'<li>{t}</li>' for t in S['判讀'])
    page(f'''<div class="eyebrow">0{n - 1}　VALUATION</div><div class="ttl">{S['名稱']} 估價</div>
<div class="sub">{S['地址']}｜地坪 {S['地坪']:.2f} 坪｜{S['房']} 房 {S['衛']} 衛｜{S['屋齡']}｜現行開價 {w(S['開價'])} 萬、心理價 {w(S['底價'])} 萬</div>
{k}{m}{extra}<div class="ttl2">判讀</div><ul>{judg}</ul>''', n)


for i, S in enumerate(A):
    val_page(S, 4 + i)

# 末頁：售價策略 + 限制 + 聯絡
N = 4 + len(A)
plan = ''.join(f'<tr><td class="b">{S["名稱"]}</td><td class="num">{w(S["開價"])}／{w(S["底價"])}</td><td class="num">{w(S["合理價"][0])}–{w(S["合理價"][1])}</td>'
               f'<td class="num b">{w(S["建議開價"])}／{w(S["建議底價"])}</td><td class="num">{(S["開價"] / S["中值"] - 1) * 100:+.0f}%</td></tr>' for S in A)
adv = ''.join(f'<li>{t}</li>' for t in C['銷售建議'])
lim = ''.join(f'<li>{t}</li>' for t in C['限制'])
page(f'''<div class="eyebrow">0{N - 1}　STRATEGY</div><div class="ttl">售價策略建議</div>
<table><tr><th>棟別</th><th class="num">現行 開價／心理價</th><th class="num">合理價區間</th><th class="num">建議 開價／心理價</th><th class="num">現行開價 vs 合理中值</th></tr>{plan}</table>
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
