"""百達艷麗 網站行情分析頁：讀 summary.json / transactions.csv → blog/baida-yanli.html。
市場資訊頁，不放特定物件開價；版型沿用 office/*.html。"""
import json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
OUT = ROOT / 'blog' / 'baida-yanli.html'
S = json.load(open(HERE / 'summary.json'))
df = pd.read_csv(HERE / 'transactions.csv').fillna({'備註': ''})
df['yr'] = df['交易日期'].str[:3].astype(int)
R3, SAME3, CMP = S['近三年'], S['同型_近三年'], S['比較組']
CB = CMP['同級距']
URL = 'https://sixhands-studio.netlify.app/blog/baida-yanli.html'
TITLE = '百達艷麗 實價登錄分析｜西區臺灣大道二段419號 興富發 12 層｜行情・產品分型・西區比較'
DESC = (f'百達艷麗（台中西區臺灣大道二段419號）實登 {S["有效筆數"]} 筆逐筆扣車位重算：近三年 {R3["net"]:.1f} 萬/坪、'
        f'臨臺灣大道端戶 {SAME3["net"]:.1f}、西區同坪數大樓 {CB["net"]:.1f} 萬/坪。')
PK1 = S['車位']['每席價格中位_全期']

# 全社區年度中位長條
yrs = df.groupby('yr')['不含車單價'].agg(['median', 'count'])
mx = yrs['median'].max()
bars = ''.join(f'<div class="yrow"><span>{y} 年</span><span class="bar" style="width:{v/mx*100:.0f}%;background:#B08D3F;opacity:{.45+.04*i:.2f}"></span>'
               f'<span class="num"><b>{v:.1f}</b> <span style="font-size:11px;color:var(--mute)">n={int(n)}</span></span></div>'
               for i, (y, (v, n)) in enumerate(yrs.iterrows()))

def f2(v): return '—' if v is None else f'{v:.2f}'
prod = ''.join(f'<tr><td>{p["型"]}</td><td class="num">{p["總面積中位"]:.2f}</td><td class="num">{p["扣車位面積中位"]:.2f}</td>'
               f'<td class="num">{p["全期n"]}</td><td class="num">{p["近三年n"]}</td><td class="num"><b>{f2(p["近三年不含車中位"])}</b></td>'
               f'<td class="num">{f2(p["近三年含車中位"])}</td></tr>' for p in S['產品'])
floors = ''.join(f'<tr><td>{b["帶"]}</td><td class="num">{b["n"]} 筆</td><td class="num"><b>{b["不含車中位"]:.2f}</b></td><td class="num">{b["含車中位"]:.2f}</td></tr>'
                 for b in S['樓層帶_110後'])
recent = ''
for r in df[df['yr'] >= 110].itertuples():
    est = '*' if r.車位價來源.startswith('估算') else ''
    recent += (f'<tr><td>{r.交易日期}</td><td>{r.棟別}・{r.樓層}F</td><td>{r.產品.split("（")[0]}</td><td class="num">{r.總價萬:,.0f}</td>'
               f'<td class="num">{r.總面積坪:.2f}</td><td class="num">{r.車位數}</td><td class="num"><b>{r.不含車單價:.2f}{est}</b></td>'
               f'<td class="num">{r.含車單價:.2f}</td><td>{r.備註.replace(";", " ").strip()[:10]}</td></tr>')
cmp_rows = ''.join(f'<tr><td>{r["日期"]}</td><td>{r["社區"]}</td><td class="num">{r["屋齡"]}</td><td class="num">{r["樓層"]}F</td><td class="num">{r["總價"]:,.0f}</td>'
                   f'<td class="num">{r["扣車位"]:.2f}</td><td class="num"><b>{r["不含車"]:.2f}{"" if r["車位價"] else "*"}</b></td><td class="num">{r["含車"]:.2f}</td></tr>'
                   for r in CMP['明細'] if r['同級距'])
cd115 = df[(df['yr'] == 115)]['不含車單價']
end113 = df[(df['yr'] == 113) & df['產品'].str.startswith('端戶')]['不含車單價']

site = '''<svg viewBox="0 0 360 190" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans TC" font-size="10">
<rect x="6" y="20" width="26" height="150" fill="#e8edf0"/><text x="19" y="95" text-anchor="middle" fill="#5d6b76" writing-mode="tb">臺灣大道</text>
''' + ''.join(f'<rect x="{x}" y="{y}" width="114" height="70" rx="3" fill="{c}" stroke="#9fb3bf"/><text x="{x+57}" y="{y+32}" text-anchor="middle" font-size="20" font-weight="700" fill="#1F4E5F">{k}</text>'
              f'<text x="{x+57}" y="{y+52}" text-anchor="middle" font-size="9.5" fill="#5d6b76">{no}・{p}</text>'
              for k, x, y, no, p, c in [('A', 44, 20, '之1', '79.82P', '#f4ecdc'), ('B', 44, 100, '之2', '79.82P', '#f4ecdc'),
                                        ('D', 232, 20, '之5', '74.94P', '#eef3f6'), ('C', 232, 100, '之3', '74.94P', '#eef3f6')]) + '''
<rect x="164" y="60" width="62" height="70" fill="#d8e0e5"/><text x="195" y="92" text-anchor="middle" font-size="9" fill="#5d6b76">梯廳</text><text x="195" y="105" text-anchor="middle" font-size="9" fill="#5d6b76">2 部電梯</text>
<text x="354" y="14" text-anchor="end" font-size="9" fill="#7b8794">北 ↗</text></svg>'''

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
<meta name="keywords" content="百達艷麗,百達艷麗實價登錄,百達艷麗行情,臺灣大道二段419號,興富發,台中西區大樓,廣三SOGO 大樓 行情,勤美 大樓 行情">
<meta name="author" content="助哥｜台中行情"><meta name="robots" content="index,follow">
<link rel="canonical" href="{URL}">
<meta name="theme-color" content="#1F3A2E">
<meta property="og:type" content="website"><meta property="og:site_name" content="助哥｜台中行情">
<meta property="og:title" content="{TITLE}"><meta property="og:description" content="{DESC}">
<meta property="og:url" content="{URL}">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Article","headline":"百達艷麗 實價登錄分析","description":"百達艷麗 實價登錄行情、產品分型、樓層與西區同坪數大樓比較。","author":{{"@type":"Person","name":"助哥"}},"datePublished":"2026-10-23","mainEntityOfPage":"{URL}"}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700&family=Noto+Serif+TC:wght@500;700;900&display=swap" rel="stylesheet">
{css}</head><body><nav><div class="wrap">
<a class="brand" href="../qiqi-realestate.html">助哥<span style="color:var(--gold)">｜</span>台中行情</a>
<span class="sp"></span>
<a class="lk" href="#trend">逐年行情</a>
<a class="lk" href="#products">產品分型</a>
<a class="lk" href="#compare">西區比較</a>
<a class="lk" href="../blog/index.html">文章</a>
<a class="btn btn-primary btn-sm" href="https://line.me/R/ti/p/@080akczk" target="_blank" rel="noopener">聊聊</a>
</div></nav>
<header class="hero"><div class="wrap">
 <div class="tag"><span class="dot" style="background:#B08D3F"></span>住宅大樓　／　台中西區・廣三 SOGO／勤美生活圈（非七期）</div>
 <h1>百達艷麗</h1>
 <p class="lead">臺灣大道二段419號｜興富發建設｜屋齡約 17 年｜12 樓｜43 戶｜每層 4 戶｜RC<br>
 <b style="color:var(--gold-light)">小社區、樣本少：看行情要分端戶與內側戶，也要看成交年度</b></p>
 <div class="kpis">
  <div class="kpi"><div class="v">{R3["net"]:.1f}</div><div class="l">萬/坪・全社區近三年<br>房屋單價（已扣車位）・{R3["n"]} 筆</div></div>
  <div class="kpi"><div class="v">{R3["gross"]:.1f}</div><div class="l">萬/坪・全社區近三年<br>總價÷總坪數（車位一起算）</div></div>
  <div class="kpi"><div class="v">{SAME3["net"]:.1f}</div><div class="l">萬/坪・端戶 A／B<br>113 年 {SAME3["n"]} 筆</div></div>
  <div class="kpi"><div class="v">{CB["net"]:.1f}</div><div class="l">萬/坪・西區同坪數大樓<br>屋齡 10–20 年・{CB["n"]} 筆</div></div>
 </div>
</div></header>

<section id="trend"><div class="wrap">
 <div class="sec-tag">PRICE TREND</div><h2 class="sec-title">全社區：逐年行情</h2>
 <p class="sec-lead">101–115 年買賣 {S["原始筆數"]} 筆，排除特殊關係 {len(S["排除"])} 筆，有效 {S["有效筆數"]} 筆。以下為「房屋單價（已扣車位）」年度中位，n 為筆數；沒有成交的年份不列。</p>
 <div style="background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px 24px">{bars}
  <div style="border-top:1px solid #ece4d4;margin-top:14px;padding-top:12px;font-size:14px">113–115 年 {R3["n"]} 筆，中位 <b>{R3["net"]:.1f}</b>。115 年 {len(cd115)} 筆都是內側戶，中位 {cd115.median():.1f}；臨臺灣大道的端戶最近一次成交在 113 年（{end113.min():.1f}–{end113.max():.1f}）。</div></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">長條自 0 起算。單價為（總價－車位價）÷（總坪數－車位坪數）；車位價未揭露者以社區坡道平面每席中位 {PK1:.0f} 萬估算。</p>
 <div class="note" style="margin-top:20px"><b>◆ 這個社區的車位很「大」。</b>坡道平面車位每席登記約 9.6–11.2 坪，兩席就佔權狀 20 坪以上。
 所以「總價÷總坪數」會比「房屋單價（已扣車位）」低 {abs(R3["gap_pct"]):.0f}% 左右，比一般大樓的落差大；跟別的社區比，兩個數字要一起看。</div>
</div></section>

<section id="products" style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">PRODUCT MIX</div><h2 class="sec-title">端戶與內側戶，行情不同</h2>
 <p class="sec-lead">每層 4 戶：之1／之2 臨臺灣大道（扣車位約 80 坪），之3／之5 在內側（約 64 坪）。坪數小的內側戶，每坪單價較高。</p>
 <div class="tblwrap"><table><tr><th>產品</th><th class="num">總坪數中位</th><th class="num">扣車位中位</th><th class="num">全期筆數</th><th class="num">113–115 筆數</th><th class="num">房屋單價（已扣車位）</th><th class="num">總價÷總坪數（車位一起算）</th></tr>{prod}</table></div>
 <div class="two" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:22px;margin-top:26px">
  <div><h3 style="font-size:18px;margin-bottom:10px">樓層：不是定價主軸</h3>
   <div class="tblwrap"><table style="min-width:360px"><tr><th>樓層帶（110 年後）</th><th class="num">筆數</th><th class="num">已扣車位</th><th class="num">車位一起算</th></tr>{floors}</table></div>
   <p style="font-size:13px;color:var(--mute);margin-top:8px">12 層的社區樓層差小；價差主要來自成交年度與產品。</p></div>
  <div><h3 style="font-size:18px;margin-bottom:10px">樓層配置</h3>
   <div style="background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px">{site}</div>
   <p style="font-size:13px;color:var(--mute);margin-top:8px">依網路刊登之樓層平面重繪，非比例尺；坪數為刊登標示。</p></div>
 </div>
</div></section>

<section><div class="wrap">
 <div class="sec-tag">RECENT DEALS</div><h2 class="sec-title">110 年後成交明細</h2>
 <div class="tblwrap"><table><tr><th>日期</th><th>戶別</th><th>產品</th><th class="num">總價（萬）</th><th class="num">總坪數</th><th class="num">車位</th><th class="num">已扣車位</th><th class="num">車位一起算</th><th>備註</th></tr>{recent}</table></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">* 車位價未揭露，以每席中位估算。單位：萬元／坪。</p>
</div></section>

<section id="compare" style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">AREA COMPARISON</div><h2 class="sec-title">跟西區同坪數大樓比</h2>
 <p class="sec-lead">比較組：西區、大樓／華廈、屋齡 10–20 年、總坪數 80–110 坪（112/10–115/10），再取扣車位 71–81 坪、與端戶同級距的 {CB["n"]} 筆（不含本社區）。</p>
 <div class="cards">
  <div class="card"><h3>西區同坪數 中位</h3><div class="big">{CB["net"]:.1f}</div><p>萬/坪（已扣車位）；車位一起算 {CB["gross"]:.1f}</p></div>
  <div class="card"><h3>百達艷麗 近三年</h3><div class="big">{R3["net"]:.1f}</div><p>萬/坪（已扣車位）；車位一起算 {R3["gross"]:.1f}</p></div>
  <div class="card"><h3>價差</h3><div class="big">{(R3["net"]/CB["net"]-1)*100:+.0f}%</div><p>12 層 RC、43 戶的小社區，成交價低於西區同坪數大樓</p></div>
 </div>
 <div class="tblwrap" style="margin-top:22px"><table><tr><th>日期</th><th>社區</th><th class="num">屋齡</th><th class="num">樓層</th><th class="num">總價（萬）</th><th class="num">扣車位坪數</th><th class="num">已扣車位</th><th class="num">車位一起算</th></tr>{cmp_rows}</table></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">「—」為實登未填社區名。* 車位價未揭露，以比較組同類別車位中位估算。屋齡為交易當時。</p>
</div></section>

<section><div class="wrap">
 <div class="sec-tag">TWO SIDES</div><h2 class="sec-title">同一份數據，兩種用法</h2>
 <div class="cards">
  <div class="card" style="border-top:3px solid var(--t2)"><div class="sec-tag" style="color:var(--t2)">如果你是買方</div>
   <h3 style="margin:8px 0 10px">先分端戶、內側戶，再看年度</h3>
   <p style="font-size:15px;line-height:1.85">端戶最近成交在 113 年，內側戶在 115 年。拿單價比的時候，記得坪數不同、年份不同；車位坪數大，兩種單價都要問。</p></div>
  <div class="card" style="border-top:3px solid var(--t3)"><div class="sec-tag" style="color:var(--t3)">如果你是屋主</div>
   <h3 style="margin:8px 0 10px">兩席平面車位與屋況是籌碼</h3>
   <p style="font-size:15px;line-height:1.85">社區近三年成交 {R3["n"]} 筆、樣本少，單筆影響大。裝修、車位數與樓層條件寫清楚，買方才有比較基準。</p></div>
 </div>
</div></section>

<section style="background:#faf7ef"><div class="wrap"><div class="cta">
 <h2>想知道百達艷麗某一戶現在值多少？</h2>
 <p>我手上有 {S["有效筆數"]} 筆買賣的逐筆明細，和西區同坪數大樓的比較組。<br>告訴我戶別、樓層跟車位數，我算給你看。</p>
 <a class="btn btn-primary" href="https://line.me/R/ti/p/@080akczk" target="_blank" rel="noopener">加 LINE 聊聊 →</a>
 <div style="margin-top:18px"><a class="btn btn-ghost" style="color:#e6dfcd;border-color:#4a6255" href="../qiqi-realestate.html">← 回台中行情首頁</a></div>
</div></div></section>
<footer><div class="wrap"><div class="fx">
<div><b>助哥｜台中行情</b><div style="margin-top:6px">不賣房子，賣判斷。<br>實登逐筆重算，數字附來源。</div></div>
<div><b>導覽</b><div style="margin-top:6px"><a href="../qiqi-realestate.html">住宅・土地・廠房</a>　<a href="../qiqi-office.html">七期商辦</a><br><a href="../blog/index.html">文章</a></div></div>
<div><b>聯絡</b><div style="margin-top:6px"><a href="https://line.me/R/ti/p/@080akczk" target="_blank" rel="noopener">LINE 諮詢</a></div></div>
</div>
<div class="dis">
資料來源：內政部不動產交易實價查詢服務網，臺灣大道二段419號買賣（101/01–115/10）；西區住宅大樓／華廈・屋齡10–20年・總面積80–110坪買賣（112/10–115/10）；撈取日 2026-10-23。
單價一律用中位數，已扣除車位、排除特殊關係；樣本少的區間另有標註。<br>
本頁為市場資訊整理與分析，僅供參考，<b style="font-size:12px">不構成價格保證、投資建議或要約</b>，亦非特定物件之銷售廣告。
個案成交條件差異極大，實際價格應以現場查看與個案評估為準。過去成交不代表未來表現。<br>
永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號
</div></div></footer></body></html>'''
OUT.write_text(html, encoding='utf-8')
print('→', OUT)
