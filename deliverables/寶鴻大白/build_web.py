"""寶鴻大白 網站行情分析頁：讀 summary.json / transactions.csv → blog/baohong-dabai.html。
市場資訊頁，不放特定物件開價；版型沿用 office/*.html（與 blog/baida-fuli.html 同）。"""
import json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
OUT = ROOT / 'blog' / 'baohong-dabai.html'
S = json.load(open(HERE / 'summary.json'))
df = pd.read_csv(HERE / 'transactions.csv').fillna({'備註': ''})
df['yr'] = df['交易日期'].str[:3].astype(int)
SAME4, CMP, BAND = S['同型_近四年'], S['比較組'], S['比較組']['同級距']
CY = {r['年']: r for r in CMP['年度_不含本社區']}
FB = {b['帶'][:2]: b for b in S['樓層帶_同型_110後']}
PK = S['車位']['每席價格中位_110後']
URL = 'https://sixhands-studio.netlify.app/blog/baohong-dabai.html'
TITLE = '寶鴻大白 實價登錄分析｜西區五權三街 美術館生活圈｜三房四衛同型行情・西區同齡比較'
DESC = (f'寶鴻大白（台中西區五權三街55巷3／5號）實登 {S["有效筆數"]} 筆逐筆扣車位重算：三房四衛同型近四年 {SAME4["net"]:.1f} 萬/坪、'
        f'西區屋齡 5–10 年同坪數大樓 {BAND["net"]:.1f} 萬/坪，車位每席約 {PK:.0f} 萬。')

same = df[df['產品'].str.startswith('三房')]
yrs = same[same['yr'] >= 108].groupby('yr')['不含車單價'].agg(['median', 'count'])
mx = yrs['median'].max()
bars = ''.join(f'<div class="yrow"><span>{y} 年</span><span class="bar" style="width:{v/mx*100:.0f}%;background:#B08D3F;opacity:{.5+.07*i:.2f}"></span>'
               f'<span class="num"><b>{v:.1f}</b> <span style="font-size:11px;color:var(--mute)">n={int(n)}</span></span></div>'
               for i, (y, (v, n)) in enumerate(yrs.iterrows()))

def f2(v): return '—' if v is None else f'{v:.2f}'
prod = ''.join(f'<tr{" style=\"background:var(--cream-dark)\"" if p["型"].startswith("三房") else ""}><td>{p["型"]}</td><td class="num">{p["總面積中位"]:.2f}</td>'
               f'<td class="num">{p["扣車位面積中位"]:.2f}</td><td class="num">{p["全期n"]}</td><td class="num">{p["近四年n"]}</td>'
               f'<td class="num"><b>{f2(p["近四年不含車中位"])}</b></td><td class="num">{f2(p["近四年含車中位"])}</td></tr>' for p in S['產品'])
floors = ''.join(f'<tr><td>{b["帶"]}</td><td class="num">{b["n"]} 筆</td><td class="num"><b>{b["不含車中位"]:.2f}</b></td><td class="num">{b["含車中位"]:.2f}</td></tr>'
                 for b in S['樓層帶_同型_110後'])
recent = ''
for r in df[df['yr'] >= 112].itertuples():
    est = '*' if r.車位價來源.startswith('估算') else ''
    note = '車位另計 630 萬' if '陸佰參拾' in r.備註 else r.備註.replace(';', ' ').strip()[:10]
    recent += (f'<tr><td>{r.交易日期}</td><td>{r.門牌}・{r.樓層}F</td><td>{r.產品.split("（")[0]}</td><td class="num">{r.總價萬:,.0f}</td>'
               f'<td class="num">{r.總面積坪:.2f}</td><td class="num">{r.車位數}</td><td class="num"><b>{r.不含車單價:.2f}{est}</b></td>'
               f'<td class="num">{r.含車單價:.2f}</td><td>{note}</td></tr>')
cyrs = ''.join(f'<tr><td>{y} 年</td><td class="num">{CY[y]["n"]} 筆</td><td class="num"><b>{CY[y]["不含車中位"]:.2f}</b></td><td class="num">{CY[y]["含車中位"]:.2f}</td></tr>' for y in sorted(CY))
site = (HERE / '棟別圖.svg').read_text(encoding='utf-8').split('?>')[-1]
site = site.replace('fill="#C0392B" stroke="#8e2a1f"', 'fill="#fff" stroke="#9fb3bf"').replace('fill="#fff" font-size="15" font-weight="700">3 號', 'fill="#1F4E5F" font-size="15" font-weight="700">3 號')
site = site.replace('<text x="158" y="70" text-anchor="middle" fill="#fff" font-size="10">本戶 8F</text>', '')
premium = (SAME4['net'] / BAND['net'] - 1) * 100
lo = same[same['yr'] >= 112]['不含車單價']

css = (ROOT / 'office' / 'ntc.html').read_text(encoding='utf-8')
css = css[css.index('<style>'):css.index('</style>') + 8]

html = f'''<!DOCTYPE html><html lang="zh-Hant"><head>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-Z2BTZV5V2P"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-Z2BTZV5V2P');
</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{TITLE}</title>
<meta name="description" content="{DESC}">
<meta name="keywords" content="寶鴻大白,寶鴻大白實價登錄,寶鴻大白行情,五權三街55巷,寶鴻建設,台中西區大樓,美術館 華廈 行情">
<meta name="author" content="助哥｜台中行情"><meta name="robots" content="index,follow">
<link rel="canonical" href="{URL}">
<meta name="theme-color" content="#1F3A2E">
<meta property="og:type" content="website"><meta property="og:site_name" content="助哥｜台中行情">
<meta property="og:title" content="{TITLE}"><meta property="og:description" content="{DESC}">
<meta property="og:url" content="{URL}">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Article","headline":"寶鴻大白 實價登錄分析","description":"寶鴻大白 實價登錄行情、產品分型、樓層與西區同齡大樓比較。","author":{{"@type":"Person","name":"助哥"}},"datePublished":"2026-10-23","mainEntityOfPage":"{URL}"}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700&family=Noto+Serif+TC:wght@500;700;900&display=swap" rel="stylesheet">
{css}</head><body><nav><div class="wrap">
<a class="brand" href="../qiqi-realestate.html">助哥<span style="color:var(--gold)">｜</span>台中行情</a>
<span class="sp"></span>
<a class="lk" href="#trend">同型行情</a>
<a class="lk" href="#products">產品分型</a>
<a class="lk" href="#compare">西區比較</a>
<a class="lk" href="../blog/index.html">文章</a>
<a class="btn btn-primary btn-sm" href="https://line.me/R/ti/p/@080akczk" target="_blank" rel="noopener">聊聊</a>
</div></nav>
<header class="hero"><div class="wrap">
 <div class="tag"><span class="dot" style="background:#B08D3F"></span>華廈　／　台中西區・美術館綠園道生活圈（非七期）</div>
 <h1>寶鴻大白</h1>
 <p class="lead">五權三街55巷3／5號｜寶鴻建設｜106 年完工・屋齡 9 年｜10 樓｜18 戶・一層兩戶｜RC<br>
 <b style="color:var(--gold-light)">戶數少、成交少：每一筆都要扣掉兩席車位再比</b></p>
 <div class="kpis">
  <div class="kpi"><div class="v">{SAME4["net"]:.1f}</div><div class="l">萬/坪・三房四衛同型<br>房屋單價（已扣車位）・112–115</div></div>
  <div class="kpi"><div class="v">{SAME4["gross"]:.1f}</div><div class="l">萬/坪・同型<br>總價÷總坪數（車位一起算）</div></div>
  <div class="kpi"><div class="v">{BAND["net"]:.1f}</div><div class="l">萬/坪・西區同齡同坪數<br>屋齡 5–10 年・112–115</div></div>
  <div class="kpi"><div class="v">{PK:.0f}</div><div class="l">萬/席・坡道平面車位<br>110 年後揭露中位</div></div>
 </div>
</div></header>

<section id="trend"><div class="wrap">
 <div class="sec-tag">PRICE TREND</div><h2 class="sec-title">同型三房四衛：逐年行情</h2>
 <p class="sec-lead">社區主力是三房四衛：權狀約 86 坪，其中約 24 坪是兩席車位，扣掉後約 62 坪。
 以下為「房屋單價（已扣車位）」年度中位，n 為筆數；114 年沒有同型成交。</p>
 <div style="background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px 24px">{bars}
  <div style="border-top:1px solid #ece4d4;margin-top:14px;padding-top:12px;font-size:14px">112–115 年同型 {SAME4["n"]} 筆：{lo.min():.1f}–{lo.max():.1f} 萬/坪，中位 <b>{SAME4["net"]:.1f}</b>。總價大多落在 3,000–3,560 萬。</div></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">長條自 0 起算。單價為（總價－車位價）÷（總坪數－車位坪數）；車位價未揭露者以社區 110 年後揭露之坡道平面每席中位 {PK:.1f} 萬估算。</p>
 <div class="note" style="margin-top:20px"><b>◆ 為什麼網路上的單價看起來比較低？</b>這個社區幾乎每戶都帶兩席平面車位、約 24 坪，
 直接拿總價除以總坪數，同型近四年只有 {SAME4["gross"]:.1f} 萬/坪；扣掉車位後的房屋單價是 {SAME4["net"]:.1f}，差了約 {SAME4["gap_pct"]:.0f}%。</div>
</div></section>

<section id="products" style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">PRODUCT MIX</div><h2 class="sec-title">產品分型與樓層</h2>
 <p class="sec-lead">2–8 樓為三房四衛；9、10 樓退縮，是 40–50 坪的小坪數戶型，單價不能直接比。</p>
 <div class="tblwrap"><table><tr><th>產品</th><th class="num">總坪數中位</th><th class="num">扣車位坪數</th><th class="num">全期筆數</th><th class="num">112–115 筆數</th><th class="num">房屋單價（已扣車位）</th><th class="num">總價÷總坪數（車位一起算）</th></tr>{prod}</table></div>
 <div class="two" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:22px;margin-top:26px">
  <div><h3 style="font-size:18px;margin-bottom:10px">樓層：價差不大</h3>
   <div class="tblwrap"><table style="min-width:360px"><tr><th>同型・110 年後</th><th class="num">筆數</th><th class="num">已扣車位</th><th class="num">車位一起算</th></tr>{floors}</table></div>
   <p style="font-size:13px;color:var(--mute);margin-top:8px">中高樓層中位 {FB["中高"]["不含車中位"]:.1f}、低樓層 {FB["低樓"]["不含車中位"]:.1f}，差約 {(FB["中高"]["不含車中位"]/FB["低樓"]["不含車中位"]-1)*100:.0f}%；本社區價格主要看屋況與車位。</p></div>
  <div><h3 style="font-size:18px;margin-bottom:10px">棟別配置</h3>
   <div style="background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px">{site}</div>
   <p style="font-size:13px;color:var(--mute);margin-top:8px">單棟一層兩戶：3 號在北、5 號在南，東側臨五權三街55巷。依社區棟別圖重繪，非比例尺。</p></div>
 </div>
</div></section>

<section><div class="wrap">
 <div class="sec-tag">RECENT DEALS</div><h2 class="sec-title">112 年後成交明細</h2>
 <div class="tblwrap"><table><tr><th>日期</th><th>門牌</th><th>產品</th><th class="num">總價（萬）</th><th class="num">總坪數</th><th class="num">車位</th><th class="num">已扣車位</th><th class="num">車位一起算</th><th>備註</th></tr>{recent}</table></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">* 車位價未揭露，以每席中位估算。單位：萬元／坪。</p>
</div></section>

<section id="compare" style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">AREA COMPARISON</div><h2 class="sec-title">跟西區同齡大樓比</h2>
 <p class="sec-lead">比較組：西區、華廈與住宅大樓、屋齡 5–10 年、總坪數 70–100 坪，112–115 年；排除特殊關係、1 樓店面與樓中樓，不含本社區。</p>
 <div class="cards">
  <div class="card"><h3>同坪數級距 中位</h3><div class="big">{BAND["net"]:.1f}</div><p>萬/坪（已扣車位），扣車位 {BAND["扣車位面積"]} 坪，{BAND["n"]} 筆；車位一起算 {BAND["gross"]:.1f}</p></div>
  <div class="card"><h3>寶鴻大白同型 中位</h3><div class="big">{SAME4["net"]:.1f}</div><p>萬/坪（已扣車位），112–115 年 {SAME4["n"]} 筆</p></div>
  <div class="card"><h3>社區 vs 西區同級</h3><div class="big">{premium:+.0f}%</div><p>社區成交多在 2–6 樓，比較組多為 11 層以上大樓</p></div>
 </div>
 <h3 style="font-size:18px;margin:26px 0 10px">西區同齡大樓・年度中位（不分坪數）</h3>
 <div class="tblwrap"><table style="min-width:420px"><tr><th>年度</th><th class="num">筆數</th><th class="num">已扣車位</th><th class="num">車位一起算</th></tr>{cyrs}</table></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">各年度樣本少、坪數與樓層組合不同，年度間差異僅供參考。</p>
</div></section>

<section><div class="wrap">
 <div class="sec-tag">TWO SIDES</div><h2 class="sec-title">同一份數據，兩種用法</h2>
 <div class="cards">
  <div class="card" style="border-top:3px solid var(--t2)"><div class="sec-tag" style="color:var(--t2)">如果你是買方</div>
   <h3 style="margin:8px 0 10px">先扣車位，再比單價</h3>
   <p style="font-size:15px;line-height:1.85">社區每戶多帶兩席平面車位，總價裡約 400 多萬是車位。拿房屋單價跟同型比，社區 110 年後多在 44–47 萬/坪；7、8 樓成交不多，看屋時把屋況和裝修一起算進去。</p></div>
  <div class="card" style="border-top:3px solid var(--t3)"><div class="sec-tag" style="color:var(--t3)">如果你是屋主</div>
   <h3 style="margin:8px 0 10px">主打稀有與屋況</h3>
   <p style="font-size:15px;line-height:1.85">18 戶的社區一年成交只有幾筆，買方會拿僅有的幾筆來比。高樓層、裝修完整、雙平面車位都要講清楚，價格才有依據。</p></div>
 </div>
</div></section>

<section style="background:#faf7ef"><div class="wrap"><div class="cta">
 <h2>想知道寶鴻大白某一戶現在值多少？</h2>
 <p>我手上有 {S["有效筆數"]} 筆社區買賣、{CMP["有效"]} 筆西區同齡大樓的逐筆明細。<br>告訴我門牌、樓層跟車位數，我算給你看。</p>
 <a class="btn btn-primary" href="https://line.me/R/ti/p/@080akczk" target="_blank" rel="noopener">加 LINE 聊聊 →</a>
 <div style="margin-top:18px"><a class="btn btn-ghost" style="color:#e6dfcd;border-color:#4a6255" href="../qiqi-realestate.html">← 回台中行情首頁</a></div>
</div></div></section>
<footer><div class="wrap"><div class="fx">
<div><b>助哥｜台中行情</b><div style="margin-top:6px">不賣房子，賣判斷。<br>實登逐筆重算，數字附來源。</div></div>
<div><b>導覽</b><div style="margin-top:6px"><a href="../qiqi-realestate.html">住宅・土地・廠房</a>　<a href="../qiqi-office.html">七期商辦</a><br><a href="../blog/index.html">文章</a></div></div>
<div><b>聯絡</b><div style="margin-top:6px"><a href="https://line.me/R/ti/p/@080akczk" target="_blank" rel="noopener">LINE 諮詢</a></div></div>
</div>
<div class="dis">
資料來源：內政部不動產交易實價查詢服務網，五權三街55巷3號、5號買賣（101/01–115/10）；西區華廈・住宅大樓・屋齡5–10年・總面積70–100坪買賣（112/01–115/10）；撈取日 2026-10-23。
單價一律用中位數，已扣除車位、排除特殊關係；樣本少的區間另有標註。<br>
本頁為市場資訊整理與分析，僅供參考，<b style="font-size:12px">不構成價格保證、投資建議或要約</b>，亦非特定物件之銷售廣告。
個案成交條件差異極大，實際價格應以現場查看與個案評估為準。過去成交不代表未來表現。<br>
永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號
</div></div></footer></body></html>'''
OUT.write_text(html, encoding='utf-8')
print('→', OUT)
