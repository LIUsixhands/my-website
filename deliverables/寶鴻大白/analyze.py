"""寶鴻大白 實登清洗 — 走小登管線（.claude/skills/skill-xiao-deng/references/實登批次處理管線.py）。
口徑：扣車位重算淨單價、排除特殊關係；3 號／5 號兩門牌合併；產品依「扣車位面積」分型；對外行情只走 headline()。
車位價未揭露者：以本社區 110 年後揭露之坡道平面每席中位估算（取代管線預設的全期中位，避免用到 107–109 年舊車位價）。
比較組：西區・華廈＋住宅大樓・屋齡 5–10 年・總面積 70–100 坪・112/01–115/10；排除 1 樓／店面與特殊關係；
同坪數級距（鐵律 8）：扣車位面積 本戶 ±5 坪。"""
import sys, json, csv, statistics as st
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / '.claude/skills/skill-xiao-deng/references'))
import 實登批次處理管線 as P

def med(v): return round(st.median(v), 2) if v else None

def ptype(x):
    if x['npark'] >= 5: return '2F 五車位（特例）'                # 111/07 5號2F：一次買 5 席，車位坪數未揭露，扣車位面積估不準
    return '三房四衛（約 62 坪）' if x['base'] >= 55 else '頂樓層小坪（約 40–50 坪）'

def bldg(addr): return '3號' if '５５巷３號' in addr or '55巷3號' in addr else '5號'

def reprice(rows, pk):
    """未揭露車位價者，改以 pk（每席）重算淨單價。"""
    for x in rows:
        x['split'] = bool(x['pk_val'] or x['pkv_row'])
        x['pv'] = x['pk_val'] or x['pkv_row'] or x['npark'] * pk
        x['pa'] = x['pk_area'] if x['pk_area'] > 0 else None
        x['val'] = (x['tot'] - x['pv']) / x['base']
        x['gross'] = x['tot'] / x['area']
    return rows

# ---------- 社區買賣 ----------
raw = []
for f in ('實登_五權三街55巷3號_買賣.xls', '實登_五權三街55巷5號_買賣.xls'):
    raw += P.load(str(HERE / f))[1]
keep, drop = P.clean(raw)
rows, MA, MV = P.recompute(keep)
disc = [(x['pk_val'] or x['pkv_row']) / x['npark'] for x in rows if (x['pk_val'] or x['pkv_row']) and x['npark']]
disc110 = [(x['pk_val'] or x['pkv_row']) / x['npark'] for x in rows if (x['pk_val'] or x['pkv_row']) and x['npark'] and x['yr'] >= 110]
PK = st.median(disc110)
reprice(rows, PK)
for x in rows:
    x['b'] = bldg(x['addr']); x['type'] = ptype(x)

out = dict(撈取日='2026-10-23', 查詢區間='101/01–115/10', 原始筆數=len(raw),
           排除=[dict(原因=w, 日期=x['date'], 樓層=x['fl'], 總價=x['tot']) for w, x in drop], 有效筆數=len(rows),
           車位=dict(類別='坡道平面', 每席面積中位=round(MA, 2), 每席價格中位_全期=round(st.median(disc), 1),
                   每席價格中位_110後=round(PK, 1), 揭露筆數_全期=len(disc), 揭露筆數_110後=len(disc110)))
MAIN = [x for x in rows if x['type'].startswith('三房')]
out['同型_近三年'] = P.headline(MAIN, window=(113, 115), name='三房四衛 113–115')
out['同型_近四年'] = P.headline(MAIN, window=(112, 115), name='三房四衛 112–115')
out['同型_近五年'] = P.headline(MAIN, window=(111, 115), name='三房四衛 111–115')
out['全社區_近四年'] = P.headline(rows, window=(112, 115), name='全社區 112–115')
out['年度'] = [dict(年=y, n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g]),
                  總價中位=med([x['tot'] for x in g]))
              for y in sorted({x['yr'] for x in MAIN}) for g in [[x for x in MAIN if x['yr'] == y]]]
out['產品'] = []
for t in ('三房四衛（約 62 坪）', '頂樓層小坪（約 40–50 坪）', '2F 五車位（特例）'):
    g = [x for x in rows if x['type'] == t]; g4 = [x for x in g if x['yr'] >= 112]
    out['產品'].append(dict(型=t, 全期n=len(g), 近四年n=len(g4), 近四年不含車中位=med([x['val'] for x in g4]),
                          近四年含車中位=med([x['gross'] for x in g4]), 總面積中位=med([x['area'] for x in g]),
                          扣車位面積中位=med([x['base'] for x in g])))
out['樓層帶_同型_110後'] = []
for lo, hi, nm in [(2, 4, '低樓層 2–4F'), (5, 8, '中高樓層 5–8F')]:
    g = [x for x in MAIN if lo <= x['fl'] <= hi and x['yr'] >= 110]
    out['樓層帶_同型_110後'].append(dict(帶=nm, n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g])))

# ---------- 比較組 ----------
CF = '實登_比較組_西區大樓華廈_屋齡5-10_70-100坪_112-115.xls'
_, craw = P.load(str(HERE / CF))
ck, cd = P.clean(craw)
cd = [(w, x) for w, x in cd]
for x in list(ck):
    if not x['fl']:
        ck.remove(x); cd.append(('跨層（含 1 樓店面／樓中樓）', x))
    elif x['fl'] == 1:
        ck.remove(x); cd.append(('1 樓／店面', x))
crow, _, _ = P.recompute(ck)
cdisc = [(x['pk_val'] or x['pkv_row']) / x['npark'] for x in crow if (x['pk_val'] or x['pkv_row']) and x['npark']]
CPK = st.median(cdisc)
reprice(crow, CPK)
import xlrd
_sh = xlrd.open_workbook(str(HERE / CF), encoding_override='cp950').sheet_by_name('案件列表')
AGE = {str(_sh.cell_value(r, 0)).strip(): str(_sh.cell_value(r, 9)).strip() for r in range(2, _sh.nrows)}
for x in crow: x['self'] = '五權三街５５巷' in x['addr']
others = [x for x in crow if not x['self']]
L = dict(門牌='五權三街55巷3號8樓', 樓層=8, 總樓層=10, 開價=3888, 總面積=86.61, 主建物=36.10, 附屬=5.71, 公設=44.79,
         車位面積=24.17, 車位數=2, 車位='坡道平面 2 席・B1 連號（B1-34A、35）', 格局='3房2廳4衛', 管理費=8400, 合約='AG1978559')
L['扣車位面積'] = round(L['總面積'] - L['車位面積'], 2)
BAND = (L['扣車位面積'] - 5, L['扣車位面積'] + 5)
band = [x for x in others if BAND[0] <= x['base'] <= BAND[1]]
out['比較組'] = dict(條件='西區・華廈／住宅大樓・屋齡5–10年・總面積70–100坪・112/01–115/10', 原始=len(craw),
                  排除=[dict(原因=w, 門牌=x['addr'].split('區')[-1], 日期=x['date']) for w, x in cd], 有效=len(crow),
                  本社區筆數=sum(x['self'] for x in crow), 車位每席中位=round(CPK, 1), 車位揭露筆數=len(cdisc),
                  不含本社區=P.headline(others, window=(112, 115), name='西區比較組（不含本社區）'),
                  近三年_不含本社區=P.headline([x for x in others if x['yr'] >= 113], window=(113, 115), name='西區比較組 113–115'),
                  同級距=dict(扣車位面積=f'{BAND[0]:.1f}–{BAND[1]:.1f}', **P.headline(band, window=(112, 115), name='同級距', min_n=5)),
                  年度_不含本社區=[dict(年=y, n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g]))
                              for y in range(112, 116) for g in [[x for x in others if x['yr'] == y]]],
                  年度_同級距=[dict(年=y, n=len(g), 不含車中位=med([x['val'] for x in g])) for y in range(112, 116) for g in [[x for x in band if x['yr'] == y]]],
                  明細=[dict(日期=x['date'], 社區=x['name'] or '—', 屋齡=AGE.get(x['no'], ''), 門牌=x['addr'].split('區')[-1], 樓層=x['fl'],
                            總價=x['tot'], 坪數=x['area'], 扣車位坪數=round(x['base'], 2), 車位=x['npark'], 車位價=round(x['pv']),
                            揭露=x['split'], 不含車=round(x['val'], 2), 含車=round(x['gross'], 2), 本社區=x['self'],
                            同級距=BAND[0] <= x['base'] <= BAND[1]) for x in sorted(others, key=lambda x: x['date'], reverse=True)])

# ---------- 本戶 ----------
L['車位估價'] = round(PK * L['車位數'], 1)
L['含車單價'] = round(L['開價'] / L['總面積'], 2)
L['不含車單價'] = round((L['開價'] - L['車位估價']) / L['扣車位面積'], 2)
out['本戶'] = L

with open(HERE / 'transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['交易日期', '門牌', '樓層', '產品', '總價萬', '總面積坪', '車位數', '車位價萬', '車位價來源', '扣車位面積坪', '含車單價', '不含車單價', '備註'])
    for x in sorted(rows, key=lambda x: x['date'], reverse=True):
        w.writerow([x['date'], x['b'], x['fl'], x['type'], x['tot'], x['area'], x['npark'], round(x['pv']),
                    '實登揭露' if x['split'] else '估算(110後每席中位)', round(x['base'], 2), round(x['gross'], 2),
                    round(x['val'], 2), x['note'].replace('\n', ' ').strip()])
json.dump(out, open(HERE / 'summary.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in out.items() if k != '比較組'}, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in out['比較組'].items() if k != '明細'}, ensure_ascii=False, indent=1))
for r in out['比較組']['明細']: print(r)
