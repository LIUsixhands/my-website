"""百達艷麗 實登清洗 — 走小登管線（.claude/skills/skill-xiao-deng/references/實登批次處理管線.py）。
口徑：扣車位重算淨單價（車位價未揭露者以本社區坡道平面每席中位估算）、排除特殊關係；
產品依門牌「之幾」分型（之1／之2＝臨臺灣大道端戶，之3／之5＝內側戶）；對外行情只走 headline()：中位數、含車／不含車並列。
比較組：西區・大樓／華廈・屋齡 10–20 年・總面積 80–110 坪・112/10–115/10，再依鐵律 8 卡「扣車位面積 ±5 坪」。"""
import sys, json, csv, statistics as st
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / '.claude/skills/skill-xiao-deng/references'))
import 實登批次處理管線 as P
import xlrd

Z2H = str.maketrans('０１２３４５６７８９', '0123456789')
CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5}
F_BUY = '實登_臺灣大道二段419號_買賣.xls'
F_CMP = '實登_比較組_西區大樓華廈_屋齡10-20_80-110坪_112-115.xls'

def unit_of(addr):
    a = addr.translate(Z2H)
    tail = a.split('之')[-1] if '之' in a else ''
    return CN.get(tail[:1]) or (int(tail[:1]) if tail[:1].isdigit() else None)

# 棟別圖（樂居／591）：之1＝A、之2＝B（79.82P，臨臺灣大道）；之3＝C、之5＝D（74.94P）
TOWER = {1: 'A', 2: 'B', 3: 'C', 5: 'D'}
def ptype(x):
    if x['fl'] == 12 and x['area'] > 150: return '頂樓大戶'
    return '端戶 A／B（之1・之2）' if x['u'] in (1, 2) else '內側戶 C／D（之3・之5）'
TYPES = ('端戶 A／B（之1・之2）', '內側戶 C／D（之3・之5）', '頂樓大戶')

def age_map(path):
    sh = xlrd.open_workbook(str(path), encoding_override='cp950').sheet_by_name('案件列表')
    return {str(sh.cell_value(r, 0)).strip(): str(sh.cell_value(r, 9)).strip() for r in range(2, sh.nrows)}

def med(v): return round(st.median(v), 2) if v else None

# ---------- 社區買賣 ----------
_, raw = P.load(str(HERE / F_BUY))
keep, drop = P.clean(raw)
rows, MA, MV = P.recompute(keep)
for x in rows:
    x['u'] = unit_of(x['addr'])
    x['tower'] = TOWER.get(x['u'], '?')
    x['gross'] = x['tot'] / x['area']
    x['type'] = ptype(x)
    x['split'] = bool(x['pkv_row'] or x['pk_val'])

park_recent = [(x['pkv_row'] or x['pk_val']) / x['npark'] for x in rows if x['split'] and x['npark'] and x['yr'] >= 110]
out = dict(撈取日='2026-10-23', 查詢區間='101/01–115/10', 原始筆數=len(raw),
           排除=[dict(原因=w, 日期=x['date'], 樓層=x['fl'], 總價=x['tot']) for w, x in drop], 有效筆數=len(rows),
           車位=dict(類別='坡道平面', 每席面積中位=round(MA, 2), 每席價格中位_全期=round(MV, 1),
                   每席價格中位_110後=med(park_recent), 揭露筆數_110後=len(park_recent)))
out['近三年'] = P.headline(rows, window=(113, 115), name='百達艷麗 近三年')
out['近五年'] = P.headline(rows, window=(111, 115), name='百達艷麗 111–115')
out['全期_參考'] = P.headline(rows, allow_full=True, name='百達艷麗 全期')
SAME = [x for x in rows if x['type'] == TYPES[0]]
out['同型_近三年'] = P.headline(SAME, window=(113, 115), name='同型端戶 113–115')
out['同型_近六年'] = P.headline(SAME, window=(110, 115), name='同型端戶 110–115')
out['年度'] = [dict(年=y, n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g]))
              for y in sorted({x['yr'] for x in rows}) for g in [[x for x in rows if x['yr'] == y]]]
out['產品'] = []
for t in TYPES:
    g = [x for x in rows if x['type'] == t]; g3 = [x for x in g if x['yr'] >= 113]
    out['產品'].append(dict(型=t, 全期n=len(g), 近三年n=len(g3), 近三年不含車中位=med([x['val'] for x in g3]),
                          近三年含車中位=med([x['gross'] for x in g3]), 扣車位面積中位=med([x['base'] for x in g]),
                          總面積中位=med([x['area'] for x in g])))
cuts = [(2, 6, '低樓層 2–6F'), (7, 12, '中高樓層 7–12F')]
out['樓層帶_110後'] = []
for lo, hi, nm in cuts:
    g = [x for x in rows if lo <= x['fl'] <= hi and x['yr'] >= 110]
    out['樓層帶_110後'].append(dict(帶=nm, n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g])))

# ---------- 社區租賃 ----------
rent = []
for x in P.load(str(HERE / '實登_臺灣大道二段419號_租賃.xls'))[1]:
    u = unit_of(x['addr'])
    whole = x['area'] >= 70 and not any(k in x['note'] for k in ('套房', '雅房', '分租', '部分範圍'))
    rent.append(dict(日期=x['date'], 戶=TOWER.get(u, '?'), 樓層=x['fl'], 月租萬=x['tot'], 面積坪=x['area'], 車位=x['npark'],
                     整戶=whole, 每坪元=round(x['tot'] * 10000 / x['area']), 備註=x['note'].replace('\n', ' ')[:30]))
rent.sort(key=lambda r: r['日期'], reverse=True)
rw = [r for r in rent if r['整戶']]
r3 = [r for r in rw if int(r['日期'][:3]) >= 113]
out['租賃'] = dict(筆數=len(rent), 明細=rent, 近三年整戶=r3, 整戶全期月租中位=med([r['月租萬'] for r in rw]),
                 整戶全期每坪中位_元=round(st.median([r['每坪元'] for r in rw])) if rw else None,
                 近三年整戶每坪中位_元=round(st.median([r['每坪元'] for r in r3])) if r3 else None)

# ---------- 本戶 ----------
PK = MV                                                     # 社區坡道平面每席中位（揭露 7 筆；110 後僅 3 筆，不單獨採用）
L = dict(門牌='臺灣大道二段419號11樓之2', 棟='B', 樓層=11, 總樓層=12, 開價=3998, 總面積=98.37, 主建物=46.355, 附屬=5.197,
         共同=46.818, 車位面積=22.48, 車位數=2, 車位='坡道平面 B2-40、41（2 席）', 格局='4房2廳3衛（雙主臥）',
         土地=9.347, 管理費季=26967)
L['扣車位面積'] = round(L['總面積'] - L['車位面積'], 2)
L['車位估價'] = round(PK * L['車位數'])
L['含車單價'] = round(L['開價'] / L['總面積'], 2)
L['不含車單價'] = round((L['開價'] - L['車位估價']) / L['扣車位面積'], 2)
out['本戶'] = L
BASE = L['扣車位面積']

# ---------- 比較組 ----------
_, cmp_raw = P.load(str(HERE / F_CMP))
AGE = age_map(HERE / F_CMP)
ck, cd = P.clean(cmp_raw)
crow, cMA, cMV = P.recompute(ck)
for x in crow:
    x['gross'] = x['tot'] / x['area']
    x['self'] = '臺灣大道二段４１９號' in x['addr']
    x['ground'] = x['fl'] in (None, 1)                         # 一樓含騎樓（青峰錦），屬店面性質
others = [x for x in crow if not x['self'] and not x['ground']]
band = [x for x in others if BASE - 5 <= x['base'] <= BASE + 5]
out['比較組'] = dict(條件='西區・大樓／華廈・屋齡10–20年・總面積80–110坪・112/10–115/10', 原始=len(cmp_raw), 排除特殊關係=len(cd),
                  有效=len(crow), 本社區筆數=sum(x['self'] for x in crow), 一樓排除=sum(x['ground'] for x in crow),
                  級距=f'扣車位面積 {BASE-5:.1f}–{BASE+5:.1f} 坪',
                  全部_不含本社區=P.headline(others, window=(112, 115), name='西區比較組（不含本社區）'),
                  同級距=P.headline(band, window=(112, 115), name='西區比較組 同級距'),
                  明細=[dict(日期=x['date'], 社區=x['name'] or '—', 屋齡=AGE.get(x['no'], ''), 門牌=x['addr'].split('區')[-1], 樓層=x['fl'], 總價=x['tot'],
                            坪數=x['area'], 扣車位=round(x['base'], 2), 車位=x['npark'], 車位類別='／'.join(dict.fromkeys(x['kinds'])),
                            車位價=round(x['pkv_row'] or x['pk_val'] or 0) or None, 不含車=round(x['val'], 2), 含車=round(x['gross'], 2),
                            本社區=x['self'], 同級距=x in band) for x in sorted(crow, key=lambda x: x['date'], reverse=True) if not x['ground']])

with open(HERE / 'transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['交易日期', '棟別', '樓層', '產品', '總價萬', '總面積坪', '車位數', '車位面積坪', '車位價萬', '車位價來源', '扣車位面積坪', '含車單價', '不含車單價', '格局', '備註'])
    for x in sorted(rows, key=lambda x: x['date'], reverse=True):
        pv = (x['pkv_row'] or x['pk_val']) if x['split'] else round(x['npark'] * MV)
        w.writerow([x['date'], x['tower'], x['fl'], x['type'], x['tot'], x['area'], x['npark'], round(x['pk_area'], 2), round(pv),
                    '實登揭露' if x['split'] else '估算(坡道平面中位)', round(x['base'], 2), round(x['gross'], 2),
                    round(x['val'], 2), '', x['note'].replace('\n', ' ').strip()])
json.dump(out, open(HERE / 'summary.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in out.items() if k != '比較組'}, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in out['比較組'].items() if k != '明細'}, ensure_ascii=False, indent=1))
for r in out['比較組']['明細']: print(r)
