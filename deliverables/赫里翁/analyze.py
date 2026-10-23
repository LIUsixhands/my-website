"""赫里翁 實登清洗 — 走小登管線（.claude/skills/skill-xiao-deng/references/實登批次處理管線.py）。
口徑：扣車位重算淨單價（車位價未揭露者以本社區坡道平面每席中位估算）、排除特殊關係與債務抵償、
排除車位未登記或非整戶的異常筆；產品依門牌「之幾」分型（棟別圖：A1 之1、A2 之2、A3 之3、B1 之5、B2 之6、B3 之7）。
對外行情只走 headline()：中位數、含車／不含車並列。
比較組：西屯區・大樓／華廈・屋齡 10–20 年・總面積 70–100 坪・113/01–115/10，再依鐵律 8 卡「扣車位面積 ±5 坪」。"""
import sys, json, csv, statistics as st
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / '.claude/skills/skill-xiao-deng/references'))
import 實登批次處理管線 as P
import xlrd

Z2H = str.maketrans('０１２３４５６７８９', '0123456789')
CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7}
F_BUY = '實登_青海路二段188號_買賣.xls'
F_RENT = '實登_青海路二段188號_租賃.xls'
F_CMP = '實登_比較組_西屯區大樓華廈_屋齡10-20_70-100坪_113-115.xls'

def unit_of(addr):
    a = addr.translate(Z2H).replace('-', '之')
    tail = a.split('之')[-1] if '之' in a else ''
    return CN.get(tail[:1]) or (int(tail[:1]) if tail[:1].isdigit() else None)

# 棟別圖（樂居）：A 棟臨弘孝路側、B 棟臨西屯路二段249-9巷側；本戶 20樓之6＝B2
TOWER = {1: 'A1', 2: 'A2', 3: 'A3', 5: 'B1', 6: 'B2', 7: 'B3'}
MID = '三房中坪（之3・之6・之7）'
BIG = '四房大坪（之1・之2・之5）'
TYPES = (MID, BIG)
def ptype(u): return MID if u in (3, 6, 7) else BIG

def med(v): return round(st.median(v), 2) if v else None
def note_of(x): return x['note'].replace('\n', ' ').strip()

def layout_map(path):
    sh = xlrd.open_workbook(str(path), encoding_override='cp950').sheet_by_name('案件列表')
    return {str(sh.cell_value(r, 0)).strip(): (str(sh.cell_value(r, 9)).strip(), str(sh.cell_value(r, 14)).strip()) for r in range(2, sh.nrows)}

# ---------- 社區買賣 ----------
_, raw = P.load(str(HERE / F_BUY))
LAY = layout_map(HERE / F_BUY)
keep, drop = P.clean(raw)
ok = []
for x in keep:
    if '債務' in x['note']: drop.append(('債務抵償', x)); continue
    if x['npark'] == 0: drop.append(('車位未登記（總坪數疑含車位）', x)); continue
    if x['area'] < 80: drop.append(('面積異常（非整戶）', x)); continue
    ok.append(x)
rows, MA, MV = P.recompute(ok)
for x in rows:
    x['u'] = unit_of(x['addr'])
    x['tower'] = TOWER.get(x['u'], '?')
    x['gross'] = x['tot'] / x['area']
    x['type'] = ptype(x['u'])
    x['split'] = bool(x['pkv_row'] or x['pk_val'])
    x['layout'] = LAY.get(x['no'], ('', ''))[1]

park_recent = [(x['pkv_row'] or x['pk_val']) / x['npark'] for x in rows if x['split'] and x['npark'] and x['yr'] >= 110]
out = dict(撈取日='2026-10-23', 查詢區間='101/01–115/10', 原始筆數=len(raw),
           排除=[dict(原因=w, 日期=x['date'], 樓層=x['fl'], 戶=TOWER.get(unit_of(x['addr']), '?'), 總價=x['tot']) for w, x in drop],
           有效筆數=len(rows),
           車位=dict(類別='坡道平面', 每席面積中位=round(MA, 2), 每席價格中位_全期=round(MV, 1),
                   每席價格中位_110後=med(park_recent), 揭露筆數_110後=len(park_recent)))
out['近三年'] = P.headline(rows, window=(113, 115), name='赫里翁 近三年')
out['近五年'] = P.headline(rows, window=(111, 115), name='赫里翁 111–115')
out['全期_參考'] = P.headline(rows, allow_full=True, name='赫里翁 全期')
SAME = [x for x in rows if x['type'] == MID]
out['同型_近三年'] = P.headline(SAME, window=(113, 115), name='三房中坪 113–115')
out['同型_近五年'] = P.headline(SAME, window=(111, 115), name='三房中坪 111–115')
B2 = [x for x in rows if x['u'] == 6]
out['B2_明細'] = [dict(日期=x['date'], 樓層=x['fl'], 總價=x['tot'], 坪數=x['area'], 車位=x['npark'], 不含車=round(x['val'], 2), 含車=round(x['gross'], 2))
                for x in sorted(B2, key=lambda x: x['date'])]
out['年度'] = [dict(年=y, n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g]))
              for y in sorted({x['yr'] for x in rows}) for g in [[x for x in rows if x['yr'] == y]]]
out['產品'] = []
for t in TYPES:
    g = [x for x in rows if x['type'] == t]; g3 = [x for x in g if x['yr'] >= 113]; g5 = [x for x in g if x['yr'] >= 111]
    out['產品'].append(dict(型=t, 全期n=len(g), 近三年n=len(g3), 近五年n=len(g5),
                          近三年不含車中位=med([x['val'] for x in g3]), 近三年含車中位=med([x['gross'] for x in g3]),
                          近五年不含車中位=med([x['val'] for x in g5]), 近五年含車中位=med([x['gross'] for x in g5]),
                          扣車位面積中位=med([x['base'] for x in g]), 總面積中位=med([x['area'] for x in g])))
cuts = [(2, 9, '低樓層 2–9F'), (10, 17, '中樓層 10–17F'), (18, 25, '高樓層 18–25F')]
out['樓層帶_110後'] = []
for lo, hi, nm in cuts:
    g = [x for x in rows if lo <= x['fl'] <= hi and x['yr'] >= 110]
    out['樓層帶_110後'].append(dict(帶=nm, n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g])))

# ---------- 社區租賃 ----------
rent = []
for x in P.load(str(HERE / F_RENT))[1]:
    u = unit_of(x['addr'])
    rent.append(dict(日期=x['date'], 戶=TOWER.get(u, '?'), 樓層=x['fl'], 月租萬=x['tot'], 面積坪=x['area'], 車位=x['npark'],
                     每坪元=round(x['tot'] * 10000 / x['area']), 備註=note_of(x)[:40]))
rent.sort(key=lambda r: r['日期'], reverse=True)
# 13樓之3 106/11 月租 15.8 萬、51.08 坪（每坪 3,093 元）為登錄異常，不計入中位
norm = [r for r in rent if r['每坪元'] < 2000]
out['租賃'] = dict(筆數=len(rent), 明細=rent, 近三年筆數=sum(int(r['日期'][:3]) >= 113 for r in rent),
                 最新=rent[0]['日期'], 排除異常後月租中位=med([r['月租萬'] for r in norm]),
                 排除異常後每坪中位_元=round(st.median([r['每坪元'] for r in norm])))

# ---------- 本戶 ----------
PK = MV                                                     # 社區坡道平面每席中位（實登揭露）
L = dict(門牌='青海路二段188號20樓之6', 棟='B2', 樓層=20, 總樓層=25, 開價=3860, 總面積=89.46, 主建物=49.362, 附屬=7.269,
         陽台=5.227, 雨遮=2.042, 共同=32.829, 車位面積=6.055, 車位數=1, 車位='坡道平面 1 席（編號 155）', 格局='3房2廳2衛',
         土地=6.414, 管理費季=20016, 朝向='西南', 屋齡=15.8, 物件編號='1922816', 登記日期='100/04/29')
L['扣車位面積'] = round(L['總面積'] - L['車位面積'], 2)
L['車位估價'] = round(PK * L['車位數'])
L['含車單價'] = round(L['開價'] / L['總面積'], 2)
L['不含車單價'] = round((L['開價'] - L['車位估價']) / L['扣車位面積'], 2)
out['本戶'] = L
BASE = L['扣車位面積']

# ---------- 比較組 ----------
_, cmp_raw = P.load(str(HERE / F_CMP))
CL = layout_map(HERE / F_CMP)
ck, cd = P.clean(cmp_raw)
crow, cMA, cMV = P.recompute(ck)
for x in crow:
    x['gross'] = x['tot'] / x['area']
    x['self'] = '青海路二段１８８號' in x['addr']
    x['ground'] = x['fl'] in (None, 1)
others = [x for x in crow if not x['self'] and not x['ground']]
band = [x for x in others if BASE - 5 <= x['base'] <= BASE + 5]
out['比較組'] = dict(條件='西屯區・大樓／華廈・屋齡10–20年・總面積70–100坪・113/01–115/10', 原始=len(cmp_raw), 排除特殊關係=len(cd),
                  有效=len(crow), 本社區筆數=sum(x['self'] for x in crow), 一樓排除=sum(x['ground'] for x in crow),
                  級距=f'扣車位面積 {BASE-5:.1f}–{BASE+5:.1f} 坪',
                  全部_不含本社區=P.headline(others, window=(113, 115), name='西屯比較組（不含本社區）'),
                  同級距=P.headline(band, window=(113, 115), name='西屯比較組 同級距'),
                  明細=[dict(日期=x['date'], 社區=x['name'] or '—', 屋齡=CL.get(x['no'], ('', ''))[0], 門牌=x['addr'].split('區')[-1], 樓層=x['fl'], 總價=x['tot'],
                            坪數=x['area'], 扣車位=round(x['base'], 2), 車位=x['npark'], 車位類別='／'.join(dict.fromkeys(x['kinds'])),
                            車位價=round(x['pkv_row'] or x['pk_val'] or 0) or None, 不含車=round(x['val'], 2), 含車=round(x['gross'], 2),
                            本社區=x['self'], 同級距=x in band) for x in sorted(crow, key=lambda x: x['date'], reverse=True) if not x['ground']])
# 同級距依社區彙整（同社區多筆者看得出群聚）
by = {}
for x in band:
    by.setdefault(x['name'] or '（未填社區名）', []).append(x)
out['比較組']['同級距_社區'] = sorted([dict(社區=k, n=len(v), 不含車中位=med([x['val'] for x in v]), 含車中位=med([x['gross'] for x in v]))
                                 for k, v in by.items()], key=lambda d: -d['n'])

with open(HERE / 'transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['交易日期', '戶別', '樓層', '產品', '總價萬', '總面積坪', '車位數', '車位面積坪', '車位價萬', '車位價來源', '扣車位面積坪', '含車單價', '不含車單價', '格局', '備註'])
    for x in sorted(rows, key=lambda x: x['date'], reverse=True):
        pv = (x['pkv_row'] or x['pk_val']) if x['split'] else round(x['npark'] * MV)
        w.writerow([x['date'], x['tower'], x['fl'], x['type'], x['tot'], x['area'], x['npark'], round(x['pk_area'], 2), round(pv),
                    '實登揭露' if x['split'] else '估算(坡道平面中位)', round(x['base'], 2), round(x['gross'], 2),
                    round(x['val'], 2), x['layout'], note_of(x)])
json.dump(out, open(HERE / 'summary.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in out.items() if k != '比較組'}, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in out['比較組'].items() if k != '明細'}, ensure_ascii=False, indent=1))
for r in out['比較組']['明細']:
    if r['同級距']: print(r)
