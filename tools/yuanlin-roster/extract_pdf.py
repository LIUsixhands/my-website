# -*- coding: utf-8 -*-
"""抽取土地登記第二類謄本 PDF 的文字。
自動濾掉：斜向浮水印（字級 >= 20）與頁緣防偽碼（頁面左右邊界）。
用法: python3 extract_pdf.py <PDF資料夾或PDF檔> <輸出.txt>
"""
import pdfplumber, glob, os, sys, hashlib

def main():
    src, out = sys.argv[1], sys.argv[2]
    files = sorted(glob.glob(os.path.join(src, '*.pdf'))) if os.path.isdir(src) else [src]
    if not files:
        sys.exit('找不到 PDF：' + src)
    seen, uniq, dup = {}, [], []
    for f in files:
        h = hashlib.md5(open(f, 'rb').read()).hexdigest()
        if h in seen:
            dup.append((os.path.basename(f), os.path.basename(seen[h])))
        else:
            seen[h] = f; uniq.append(f)
    for d, orig in dup:
        print(f'  略過重複檔（內容同 {orig}）：{d}')
    files = uniq

    buf = []
    for f in files:
        buf.append('@@@FILE@@@ ' + os.path.basename(f))
        with pdfplumber.open(f) as pdf:
            for i, p in enumerate(pdf.pages):
                pp = p.crop((30, 0, min(562, p.width), p.height)).filter(
                    lambda o: o.get('size', 0) < 20 if o['object_type'] == 'char' else True)
                buf.append('@@@PAGE@@@ %d' % (i + 1))
                buf.append(pp.extract_text() or '')
    open(out, 'w').write('\n'.join(buf))
    print(f'{len(files)} 個 PDF（已去重，略過 {len(dup)} 個重複檔）-> {out}')

main()
