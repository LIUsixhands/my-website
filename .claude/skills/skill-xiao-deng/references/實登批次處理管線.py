#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
實登批次處理管線 — 小登 · Sixhands Studio
用途：把內政部實價登錄 .xls（買賣／預售／租賃）統一清洗、扣車位重算、分波分層，輸出統計 JSON。
固化的口徑規則（踩過坑才寫的，別改）：
  1. 買賣：淨單價 =（總價 − 車位價）÷（總面積 − 車位面積）
     ⚠️ 實登「單價」欄口徑不一致（車位價有揭露才扣）→ 一律自行重算
  2. 車位面積、車位價 逐案件由「車位」分頁加總（同一棟可能平面+機械並存，坪數差數倍）
  3. 未揭露車位價／面積者，以該棟已揭露之中位數估算
  4. 排除：備註含 親友|員工|共有人|特殊關係；解約情形非空
  5. 預售屋：車位價多半全揭露 → 單價欄已扣車位，可直接用（本管線仍反推驗證）
  6. 交屋潮 vs 中古轉售 必須分開統計（差距可達 1.77 倍）
  7. ⛔⛔ 行情一律只取【近三年】成交中位數，不得跨多年平均（助哥 2026-09-12 指正）
     行情逐年變動：親家T3 108年 23.0 → 114年 41.7；八年平均會得到 27.7，低估三成以上
     ※ 例外：坪數是「產品屬性」不隨行情變動 → 坪數採全部中古轉售樣本，樣本越多越穩
  8. 一律用【中位數】，不用平均數（平均會被大坪數特例拉動）
  9. 毛投報 ＝ 租金 × 12 ÷（單價 × 10,000）：房屋對房屋，兩邊都已扣車位
用法：BUILD 清單填入標的與檔案，執行本檔。
"""
import xlrd, re, json, statistics as st, collections, sys, os

CN={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
def floor_of(s):
    s=(s or '').split('/')[0].replace('層','').strip()
    if not s: return None
    if s.isdigit(): return int(s)
    if s.startswith('三十'): return 30+(CN.get(s[2:],0) if len(s)>2 else 0)
    if s.startswith('二十'): return 20+(CN.get(s[2:],0) if len(s)>2 else 0)
    if s.startswith('十'):  return 10+(CN.get(s[1:],0) if len(s)>1 else 0)
    if s.endswith('十'):    return CN.get(s[0],0)*10
    return CN.get(s)

def num(x):
    x=(x or '').replace(',','').replace('元','').strip()
    try: return float(x)
    except: return None

EXCL=('親友','員工','共有人','特殊關係')

def parking_map(book):
    """由『車位』分頁逐案件加總面積與價格（價格單位轉萬元）"""
    try: c=book.sheet_by_name('車位')
    except: return {}
    M=collections.defaultdict(lambda:{'area':0.0,'val':0.0,'n':0,'kinds':[]})
    for r in range(1,c.nrows):
        sn=str(c.cell_value(r,0)).strip()
        if not sn or '-' not in sn: continue
        d=M[sn.split('-')[0]]; d['n']+=1
        d['kinds'].append(str(c.cell_value(r,1)).strip())
        a=num(str(c.cell_value(r,3)).replace('坪',''))
        p=num(str(c.cell_value(r,2)))
        if a: d['area']+=a
        if p: d['val']+=p/10000
    return M

def load(path):
    """回傳 (kind, rows)；kind ∈ 買賣/預售/租賃"""
    b=xlrd.open_workbook(path, encoding_override='cp950')
    sh=b.sheet_by_name('案件列表'); hdr=str(sh.cell_value(0,0))
    kind='租賃' if '租賃' in hdr else ('預售' if '預售' in hdr else '買賣')
    PK=parking_map(b); rows=[]
    # 欄位索引（三種格式不同）
    IDX={'買賣':dict(date=3,tot=4,up=5,area=6,fl=10,use=11,cnt=13,pkv=15,note=18,addr=1,name=2,cancel=None),
         '預售':dict(date=4,tot=5,up=6,area=7,fl=10,use=15,cnt=12,pkv=14,note=18,addr=1,name=2,cancel=17),
         '租賃':dict(date=2,tot=3,up=4,area=5,fl=8,use=9,cnt=11,pkv=13,note=20,addr=1,name=None,cancel=None)}[kind]
    for r in range(2, sh.nrows):
        g=lambda i: str(sh.cell_value(r,i)).strip() if i is not None else ''
        if not g(IDX['date']): continue
        cnt=g(IDX['cnt'])
        n=int(re.search(r'車位:(\d+)',cnt).group(1)) if '車位:' in cnt else 0
        p=PK.get(g(0), {'area':0.0,'val':0.0,'n':0,'kinds':[]})
        rows.append(dict(kind=kind, no=g(0), addr=g(IDX['addr']), name=g(IDX['name']),
            unit=g(2) if kind=='預售' else '', date=g(IDX['date']),
            tot=num(g(IDX['tot'])), up=num(g(IDX['up'])), area=num(g(IDX['area'])),
            fl=floor_of(g(IDX['fl'])), use=g(IDX['use']), npark=n,
            pkv_row=num(g(IDX['pkv'])), pk_area=p['area'], pk_val=p['val'], pk_n=p['n'],
            kinds=p['kinds'], cancel=g(IDX['cancel']), note=g(IDX['note']),
            yr=int(g(IDX['date'])[:3])))
    return kind, rows

def clean(rows):
    """排除特殊關係與解約，回傳 (有效, 排除清單)"""
    keep, drop = [], []
    for x in rows:
        if any(k in x['note'] for k in EXCL): drop.append(('特殊關係',x)); continue
        if x['cancel']: drop.append(('解約',x)); continue
        keep.append(x)
    return keep, drop

def recompute(rows):
    """統一口徑重算：買賣/預售→net(萬/坪)；租賃→rent(元/坪/月)"""
    va=[x['pk_area']/x['pk_n'] for x in rows if x['pk_n'] and x['pk_area']>0]
    vv=[(x['pk_val'] or x['pkv_row'] or 0)/x['pk_n'] for x in rows if x['pk_n'] and (x['pk_val']>0 or x['pkv_row'])]
    MA=st.median(va) if va else 0.0
    MV=st.median(vv) if vv else 0.0
    out=[]
    for x in rows:
        pa = x['pk_area'] if x['pk_area']>0 else x['npark']*MA
        pv = x['pk_val'] if x['pk_val']>0 else (x['pkv_row'] if x['pkv_row'] else x['npark']*MV)
        base = (x['area'] or 0) - pa
        if base<=0: continue
        x['base']=base
        if x['kind']=='租賃':
            x['val']=(x['tot']-pv/10000 if x['pkv_row'] else x['tot']-pv)/base*10000
        else:
            x['val']=(x['tot']-pv)/base
        out.append(x)
    return out, MA, MV

def bands(rows, key='val', cuts=None):
    cuts = cuts or [(2,9,'低'),(10,17,'中'),(18,25,'中高'),(26,99,'高')]
    res=[]
    for lo,hi,nm in cuts:
        g=[x[key] for x in rows if x['fl'] and lo<=x['fl']<=hi]
        if g: res.append(dict(band=f"{nm} {lo}-{hi if hi<99 else ''}F", n=len(g),
                              mean=st.mean(g), median=st.median(g)))
    return res

def summarize(name, rows, wave_cut=None):
    v=[x['val'] for x in rows]
    s=dict(name=name, kind=rows[0]['kind'], n=len(rows),
           date_min=min(x['date'] for x in rows), date_max=max(x['date'] for x in rows),
           lo=min(v), hi=max(v), median=st.median(v), mean=st.mean(v),
           years={str(y):dict(n=sum(1 for x in rows if x['yr']==y),
                              mean=st.mean([x['val'] for x in rows if x['yr']==y]),
                              median=st.median([x['val'] for x in rows if x['yr']==y]))
                  for y in sorted(set(x['yr'] for x in rows))},
           bands=bands(rows))
    if rows[0]['kind']!='租賃':
        s['total_price']=dict(lo=min(x['tot'] for x in rows), hi=max(x['tot'] for x in rows),
                              median=st.median([x['tot'] for x in rows]))
        s['base_ping']=dict(lo=min(x['base'] for x in rows), hi=max(x['base'] for x in rows),
                            median=st.median([x['base'] for x in rows]))
    if wave_cut:
        e=[x['val'] for x in rows if x['yr']<=wave_cut]; l=[x['val'] for x in rows if x['yr']>wave_cut]
        if e and l:
            s['wave']=dict(cut=wave_cut, early_n=len(e), early_mean=st.mean(e),
                           late_n=len(l), late_mean=st.mean(l), gap=st.mean(l)/st.mean(e)-1)
    return s

def run(name, files, wave_cut=None):
    allrows=[]; kinds=set()
    for f in files:
        k,r=load(f); kinds.add(k); allrows+=r
    keep,drop=clean(allrows)
    rows,MA,MV=recompute(keep)
    s=summarize(name, rows, wave_cut)
    s['excluded']=[{'why':w,'date':x['date'],'note':x['note'][:40]} for w,x in drop]
    s['park']=dict(median_area=MA, median_val=MV,
                   kinds=dict(collections.Counter(k for x in rows for k in x['kinds'])))
    return s, rows
