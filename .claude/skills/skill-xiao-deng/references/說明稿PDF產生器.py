#!/usr/bin/env python3
"""說明稿 PDF 產生器 — 小登

把 Markdown 說明稿（例：deliverables/一中透套/一中透套_屋主說明稿.md）轉成 A4 PDF，同資料夾同檔名。
用法：python3 說明稿PDF產生器.py <說明稿.md>
依賴：markdown、playwright（Chromium 在 /opt/pw-browsers）、字型 WenQuanYi Zen Hei。
"""
import glob, sys
from pathlib import Path

import markdown

SRC = Path(sys.argv[1]).resolve()
md = SRC.read_text(encoding='utf-8')
body = markdown.markdown(md, extensions=['tables', 'sane_lists'])
CONTACT = '助哥 0925-313-570　｜　LINE @080akczk　｜　sixhands.tw'
DISC = '永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號'
CSS = '''
@page { size: A4; margin: 16mm 16mm 20mm 16mm; }
* { box-sizing: border-box; }
body { font-family: "WenQuanYi Zen Hei", sans-serif; color: #222; font-size: 10.2pt; line-height: 1.75;
  -webkit-print-color-adjust: exact; print-color-adjust: exact; margin: 0; }
h1 { font-size: 19pt; color: #1A2942; border-left: 6px solid #B8893E; padding-left: 10px; margin: 0 0 4mm; }
h2 { font-size: 13pt; color: #fff; background: #1A2942; padding: 2mm 3.5mm; margin: 6mm 0 3mm; break-after: avoid; }
h2 + p strong:first-child { color: #8a6a2c; }
blockquote { margin: 0 0 4mm; padding: 2.5mm 4mm; background: #f7f1e3; border-left: 4px solid #B8893E; color: #555; font-size: 9pt; }
blockquote p { margin: 0; }
table { width: 100%; border-collapse: collapse; margin: 2mm 0 3mm; font-size: 9.2pt; break-inside: avoid; }
th { background: #B8893E; color: #fff; padding: 4px 6px; text-align: left; font-weight: 400; }
td { padding: 4px 6px; border-bottom: 1px solid #e5e7eb; }
tr:nth-child(even) td { background: #f6f7f9; }
td[style*="right"], th[style*="right"] { text-align: right; white-space: nowrap; }
p { margin: 1.5mm 0; }
ul, ol { margin: 1mm 0 2mm; padding-left: 6mm; }
li { margin-bottom: 1mm; }
strong { color: #1A2942; }
hr { border: none; border-top: 1px dashed #ccc; margin: 4mm 0; }
code { font-family: inherit; background: #f3f4f6; padding: 0 3px; }
'''
html = f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>{SRC.stem}</title><style>{CSS}</style></head><body>{body}</body></html>'
out_html = SRC.with_suffix('.html')
out_html.write_text(html, encoding='utf-8')

from playwright.sync_api import sync_playwright
exe = sorted(glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome'))
foot = (f'<div style="width:100%;font-family:WenQuanYi Zen Hei;font-size:7px;color:#666;padding:0 16mm;display:flex;justify-content:space-between">'
        f'<span>{DISC}<br><b style="color:#1A2942">{CONTACT}</b></span><span>第 <span class="pageNumber"></span> / <span class="totalPages"></span> 頁</span></div>')
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exe[-1] if exe else None)
    pg = b.new_page()
    pg.goto(out_html.as_uri())
    pg.wait_for_timeout(300)
    pg.pdf(path=str(SRC.with_suffix('.pdf')), prefer_css_page_size=True, print_background=True,
           display_header_footer=True, header_template='<div></div>', footer_template=foot)
    b.close()
out_html.unlink()
print('PDF →', SRC.with_suffix('.pdf'))
