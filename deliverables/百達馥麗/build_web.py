"""百達馥麗 網站行情分析頁：讀 summary.json / transactions.csv → community/baida-fuli.html。
市場資訊頁，不放特定物件開價；版型沿用 office/*.html。"""
import json, statistics as st
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
OUT = ROOT / 'community' / 'baida-fuli.html'
S = json.load(open(HERE / 'summary.json'))
df = pd.read_csv(HERE / 'transactions.csv').fillna({'備註': ''})
df['yr'] = df['交易日期'].str[:3].astype(int)
SAME4, CMP3, R = S['同型_近四年'], S['比較組']['近三年_不含本社區'], S['租賃']
URL = 'https://sixhands-studio.netlify.app/community/baida-fuli.html'
TITLE = '百達馥麗 實價登錄分析｜西區中興街 興富發 34 層｜同型行情・產品分型・租金'
DESC = (f'百達馥麗（台中西區中興街287／289號）實登 {S["有效筆數"]} 筆逐筆扣車位重算：三房＋1 同型近四年 {SAME4["net"]:.1f} 萬/坪、'
        f'西區同級大樓 {CMP3["net"]:.1f} 萬/坪、整戶租金約 {R["近三年整戶每坪中位_元"]} 元/坪。')

# 同型年度中位長條（110 年後）
same = df[df['產品'].str.startswith('三房')]
yrs = same[same['yr'] >= 108].groupby('yr')['不含車單價'].agg(['median', 'count'])
mx = yrs['median'].max()
bars = ''.join(f'<div class="yrow"><span>{y} 年</span><span class="bar" style="width:{v/mx*100:.0f}%;background:#B08D3F;opacity:{.5+.07*i:.2f}"></span>'
               f'<span class="num"><b>{v:.1f}</b> <span style="font-size:11px;color:var(--mute)">n={int(n)}</span></span></div>'
               for i, (y, (v, n)) in enumerate(yrs.iterrows()))

def f2(v): return '—' if v is None else f'{v:.2f}'
prod = ''.join(f'<tr{" style=\"background:var(--cream-dark)\"" if p["型"].startswith("三房") else ""}><td>{p["型"]}</td><td class="num">{p["總面積中位"]:.2f}</td>'
               f'<td class="num">{p["全期n"]}</td><td class="num">{p["近四年n"]}</td><td class="num"><b>{f2(p["近四年不含車中位"])}</b></td>'
               f'<td class="num">{f2(p["近四年含車中位"])}</td></tr>' for p in S['產品'])
floors = ''.join(f'<tr><td>{b["帶"]}</td><td class="num">{b["n"]} 筆</td><td class="num"><b>{b["不含車中位"]:.2f}</b></td><td class="num">{b["含車中位"]:.2f}</td></tr>'
                 for b in S['樓層帶_110後'])
recent = ''
for r in df[df['yr'] >= 112].itertuples():
    est = '*' if r.車位價來源.startswith('估算') else ''
    recent += (f'<tr><td>{r.交易日期}</td><td>{r.棟別}・{r.樓層}F</td><td>{r.產品.split("（")[0]}</td><td class="num">{r.總價萬:,.0f}</td>'
               f'<td class="num">{r.總面積坪:.2f}</td><td class="num">{r.車位數}</td><td class="num"><b>{r.不含車單價:.2f}{est}</b></td>'
               f'<td class="num">{r.含車單價:.2f}</td><td>{r.備註.replace(";", " ").strip()[:10]}</td></tr>')
rent = ''.join(f'<tr><td>{r["日期"]}</td><td>{r["棟"]}・{r["樓層"]}F</td><td class="num">{r["面積坪"]:.2f}</td><td class="num">{r["車位"]}</td>'
               f'<td class="num"><b>{r["月租萬"]:.2f}</b></td><td class="num">{r["月租萬"]*10000/r["面積坪"]:,.0f}</td></tr>' for r in R['近三年整戶'])
site = (HERE / '棟別圖.svg').read_text(encoding='utf-8').split('?>')[-1].replace('B1 本戶', 'B1').replace('fill="#C0392B" stroke="#8e2a1f"', 'fill="#fff" stroke="#9fb3bf"').replace('fill="#fff">B1', 'fill="#1F4E5F">B1').replace('fill="#fbe3df"', 'fill="#6b7d8a"')
lo = same[same['yr'] >= 112]['不含車單價']
premium = (SAME4['net'] / CMP3['net'] - 1) * 100

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
<meta name="keywords" content="百達馥麗,百達馥麗實價登錄,百達馥麗行情,中興街287號,中興街289號,興富發,台中西區大樓,勤美 大樓 行情">
<meta name="author" content="助哥｜台中行情"><meta name="robots" content="index,follow">
<link rel="canonical" href="{URL}">
<meta name="theme-color" content="#1F3A2E">
<meta property="og:type" content="website"><meta property="og:site_name" content="助哥｜台中行情">
<meta property="og:title" content="{TITLE}"><meta property="og:description" content="{DESC}">
<meta property="og:url" content="{URL}">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Article","headline":"百達馥麗 實價登錄分析","description":"百達馥麗 實價登錄行情、產品分型、樓層、租金與西區同級大樓比較。","author":{{"@type":"Person","name":"助哥"}},"datePublished":"2026-10-16","mainEntityOfPage":"{URL}"}}</script>
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
 <div class="tag"><span class="dot" style="background:#B08D3F"></span>住宅大樓　／　台中西區・勤美草悟道生活圈（非七期）</div>
 <h1>百達馥麗</h1>
 <p class="lead">中興街287／289號｜興富發建設｜99 年完工・屋齡 16 年｜34 樓｜191 戶｜SRC<br>
 <b style="color:var(--gold-light)">看行情要先分產品：三房＋1 比全社區中位高約 {(SAME4["net"]/S["近三年"]["net"]-1)*100:.0f}%</b></p>
 <div class="kpis">
  <div class="kpi"><div class="v">{SAME4["net"]:.1f}</div><div class="l">萬/坪・三房＋1 同型<br>房屋單價（已扣車位）・112–115</div></div>
  <div class="kpi"><div class="v">{S["近三年"]["net"]:.1f}</div><div class="l">萬/坪・全社區近三年<br>總價÷總坪數 {S["近三年"]["gross"]:.1f}</div></div>
  <div class="kpi"><div class="v">{CMP3["net"]:.1f}</div><div class="l">萬/坪・西區同級大樓<br>屋齡 15–20 年・80–100 坪</div></div>
  <div class="kpi"><div class="v">{R["近三年整戶每坪中位_元"]}</div><div class="l">元/坪/月・整戶租金<br>月租中位 {R["近三年整戶月租中位"]:.1f} 萬</div></div>
 </div>
</div></header>

<section id="trend"><div class="wrap">
 <div class="sec-tag">PRICE TREND</div><h2 class="sec-title">同型三房＋1：逐年行情</h2>
 <p class="sec-lead">扣除車位後約 88 坪的三房＋1（權狀含 1 車位約 93 坪、含 2 車位約 98 坪），是社區成交最多的產品。
 以下為「房屋單價（已扣車位）」年度中位，n 為筆數。</p>
 <div style="background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px 24px">{bars}
  <div style="border-top:1px solid #ece4d4;margin-top:14px;padding-top:12px;font-size:14px">112–115 年同型 {SAME4["n"]} 筆：{lo.min():.1f}–{lo.max():.1f} 萬/坪，中位 <b>{SAME4["net"]:.1f}</b>。樣本少，單筆差異大，議價前逐戶比對。</div></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">長條自 0 起算。單價為（總價－車位價）÷（總坪數－車位坪數）；車位價未揭露者以社區坡道平面每席中位 {S["車位"]["每席價格中位_112後"]:.0f} 萬估算。</p>
 <div class="note" style="margin-top:20px"><b>◆ 全社區中位會被拉低。</b>近三年全社區 {S["近三年"]["n"]} 筆中位 {S["近三年"]["net"]:.1f}，
 但其中 114/12 兩戶 30F 為毛胚屋（31.7–32.0）、113/01 一戶為 2F 大坪（31.6）。只看「全社區平均」會低估三房＋1 的行情。</div>
</div></section>

<section id="products" style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">PRODUCT MIX</div><h2 class="sec-title">四種產品，行情不同</h2>
 <p class="sec-lead">實登總坪數有含 1 車位、2 車位、3–4 車位之分，直接比會失準；本頁依扣車位後的坪數分型。</p>
 <div class="tblwrap"><table><tr><th>產品</th><th class="num">總坪數中位</th><th class="num">全期筆數</th><th class="num">112–115 筆數</th><th class="num">房屋單價（已扣車位）</th><th class="num">總價÷總坪數（車位一起算）</th></tr>{prod}</table></div>
 <div class="two" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:22px;margin-top:26px">
  <div><h3 style="font-size:18px;margin-bottom:10px">樓層：不是定價主軸</h3>
   <div class="tblwrap"><table style="min-width:360px"><tr><th>樓層帶（110 年後）</th><th class="num">筆數</th><th class="num">已扣車位</th><th class="num">車位一起算</th></tr>{floors}</table></div>
   <p style="font-size:13px;color:var(--mute);margin-top:8px">高樓層中位反而略低，因含多戶毛胚與大坪數；本社區價格主要看產品與屋況。</p></div>
  <div><h3 style="font-size:18px;margin-bottom:10px">棟別配置</h3>
   <div style="background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px">{site}</div>
   <p style="font-size:13px;color:var(--mute);margin-top:8px">A 棟＝289 號、B 棟＝287 號，每層三戶。依社區棟別圖重繪，非比例尺。</p></div>
 </div>
</div></section>

<section><div class="wrap">
 <div class="sec-tag">RECENT DEALS</div><h2 class="sec-title">112 年後成交明細</h2>
 <div class="tblwrap"><table><tr><th>日期</th><th>棟別</th><th>產品</th><th class="num">總價（萬）</th><th class="num">總坪數</th><th class="num">車位</th><th class="num">已扣車位</th><th class="num">車位一起算</th><th>備註</th></tr>{recent}</table></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">* 車位價未揭露，以每席中位估算。單位：萬元／坪。</p>
</div></section>

<section id="compare" style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">AREA COMPARISON</div><h2 class="sec-title">跟西區同級大樓比</h2>
 <p class="sec-lead">比較組：西區、住宅大樓、屋齡 15–20 年、總坪數 80–100 坪，113–115 年 {CMP3["n"]} 筆（不含本社區）。</p>
 <div class="cards">
  <div class="card"><h3>西區同級 中位</h3><div class="big">{CMP3["net"]:.1f}</div><p>萬/坪（已扣車位）；車位一起算 {CMP3["gross"]:.1f}</p></div>
  <div class="card"><h3>百達同型 中位</h3><div class="big">{SAME4["net"]:.1f}</div><p>萬/坪（已扣車位），112–115 年 {SAME4["n"]} 筆</p></div>
  <div class="card"><h3>社區溢價</h3><div class="big">{premium:+.0f}%</div><p>34 層地標、大型公設與勤美生活圈的價差</p></div>
 </div>
</div></section>

<section><div class="wrap">
 <div class="sec-tag">RENT</div><h2 class="sec-title">整戶出租行情</h2>
 <div class="tblwrap"><table style="min-width:520px"><tr><th>日期</th><th>棟別</th><th class="num">面積（坪）</th><th class="num">車位</th><th class="num">月租（萬）</th><th class="num">元／坪／月</th></tr>{rent}</table></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">近三年整戶出租，已排除分租套房與多人合租。以同型行情換算，毛租金約 2.2–2.5%，以自住為主。</p>
</div></section>

<section style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">TWO SIDES</div><h2 class="sec-title">同一份數據，兩種用法</h2>
 <div class="cards">
  <div class="card" style="border-top:3px solid var(--t2)"><div class="sec-tag" style="color:var(--t2)">如果你是買方</div>
   <h3 style="margin:8px 0 10px">先確認產品與屋況</h3>
   <p style="font-size:15px;line-height:1.85">拿同型的成交比，不要拿全社區平均。也要看屋況：114/12 兩戶 30F 毛胚屋成交 31.7–32.0 萬/坪，明顯低於同期。樓層在這個社區不是主要價差。</p></div>
  <div class="card" style="border-top:3px solid var(--t3)"><div class="sec-tag" style="color:var(--t3)">如果你是屋主</div>
   <h3 style="margin:8px 0 10px">主打屋況與採光</h3>
   <p style="font-size:15px;line-height:1.85">三房＋1 近四年成交在 38–43 萬/坪之間；裝修完整、可立即入住的戶，比較有機會談到區間上緣。</p></div>
 </div>
</div></section>

<section><div class="wrap"><div class="cta">
 <h2>想知道百達馥麗某一戶現在值多少？</h2>
 <p>我手上有 {S["有效筆數"]} 筆買賣、{R["筆數"]} 筆租賃的逐筆明細。<br>告訴我棟別、樓層跟車位數，我算給你看。</p>
 <a class="btn btn-primary" href="https://line.me/R/ti/p/@080akczk" target="_blank" rel="noopener">加 LINE 聊聊 →</a>
 <div style="margin-top:18px"><a class="btn btn-ghost" style="color:#e6dfcd;border-color:#4a6255" href="../qiqi-realestate.html">← 回台中行情首頁</a></div>
</div></div></section>
<footer><div class="wrap"><div class="fx">
<div><b>助哥｜台中行情</b><div style="margin-top:6px">不賣房子，賣判斷。<br>實登逐筆重算，數字附來源。</div></div>
<div><b>導覽</b><div style="margin-top:6px"><a href="../qiqi-realestate.html">住宅・土地・廠房</a>　<a href="../qiqi-office.html">七期商辦</a><br><a href="../blog/index.html">文章</a></div></div>
<div><b>聯絡</b><div style="margin-top:6px"><a href="https://line.me/R/ti/p/@080akczk" target="_blank" rel="noopener">LINE 諮詢</a></div></div>
</div>
<div class="dis">
資料來源：內政部不動產交易實價查詢服務網，中興街287號、289號買賣與租賃（101/01–115/10）；西區住宅大樓・屋齡15–20年・總面積80–100坪買賣（112/01–115/10）；撈取日 2026-10-16。
單價一律用中位數，已扣除車位、排除特殊關係與部分移轉；樣本少的區間另有標註。<br>
本頁為市場資訊整理與分析，僅供參考，<b style="font-size:12px">不構成價格保證、投資建議或要約</b>，亦非特定物件之銷售廣告。
個案成交條件差異極大，實際價格應以現場查看與個案評估為準。過去成交不代表未來表現。<br>
永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號
</div></div></footer></body></html>'''
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(html, encoding='utf-8')
print('→', OUT)
