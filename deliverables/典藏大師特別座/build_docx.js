// 典藏大師特別座 銷售報告書 Word 版排版：讀 _docx_assets/docx_model.json（build_docx_model.py 產出）→ 典藏大師特別座_銷售報告書.docx
// 文字、表格為 Word 原生可編輯；社區成交圖、樓層配置圖為 PNG。
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, AlignmentType, PageBreak, Footer, LevelFormat, PageNumber, TabStopType, VerticalAlign,
} = require('docx');

const HERE = __dirname;
const M = JSON.parse(fs.readFileSync(path.join(HERE, '_docx_assets', 'docx_model.json'), 'utf8'));
const OUT = path.join(HERE, '典藏大師特別座_銷售報告書.docx');

const FONT = 'Microsoft JhengHei';
const C = { navy: '163A47', teal: '1F4E5F', gold: 'C8963E', mute: '5D6B76', text: '1E2A33', hl: 'FBEEE0', alt: 'EEF3F6',
  note: 'FBF3E2', warn: 'FBECEB', red: 'C0392B', line: 'DDE4E9' };
const PAGE_W = 11906, MARGIN = 907, CW = PAGE_W - 2 * MARGIN;   // A4，左右邊界 1.6 cm
const cm2px = (cm) => Math.round(cm / 2.54 * 96);

const run = (text, o = {}) => new TextRun({ text, font: FONT, size: o.size || 20, bold: o.bold, color: o.color || C.text,
  characterSpacing: o.spacing });
const NONE = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
const NOBORDER = { top: NONE, bottom: NONE, left: NONE, right: NONE, insideHorizontal: NONE, insideVertical: NONE };

function imgRun(p, widthCm, px) {
  const ext = path.extname(p).toLowerCase().replace('.', '');
  const w = cm2px(widthCm), h = Math.round(w * px[1] / px[0]);
  return new ImageRun({ type: ext === 'jpeg' ? 'jpg' : ext, data: fs.readFileSync(p), transformation: { width: w, height: h } });
}
const caption = (t) => new Paragraph({ spacing: { before: 40, after: 120 }, children: [run(t, { size: 15, color: C.mute })] });
const boxPara = (t, fill, edge, o = {}) => new Paragraph({
  shading: { type: ShadingType.CLEAR, fill, color: 'auto' },
  border: { left: { style: BorderStyle.SINGLE, size: 24, color: edge, space: 8 } },
  spacing: { before: o.first ? 120 : 0, after: o.last ? 160 : 0, line: 300 }, indent: { left: 160, right: 120 },
  children: [run(t, { size: 18, bold: o.bold })] });

function cell(children, wDxa, o = {}) {
  return new TableCell({ width: { size: wDxa, type: WidthType.DXA }, children, verticalAlign: o.vAlign || VerticalAlign.CENTER,
    shading: o.fill ? { type: ShadingType.CLEAR, fill: o.fill, color: 'auto' } : undefined,
    margins: { top: o.pad ?? 50, bottom: o.pad ?? 50, left: 80, right: 80 }, borders: o.borders });
}

function dataTable(b) {
  const tot = b.widths.reduce((a, c) => a + c, 0);
  const W = b.widths.map((w) => Math.floor(CW * w / tot));
  W[W.length - 1] += CW - W.reduce((a, c) => a + c, 0);
  const fs_ = b.small ? 14 : 17;
  const lineB = { style: BorderStyle.SINGLE, size: 4, color: C.line };
  const borders = { top: NONE, left: NONE, right: NONE, bottom: lineB };
  const head = new TableRow({ tableHeader: true, children: b.headers.map((h, i) => cell(
    [new Paragraph({ children: [run(h, { size: fs_, color: 'FFFFFF', bold: true })] })], W[i], { fill: C.teal, borders })) });
  const rows = b.rows.map((r, ri) => {
    const hl = (b.hl || []).includes(ri);
    const fill = hl ? C.hl : (ri % 2 ? C.alt : 'FFFFFF');
    return new TableRow({ cantSplit: true, children: r.map((v, i) => cell([new Paragraph({
      alignment: (b.num || []).includes(i) ? AlignmentType.RIGHT : AlignmentType.LEFT,
      children: [run(String(v), { size: fs_, bold: hl })] })], W[i], { fill, borders })) });
  });
  return new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: W, rows: [head, ...rows],
    borders: { top: NONE, bottom: NONE, left: NONE, right: NONE, insideHorizontal: lineB, insideVertical: NONE } });
}

function kpiTable(items) {
  const n = items.length, gap = 120;
  const w = Math.floor((CW - gap * (n - 1)) / n);
  const cells = [], W = [];
  items.forEach(([v, u, l], i) => {
    if (i) { cells.push(cell([new Paragraph('')], gap, { borders: NOBORDER })); W.push(gap); }
    cells.push(cell([
      new Paragraph({ alignment: AlignmentType.CENTER, children: [run(v, { size: 32, bold: true, color: C.navy })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, children: [run(u, { size: 15, color: C.gold })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40 }, children: [run(l, { size: 14, color: C.mute })] }),
    ], w, { fill: 'FFFFFF', pad: 110, borders: { top: { style: BorderStyle.SINGLE, size: 18, color: C.gold },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: C.line }, left: { style: BorderStyle.SINGLE, size: 4, color: C.line },
      right: { style: BorderStyle.SINGLE, size: 4, color: C.line } } }));
    W.push(w);
  });
  W[W.length - 1] += CW - W.reduce((a, c) => a + c, 0);
  return new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: W, rows: [new TableRow({ cantSplit: true, children: cells })], borders: NOBORDER });
}

function specTable(rows) {
  const W = [1700, CW - 1700];
  const b = { top: NONE, left: NONE, right: NONE, bottom: { style: BorderStyle.SINGLE, size: 4, color: C.line } };
  return new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: W, borders: NOBORDER,
    rows: rows.map(([k, v]) => new TableRow({ cantSplit: true, children: [
      cell([new Paragraph({ children: [run(k, { size: 18, color: '8A6A2C' })] })], W[0], { borders: b }),
      cell([new Paragraph({ children: [run(v, { size: 18 })] })], W[1], { borders: b })] })) });
}

function images2(b) {   // 一列 n 張（2 或 3），欄寬均分
  const n = b.items.length, cw = Math.floor(CW / n);
  const W = b.items.map((_, i) => (i === n - 1 ? CW - cw * (n - 1) : cw));
  return new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: W, borders: NOBORDER,
    rows: [new TableRow({ cantSplit: true, children: b.items.map(([p, cap], i) => cell([
      new Paragraph({ alignment: AlignmentType.CENTER, children: [imgRun(p, b.w || 8.6, b.px[i])] }), caption(cap)], W[i], { borders: NOBORDER, vAlign: VerticalAlign.TOP })) })] });
}

function contact(b) {
  const W = [CW - 2 * 1700, 1700, 1700];
  const qr = (p, t) => cell([new Paragraph({ alignment: AlignmentType.CENTER, children: [imgRun(p, 2.2, [1, 1])] }),
    new Paragraph({ alignment: AlignmentType.CENTER, children: [run(t, { size: 14, color: 'FFFFFF', bold: true })] })], 1700, { fill: C.navy, borders: NOBORDER });
  return new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: W, borders: NOBORDER, rows: [new TableRow({ children: [
    cell([
      new Paragraph({ children: [run(b.title || '預約帶看・行情諮詢', { size: 15, color: 'E3B66A', spacing: 40 })] }),
      new Paragraph({ spacing: { before: 60 }, children: [run('助哥　', { size: 32, bold: true, color: 'FFFFFF' }), run('0925-313-570', { size: 32, bold: true, color: 'F0D9A4' })] }),
      new Paragraph({ spacing: { before: 60 }, children: [run('永慶不動產 七期河南市政店', { size: 16, color: 'B9CAD3' })] }),
      new Paragraph({ children: [run('LINE @080akczk　｜　sixhands.tw', { size: 16, color: 'B9CAD3' })] }),
    ], W[0], { fill: C.navy, pad: 160, borders: NOBORDER }),
    qr(b.qr[0], '加 LINE'), qr(b.qr[1], '看網站')] })] });
}

const out = [];
let first = true;
for (const b of M.blocks) {
  switch (b.type) {
    case 'pagebreak': out.push(new Paragraph({ children: [new PageBreak()] })); break;
    case 'spacer': out.push(new Paragraph({ spacing: { before: 240 }, keepNext: true, children: [] })); break;
    case 'eyebrow': out.push(new Paragraph({ spacing: { before: first ? 200 : 0, after: 60 }, keepNext: true, children: [run(b.text, { size: 15, color: C.gold, spacing: 60 })] })); break;
    case 'h1': out.push(new Paragraph({ spacing: { after: 160 }, keepNext: true, border: { left: { style: BorderStyle.SINGLE, size: 36, color: C.gold, space: 8 } },
      children: [run(b.text, { size: 36, bold: true, color: C.navy })] })); break;
    case 'h2': out.push(new Paragraph({ spacing: { before: 200, after: 80 }, keepNext: true, children: [run(b.text, { size: 22, bold: true, color: C.navy })] })); break;
    case 'title': out.push(new Paragraph({ spacing: { before: 60 }, children: [run(b.text, { size: 72, bold: true, color: C.navy })] })); break;
    case 'subtitle': out.push(new Paragraph({ spacing: { after: 100 }, children: [run(b.text, { size: 28, color: C.navy })] })); break;
    case 'p': out.push(new Paragraph({ spacing: { after: 100, line: 300 }, children: [run(b.text, {
      size: b.small ? 15 : 19, color: b.gold ? C.gold : (b.muted || b.small ? C.mute : C.text) })] })); break;
    case 'note': case 'warn': {
      const lines = b.lines || [b.text];
      const [fill, edge] = b.type === 'note' ? [C.note, C.gold] : [C.warn, C.red];
      lines.forEach((t, i) => out.push(boxPara(t, fill, edge, { first: i === 0, last: i === lines.length - 1, bold: b.lines && i === 0 })));
      break;
    }
    case 'bullets': b.items.forEach((t) => out.push(new Paragraph({ numbering: { reference: 'bul', level: 0 }, spacing: { after: 60, line: 300 }, children: [run(t, { size: 19 })] }))); break;
    case 'kpi': out.push(kpiTable(b.items), new Paragraph({ spacing: { after: 80 }, children: [] })); break;
    case 'spec': out.push(specTable(b.rows)); break;
    case 'table': out.push(dataTable(b)); break;
    case 'image': out.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80 }, keepNext: !!b.caption, children: [imgRun(b.path, b.width, b.px)] }));
      if (b.caption) out.push(caption(b.caption)); break;
    case 'images2': {
      // b.lead＝前面幾個段落（章名、說明）要跟第一列照片綁在同一頁：包進外框表格的同一列，避免標題孤懸在頁尾
      if (!b.lead) { out.push(images2(b)); break; }
      const head = out.splice(out.length - b.lead, b.lead);
      out.push(new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: [CW], borders: NOBORDER,
        rows: [new TableRow({ cantSplit: true, children: [cell([...head, images2(b), new Paragraph({ children: [] })], CW, { borders: NOBORDER, pad: 0 })] })] }));
      break;
    }
    case 'feats': b.items.forEach(([t, d], i) => {
      out.push(new Paragraph({ spacing: { before: 120 }, keepNext: true, children: [run(String(i + 1).padStart(2, '0') + '　', { size: 28, bold: true, color: C.gold }), run(t, { size: 22, bold: true, color: C.navy })] }));
      out.push(new Paragraph({ spacing: { after: 60, line: 300 }, indent: { left: 640 }, children: [run(d, { size: 19 })] }));
    }); break;
    case 'contact': out.push(new Paragraph({ spacing: { after: 120 }, children: [] }), contact(b)); break;
    default: throw new Error('unknown block ' + b.type);
  }
  first = false;
}

const footer = new Footer({ children: [
  new Paragraph({ border: { top: { style: BorderStyle.SINGLE, size: 6, color: C.gold, space: 4 } },
    tabStops: [{ type: TabStopType.RIGHT, position: CW }],
    children: [run(M.footer_disc, { size: 13, color: C.mute }), run('\t典藏大師特別座 銷售報告書　', { size: 13, color: C.mute }),
      new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 13, color: C.mute })] }),
  new Paragraph({ children: [run(M.footer_contact, { size: 14, bold: true, color: C.navy })] }),
] });

const doc = new Document({
  creator: 'Sixhands Studio', title: '典藏大師特別座 銷售報告書',
  styles: { default: { document: { run: { font: FONT, size: 19 } } } },
  numbering: { config: [{ reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 360, hanging: 260 } } } }] }] },
  sections: [{ properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: 620, bottom: 900, left: MARGIN, right: MARGIN, footer: 300 } } },
    footers: { default: footer }, children: out }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log('DOCX →', OUT); });
