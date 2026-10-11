"""文化第王 實登比較 — 走小登管線（.claude/skills/skill-xiao-deng/references/實登批次處理管線.py）。
資料：不動產交易實價查詢服務網，板橋區 111/01–115/10，條件＝屋齡 25–35 年、3房2廳2衛（即本戶售屋條件），再限建坪 30–40 坪；
另含本社區逐門牌查詢 101/01–115/10（社區實登_*.xls）。
口徑：扣車位重算淨單價（未拆價車位逐類別中位估算）、排除特殊關係、
比較一律分【無車位】與【有車位】，有車位再並列含車／不含車；年度一律中位數。"""
import re, sys, json, csv, glob, statistics as st
from pathlib import Path
import xlrd
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / '.claude/skills/skill-xiao-deng/references'))
import 實登批次處理管線 as P

T = str.maketrans('０１２３４５６７８９', '0123456789')
# 江子翠生活圈：以門牌路段界定，只取捷運江子翠站步行圈（不含華江側的金門街、懷德街、民生路三段百號以後）
JZC = ('文化路二段', '莊敬路', '雙十路二段', '雙十路三段', '文聖街', '松柏街', '仁化街', '松江街', '吳鳳路')
def in_jzc(a):
    m = re.search(r'民生路三段(\d+)', a)
    if m: return int(m.group(1)) < 100
    return any(k in a for k in JZC)
# 本社區（樂居棟別圖）：182巷1弄 2–12 號雙號、182巷3弄 1–11 號單號
def is_community(a):
    m = re.search(r'文化路二段182巷([13])弄(\d+)號', a)
    if not m: return False
    l, n = m.group(1), int(m.group(2))
    return (l == '1' and n in (2, 4, 6, 8, 10, 12)) or (l == '3' and n in (1, 3, 5, 7, 9, 11))

LISTING = dict(樓層=6, 總價=2898, 建坪=34.39, 主建物=27.65, 附屬=3.57, 公設=3.17)
LISTING['單價'] = LISTING['總價'] / LISTING['建坪']
LISTING['主建物佔比'] = LISTING['主建物'] / LISTING['建坪']

raw = []
for f in sorted(HERE.glob('實登_*.xls')):
    _, r = P.load(str(f))
    sh = xlrd.open_workbook(str(f), encoding_override='cp950').sheet_by_name('案件列表')
    extra = {str(sh.cell_value(i, 0)).strip(): (sh.cell_value(i, 7), sh.cell_value(i, 8), sh.cell_value(i, 9))
             for i in range(2, sh.nrows)}
    for x in r:
        share, typ, age = extra[x['no']]
        x['share'] = float(str(share).replace('%', '') or 0) / 100
        x['typ'] = typ[:4]
        x['age'] = int(float(age)) if age else None
        x['addr'] = x['addr'].translate(T)
    raw += r

keep, drop = P.clean(raw)
rows, MA, MV = P.recompute(keep)
for x in rows:
    x['gross'] = x['tot'] / x['area']
    x['park'] = x['npark'] > 0
    x['est'] = x['park'] and not (x['pk_val'] > 0 or x['pkv_row'])
    x['jzc'] = in_jzc(x['addr'])
    x['comm'] = is_community(x['addr'])
    x['road'] = (re.match(r'板橋區(.+?[路街道](?:[一二三四五六]段)?)', x['addr']) or [None, ''])[1]

# 比較母體：住宅大樓、建坪 30–40 坪（有車位者以扣除車位後的建坪計，與本戶 34.39 坪同級）、
# 排除 1 樓（店面）、頂樓加蓋、夾層（夾層戶登記坪數小、單價虛高）
def ok(x): return (x['typ'] == '住宅大樓' and x['fl'] and x['fl'] > 1 and 30 <= x['base'] <= 40
                   and '頂樓加蓋' not in x['note'] and '夾層' not in x['note'])
base = [x for x in rows if ok(x)]
def med(v): return round(st.median(v), 2) if v else None
YEARS = range(111, 116)

def by_year(g):
    out = []
    for y in YEARS:
        a = [x for x in g if x['yr'] == y and not x['park']]
        b = [x for x in g if x['yr'] == y and x['park']]
        out.append(dict(年=y, 無車位n=len(a), 無車位中位=med([x['val'] for x in a]),
                        無車位總價=med([x['tot'] for x in a]), 無車位坪數=med([x['area'] for x in a]),
                        有車位n=len(b), 含車中位=med([x['gross'] for x in b]), 不含車中位=med([x['val'] for x in b]),
                        有車位總價=med([x['tot'] for x in b])))
    return out

def hl(g, name):
    out = {}
    for k, gg in (('無車位', [x for x in g if not x['park']]), ('有車位', [x for x in g if x['park']])):
        out[k] = P.headline(gg, window=(113, 115), name=f'{name} {k} 近三年', min_n=10) if any(113 <= x['yr'] for x in gg) else None
    out['主建物佔比中位'] = med([x['share'] for x in g if x['yr'] >= 113])
    return out

JZ = [x for x in base if x['jzc']]
S = dict(撈取日='2026-10-09', 查詢區間='111/01–115/10', 查詢條件='板橋區・屋齡25–35年・3房2廳2衛',
         原始筆數=len(raw), 排除特殊關係=len(drop), 有效筆數=len(rows), 大樓母體=len(base), 江子翠母體=len(JZ),
         車位=dict(每席面積中位=round(MA, 2), 每席價格中位=round(MV, 1)),
         江子翠路段=JZC, 本戶=LISTING)
S['板橋_年度'] = by_year(base)
S['江子翠_年度'] = by_year(JZ)
S['板橋_近三年'] = hl(base, '板橋大樓')
S['江子翠_近三年'] = hl(JZ, '江子翠大樓')
# 115 年單年（最新行情）
for nm, g in (('江子翠', JZ), ('板橋', base)):
    a = [x for x in g if x['yr'] == 115 and not x['park']]
    S[f'{nm}_115無車位'] = dict(n=len(a), 單價中位=med([x['val'] for x in a]), 總價中位=med([x['tot'] for x in a]))

# ---------- 文化第王（實登簡稱「文化遠見」）全社區成交 101–115：逐門牌查詢檔 ----------
# 3弄6號查無社區名、位於巷道對側，非本社區，不列入
craw = []
for f in sorted(HERE.glob('社區實登_*.xls')):
    if '3弄6號' in f.name: continue
    craw += P.load(str(f))[1]
ckeep, cdrop = P.clean(craw)
# 社區檔車位面積、價格多未揭露 → 以板橋同條件母體「逐車位類別」的單席面積／價格中位估算
KA, KVv = {}, {}
for k in {k for x in rows for k in x['kinds']}:
    g = [x for x in rows if set(x['kinds']) == {k} and x['pk_n']]
    ar = [x['pk_area'] / x['pk_n'] for x in g if x['pk_area'] > 0]
    vv = [(x['pk_val'] or x['pkv_row'] or 0) / x['pk_n'] for x in g if (x['pk_val'] or x['pkv_row'])]
    if ar: KA[k] = st.median(ar)
    if vv: KVv[k] = st.median(vv)
S['車位類別估算'] = {k: dict(每席坪=round(KA.get(k, MA), 2), 每席萬=round(KVv.get(k, MV))) for k in KA}
crows = []
for x in ckeep:
    pa = x['pk_area'] or sum(KA.get(k, MA) for k in x['kinds'])
    pv = x['pk_val'] or x['pkv_row'] or sum(KVv.get(k, MV) for k in x['kinds'])
    x['base'] = x['area'] - pa
    x['val'] = (x['tot'] - pv) / x['base']
    crows.append(x)
def ptype(x):
    if x['base'] < 15: return '套房'
    if x['base'] < 30: return '兩房'
    if x['base'] <= 40: return '三房30–40坪'
    return '大坪數'
S['社區成交'] = [dict(日期=x['date'], 年=x['yr'], 門牌=x['addr'].translate(T).split('182巷')[1], 樓層=x['fl'], 總價=x['tot'],
                  坪數=x['area'], 扣車位坪數=round(x['base'], 2), 車位=x['npark'], 含車單價=round(x['tot'] / x['area'], 2),
                  單價=round(x['val'], 2), 車位估算=bool(x['npark'] and not x['pkv_row']), 產品=ptype(x),
                  用途=x['use'], 備註=x['note'].replace('\n', ' '))
               for x in sorted(crows, key=lambda x: x['date'])]
S['社區排除'] = [dict(日期=x['date'], 門牌=x['addr'].translate(T).split('182巷')[1], 原因=w) for w, x in cdrop]
S['社區_年度'] = [dict(年=y, n=len(g), 中位=med([x['val'] for x in g]))
                for y in sorted({x['yr'] for x in crows}) for g in [[x for x in crows if x['yr'] == y]]]

with open(HERE / 'transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['交易日期', '門牌', '路段', '江子翠', '同社區', '樓層', '屋齡', '總價萬', '總面積坪', '主建物佔比', '車位數', '車位類別',
                '車位價萬', '車位價來源', '扣車位面積坪', '含車單價', '不含車單價', '用途', '備註'])
    for x in sorted(base, key=lambda x: x['date'], reverse=True):
        pv = x['tot'] - x['val'] * x['base']
        w.writerow([x['date'], x['addr'].replace('板橋區', ''), x['road'], int(x['jzc']), int(x['comm']), x['fl'], x['age'],
                    x['tot'], x['area'], round(x['share'], 4), x['npark'], '/'.join(x['kinds']), round(pv),
                    '' if not x['park'] else ('估算(類別中位)' if x['est'] else '實登揭露'),
                    round(x['base'], 2), round(x['gross'], 2), round(x['val'], 2), x['use'], x['note']])
json.dump(S, open(HERE / 'summary.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in S.items() if k in ('大樓母體','江子翠母體','江子翠_年度','板橋_年度','板橋_近三年','江子翠_近三年','江子翠_115無車位','板橋_115無車位','社區成交','社區排除','社區_年度')}, ensure_ascii=False))
