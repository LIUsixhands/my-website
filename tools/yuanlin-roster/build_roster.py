# -*- coding: utf-8 -*-
"""把解析後的謄本 JSON 併入「員林交流道特定區 地主同意書整合名冊.xlsx」
用法: python3 build_xlsx.py data.json out.xlsx [區塊] [--merge 既有.xlsx]
可重複執行，後續批次自動併入並保留人工填寫欄位。"""
import json, sys, os, re, datetime
from fractions import Fraction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

PING = 3.305785  # 1坪 = 3.305785 ㎡
MANUAL = ['同意書狀態','紙本收件日','印鑑證明','聯絡方式','上次接觸日','下次追蹤日','位置關鍵性','備註']
STATUS = '"未接觸,已接觸,意向(口頭/LINE),已簽紙本,已備印鑑,婉拒,持續協商"'
SEAL   = '"未備,已備,不需"'
KEY    = '"邊緣,一般,卡中央,卡道路,卡出入口"'

HDR = ['區塊','縣市','鄉鎮市','段別','地號','地號全碼','宗地面積(㎡)','宗地面積(坪)',
       '公告現值(元/㎡)','宗地現值總額(元)','使用分區','使用地類別',
       '登記次序','所有權人','統一編號','所有權人類型','管理者',
       '權利範圍','持分型態','持分比例','持分面積(㎡)','持分面積(坪)','持分現值(元)',
       '登記日期','登記原因','權狀字號','設定他項權利','其他登記事項'] + MANUAL + \
      ['謄本列印時間','來源檔案','資料鍵值']

ZH_DIGIT = str.maketrans('０１２３４５６７８９', '0123456789')

def share_type(rv):
    rv = rv or ''
    if '公同共有' in rv: return '公同共有'
    if re.search(r'(\d+)分之(\d+)', rv):
        m = re.search(r'(\d+)分之(\d+)', rv)
        return '單獨所有' if m.group(1) == m.group(2) else '分別共有'
    return '待確認'

def frac(s):
    if not s: return None
    s = s.replace('全部','').replace('公同共有','').strip()
    m = re.search(r'(\d+)分之(\d+)', s)
    if m: return Fraction(int(m.group(2)), int(m.group(1)))
    if '全部' in (s or '') or s == '': return Fraction(1,1)
    return None

def joint_groups(owners):
    """辨識公同共有群組。優先讀「主登記2.3.4…為公同共有」註記，
    讀不到時退而以相同權利範圍字串歸為同一群。回傳 (登記次序->群組id, 群組id->人數)"""
    gid, members = {}, {}
    for o in owners:
        if '公同共有' not in (o.get('權利範圍') or ''): continue
        seq = o.get('登記次序','')
        note = (o.get('其他登記事項') or '').translate(ZH_DIGIT)
        m = re.search(r'主登記([\d．\.、,\s]+)為公同共有', note)
        if m:
            nums = tuple(sorted(int(x) for x in re.findall(r'\d+', m.group(1))))
            key = ('note', nums)
        else:
            key = ('rv', o.get('權利範圍'))
        gid[seq] = key
        members.setdefault(key, set()).add(seq)
    gsize = {}
    for key, seqs in members.items():
        # 有註記時以註記列舉的人數為準（可涵蓋本謄本以外的登記次序）
        gsize[key] = len(key[1]) if key[0] == 'note' else len(seqs)
    return gid, gsize

def owner_type(name, uid):
    n, u = name or '', uid or ''
    if n in ('中華民國',) or '國有' in n: return '公有(國有)'
    if re.search(r'(縣|市|鄉|鎮)政府$|^(彰化縣|臺灣省|台灣省)', n): return '公有(地方)'
    if re.search(r'(公司|農會|銀行|合作社|工廠|企業社|寺|宮|廟|協會|基金會|學校)', n): return '法人/團體'
    if re.match(r'^\d{8}$', u): return '法人/團體'
    if re.match(r'^\d{10}$', u): return '公有(國有)'
    if re.search(r'[A-Za-z]', u): return '自然人'
    return '待確認'

def rows_from(parcels, block):
    out = []
    for p in parcels:
        area = p.get('面積_平方公尺') or 0
        cur  = p.get('公告土地現值_元每平方公尺') or 0
        gid, gsize = joint_groups(p.get('所有權人清單', []))
        rights_by_seq = {}
        for r in p.get('他項權利清單', []):
            rights_by_seq.setdefault(r.get('標的登記次序',''), []).append(
                f"{r.get('權利種類','')}／{r.get('權利人','')}")
        for o in p.get('所有權人清單', []):
            f = frac(o.get('權利範圍'))
            st = share_type(o.get('權利範圍'))
            seq = o.get('登記次序','')
            if st == '公同共有' and f is not None:
                n = gsize.get(gid.get(seq), 1) or 1
                f = f / n                      # 公同共有無應有部分，按人數均分推估
                st = f'公同共有(全體{n}人)'
            sh_area = float(area) * float(f) if f else None
            uid = o.get('統一編號','')
            key = f"{p['段別']}|{p['地號全碼']}|{o.get('登記次序','')}|{uid}"
            out.append({
                '區塊': block, '縣市': p.get('縣市',''), '鄉鎮市': p.get('鄉鎮市',''),
                '段別': p.get('段別',''), '地號': p.get('地號',''), '地號全碼': p.get('地號全碼',''),
                '宗地面積(㎡)': area, '宗地面積(坪)': round(area/PING,2) if area else None,
                '公告現值(元/㎡)': cur or None,
                '宗地現值總額(元)': round(area*cur) if area and cur else None,
                '使用分區': p.get('使用分區','') or '(空白)', '使用地類別': p.get('使用地類別','') or '(空白)',
                '登記次序': o.get('登記次序',''), '所有權人': o.get('所有權人',''), '統一編號': uid,
                '所有權人類型': owner_type(o.get('所有權人'), uid),
                '管理者': o.get('管理者',''),
                '權利範圍': o.get('權利範圍',''), '持分型態': st,
                '持分比例': round(float(f),6) if f else None,
                '持分面積(㎡)': round(sh_area,2) if sh_area is not None else None,
                '持分面積(坪)': round(sh_area/PING,2) if sh_area is not None else None,
                '持分現值(元)': round(sh_area*cur) if sh_area is not None and cur else None,
                '登記日期': o.get('登記日期',''), '登記原因': o.get('登記原因',''),
                '權狀字號': o.get('權狀字號',''),
                '設定他項權利': '；'.join(rights_by_seq.get(o.get('登記次序',''), [])),
                '其他登記事項': '／'.join(x for x in [
                    o.get('其他登記事項',''),
                    ('地價備註：'+o['地價備註事項']) if o.get('地價備註事項') else '',
                    ('權狀註記：'+o['權狀註記事項']) if o.get('權狀註記事項') else '',
                ] if x),
                '同意書狀態': '未接觸', '紙本收件日': '', '印鑑證明': '未備', '聯絡方式': '',
                '上次接觸日': '', '下次追蹤日': '', '位置關鍵性': '', '備註': '',
                '謄本列印時間': re.sub(r'\s*頁次.*$', '', p.get('謄本列印時間','')),
                '來源檔案': p.get('來源檔案',''), '資料鍵值': key,
            })
    return out

def right_rows(parcels, block):
    out=[]
    for p in parcels:
        for r in p.get('他項權利清單', []):
            out.append([block, p.get('地號',''), p.get('地號全碼',''), r.get('序號',''),
                        r.get('登記次序',''), r.get('權利種類',''), r.get('權利人',''),
                        r.get('權利人統一編號',''), r.get('擔保債權總金額'),
                        r.get('標的登記次序',''), r.get('設定權利範圍',''),
                        r.get('存續期間',''), r.get('共同擔保地號',''),
                        r.get('登記日期',''), r.get('登記原因','')])
    return out

# ---------- 樣式 ----------
H_FILL = PatternFill('solid', fgColor='1F3864')
M_FILL = PatternFill('solid', fgColor='C55A11')   # 人工填寫欄位
S_FILL = PatternFill('solid', fgColor='F2F2F2')
THIN = Border(*[Side(style='thin', color='BFBFBF')]*4)

def style_header(ws, headers, manual=()):
    for c, h in enumerate(headers, 1):
        cell = ws.cell(1, c, h)
        cell.fill = M_FILL if h in manual else H_FILL
        cell.font = Font(bold=True, color='FFFFFF', size=10)
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions

def autowidth(ws, headers, maxw=32):
    for c, h in enumerate(headers, 1):
        w = max([len(str(h))*2] + [len(str(ws.cell(r, c).value or ''))*1.6
                                   for r in range(2, min(ws.max_row, 400)+1)])
        ws.column_dimensions[get_column_letter(c)].width = min(max(w+2, 8), maxw)

def main():
    src, out = sys.argv[1], sys.argv[2]
    block = sys.argv[3] if len(sys.argv) > 3 else 'A區'
    parcels = json.load(open(src))
    new = rows_from(parcels, block)

    # ---- 併入既有檔案（保留人工填寫欄位）----
    old_rows, old_rights = [], []
    if os.path.exists(out):
        wb0 = load_workbook(out)
        if '地主同意書總表' in wb0.sheetnames:
            ws0 = wb0['地主同意書總表']
            h0 = [c.value for c in ws0[1]]
            for r in ws0.iter_rows(min_row=2, values_only=True):
                if r and r[0]: old_rows.append(dict(zip(h0, r)))
        if '他項權利' in wb0.sheetnames:
            ws1 = wb0['他項權利']
            for r in ws1.iter_rows(min_row=2, values_only=True):
                if r and r[1] is not None: old_rights.append(list(r))
    keep = {r.get('資料鍵值'): r for r in old_rows}
    merged = []
    for r in new:
        prev = keep.pop(r['資料鍵值'], None)
        if prev:
            for m in MANUAL:
                if prev.get(m) not in (None, ''): r[m] = prev[m]
        merged.append(r)
    merged += list(keep.values())            # 既有但本批未含者保留
    merged.sort(key=lambda r: (str(r.get('段別')), str(r.get('地號全碼')), str(r.get('登記次序'))))

    rights = right_rows(parcels, block)
    seen = {tuple(map(str, x[1:6])) for x in rights}
    for x in old_rights:
        if tuple(map(str, x[1:6])) not in seen: rights.append(x)
    rights.sort(key=lambda x: (str(x[2]), str(x[3])))

    wb = Workbook(); wb.remove(wb.active)

    # ===== 1. 地主同意書總表 =====
    ws = wb.create_sheet('地主同意書總表')
    style_header(ws, HDR, MANUAL)
    for r in merged:
        ws.append([r.get(h) for h in HDR])
    n = ws.max_row
    for row in ws.iter_rows(min_row=2, max_row=n, max_col=len(HDR)):
        for c in row:
            c.border = THIN; c.font = Font(size=10)
            c.alignment = Alignment(vertical='center')
    for h, fmt in [('宗地面積(㎡)','#,##0.00'),('宗地面積(坪)','#,##0.00'),
                   ('公告現值(元/㎡)','#,##0'),('宗地現值總額(元)','#,##0'),
                   ('持分比例','0.000000'),('持分面積(㎡)','#,##0.00'),
                   ('持分面積(坪)','#,##0.00'),('持分現值(元)','#,##0')]:
        ci = HDR.index(h)+1
        for r in range(2, n+1): ws.cell(r, ci).number_format = fmt
    if n >= 2:
        for col, dv_f in [('同意書狀態', STATUS), ('印鑑證明', SEAL), ('位置關鍵性', KEY)]:
            dv = DataValidation(type='list', formula1=dv_f, allow_blank=True)
            ws.add_data_validation(dv)
            L = get_column_letter(HDR.index(col)+1)
            dv.add(f'{L}2:{L}{max(n,2000)}')
    ws.auto_filter.ref = f'A1:{get_column_letter(len(HDR))}{n}'
    autowidth(ws, HDR)
    ws.column_dimensions[get_column_letter(HDR.index('資料鍵值')+1)].hidden = True

    # ===== 2. 地號彙總 =====
    H2 = ['區塊','段別','地號','地號全碼','宗地面積(㎡)','宗地面積(坪)','公告現值(元/㎡)',
          '所有權人數','持分型態','持分合計檢核','公私有別','他項權利筆數','已簽紙本人數','同意進度',
          '位置關鍵性','備註']
    ws2 = wb.create_sheet('地號彙總'); style_header(ws2, H2, ('位置關鍵性','備註'))
    par = {}
    for r in merged:
        k = (r['段別'], r['地號全碼'])
        d = par.setdefault(k, {'r': r, 'n': 0, 'sum': Fraction(0), 'types': set(), 'jt': False})
        d['n'] += 1
        st = r.get('持分型態','') or ''
        f = frac(r.get('權利範圍'))
        if st.startswith('公同共有'):
            gk = (r['段別'], r['地號全碼'], r.get('權利範圍'))
            if gk not in d.setdefault('joint', set()):
                d['joint'].add(gk)
                if f: d['sum'] += f          # 整群只計一次
        elif f:
            d['sum'] += f
        d['types'].add(r.get('所有權人類型',''))
        if st.startswith('公同共有'): d['jt'] = True
    rcount = {}
    for x in rights: rcount[str(x[2])] = rcount.get(str(x[2]), 0) + 1
    CL_NO = get_column_letter(HDR.index('地號全碼')+1)
    CL_ST = get_column_letter(HDR.index('同意書狀態')+1)
    S_NO  = get_column_letter(H2.index('地號全碼')+1)      # 本表地號全碼欄
    S_CNT = get_column_letter(H2.index('所有權人數')+1)
    S_SGN = get_column_letter(H2.index('已簽紙本人數')+1)
    rn = 1
    for (seg, no), d in sorted(par.items()):
        r = d['r']; rn += 1
        s = float(d['sum'])
        pub = [t for t in d['types'] if t.startswith('公有')]
        kind = '公有' if pub and len(d['types']) == 1 else ('公私共有' if pub else '私有')
        ws2.append([r['區塊'], seg, r['地號'], no, r['宗地面積(㎡)'], r['宗地面積(坪)'],
                    r['公告現值(元/㎡)'], d['n'],
                    '公同共有' if d.get('jt') else ('單獨所有' if d['n'] == 1 else '分別共有'),
                    '✔ 1/1' if abs(s-1) < 1e-9 else f'⚠ {s:.4f}',
                    kind, rcount.get(no, 0),
                    f'=COUNTIFS(地主同意書總表!${CL_NO}:${CL_NO},${S_NO}{rn},地主同意書總表!${CL_ST}:${CL_ST},"已簽紙本")'
                    f'+COUNTIFS(地主同意書總表!${CL_NO}:${CL_NO},${S_NO}{rn},地主同意書總表!${CL_ST}:${CL_ST},"已備印鑑")',
                    f'=IF(${S_CNT}{rn}=0,"",${S_SGN}{rn}&" / "&${S_CNT}{rn})', '', ''])
    for row in ws2.iter_rows(min_row=2, max_row=ws2.max_row, max_col=len(H2)):
        for c in row: c.border = THIN; c.font = Font(size=10)
    for h, fmt in [('宗地面積(㎡)','#,##0.00'),('宗地面積(坪)','#,##0.00'),('公告現值(元/㎡)','#,##0')]:
        ci = H2.index(h)+1
        for r in range(2, ws2.max_row+1): ws2.cell(r, ci).number_format = fmt
    dv = DataValidation(type='list', formula1=KEY, allow_blank=True); ws2.add_data_validation(dv)
    L = get_column_letter(H2.index('位置關鍵性')+1); dv.add(f'{L}2:{L}500')
    ws2.auto_filter.ref = f'A1:{get_column_letter(len(H2))}{ws2.max_row}'
    autowidth(ws2, H2)

    # ===== 3. 地主彙總（＝同意書份數）=====
    H3 = ['所有權人','統一編號','所有權人類型','管理者','登記筆數','涉及地號數','合計持分面積(㎡)',
          '合計持分面積(坪)','合計持分現值(元)','涉及地號','待釐清','同意書狀態','紙本收件日',
          '印鑑證明','聯絡方式','下次追蹤日','備註']
    ws3 = wb.create_sheet('地主彙總'); style_header(ws3, H3, ('同意書狀態','紙本收件日','印鑑證明','聯絡方式','下次追蹤日','備註'))
    own = {}
    for r in merged:
        k = (r.get('所有權人',''), r.get('統一編號',''))
        d = own.setdefault(k, {'t': r.get('所有權人類型',''), 'mgr': r.get('管理者',''),
                               'n': 0, 'a': 0.0, 'v': 0, 'lots': [], 'st': [], 'note': []})
        d['n'] += 1
        d['a'] += r.get('持分面積(㎡)') or 0
        d['v'] += r.get('持分現值(元)') or 0
        d['lots'].append(r.get('地號',''))
        d.setdefault('seq', []).append((r.get('地號',''), r.get('登記次序','')))
        d['st'].append(r.get('同意書狀態',''))
        for f in ('聯絡方式','紙本收件日','印鑑證明','下次追蹤日','備註'):
            pass
        d.setdefault('manual', {})
        for f in ('紙本收件日','印鑑證明','聯絡方式','下次追蹤日','備註'):
            if r.get(f) not in (None,'','未備'): d['manual'][f] = r.get(f)
    for (nm, uid), d in sorted(own.items(), key=lambda x: (-x[1]['a'], x[0][0])):
        sts = set(d['st'])
        st = d['st'][0] if len(sts) == 1 else '各地號不一致'
        m = d.get('manual', {})
        lots = sorted(set(d['lots']), key=lambda s: (len(s), s))
        dup = sorted({lot for lot, _ in d.get('seq', [])
                      if sum(1 for l2, _ in d['seq'] if l2 == lot) > 1})
        flag = ('地號 ' + '、'.join(dup) + ' 有多筆登記次序，遮罩統編相同；'
                '須以第一類謄本確認是否同一人（影響同意書份數）') if dup else ''
        ws3.append([nm, uid, d['t'], d['mgr'], d['n'], len(lots), round(d['a'], 2),
                    round(d['a']/PING, 2), d['v'], '、'.join(lots), flag,
                    st, m.get('紙本收件日',''), m.get('印鑑證明','未備'), m.get('聯絡方式',''),
                    m.get('下次追蹤日',''), m.get('備註','')])
    for row in ws3.iter_rows(min_row=2, max_row=ws3.max_row, max_col=len(H3)):
        for c in row: c.border = THIN; c.font = Font(size=10)
    for h, fmt in [('合計持分面積(㎡)','#,##0.00'),('合計持分面積(坪)','#,##0.00'),('合計持分現值(元)','#,##0')]:
        ci = H3.index(h)+1
        for r in range(2, ws3.max_row+1): ws3.cell(r, ci).number_format = fmt
    dv = DataValidation(type='list', formula1=STATUS, allow_blank=True); ws3.add_data_validation(dv)
    L = get_column_letter(H3.index('同意書狀態')+1); dv.add(f'{L}2:{L}1000')
    dv2 = DataValidation(type='list', formula1=SEAL, allow_blank=True); ws3.add_data_validation(dv2)
    L2 = get_column_letter(H3.index('印鑑證明')+1); dv2.add(f'{L2}2:{L2}1000')
    ws3.auto_filter.ref = f'A1:{get_column_letter(len(H3))}{ws3.max_row}'
    autowidth(ws3, H3)

    # ===== 4. 他項權利 =====
    H4 = ['區塊','地號','地號全碼','序號','登記次序','權利種類','權利人','權利人統一編號',
          '擔保債權總金額','標的登記次序','設定權利範圍','存續期間','共同擔保地號','登記日期','登記原因']
    ws4 = wb.create_sheet('他項權利'); style_header(ws4, H4)
    for x in rights: ws4.append(x)
    for row in ws4.iter_rows(min_row=2, max_row=ws4.max_row, max_col=len(H4)):
        for c in row: c.border = THIN; c.font = Font(size=10)
    ci = H4.index('擔保債權總金額')+1
    for r in range(2, ws4.max_row+1): ws4.cell(r, ci).number_format = '#,##0'
    autowidth(ws4, H4)

    # ===== 5. 說明與進度 =====
    ws5 = wb.create_sheet('說明與進度')
    total_area = sum(v['r']['宗地面積(㎡)'] or 0 for v in par.values())
    n_lots = len(par); n_owner_rows = len(merged); n_persons = len(own)
    pub_lots = sum(1 for v in par.values() if any(t.startswith('公有') for t in v['types']))
    A = [
        ('員林交流道附近特定區｜產業發展儲備用地　地主同意書整合名冊', ''),
        ('', ''),
        ('■ 本檔用途', '整合都市計畫變更階段所需之「土地使用同意書」，逐地號 × 逐所有權人追蹤'),
        ('資料來源', '土地登記第二類謄本（電子謄本）'),
        ('本次區塊', block),
        ('產製日期', datetime.date.today().isoformat()),
        ('', ''),
        ('■ 目前彙總（隨每批謄本累加）', ''),
        ('已建檔地號筆數', n_lots),
        ('已建檔面積（㎡）', round(total_area, 2)),
        ('已建檔面積（坪）', round(total_area/PING, 2)),
        ('已建檔面積（公頃）', round(total_area/10000, 4)),
        ('所有權登記筆數（地號×所有權人）', n_owner_rows),
        ('不重複地主人數（依姓名＋遮罩統編歸戶）', n_persons),
        ('同意書份數（估）', f'{n_persons} 份；遇「待釐清」註記者須先以第一類謄本確認是否同一人'),
        ('含公有地之地號數', pub_lots),
        ('他項權利（抵押權等）筆數', len(rights)),
        ('', ''),
        ('■ 門檻對照（來源：主要計畫四通 表9-1，頁9-2）', ''),
        ('A區公告面積', '13.18 公頃 = 131,800 ㎡'),
        ('B區公告面積', '9.35 公頃 = 93,500 ㎡'),
        ('變更面積門檻', '不得小於 5 公頃（都市計畫農業區變更使用審議規範 §12）'),
        ('本檔已建檔面積佔 A 區比例', f'{total_area/131800*100:.2f}%'),
        ('本檔已建檔面積佔 5 公頃門檻比例', f'{total_area/50000*100:.2f}%'),
        ('', ''),
        ('■ 同意門檻（兩階段，不可混用）', ''),
        ('變更階段（現階段）', '申請範圍內全體土地所有權人同意（100%），須檢具土地使用同意書'),
        ('重劃階段（變更發布後）', '私有土地所有權人半數以上且面積超過半數（平均地權條例 §58）'),
        ('送件硬期限', '117.08.31（主要計畫 112.08.31 發布實施起 5 年內）'),
        ('', ''),
        ('■ 工作提醒', ''),
        ('1', '催收優先序依「位置關鍵性」排，不依面積大小排（卡道路／卡中央的小坪數殺傷力最大）'),
        ('2', '口頭應允、LINE 回訊一律歸「意向」，只有紙本才計入同意率'),
        ('3', '夾雜公有地／未登錄地須另取得「同意合併開發證明書」（審議規範 §51），流程最久，最早啟動'),
        ('4', '面積均為謄本登載值，實際面積以核定圖實地分割測量面積為準'),
        ('5', '本檔含個資，僅限內部使用；不得外流、不得寫入對外文案或公開連結'),
        ('', ''),
        ('■ 欄位說明', ''),
        ('橘色標題欄位', '人工填寫（同意書狀態／紙本收件日／印鑑證明／聯絡方式／接觸日／追蹤日／位置關鍵性／備註）'),
        ('深藍色標題欄位', '謄本自動帶入，請勿手改（下批併檔會覆蓋）'),
        ('資料鍵值', '併檔比對用（段別|地號全碼|登記次序|統一編號），已隱藏'),
        ('持分合計檢核', '各地號權利範圍加總應為 1；顯示 ⚠ 表示謄本尚未收齊或解析需複核'),
        ('公同共有的處理', '公同共有無應有部分，謄本每人皆載「公同共有 1分之1」。本檔持分合計以整群計 1 次；'
                          '持分面積為「按公同共有人數均分」之推估值，僅供面積概算，不是應有部分。'
                          '同意書仍須公同共有人全體簽署（民法 §828）。'),
        ('後續批次', '再上傳謄本 PDF 即可併入本檔，人工填寫欄位會自動保留'),
    ]
    ws5.column_dimensions['A'].width = 36; ws5.column_dimensions['B'].width = 86
    for i, (a, b) in enumerate(A, 1):
        ws5.cell(i, 1, a); ws5.cell(i, 2, b)
        if str(a).startswith('■') or i == 1:
            ws5.cell(i, 1).font = Font(bold=True, size=12 if i == 1 else 11, color='1F3864')
        ws5.cell(i, 2).alignment = Alignment(wrap_text=True, vertical='center')
    wb.move_sheet('說明與進度', offset=-4)
    wb.save(out)
    print(f'OK -> {out}')
    print(f'地號 {n_lots} 筆｜所有權登記 {n_owner_rows} 筆｜地主 {n_persons} 人｜'
          f'面積 {total_area:,.2f} ㎡ ({total_area/10000:.4f} ha)｜他項權利 {len(rights)} 筆')

main()
