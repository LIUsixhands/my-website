"""百達馥麗 實登清洗 — 走小登管線（.claude/skills/skill-xiao-deng/references/實登批次處理管線.py）。
口徑：扣車位重算淨單價（車位價未揭露者以本社區坡道平面每席中位估算）、排除特殊關係／部分移轉／單買車位；
287／289 兩門牌合併去重；產品依「扣車位面積」分型；對外行情只走 headline()：中位數、含車／不含車並列。
比較組：西區・住宅大樓・屋齡 15–20 年・總面積 80–100 坪・112/01–115/10（本戶 93.16 坪落在級距內）。"""
import sys, json, csv, statistics as st
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / '.claude/skills/skill-xiao-deng/references'))
import 實登批次處理管線 as P

Z2H = str.maketrans('０１２３４５６７８９', '0123456789')
CN = {'一': 1, '二': 2, '三': 3}

def unit_of(addr):
    a = addr.translate(Z2H)
    bldg = '287' if '287' in a else '289' if '289' in a else ''
    tail = a.split('之')[-1] if '之' in a else (a.split('-')[-1] if '-' in a else '')
    u = CN.get(tail[:1]) or (int(tail[:1]) if tail[:1].isdigit() else None)
    return bldg, u

# 棟別：289 號＝A 棟、287 號＝B 棟；之一／之二／之三＝ -1／-2／-3（樂居棟別圖）
def tower(b, u): return ('A' if b == '289' else 'B') + (str(u) if u else '')

# 產品分型（依扣車位面積，同型在實登中面積高度重複）
def ptype(base):
    if base < 95: return '三房＋1（約 88 坪）'
    if base < 110: return '四房（約 100–104 坪）'
    if base < 130: return '四房大坪（約 112–117 坪）'
    return '頂層大戶（約 214 坪）'

# ---------- 社區買賣 ----------
raw = []
for f in ('實登_中興街287號_買賣.xls', '實登_中興街289號_買賣.xls'):
    raw += P.load(str(HERE / f))[1]
seen, rows0 = set(), []
for x in raw:
    k = (x['date'], x['tot'], x['area'])
    if k in seen: continue
    seen.add(k); rows0.append(x)
keep, drop = P.clean(rows0)
drop = [(w, x) for w, x in drop]
for x in list(keep):
    if not x['fl'] or not x['area'] or x['area'] < 40:      # 單買車位／公設、部分移轉（14F之3 13.33 坪 888 萬）
        keep.remove(x); drop.append(('部分移轉／單買車位', x))
for x in keep:                                              # 筆棟數未寫車位數、但車位分頁有登載者
    if not x['npark'] and x['kinds']: x['npark'] = len(x['kinds'])
rows, MA, MV = P.recompute(keep)
for x in rows:
    x['bldg'], x['u'] = unit_of(x['addr'])
    x['tower'] = tower(x['bldg'], x['u'])
    x['gross'] = x['tot'] / x['area']
    x['type'] = ptype(x['base'])
    x['split'] = bool(x['pkv_row'])

def med(v): return round(st.median(v), 2) if v else None
park_recent = [x['pkv_row'] / x['npark'] for x in rows if x['pkv_row'] and x['yr'] >= 112]
out = dict(撈取日='2026-10-16', 查詢區間='101/01–115/10', 原始筆數=len(raw), 重複筆數=len(raw) - len(rows0),
           排除=[dict(原因=w, 日期=x['date'], 樓層=x['fl'], 總價=x['tot']) for w, x in drop], 有效筆數=len(rows),
           車位=dict(類別='坡道平面', 每席面積中位=round(MA, 2), 每席價格中位_全期=round(MV, 1),
                   每席價格中位_112後=med(park_recent), 揭露筆數_112後=len(park_recent)))
out['近三年'] = P.headline(rows, window=(113, 115), name='百達馥麗 近三年')
out['近四年'] = P.headline(rows, window=(112, 115), name='百達馥麗 112–115')
out['全期_參考'] = P.headline(rows, allow_full=True, name='百達馥麗 全期')
SAME = [x for x in rows if x['type'].startswith('三房')]
out['同型_近四年'] = P.headline(SAME, window=(112, 115), name='同型三房＋1 112–115')
out['同型_近六年'] = P.headline(SAME, window=(110, 115), name='同型三房＋1 110–115')
out['年度'] = [dict(年=y, n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g]))
              for y in sorted({x['yr'] for x in rows}) for g in [[x for x in rows if x['yr'] == y]]]
out['產品'] = []
for t in ('三房＋1（約 88 坪）', '四房（約 100–104 坪）', '四房大坪（約 112–117 坪）', '頂層大戶（約 214 坪）'):
    g = [x for x in rows if x['type'] == t]; g3 = [x for x in g if x['yr'] >= 112]
    out['產品'].append(dict(型=t, 全期n=len(g), 近四年n=len(g3), 近四年不含車中位=med([x['val'] for x in g3]),
                          近四年含車中位=med([x['gross'] for x in g3]), 總面積中位=med([x['area'] for x in g])))
cuts = [(2, 11, '低樓層 2–11F'), (12, 22, '中樓層 12–22F'), (23, 34, '高樓層 23–34F')]
out['樓層帶_110後'] = []
for lo, hi, nm in cuts:
    g = [x for x in rows if lo <= x['fl'] <= hi and x['yr'] >= 110]
    out['樓層帶_110後'].append(dict(帶=nm, n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g])))

# ---------- 社區租賃 ----------
rent = []
for f in ('實登_中興街287號_租賃.xls', '實登_中興街289號_租賃.xls'):
    for x in P.load(str(HERE / f))[1]:
        b, u = unit_of(x['addr'])
        whole = not any(k in x['note'] for k in ('套房', '雅房', '分租', '共同承租', '部分範圍'))
        rent.append(dict(日期=x['date'], 棟=tower(b, u), 樓層=x['fl'], 月租萬=x['tot'], 面積坪=x['area'], 車位=x['npark'],
                         整戶=bool(whole and x['area'] > 85), 備註=x['note'][:30]))
rent.sort(key=lambda r: r['日期'], reverse=True)
r3 = [r for r in rent if r['整戶'] and int(r['日期'][:3]) >= 112]
out['租賃'] = dict(筆數=len(rent), 近三年整戶=r3, 近三年整戶月租中位=med([r['月租萬'] for r in r3]),
                 近三年整戶每坪中位_元=round(st.median([r['月租萬'] * 10000 / r['面積坪'] for r in r3])) if r3 else None)

# ---------- 比較組：西區 15–20 年 80–100 坪 ----------
_, cmp_raw = P.load(str(HERE / '實登_比較組_西區大樓_屋齡15-20_80-100坪_112-115.xls'))
ck, cd = P.clean(cmp_raw)
crow, cMA, cMV = P.recompute(ck)
for x in crow:
    x['gross'] = x['tot'] / x['area']
    x['self'] = '中興街２８' in x['addr'] or '百達' in x['name']
others = [x for x in crow if not x['self']]
out['比較組'] = dict(條件='西區・住宅大樓・屋齡15–20年・總面積80–100坪・112/01–115/10', 原始=len(cmp_raw), 排除=len(cd),
                  有效=len(crow), 本社區筆數=sum(x['self'] for x in crow),
                  全部=P.headline(crow, window=(112, 115), name='西區比較組'),
                  不含本社區=P.headline(others, window=(112, 115), name='西區比較組（不含百達）'),
                  近三年_不含本社區=P.headline([x for x in others if x['yr'] >= 113], window=(113, 115), name='西區比較組 113–115'),
                  明細=[dict(日期=x['date'], 社區=x['name'] or '—', 門牌=x['addr'].split('區')[-1], 樓層=x['fl'], 總價=x['tot'],
                            坪數=x['area'], 車位=x['npark'], 車位類別='／'.join(dict.fromkeys(x['kinds'])),
                            車位價=round(x['pkv_row'] or 0) or None, 不含車=round(x['val'], 2), 含車=round(x['gross'], 2),
                            本社區=x['self']) for x in sorted(crow, key=lambda x: x['date'], reverse=True)])

# ---------- 本戶 ----------
PK = out['車位']['每席價格中位_112後'] or MV
L = dict(門牌='中興街287號16樓之1', 棟='B1', 樓層=16, 總樓層=34, 開價=3980, 總面積=93.16, 主建物=49.90, 附屬=11.41,
         公設=31.85, 車位面積_實登=5.16, 車位='坡道平面 B4-146（1 席）', 格局='3+1房2廳3衛', 管理費=8500)
L['扣車位面積'] = round(L['總面積'] - L['車位面積_實登'], 2)
L['含車單價'] = round(L['開價'] / L['總面積'], 2)
L['不含車單價'] = round((L['開價'] - PK) / L['扣車位面積'], 2)
L['車位估價'] = PK
out['本戶'] = L

with open(HERE / 'transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['交易日期', '棟別', '樓層', '產品', '總價萬', '總面積坪', '車位數', '車位價萬', '車位價來源', '扣車位面積坪', '含車單價', '不含車單價', '備註'])
    for x in sorted(rows, key=lambda x: x['date'], reverse=True):
        pv = x['pkv_row'] or round(x['npark'] * MV)
        w.writerow([x['date'], x['tower'], x['fl'], x['type'], x['tot'], x['area'], x['npark'], pv,
                    '實登揭露' if x['split'] else '估算(坡道平面中位)', round(x['base'], 2), round(x['gross'], 2),
                    round(x['val'], 2), x['note'].replace('\n', ' ').strip()])
json.dump(out, open(HERE / 'summary.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ('有效筆數', '排除', '車位', '近三年', '近四年', '同型_近四年', '同型_近六年', '產品', '樓層帶_110後', '租賃', '本戶')},
                 ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in out['比較組'].items() if k != '明細'}, ensure_ascii=False, indent=1))
for r in out['比較組']['明細']: print(r)
