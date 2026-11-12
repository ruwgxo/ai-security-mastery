"""Render one chapter (its index and every section, as they stand in a book folder) into a single
review PDF, then prove the PDF holds exactly the YAML's content: nothing added, nothing dropped.

Every scalar in every file is printed once. Keys become small labels or headings; those labels,
list bullets and numbers are the only text the renderer adds, and it records each one. After
building, the PDF's extracted text (pdftotext) is compared with what was recorded, character by
character (whitespace ignored), so a truncated cell, a lost line of code or an extra word fails.

Usage: chapter_pdf.py BOOK_DIR CHAPTER_NUMBER OUT.pdf
Prints a JSON report and exits 1 if the check fails."""
import sys, os, re, glob, json, subprocess, collections
import yaml
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak, Preformatted,
                                Table, TableStyle, ListFlowable, ListItem)
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

D = '/usr/share/fonts/truetype/dejavu/'
for name, f in [('Serif', 'DejaVuSerif.ttf'), ('Serif-B', 'DejaVuSerif-Bold.ttf'), ('Sans', 'DejaVuSans.ttf'),
                ('Sans-B', 'DejaVuSans-Bold.ttf'), ('Mono', 'DejaVuSansMono.ttf')]:
    pdfmetrics.registerFont(TTFont(name, D + f))

INK, GREY = '#1d1d1f', '#6e6e73'
S = {
    'body': ParagraphStyle('body', fontName='Serif', fontSize=9.5, leading=13.5, spaceAfter=6, textColor=INK),
    'lead': ParagraphStyle('lead', fontName='Serif', fontSize=10.5, leading=15, spaceAfter=8, textColor='#3a3a3c'),
    'h0': ParagraphStyle('h0', fontName='Sans-B', fontSize=17, leading=22, spaceAfter=10, textColor=INK),
    'h1': ParagraphStyle('h1', fontName='Sans-B', fontSize=13, leading=17, spaceBefore=10, spaceAfter=5, textColor=INK),
    'h2': ParagraphStyle('h2', fontName='Sans-B', fontSize=11, leading=15, spaceBefore=8, spaceAfter=4, textColor=INK),
    'h3': ParagraphStyle('h3', fontName='Sans-B', fontSize=9.5, leading=13, spaceBefore=6, spaceAfter=3, textColor='#3a3a3c'),
    'kv': ParagraphStyle('kv', fontName='Sans', fontSize=8.5, leading=11.5, spaceAfter=2, textColor=GREY),
    'cell': ParagraphStyle('cell', fontName='Serif', fontSize=8, leading=10.5, textColor=INK),
    'head': ParagraphStyle('headcell', fontName='Sans-B', fontSize=8, leading=10.5, textColor=INK),
    'code': ParagraphStyle('code', fontName='Mono', fontSize=7, leading=9, textColor=INK, backColor='#f5f5f7',
                           borderPadding=4, spaceBefore=4, spaceAfter=8),
    'call': ParagraphStyle('call', fontName='Serif', fontSize=9.5, leading=13.5, spaceAfter=6, textColor=INK,
                           backColor='#eef3fb', borderPadding=5, leftIndent=4),
}
CODE_COLS = 118
WIDTH = A4[0] - 30 * mm


class Doc:
    def __init__(self):
        self.story, self.added, self.values = [], [], []

    def para(self, text, style, added=''):
        """added: renderer text in front of the value (a label); recorded separately."""
        if added: self.added.append(added)
        self.values.append(text)
        body = (f'<b>{escape(added)}</b> ' if added else '') + escape(text).replace('\n', '<br/>')
        self.story.append(Paragraph(body, S[style]))

    def label(self, text, style):
        self.added.append(text)
        self.story.append(Paragraph(escape(text), S[style]))


def nice(key):
    return str(key).replace('_', ' ').strip().capitalize()


def scalar(v):
    if v is None: return ''
    if isinstance(v, bool): return 'true' if v else 'false'
    return str(v)


def short(v):
    return not isinstance(v, (dict, list)) and '\n' not in scalar(v).strip() and len(scalar(v)) <= 110


def table(doc, b):
    cols, rows = b.get('columns') or [], b.get('rows') or []
    data = []
    if cols:
        data.append([Paragraph(escape(scalar(c)), S['head']) for c in cols]); doc.values += [scalar(c) for c in cols]
    for r in rows:
        cells = r if isinstance(r, list) else list(r.values()) if isinstance(r, dict) else [r]
        if isinstance(r, dict): doc.added += [str(k) + ':' for k in r]  # mapping rows keep their keys visible
        row = []
        for k, c in zip(r if isinstance(r, dict) else [None] * len(cells), cells):
            txt = scalar(c); doc.values.append(txt)
            row.append(Paragraph((f'<b>{escape(str(k))}:</b> ' if k is not None else '') + escape(txt).replace('\n', '<br/>'), S['cell']))
        data.append(row)
    if not data: return
    n = max(len(r) for r in data)
    data = [r + [''] * (n - len(r)) for r in data]
    t = Table(data, colWidths=[WIDTH / n] * n, repeatRows=1 if cols else 0)
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#c7c7cc')),
                           ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                           ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f2f2f7') if cols else colors.white)]))
    doc.story += [t, Spacer(1, 6)]
    rest = {k: v for k, v in b.items() if k not in ('type', 'columns', 'rows')}
    walk(doc, rest, 3)


def bullets(doc, items, ordered, depth):
    flow, n = [], 0
    for it in items:
        if isinstance(it, (dict, list)):
            sub = Doc(); walk(sub, it, depth + 1)
            doc.added += sub.added; doc.values += sub.values
            flow.append(ListItem(sub.story or [Spacer(1, 1)], value=None)); continue
        n += 1
        txt = scalar(it); doc.values.append(txt)
        flow.append(ListItem(Paragraph(escape(txt).replace('\n', '<br/>'), S['body'])))
        doc.added.append(f'{n}.' if ordered else '•')
    doc.story.append(ListFlowable(flow, bulletType='1' if ordered else 'bullet', start='1' if ordered else '•',
                                  bulletFormat='%s.' if ordered else None,
                                  bulletFontName='Sans', bulletFontSize=8, leftIndent=12))


def code(doc, text, lang):
    if lang:
        doc.values.append(lang); doc.added.append('[]')
        doc.story.append(Paragraph(escape(f'[{lang}]'), S['kv']))
    txt = scalar(text).rstrip('\n'); doc.values.append(txt)
    doc.story.append(Preformatted(txt, S['code'], maxLineLength=CODE_COLS, newLineChars=''))


def block(doc, b, depth):
    ty = b.get('type')
    rest = {k: v for k, v in b.items() if k != 'type'}
    if ty in ('prose', 'lead') and set(rest) <= {'text'}:
        doc.para(scalar(rest.get('text', '')).strip(), 'lead' if ty == 'lead' else 'body'); return
    if ty == 'code' and set(rest) <= {'text', 'lang'}:
        code(doc, rest.get('text', ''), rest.get('lang', '')); return
    if ty == 'list' and set(rest) <= {'items', 'style'}:
        bullets(doc, rest.get('items') or [], rest.get('style') == 'ordered', depth); return
    if ty == 'table':
        table(doc, b); return
    if ty == 'callout' and set(rest) <= {'variant', 'title', 'text'}:
        head = scalar(rest.get('variant', 'note')).capitalize() + (' - ' + scalar(rest['title']) if rest.get('title') else '')
        doc.added.append(head.split(' - ')[0] + ':'); doc.values.append(scalar(rest.get('title', '')))
        doc.values.append(scalar(rest.get('text', '')).strip())
        body = f'<b>{escape(head)}:</b> ' + escape(scalar(rest.get("text", "")).strip()).replace('\n', '<br/>')
        doc.story.append(Paragraph(body, S['call'])); return
    doc.label(f'[{ty}]', 'kv')  # any other block shape: show its type, then every field
    walk(doc, rest, depth + 1)


def walk(doc, v, depth):
    if isinstance(v, dict):
        if 'type' in v and isinstance(v.get('type'), str):
            block(doc, v, depth); return
        if 'heading' in v:  # a part: its heading is content, printed as a heading
            h = scalar(v['heading']); doc.values.append(h)
            doc.story.append(Paragraph(escape(h), S['h%d' % min(depth, 3)]))
            v = {k: x for k, x in v.items() if k != 'heading'}
        for k, x in v.items():
            if k in ('blocks',) and isinstance(x, list):
                walk(doc, x, depth); continue
            if isinstance(x, (list, dict)) and not x:
                continue  # an empty slot (16.07's deliverables) has no content, so no heading either
            if short(x):
                doc.para(scalar(x), 'kv', nice(k) + ':')
            else:
                doc.label(nice(k), 'h%d' % min(depth, 3))
                walk(doc, x, depth + 1)
    elif isinstance(v, list):
        if v and all(not isinstance(i, (dict, list)) and re.fullmatch(r'\S{1,40}', scalar(i)) for i in v):
            doc.values += [scalar(i) for i in v]; doc.added += ['·'] * (len(v) - 1)  # tags and similar: one line
            doc.story.append(Paragraph(escape(' · '.join(scalar(i) for i in v)), S['kv']))
        elif all(not isinstance(i, (dict, list)) for i in v):
            bullets(doc, v, False, depth)
        else:
            for i in v: walk(doc, i, depth)
    else:
        txt = scalar(v)
        if '\n' in txt.strip() and re.search(r'^\s{2,}\S', txt, re.M): code(doc, txt, '')
        else: doc.para(txt.strip(), 'body')


def collect(v, out):
    if isinstance(v, dict):
        for k, x in v.items():
            # a block's type, and a list block's style, pick its layout; they are not text
            if k == 'type' and isinstance(x, str): continue
            if k == 'style' and v.get('type') == 'list': continue
            collect(x, out)
    elif isinstance(v, list):
        for x in v: collect(x, out)
    else: out.append(scalar(v))


def chapter_files(book, ch):
    idx = os.path.join(book, f'chapter_{ch:02d}_index.yaml')
    secs = sorted(glob.glob(os.path.join(book, f'section_{ch:02d}_*.yaml')))
    return ([idx] if os.path.exists(idx) else []) + secs


def main(book, ch, out):
    ch = int(ch); doc = Doc(); leaves = []
    files = chapter_files(book, ch)
    for i, f in enumerate(files):
        d = yaml.safe_load(open(f, encoding='utf-8'))
        collect(d, leaves)
        if i: doc.story.append(PageBreak())
        doc.label(os.path.basename(f), 'kv')
        title = scalar(d.pop('title', '')) if isinstance(d, dict) else ''
        if title: doc.values.append(title); doc.story.append(Paragraph(escape(title), S['h0']))
        walk(doc, d, 1)
    SimpleDocTemplate(out, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                      bottomMargin=14 * mm, title=f'Chapter {ch} - review copy').build(doc.story)

    nows = lambda s: collections.Counter(re.sub(r'\s+', '', s))
    # -raw keeps a hyphen that ends a line (the default mode joins and drops it)
    got = nows(subprocess.run(['pdftotext', '-raw', '-enc', 'UTF-8', out, '-'], capture_output=True, text=True).stdout)
    want = nows(''.join(doc.values) + ''.join(doc.added))
    missing, extra = want - got, got - want
    yaml_chars = sum(nows(''.join(leaves)).values())
    unprinted = nows(''.join(leaves)) - nows(''.join(doc.values))
    unyaml = nows(''.join(doc.values)) - nows(''.join(leaves))
    report = {'files': len(files), 'pdf': out, 'yaml_chars': yaml_chars,
              'renderer_label_chars': sum(nows(''.join(doc.added)).values()),
              'yaml_values_not_rendered': sum(unprinted.values()), 'rendered_values_not_in_yaml': sum(unyaml.values()),
              'missing_chars': sum(missing.values()), 'extra_chars': sum(extra.values()),
              'missing_sample': dict(missing.most_common(8)), 'extra_sample': dict(extra.most_common(8))}
    report['PASS'] = not (report['missing_chars'] or report['extra_chars'] or unprinted or unyaml)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report['PASS'] else 1


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
