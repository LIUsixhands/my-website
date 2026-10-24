"""南屯透天分區行情管線（小登）
用法：python3 南屯透天分區行情.py
讀同目錄 南屯透天_實登原始_*.xls → 分區（地段為主、路名為輔）→ 排除 → 各區歷年／屋齡帶中位數。
分區規則見 南屯透天_實登行情.md「分區判定」。
"""
import pandas as pd,glob,re
import sys,os
U=os.path.dirname(os.path.abspath(__file__))+'/'
rows=[]
for f in sorted(glob.glob(U+'南屯透天_實登原始_*.xls')):
    c=pd.read_excel(f,sheet_name='案件列表',header=1,dtype=str); land=pd.read_excel(f,sheet_name='土地',dtype=str); bld=pd.read_excel(f,sheet_name='建物',dtype=str)
    land['k']=land['序號'].str.split('-').str[0]; bld['k']=bld['序號'].str.split('-').str[0]
    def a(s):
        try: return float(str(s).replace('坪','').replace(',',''))
        except: return 0.0
    land['a']=land['土地移轉面積'].map(a); bld['a']=bld['建物移轉面積'].map(a)
    lg=land.groupby('k'); bg=bld.groupby('k')
    for _,r in c.iterrows():
        k=str(r['編號']).strip()
        if k not in lg.groups: continue
        L=lg.get_group(k); B=bg.get_group(k) if k in bg.groups else None
        secs=L['土地位置'].str.extract(r'^(.+?段)')[0].dropna()
        rows.append(dict(file=f.split('/')[-1],addr=r['地段位置或門牌'],comm=r['社區簡稱'],date=r['交易日期'],
          total=a(r['總價(萬元)']),barea=a(r['總面積(坪)']),larea=L['a'].sum(),age=r['屋齡'],floors=r['樓別/樓高'],
          use=r['主要用途'],target=r['交易標的'],cnt=r['交易筆棟數'],note=str(r['備註']) if pd.notna(r['備註']) else '',
          sec=secs.mode().iloc[0] if len(secs) else '',buse='、'.join(B['主要用途'].dropna().astype(str)) if B is not None else '',layout=str(r['建物現況格局']) if pd.notna(r['建物現況格局']) else '',zone_land=L['使用分區或編定'].iloc[0],
          partial=(L['備註'].fillna('').str.contains('持分').any() or (B is not None and B['持分'].fillna('').str.contains('持分').any()))))
df=pd.DataFrame(rows)
df['year']=df.date.str[:3].astype(int)
df['age']=pd.to_numeric(df.age,errors='coerce')
df['road']=df.addr.str.replace('南屯區','').str.extract(r'^(.+?(?:路|街|大道))')[0]

print(len(df), df.groupby('year').size().to_dict())

# ---- 分區與排除 ----
import re
df['age_missing']=df.age.isna(); df['age']=df.age.fillna(0)
df['road2']=df.addr.str.replace('南屯區','').str.extract(r'^(.+?(?:路|街|大道|巷)(?:[一二三四五六]段)?)')[0].fillna('')
def zone(r):
    s,rd=r.sec,r.road2
    if s.startswith('惠'): return '七期重劃區'
    if s in('大新段','大進段'): return '五期重劃區'
    if s=='田心段':
        return '其他' if rd in('惠弘街','惠心街','惠德街','惠文南街','南屯路二段','向上南路一段','向心路','惠文路') else '五期重劃區'
    if s in('豐功段','豐富段'): return '八期重劃區'
    if s=='豐業段': return '13期重劃區' if rd in('永春東二路','永春東三路') else '八期重劃區'
    if s=='新富段' and rd=='龍富十五路': return '單元三重劃區'
    if s in('新富段','三富段','昌明段'): return '單元二重劃區'
    if s=='永富段':
        if rd=='大墩十二街': return '單元三重劃區'
        return '其他' if rd in('五權西路二段','向上路三段') else '單元二重劃區'
    if s in('永新段','永春段'): return '單元三重劃區'
    if s=='三塊厝段':
        if rd in('永春東七路','三厝街','三和街','大墩十二街'): return '單元三重劃區'
        if rd=='永春東六路': return '單元四重劃區'
        if rd.startswith('黎明'): return '黎明生活圈'
        return '其他'
    if s in('永定段','鎮安段'): return '單元四重劃區'
    if s=='鎮福段': return '單元五重劃區'
    if s=='楓樹段': return '13期重劃區' if rd in('楓樹東街','楓香街','楓平路','永春東二路','永春東三路') else '楓樹生活圈'
    if s in('埔興段','鎮南段'): return '楓樹生活圈'
    if s=='黎明段': return '黎明生活圈'
    if s=='南屯段': return '黎明生活圈' if rd.startswith('黎明') else '其他'
    if s in('春安段','保安段','春社段','寶山段','台安段','寶文段'): return '嶺東科大生活圈'
    return '其他'
df['zone']=df.apply(zone,axis=1)
# 排除
def excl(r):
    if any(k in r.note for k in ('親友','員工','共有人','特殊關係')): return '特殊關係'
    if r.partial: return '持分移轉'
    if '租約' in r.note: return '含租約'
    zl=str(r.zone_land)
    if '工業' in zl or zl.endswith('：工') or r.use=='工業用' or re.search(r'廠房|工廠|作業場',r.buse): return '工廠/工業區'
    if '農業' in zl or zl.endswith('：農'): return '農業區'
    if '住' not in r.buse and ('房' not in r.layout or r.floors=='全/一層'): return '非住宅(店面/辦公/加油站)'
    if not (25<=r.barea<=200): return '建坪非25-200'
    if r.larea<=0: return '無地坪'
    if r.larea>150: return '地坪>150坪(土地交易)'
    if pd.isna(r.age): return '屋齡缺'
    return ''
df['excl']=df.apply(excl,axis=1)
df['bp']=df.total/df.barea; df['lp']=df.total/df.larea
bins=[-1,5,10,20,30,40,999]; labs=['0~5年','6~10年','11~20年','21~30年','31~40年','41年以上']
df['ageband']=pd.cut(df.age,bins,labels=labs)

print(df.zone.value_counts().to_string()); print(df.excl.value_counts().to_string())
v=df[df.excl=='']
print(pd.crosstab(v.zone,v.year,margins=True).to_string())
print(df[df.zone=='其他'].groupby(['sec','road2']).size().sort_values(ascending=False).head(40).to_string())

# ---- 統計 ----
import json
v=df[df.excl==''].copy()
Z=['五期重劃區','七期重劃區','八期重劃區','13期重劃區','單元二重劃區','單元三重劃區','單元四重劃區','單元五重劃區','楓樹生活圈','黎明生活圈','嶺東科大生活圈']
Y=sorted(v.year.unique().tolist()); A=['0~5年','6~10年','11~20年','21~30年','31~40年','41年以上']
def agg(g):
    return dict(n=int(len(g)),bp=round(float(g.bp.median()),1) if len(g) else None,lp=round(float(g.lp.median()),1) if len(g) else None,
                tp=round(float(g.total.median())) if len(g) else None, sum=round(float(g.total.sum())))
out={}
for z in ['南屯全區']+Z:
    g=v if z=='南屯全區' else v[v.zone==z]
    out[z]=dict(total=agg(g),year={y:agg(g[g.year==y]) for y in Y},age={a:agg(g[g.ageband==a]) for a in A},
      secs=sorted(g.sec.unique().tolist()) if z!='南屯全區' else [], roads=g.road2.value_counts().head(8).index.tolist())

for z,d in out.items():
    print(z,d['total'],'|',' '.join(f"{y}:{d['year'][y]['n']}/{d['year'][y]['bp']}/{d['year'][y]['lp']}" for y in Y))
    print('   ',' '.join(f"{a}:{d['age'][a]['n']}/{d['age'][a]['bp']}/{d['age'][a]['lp']}" for a in A))
print(df.excl.value_counts().to_dict())

# ---- 輸出 ----
import sys
if len(sys.argv)>1:
    od=sys.argv[1]
    o=v.copy(); o['date']=o.date.str.replace('/','-')
    o=o[['zone','year','date','ageband','age','road2','sec','total','barea','larea','bp','lp']].rename(columns={'road2':'road','sec':'section','total':'total_wan','barea':'build_ping','larea':'land_ping','bp':'build_price','lp':'land_price'})
    for c in ['build_ping','land_ping','build_price','land_price']: o[c]=o[c].round(2)
    o.sort_values(['zone','date']).to_csv(od+'/nantun_townhouse_108_115.csv',index=False)
    json.dump(out,open(od+'/stats.json','w'),ensure_ascii=False)
