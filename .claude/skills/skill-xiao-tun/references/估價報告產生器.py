#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
估價報告產生器（精裝版 v1）— 小屯 · AI 數字員工龍蝦學院
用途：把單一物件數據填入 DATA，生成「房地產市場行情分析暨建議售價報告」PDF。
換一棟物件：複製 DATA、改數值、執行本檔即可產出新報告。
依賴：weasyprint（pip install weasyprint）；中文用系統字型 WenQuanYi Zen Hei。
合規：報告定位為「市場行情分析」，非不動產估價師法之估價報告（已含免責）。
"""
from weasyprint import HTML

# ===== 換棟只改這個 DATA =====
DATA = {
    "案名": "寶璽睿觀 · 公園綠景五房雙平車",
    "地址": "台中市西屯區惠文路788號 6樓之5",
    "物件副標": "5房3廳3衛 ｜ 總建坪 148.94 ｜ 雙平面車位",
    "報告編號": "YG0140543",
    "日期": "2026/05/22",
    # 基本資料 (欄位, 值) — 偶數欄位為淺底標籤
    "基本資料": [
        ("案名","寶璽睿觀（七期·公園綠景）"),("地址","西屯區惠文路788號6F之5"),
        ("格局","5房3廳3衛"),("樓層","6F / 20F（地下2層）"),
        ("總建坪","148.94 坪"),("淨房面積","130.96 坪（不含車位）"),
        ("車位","雙坡道平面 17.98坪"),("公設比","31.91%（不含車位）"),
        ("屋齡","18 年（097/02 完工）"),("構造","SRC鋼骨鋼筋混凝土／二丁掛"),
        ("朝向","建物朝西北·大門朝東南"),("管理費","19,340 元/月"),
        ("總戶數","65（戶/梯 2/2）"),("現況","空屋（可直接入住）"),
    ],
    "物件優勢": [
        "正面公園綠景（公一之三公園）、三面採光，視野與採光佳",
        "5房稀有大格局、雙平面車位，總價帶買方鎖定換屋／置產族",
        "社區設施：25米無邊鏡面泳池、健身房、SPA；SRC＋OILES制震、抗輻射節能玻璃",
        "學區：惠來國小、惠文國小、惠文高中國中部；近三越大遠百、林新醫院",
    ],
    # 區域市場 (指標, 數值, 判讀)
    "區域市場": [
        ("一年成交均價","65.35 萬/坪","含新案；中古宅低於此"),
        ("新案成交均價","85.27 萬/坪","新案天花板"),
        ("屋齡10-20年帶均價","43.81 萬/坪","本物件所屬屋齡帶"),
        ("近一年價格趨勢","-9.96%","價格修正中"),
        ("成交量變化","2024 高峰2251戶 → 2025 暴跌601戶（-73%）","量縮劇烈，買方市場"),
    ],
    "市場結論": "七期目前「價量俱跌」，量縮幅度（-73%）遠大於價跌（-9.96%），代表<b>有行無市、賣壓沉重</b>。此時訂價貼近行情，才能在買方觀望中勝出。",
    # 同社區比較 (基準, 淨單價, 說明)
    "社區比較": [
        ("社區歷史均值","43.7","有效17筆平均"),
        ("社區成交高標","52.5","113/03 八樓（近年最高）"),
        ("同戶型「之5」成交","約 46","112年 13F、14F（樓層更高）"),
        ("本戶開價推算","56.8","明顯高於上述全部基準"),
    ],
    "關鍵比較": "同棟同戶型「之5」於 13、14 樓成交淨價約 46 萬/坪；本戶位於<b>較低的 6 樓</b>，開價淨單價卻達 56.8，<b>高出逾 20%</b>。買方一經比對即難接受。",
    # 機率帶
    "機率帶": {"高_價":"6,900 萬以下","高_單":"≤ 50 萬/坪",
               "中_價":"6,900 ~ 7,250 萬","中_單":"50 ~ 52.5",
               "低_價":"7,300 萬以上","低_單":"≥ 53 萬/坪",
               "中位":"約 7,050 萬（淨單價約 51 萬/坪）","屋主期望":"7,800 萬"},
    # 售價策略 (項目, 值)
    "售價策略": [
        ("建議委託開價","<b>7,280 萬</b>（貼近合理上緣，預留議價空間）"),
        ("預期成交目標","<b>7,000 ~ 7,150 萬</b>（50% 合理帶中段）"),
        ("建議心理底價","<b>6,900 萬</b>（高機率成交線）"),
    ],
    "策略說明": [
        "若<b>追求速售</b>（3個月內）：開價貼近 7,180~7,280，成交機率高。",
        "若<b>願等待試高價</b>：可開 7,500，但市場量縮下，銷售期恐拉長且未必成交。",
        "<b>不建議</b>開價 7,800：淨單價超社區天花板，買方比對同棟成交後易卻步。",
    ],
    "資料區間": "101/10 ~ 114/04",
}

CSS = """
@page { size:A4; margin:1.6cm 1.5cm 1.8cm 1.5cm;
  @bottom-center{ content:"本報告為市場行情分析，非不動產估價師法之估價報告，僅供參考"; font-size:7pt; color:#999; }
  @bottom-right{ content:"第 " counter(page) " 頁"; font-size:8pt; color:#999; } }
@page :first { margin:0; @bottom-center{content:none;} @bottom-right{content:none;} }
* { font-family:"WenQuanYi Zen Hei",sans-serif; box-sizing:border-box; }
body { margin:0; color:#222; font-size:10.5pt; line-height:1.55; }
.cover { height:297mm; background:linear-gradient(135deg,#1A2942 0%,#2C3E5A 60%,#1A2942 100%); color:#fff; padding:42mm 24mm; position:relative; }
.cover .brand { font-size:12pt; letter-spacing:3px; color:#C9A961; border-bottom:1px solid #C9A96155; padding-bottom:8px; }
.cover h1 { font-size:30pt; margin:30mm 0 6mm; line-height:1.3; }
.cover .sub { font-size:13pt; color:#C9A961; }
.cover .obj { margin-top:26mm; padding:8mm; background:#ffffff10; border-left:4px solid #C9A961; }
.cover .obj b { font-size:15pt; color:#fff; }
.cover .meta { position:absolute; bottom:30mm; left:24mm; font-size:10pt; color:#cdd; }
.cover .meta span{ color:#C9A961; }
h2 { color:#1A5276; font-size:14pt; border-left:6px solid #C9A961; padding-left:10px; margin:18px 0 8px; }
h3 { color:#1A5276; font-size:11.5pt; margin:10px 0 4px; }
table { width:100%; border-collapse:collapse; margin:6px 0 10px; font-size:9.8pt; }
th,td { border:1px solid #ccc; padding:5px 7px; text-align:left; }
th { background:#1A5276; color:#fff; font-weight:normal; }
tr:nth-child(even) td { background:#F4F6F8; }
.kv td:nth-child(odd){ background:#EDF1F5; color:#1A5276; width:18%; }
.band { display:flex; margin:10px 0; border-radius:6px; overflow:hidden; }
.band div{ flex:1; padding:12px 10px; color:#fff; text-align:center; }
.b1{background:#27AE60;} .b2{background:#F39C12;} .b3{background:#C0392B;}
.band b{ font-size:14pt; display:block; }
.hl { background:#FBEFD8; border:1px solid #C9A961; padding:10px 14px; border-radius:6px; margin:8px 0; }
.note { font-size:8.5pt; color:#777; border-top:1px solid #ddd; padding-top:8px; margin-top:14px; }
.big { font-size:13pt; color:#C0392B; font-weight:bold; }
ul{ margin:4px 0 10px; padding-left:20px; } li{ margin:2px 0; }
"""

def generate(d, out_path):
    # 基本資料：兩欄一列
    bi = d['基本資料']; rows=""
    for i in range(0,len(bi),2):
        c=bi[i]; c2=bi[i+1] if i+1<len(bi) else ("","")
        rows+=f"<tr><td>{c[0]}</td><td>{c[1]}</td><td>{c2[0]}</td><td>{c2[1]}</td></tr>"
    adv = "".join(f"<li>{x}</li>" for x in d['物件優勢'])
    mkt = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a,b,c in d['區域市場'])
    cmp_rows=""
    for a,b,c in d['社區比較']:
        cls=' class="big"' if '本戶' in a else ''
        cmp_rows+=f"<tr><td{cls}>{a}</td><td{cls}>{b}</td><td>{c}</td></tr>"
    mb=d['機率帶']
    strat="".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a,b in d['售價策略'])
    stratnote="".join(f"<li>{x}</li>" for x in d['策略說明'])
    body=f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="cover">
 <div class="brand">助哥 ｜ 七期房地產 · 房仲土仲</div>
 <h1>房地產市場行情分析<br>暨建議售價報告</h1>
 <div class="sub">不賣房子，賣判斷 — 用數據幫您訂出最好成交的價格</div>
 <div class="obj"><b>{d['案名']}</b><br>{d['地址']}<br>{d['物件副標']}</div>
 <div class="meta">委託人：<span>屋主</span>　｜　分析提供：<span>助哥團隊</span><br>
  報告日期：<span>{d['日期']}</span>　｜　資料來源：內政部實價登錄<br>報告編號：<span>{d['報告編號']}</span></div>
</div>
<h2>一、物件基本資料</h2>
<table class="kv">{rows}</table>
<h3>物件優勢（價格支撐點）</h3><ul>{adv}</ul>
<h2>二、區域市場分析（七期重劃區）</h2>
<table><tr><th>指標</th><th>數值</th><th>判讀</th></tr>{mkt}</table>
<div class="hl"><b>市場結論：</b>{d['市場結論']}</div>
<h2>三、同社區實價登錄比較</h2>
<p>以本社區實登成交為基礎，剔除特殊關係交易、扣除車位後之「淨房單價」：</p>
<table><tr><th>比較基準</th><th>淨房單價（萬/坪）</th><th>說明</th></tr>{cmp_rows}</table>
<div class="hl"><b>關鍵比較：</b>{d['關鍵比較']}</div>
<h2>四、估價方法</h2>
<ul><li><b>市場比較法</b>：以同社區、同戶型、同屋齡帶之實登成交為基準。</li>
<li><b>扣車位淨房單價法</b>：將車位價值自總價扣除、車位坪數自面積扣除，還原真實房屋單價。</li>
<li>建議售價＝合理淨房單價 × 淨房面積 ＋ 車位價值。</li></ul>
<h2 style="page-break-before:always;">五、成交機率與建議售價（核心）</h2>
<div class="band">
 <div class="b1">高機率成交<br><b>{mb['高_價']}</b><br>約 80% 以上</div>
 <div class="b2">合理成交區間<br><b>{mb['中_價']}</b><br>約 50%</div>
 <div class="b3">低機率成交<br><b>{mb['低_價']}</b><br>約 20% 以下</div></div>
<table><tr><th>成交機率</th><th>總價區間</th><th>對應淨單價</th></tr>
<tr><td>● 80% 以上（容易成交）</td><td>{mb['高_價']}</td><td>{mb['高_單']}</td></tr>
<tr><td>● 約 50%（合理區間）</td><td>{mb['中_價']}</td><td>{mb['中_單']}</td></tr>
<tr><td>● 20% 以下（不易成交）</td><td>{mb['低_價']}</td><td>{mb['低_單']}</td></tr></table>
<div class="hl"><b>中位推估成交價：{mb['中位']}</b>。<br>屋主目前期望價 <b class="big">{mb['屋主期望']}</b> → 落在「20% 以下不易成交」區間，且高於社區歷史最高成交。</div>
<h2>六、建議售價策略</h2>
<table class="kv">{strat}</table><ul>{stratnote}</ul>
<div class="note">【免責聲明】本報告係依內政部不動產實價登錄公開資料及市場行情所作之「市場行情分析暨建議售價」，<b>非《不動產估價師法》所稱之不動產估價報告</b>，亦不作為交易價格之保證。實際成交價格受個別屋況、裝潢、市場時機、雙方議價等因素影響。淨房單價中車位價值為估算值。本報告僅供委託人內部參考。<br>
資料來源：內政部不動產交易實價登錄（統計區間 {d['資料區間']}）。　製作：助哥團隊 · AI 數字員工龍蝦學院。</div>
</body></html>"""
    HTML(string=body).write_pdf(out_path)
    return out_path

if __name__ == "__main__":
    p = generate(DATA, "/tmp/估價報告_輸出.pdf")
    print("PDF generated:", p)
