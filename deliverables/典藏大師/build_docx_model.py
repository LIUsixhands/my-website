"""典藏大師 銷售報告書 Word 版：內容模型（與 build_report.py 同源同字句），輸出 docx_model.json 給 build_docx.js 排版。
兩張圖由 build_report.py 產出的 HTML 擷取成 PNG（_docx_assets/svg0–1.png），文字與表格為 Word 原生可編輯。"""
import json
from pathlib import Path

HERE = Path(__file__).parent
A = HERE / '_docx_assets'
S = json.load(open(HERE / 'summary.json'))
L = S['本戶']; ASK = L['開價']
COMM = [c for c in S['本社區'] if not c['排除']]; C108 = COMM[0]
CY = {d['年']: d for d in S['比較組逐年']}; Z7 = {d['年']: d for d in S['七期逐年']}
CMP = S['比較組']
LAND_MED = [CY[y]['地坪中位'] for y in CY]; LAND_GAP = L['土地'] - min(LAND_MED)
Z108, Z115 = Z7[108]['土地單價中位'], Z7[115]['土地單價中位']
P_ALL, P_HOUSE, P_LAND = '總價÷建物總坪（車位一起算）', '房屋單價（已扣車位）', '總價÷土地坪'
def wan(v): return '—' if v is None else f'{v:,.0f}'
def pct(a, b): return (a / b - 1) * 100
def yl(y): return str(y) if y < 115 else '115*'
def img(name): return str(HERE / name)

B = []
def add(t, **k): B.append(dict(type=t, **k))
def section(eyebrow, title, sub=None):
    add('spacer'); add('eyebrow', text=eyebrow); add('h1', text=title)
    if sub: add('p', text=sub, muted=True)

# ---------- 封面 ----------
add('image', path=img('位置圖.png'), width=16.5)
add('eyebrow', text='PROPERTY SALES REPORT')
add('p', text='臺中市南屯區 · 大通街85號 · 七期惠文學區', gold=True)
add('title', text='典藏大師')
add('subtitle', text='買方銷售報告書 · 鄰綠園道透天邊間 · 六房 · B1 車位')
add('p', text=f'臺中市南屯區大通街85號・地上 4 層透天・{L["朝向"]}向　開價 {wan(ASK)} 萬 · 建坪 {L["建坪"]} 坪（含車位 {L["車位面積"]} 坪）· 土地 {L["土地"]} 坪 · {L["格局"]}', muted=True)
add('h2', text='核心數字')
add('bullets', items=[
    '七期重劃區內、惠文國小／惠文高中學區的社區型透天，門前綠園道，地下室有坡道平面車位。',
    f'土地 {L["土地"]} 坪，比七期同齡透天常見的 {min(LAND_MED):.0f}–{max(LAND_MED):.0f} 坪多出約 {LAND_GAP:.0f} 坪。',
    f'開價換算{P_LAND} {L["土地單價"]:.1f} 萬，七期同齡透天 112–115 年逐年中位在 {min(d["土地單價中位"] for d in CY.values()):.0f}–{max(d["土地單價中位"] for d in CY.values()):.0f} 之間。',
    f'開價 {wan(ASK)} 萬，{P_ALL} {L["總價除總坪"]:.1f} 萬／坪。'])
add('contact', qr=[img('QR_LINE.png'), img('QR_網站.png')], title='預約帶看')
add('p', text='資料：內政部實價登錄（臺中市南屯區透天厝買賣 108/01–115/10，查詢 2026-10-24）；物件資料取自刊登資訊與建物謄本', small=True)

# ---------- 01 物件總覽 ----------
section('01 · PROPERTY OVERVIEW', '物件總覽')
add('kpi', items=[(wan(ASK), '萬元', '開價（含 B1 車位 1 席）'), (f'{L["土地"]}', '坪', '土地坪數'), (f'{L["建坪"]}', '坪', f'建物總坪（含車位 {L["車位面積"]}）'),
                  (f'{L["主建物"]}', '坪', '主建物（1–4F 室內）'), (f'{L["管理費月"]:,}', '元／月', '管理費')])
add('h2', text='本戶資料')
add('spec', rows=[('地址', '臺中市南屯區大通街85號'), ('型態', f'透天・地上 4 層・邊間・{L["朝向"]}向'), ('格局', f'{L["格局"]}，六房皆開窗（刊登資料）'),
                  ('土地', f'{L["土地"]} 坪（惠義段・都市計畫住宅區）'),
                  ('建物', f'主建物 {L["主建物"]}＋附屬（雨遮）{L["附屬"]}＋共同使用 {L["共同"]}（含車位 {L["車位面積"]}）＝{L["建坪"]} 坪'),
                  ('車位', L['車位']), ('管理費', f'月繳 {L["管理費月"]:,} 元'), ('屋齡', f'約 {L["屋齡"]} 年（87 年 8 月完工，88/02/23 登記）'),
                  ('登記用途', L['用途']), ('物件編號', L['物件編號'])])
add('h2', text='社區與學區')
add('spec', rows=[('社區', '典藏大師（實登社區簡稱「大師特別座」），透天社區、有管理組織'), ('地下室', '社區共用地下室，坡道進出、平面車位'),
                  ('小學', L['小學']), ('國中', L['國中']), ('分區', '七期重劃區（南屯區惠義段）'),
                  ('道路', '門前約 10 米路，門口無畫線可再停一部車（刊登資料）'), ('景觀', '面綠園道，客廳面自家花圃')])
add('h2', text='坪數怎麼看')
add('note', lines=[f'權狀建坪 {L["建坪"]} 坪裡，主建物 {L["主建物"]} 坪是 1 到 4 樓的室內空間；共同使用 {L["共同"]} 坪是社區地下室等公共部分，其中 {L["車位面積"]} 坪是本戶的 B1 車位。',
                   f'透天的價值大半在土地。本戶土地 {L["土地"]} 坪，七期同齡、同坪數透天 112–115 年的地坪中位在 {min(LAND_MED):.1f}–{max(LAND_MED):.1f} 坪，本戶多出約 {LAND_GAP:.0f} 坪。'])

# ---------- 02 區位 ----------
section('02 · LOCATION', '區位與六大賣點')
add('image', path=img('位置圖.png'), width=16.5, caption='房屋圖示為本戶位置（大通街與綠園道轉角）。地圖取自刊登資訊，北方朝上。')
add('feats', items=[('七期・惠文學區', '位在七期重劃區南側，學區為市立惠文國小、惠文高中附設國中。'),
                    ('面綠園道', '房子在大通街與綠園道轉角，客廳面自家花圃與園道綠帶，前方沒有房子擋。'),
                    ('邊間・六房皆開窗', '邊間三面採光，6 房 2 廳 3 衛，每一房都有對外窗，適合三代同堂或要書房、孝親房的家庭。'),
                    (f'地大・土地 {L["土地"]} 坪', f'比七期同齡透天常見的地坪多約 {LAND_GAP:.0f} 坪；透天的價值主要在土地。'),
                    ('B1 車位＋門前停車', '社區地下室坡道平面車位 1 席（B1-25），門前約 10 米路、無畫線可再停一部車。'),
                    ('生活圈完整', '北邊緊鄰公益路二段；刊登資料載明鄰近 IKEA、文心森林公園、捷運綠線水安宮站。')])
add('note', text=f'社區型透天：典藏大師為有管理組織的透天社區，共用地下室停車；管理費月繳 {L["管理費月"]:,} 元，可向管委會索取收支與地下室維護紀錄。')

# ---------- 03 本社區與同街廓 ----------
HEAD = ['日期', '門牌', '社區', '屋齡', '樓層', '總價（萬）', '建坪', '地坪', '車位', P_ALL, P_LAND]
WID = [8, 19, 9, 4, 5, 8, 7, 7, 4, 11, 9]
NUM = [3, 5, 6, 7, 8, 9, 10]
def trow(c): return [c['日期'], c['門牌'], c['社區'], str(c['屋齡']), c['樓層'], wan(c['總價']), f'{c["建坪"]:.2f}', f'{c["地坪"]:.2f}', str(c['車位']), f'{c["建坪單價"]:.1f}', f'{c["土地單價"]:.1f}']
section('03 · NEARBY SALES', '本社區與同街廓成交',
        f'南屯區透天實登 108/01–115/10 中，本社區（實登社區簡稱「大師特別座」）成交 {len(COMM)} 筆（淡橘底），以及同一街廓（大通街、大川街、大觀路）其他透天 {len(S["同街廓"])} 筆。透天比較看兩個單價：{P_ALL}，以及{P_LAND}。')
rows = [trow(c) for c in COMM] + [trow(c) for c in S['同街廓']]
add('table', headers=HEAD, rows=rows, hl=list(range(len(COMM))), widths=WID, num=NUM, small=True)
add('p', text='單位：萬元、坪、萬元／坪。建坪含車位坪數（如有）。已排除特殊關係、持分、非住宅等交易。', small=True)
add('h2', text='同社區 108 年成交 vs 本戶')
add('spec', rows=[('108/11 成交', f'{wan(C108["總價"])} 萬・建坪 {C108["建坪"]} 坪（含車位 2 席）・土地 {C108["地坪"]} 坪・屋齡 {C108["屋齡"]} 年'),
                  ('本戶開價', f'{wan(ASK)} 萬・建坪 {L["建坪"]} 坪（含車位 1 席）・土地 {L["土地"]} 坪・屋齡 {L["屋齡"]} 年')])
add('p', text=f'兩戶土地都約 33 坪、主建物約 51–52 坪，條件接近。以{P_LAND}看，108 年成交 {C108["土地單價"]:.1f}，本戶開價 {L["土地單價"]:.1f}，差 {pct(L["土地單價"], C108["土地單價"]):+.0f}%；同期七期透天土地單價中位由 108 年 {Z108:.1f} 到 115 年 {Z115:.1f}，{pct(Z115, Z108):+.0f}%。')
add('h2', text='七期透天土地單價，逐年中位')
add('image', path=str(A / 'svg0.png'), width=17.0, caption='七期重劃區（南屯部分）透天有效成交，每年中位數；115* 為 115 年 1–8 月成交。橘點為本社區 108/11 成交，紅線為本戶開價。')

# ---------- 04 比較 ----------
section('04 · AREA COMPARISON', '七期同齡透天比較',
        f'條件：{S["比較組條件"]}，共 {len(CMP)} 筆（不含本社區）。逐年列中位，不跨年合併；單價達同年中位 1.8 倍以上的 {sum("異常" in c["標記"] for c in CMP)} 筆列出但不計入中位。')
rows = [[yl(y), str(d['n']), wan(d['總價中位']), f'{d["建坪中位"]:.1f}', f'{d["地坪中位"]:.1f}', f'{d["建坪單價中位"]:.1f}', f'{d["土地單價中位"]:.1f}'] for y, d in CY.items()]
rows.append(['本戶開價', '—', wan(ASK), f'{L["建坪"]:.1f}', f'{L["土地"]:.1f}', f'{L["總價除總坪"]:.1f}', f'{L["土地單價"]:.1f}'])
add('table', headers=['年度', '筆數', '總價中位（萬）', '建坪中位', '地坪中位', P_ALL, P_LAND], rows=rows, hl=[len(rows) - 1],
    widths=[12, 8, 14, 11, 11, 24, 20], num=[1, 2, 3, 4, 5, 6])
add('p', text='115* 為 115 年 1–8 月。單位：萬元、坪、萬元／坪。', small=True)
add('h2', text='每一筆放在一起看')
add('image', path=str(A / 'svg1.png'), width=17.0, caption=f'橫軸為{P_LAND}，縱軸為{P_ALL}；每點一筆 112–115 年成交。紅點為本戶開價。')
add('note', text='怎麼看這張圖：本戶在土地單價上落在比較組中間，建坪單價偏高。原因是本戶建坪精簡、土地較大：同樣的總價，建坪越小，「總價÷建坪」就越高。透天買的是土地，建議以土地單價為主要比較基準。')

# ---------- 05 明細 ----------
section('05 · COMPARABLES', '比較組明細', '七期重劃區透天・屋齡 18–35 年・建物總面積 60–100 坪・112/01–115/10，新到舊排列。淡橘底為同街廓；備註「異常」者不計入中位。')
rows, hl = [], []
for i, c in enumerate(reversed(CMP)):
    r = trow(c)
    if '異常' in c['標記']: r[-1] += '（異常）'
    if c['標記'].startswith('同街廓'): hl.append(i)
    rows.append(r)
add('table', headers=HEAD, rows=rows, hl=hl, widths=WID, num=NUM, small=True)
add('p', text='單位：萬元、坪、萬元／坪。資料：內政部實價登錄，查詢 2026-10-24。', small=True)

# ---------- 06 價格分析與試算 ----------
section("06 · PRICE & BUYER'S GUIDE", '價格分析與購屋試算')
add('kpi', items=[(f'{L["土地單價"]:.1f}', '萬／土地坪', f'開價 {P_LAND}'), (f'{L["總價除總坪"]:.1f}', '萬／坪', f'開價 {P_ALL}'),
                  (f'{L["房屋單價_扣車位"]:.1f}', '萬／坪', f'開價 {P_HOUSE}')])
rows = [['本戶開價', f'{L["總價除總坪"]:.1f}', f'{L["土地單價"]:.1f}', f'建坪 {L["建坪"]}、地坪 {L["土地"]}']]
rows += [[f'七期同齡透天 {yl(y)} 年中位（{d["n"]} 筆）', f'{d["建坪單價中位"]:.1f}', f'{d["土地單價中位"]:.1f}',
          f'本戶相差 建坪 {pct(L["總價除總坪"], d["建坪單價中位"]):+.0f}%／土地 {pct(L["土地單價"], d["土地單價中位"]):+.0f}%'] for y, d in CY.items()]
add('table', headers=['參考點', P_ALL, P_LAND, '說明'], rows=rows, hl=[0], widths=[32, 20, 16, 32], num=[1, 2])
add('note', text=f'{P_HOUSE}怎麼算：（總價－車位價）÷（總坪－車位坪）。南屯透天社區 B1 坡道平面車位實登揭露 3 筆，每席 150–200 萬；本戶車位 {L["車位面積"]} 坪較小，以 {L["車位估價"]} 萬估：（{wan(ASK)}－{L["車位估價"]}）÷ {L["扣車位面積"]:.2f} 坪＝{L["房屋單價_扣車位"]:.1f}。比較組多數未分開登記車位價，所以表格以總價÷建坪與總價÷土地坪比較。')
RATE, YEARS, LTV = 0.022, 30, 0.8
loan = ASK * LTV; rm = RATE / 12; pay = loan * 10000 * rm / (1 - (1 + rm) ** (-YEARS * 12)); down = ASK - loan
add('kpi', items=[(f'{ASK:,}', '萬元', '以開價試算'), (wan(down), '萬元', '自備款（兩成）'), (wan(loan), '萬元', '貸款（八成）'), (f'{pay/10000:.1f}', '萬元／月', '本息攤還')])
add('p', text=f'假設貸款八成、年利率 {RATE*100:.1f}%、{YEARS} 年本息平均攤還，每月約 {pay:,.0f} 元；另需預留契稅、代書與仲介服務費。實際成數依銀行鑑價與個人條件核定。', muted=True)
add('h2', text='看屋重點')
add('bullets', items=[f'屋況：屋齡約 {L["屋齡"]:.0f} 年，請看屋頂防水、外牆、管線與窗框；索取歷年修繕紀錄。',
                      '地下室與車位：確認 B1-25 位置、車道坡度與地下室排水，車位使用以分管協議為準。',
                      f'管理費：月繳 {L["管理費月"]:,} 元，可索取管委會收支與公共設施維護項目。',
                      '增建與花圃：花圃與門前空間的使用範圍，以現況、謄本與不動產說明書確認。'])
add('h2', text='資料來源與免責聲明')
add('p', text='實價登錄：內政部不動產交易實價查詢服務網，臺中市南屯區透天厝買賣 108/01–115/10（115 年成交登錄至 8 月），查詢日 2026-10-24；分區依土地地段判定。物件資料取自刊登資訊與建物謄本，地圖取自刊登頁。', small=True)
add('p', text='本報告書為不動產經紀業務之行銷參考資料，非不動產估價師出具之估價報告。行情統計與試算係依公開資料整理，不構成價格保證、投資建議或獲利承諾。實際面積、用途、產權及使用現況，以權狀、謄本、不動產說明書及買賣契約記載為準。', small=True)
add('contact', qr=[img('QR_LINE.png'), img('QR_網站.png')], title='預約帶看・行情諮詢')

from PIL import Image
def px(path):
    with Image.open(path) as im: return list(im.size)
for b in B:
    if b['type'] == 'image': b['px'] = px(b['path'])
json.dump(dict(blocks=B, footer_disc='永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號',
               footer_contact='助哥 0925-313-570　｜　LINE @080akczk　｜　sixhands.tw'),
          open(A / 'docx_model.json', 'w'), ensure_ascii=False, indent=1)
print('blocks', len(B))
