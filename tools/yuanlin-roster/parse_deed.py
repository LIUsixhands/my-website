# -*- coding: utf-8 -*-
"""解析土地登記第二類謄本純文字 -> 結構化 JSON"""
import re, json, sys, unicodedata

def nfkc(s):
    # NFKC 會把全形冒號/括號轉半形，此處把冒號轉回全形以利欄位切分
    return unicodedata.normalize('NFKC', s or '').replace(':', '：').strip()

def val(line):
    line = nfkc(line)
    return line.split('：',1)[1].strip() if '：' in line else ''

def rawval(line):
    # 保留全形＊等原樣（姓名、統一編號的遮罩字元）
    line = line.replace(':', '：')
    return line.split('：',1)[1].strip() if '：' in line else ''

def clean_star(s):
    s = re.sub(r'[*＊]+', '', s or '').strip()
    return s

def blank(s):
    s = (s or '').strip()
    return '' if s in ('（空白）','(空白)','') else s

HEAD_RE = re.compile(r'^(\S*?[鄉鎮市區])(\S+段)\s*(\d{4}-\d{4})地號')

def parse(text):
    parcels = []
    cur_file = None
    pages = []  # (file, pagetext)
    for chunk in text.split('@@@PAGE@@@'):
        if chunk.startswith(' ') or chunk.strip():
            pass
    # split into pages preserving file
    parts = re.split(r'@@@FILE@@@ ', text)
    for part in parts:
        if not part.strip(): continue
        lines = part.split('\n')
        cur_file = lines[0].strip()
        body = '\n'.join(lines[1:])
        for pg in re.split(r'@@@PAGE@@@ \d+\n', body):
            if pg.strip():
                pages.append((cur_file, pg))

    # group pages into 謄本 (new one when title line present)
    docs = []
    for f, pg in pages:
        if '土地登記第二類謄本' in pg.split('\n')[0] or '土地登記第二類謄本' in '\n'.join(pg.split('\n')[:2]):
            docs.append([f, pg])
        else:
            if docs: docs[-1][1] += '\n' + pg
            else: docs.append([f, pg])

    for f, doc in docs:
        p = parse_doc(doc)
        if p:
            p['來源檔案'] = f
            parcels.append(p)
    return parcels

def parse_doc(doc):
    lines = [l.rstrip() for l in doc.split('\n')]
    # 去除頁尾注意事項與續次頁
    out = []
    for l in lines:
        if l.startswith('※注意') or '本謄本列印完畢' in l:
            break_flag = True
        out.append(l)
    # remove note blocks
    txt = '\n'.join(lines)
    txt = re.sub(r'※注意：.*?(?=(\n土地登記第二類謄本|\Z))', '', txt, flags=re.S)
    txt = txt.replace('〈 本謄本列印完畢 〉', '')
    lines = [l for l in txt.split('\n')
             if l.strip() and '（續次頁）' not in l and not l.startswith('頁次')]

    info = {}
    for l in lines:
        m = HEAD_RE.match(nfkc(l).replace(' ', ' '))
        if m:
            info['鄉鎮市'] = m.group(1); info['段別'] = m.group(2); info['地號全碼'] = m.group(3)
            break
    if '地號全碼' not in info:
        return None
    mu, xu = info['地號全碼'].split('-')
    info['地號'] = str(int(mu)) + ('-' + str(int(xu)) if int(xu) else '')
    info['縣市'] = '彰化縣'
    for l in lines:
        if l.startswith('列印時間'):
            info['謄本列印時間'] = val(l); break
    for l in lines:
        if '資料管轄機關' in l:
            m = re.search(r'資料管轄機關：(\S+?)\s', l+' ')
            if m: info['資料管轄機關'] = m.group(1)
            break

    # 移除（含續頁重複的）頁首列，避免混入欄位值
    def is_header(l):
        n = nfkc(l)
        return bool(HEAD_RE.match(n) or n.startswith('列印時間') or n.startswith('本謄本係')
                    or n.startswith('謄本種類碼') or n.startswith('資料管轄機關')
                    or '土地登記第二類謄本' in n
                    or re.match(r'^\S*地政事務所\s*主\s*任', n)
                    or re.match(r'^\S*電謄字第', n))
    lines = [l for l in lines if not is_header(l)]

    # section indices
    def find(marker):
        for i,l in enumerate(lines):
            if marker in l: return i
        return None
    i_mark = find('土地標示部'); i_own = find('土地所有權部'); i_oth = find('土地他項權利部')
    end_own = i_oth if i_oth is not None else len(lines)

    # 標示部
    sec = lines[i_mark+1:i_own] if i_mark is not None and i_own is not None else []
    other_reg = []
    grab = False
    for l in sec:
        n = nfkc(l)
        if n.startswith('登記日期'):
            m = re.search(r'登記日期：(\S+?)\s*登記原因：(\S*)', n)
            if m: info['標示部登記日期'], info['標示部登記原因'] = m.group(1), m.group(2)
            grab = False
        elif n.startswith('面 積') or n.startswith('面積'):
            m = re.search(r'([\d,\.]+)平方公尺', clean_star(n))
            info['面積_平方公尺'] = float(m.group(1).replace(',','')) if m else None
            grab = False
        elif n.startswith('使用分區'):
            m = re.search(r'使用分區：(.*?)\s*使用地類別：(.*)$', n)
            if m:
                info['使用分區'] = blank(m.group(1)); info['使用地類別'] = blank(m.group(2))
            grab = False
        elif '公告土地現值' in n:
            m = re.search(r'([\d,]+)元', clean_star(n))
            info['公告土地現值_元每平方公尺'] = int(m.group(1).replace(',','')) if m else None
            m2 = re.match(r'(民國\d+年\d+月)', n)
            if m2: info['公告現值期別'] = m2.group(1)
            grab = False
        elif n.startswith('地上建物建號'):
            info['地上建物建號'] = blank(val(n)); grab = False
        elif n.startswith('其他登記事項'):
            other_reg.append(blank(val(n))); grab = True
        elif grab:
            other_reg.append(n)
    info['標示部其他登記事項'] = ' / '.join([x for x in other_reg if x])

    # 所有權部
    owners = []
    LABEL = re.compile(r'^([\u4e00-\u9fff]{2,10})：')
    if i_own is not None:
        cur = None; last_key = None; who = None
        for l in lines[i_own+1:end_own]:
            n = nfkc(l)
            m = re.match(r'[（(](\d{4})[）)]登記次序：(\S+)', n)
            if m:
                if cur: owners.append(cur)
                cur = {'序號': m.group(1), '登記次序': m.group(2), '其他登記事項': []}
                last_key = None; who = None
                continue
            if cur is None: continue
            lm = LABEL.match(n.replace(' ', ''))
            label = lm.group(1) if lm else None
            if label:
                v_raw = rawval(l); v = nfkc(v_raw)
                if label == '登記日期':
                    mm = re.search(r'登記日期：(\S+?)\s*登記原因：(\S*)', n)
                    if mm: cur['登記日期'], cur['登記原因'] = mm.group(1), mm.group(2)
                elif label == '原因發生日期': cur['原因發生日期'] = v
                elif label == '所有權人': cur['所有權人'] = v_raw; who = 'owner'
                elif label == '管理者': cur['管理者'] = v_raw; who = 'mgr'
                elif label == '統一編號':
                    cur['管理者統一編號' if who == 'mgr' else '統一編號'] = v_raw
                elif label == '住址':
                    cur['管理者住址' if who == 'mgr' else '住址'] = blank(v)
                elif label == '權利範圍': cur['權利範圍'] = clean_star(v)
                elif label == '權狀字號':
                    w = clean_star(v).replace('-', '')
                    cur['權狀字號'] = '' if '空白' in w else w
                elif label == '當期申報地價':
                    mm = re.search(r'([\d,\.]+)元', clean_star(n))
                    cur['當期申報地價_元每平方公尺'] = float(mm.group(1).replace(',','')) if mm else None
                elif label == '歷次取得權利範圍': cur['歷次取得權利範圍'] = clean_star(v)
                elif label == '相關他項權利登記次序': cur['相關他項權利登記次序'] = v
                elif label == '其他登記事項':
                    if blank(v): cur['其他登記事項'].append(blank(v))
                elif label in ('前次移轉現值或原規定地價',): pass
                else:
                    cur[label] = v          # 地價備註事項、權狀註記事項等一律保留
                last_key = label
            else:
                if last_key == '其他登記事項' and n.strip():
                    cur['其他登記事項'].append(n.strip())
                elif last_key in cur and isinstance(cur.get(last_key), str) and n.strip() \
                        and last_key not in ('登記日期','權利範圍','所有權人','統一編號'):
                    cur[last_key] = (cur[last_key] + n.strip()).strip()
        if cur: owners.append(cur)
    for o in owners:
        o['其他登記事項'] = ' / '.join(o.get('其他登記事項') or [])
    info['所有權人清單'] = owners

    # 他項權利部
    rights = []
    if i_oth is not None:
        cur=None; last=None
        for l in lines[i_oth+1:]:
            n = nfkc(l)
            m = re.match(r'[（(](\d{4})[）)]登記次序：(\S+)\s*權利種類：(\S+)', n)
            if m:
                if cur: rights.append(cur)
                cur={'序號':m.group(1),'登記次序':m.group(2),'權利種類':m.group(3)}
                continue
            if cur is None: continue
            if re.match(r'^權\s*利\s*人', n): cur['權利人']=val(n); last='r'
            elif n.startswith('統一編號'): cur['權利人統一編號']=val(n)
            elif re.match(r'^住\s*址', n): cur['權利人住址']=val(n)
            elif '擔保債權總金額' in n:
                mm=re.search(r'([\d,]+)元', clean_star(n)); cur['擔保債權總金額']=int(mm.group(1).replace(',','')) if mm else None
            elif n.startswith('登記日期'):
                mm=re.search(r'登記日期：(\S+?)\s*登記原因：(\S*)',n)
                if mm: cur['登記日期'],cur['登記原因']=mm.group(1),mm.group(2)
            elif n.startswith('標的登記次序'): cur['標的登記次序']=val(n)
            elif n.startswith('設定權利範圍'): cur['設定權利範圍']=clean_star(val(n))
            elif n.startswith('共同擔保地號'): cur['共同擔保地號']=val(n)
            elif n.startswith('存續期間'): cur['存續期間']=val(n)
        if cur: rights.append(cur)
    info['他項權利清單'] = rights
    return info

if __name__ == '__main__':
    text = open(sys.argv[1]).read()
    ps = parse(text)
    json.dump(ps, open(sys.argv[2],'w'), ensure_ascii=False, indent=1)
    print("parcels:", len(ps))
    for p in ps:
        print(p['段別'], p['地號'], p.get('面積_平方公尺'), '所有權人', len(p['所有權人清單']), '他項', len(p['他項權利清單']))
