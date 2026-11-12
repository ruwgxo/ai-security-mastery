"""Book index YAML -> reader-facing PDF (no metadata), tuned for text-to-speech."""
import sys, re, yaml
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, ListFlowable, ListItem, KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

D = '/usr/share/fonts/truetype/dejavu/'
for name, f in [('Serif', 'DejaVuSerif.ttf'), ('Serif-B', 'DejaVuSerif-Bold.ttf'), ('Serif-I', '../liberation/LiberationSerif-Italic.ttf'),
                ('Serif-BI', '../liberation/LiberationSerif-BoldItalic.ttf'), ('Sans-B', 'DejaVuSans-Bold.ttf'), ('Sans', 'DejaVuSans.ttf')]:
    pdfmetrics.registerFont(TTFont(name, D + f))
addMapping('Serif', 0, 0, 'Serif'); addMapping('Serif', 1, 0, 'Serif-B'); addMapping('Serif', 0, 1, 'Serif-I'); addMapping('Serif', 1, 1, 'Serif-BI')

INK = '#1d1d1f'
body = ParagraphStyle('body', fontName='Serif', fontSize=10.5, leading=15.5, alignment=0, spaceAfter=8, textColor=INK)
item = ParagraphStyle('item', parent=body, alignment=0, spaceAfter=3)
h1 = ParagraphStyle('h1', fontName='Sans-B', fontSize=19, leading=24, spaceBefore=0, spaceAfter=14, textColor=INK)
h2 = ParagraphStyle('h2', fontName='Sans-B', fontSize=13.5, leading=18, spaceBefore=14, spaceAfter=7, textColor=INK)
h3 = ParagraphStyle('h3', fontName='Sans-B', fontSize=11, leading=15, spaceBefore=10, spaceAfter=4, textColor='#3a3a3c')
kicker = ParagraphStyle('kicker', fontName='Sans', fontSize=9.5, leading=13, spaceAfter=4, textColor='#6e6e73')
t_title = ParagraphStyle('tt', fontName='Sans-B', fontSize=24, leading=30, alignment=TA_CENTER, textColor=INK)
t_sub = ParagraphStyle('ts', fontName='Serif-I', fontSize=13, leading=18, alignment=TA_CENTER, textColor='#3a3a3c')
t_auth = ParagraphStyle('ta', fontName='Serif', fontSize=12, leading=16, alignment=TA_CENTER, textColor=INK)

STOP = {'a','an','the','and','or','of','in','on','at','to','for','vs','via'}
def label(k):
    w = str(k).replace('_', ' ').split()
    return ' '.join(x.capitalize() if i == 0 or x not in STOP else x for i, x in enumerate(w))

def P(t, s=body): return Paragraph(escape(str(t).strip()), s)
def paras(t):
    return [P(' '.join(p.split())) for p in re.split(r'\n\s*\n', str(t).strip()) if p.strip()]
def bullets(items):
    return ListFlowable([ListItem(P(i, item), leftIndent=14, value='•') for i in items], bulletType='bullet',
                        start='•', leftIndent=14, bulletFontName='Serif', bulletFontSize=9)
def fieldline(lbl, val):
    return Paragraph(f"<b>{escape(lbl)}.</b> " + escape(str(val).strip()), body)

def generic(d, lvl, out):
    """Render a nested dict/list of reader content."""
    for k, v in d.items():
        if isinstance(v, str) and '\n' not in v.strip() and lvl >= 3:
            out.append(fieldline(label(k), v))
        elif isinstance(v, str):
            out.append(Paragraph(escape(label(k)), h2 if lvl == 2 else h3)); out += paras(v)
        elif isinstance(v, list):
            out.append(Paragraph(escape(label(k)), h2 if lvl == 2 else h3)); out.append(bullets(v))
        elif isinstance(v, dict):
            out.append(Paragraph(escape(label(k)), h2 if lvl == 2 else h3)); generic(v, lvl + 1, out)

def build(src, dst):
    doc = [x for x in yaml.safe_load_all(open(src)) if x][0]
    di, bm = doc['document_info'], doc['book_metadata']
    s = []
    # title page
    s += [Spacer(1, 55 * mm), P(di['title'].split(':')[0], t_title), Spacer(1, 4 * mm),
          P(di['title'].split(':', 1)[1].strip(), t_sub), Spacer(1, 3 * mm), P(di['subtitle'], t_sub),
          Spacer(1, 18 * mm), P(di['author'], t_auth), Spacer(1, 6 * mm), P(bm['tagline'], t_sub), PageBreak()]
    # who this book is for
    s.append(P('Who This Book Is For', h1))
    for grp, label_ in (('primary', 'Primary Readers'), ('secondary', 'Also Useful For')):
        s += [P(label_, h3), bullets(bm['target_audience'][grp])]
    s.append(P('Prerequisites', h2))
    for grp in ('required', 'recommended', 'not_required'):
        s += [P(label(grp).replace('Not Required', 'Not Required'), h3), bullets(bm['prerequisites'][grp])]
    s.append(PageBreak())
    # overview
    bo = doc['book_overview']
    s.append(P('About This Book', h1))
    s += [P('What This Book Covers', h2)] + paras(bo['what_this_book_covers'])
    s += [P('Why This Book Exists', h2)] + paras(bo['why_this_book_exists'])
    s.append(P('What Makes This Different', h2))
    for k, v in bo['what_makes_this_different'].items():
        blk = [P(label(k), h3)]
        for f, x in v.items():
            blk.append(fieldline(label(f), x) if isinstance(x, str) else Paragraph(f'<b>{escape(label(f))}.</b>', body))
            if isinstance(x, list): blk.append(bullets(x))
        s.append(KeepTogether(blk))
    s.append(P('Learning Philosophy', h2))
    for k, v in bo['learning_philosophy'].items():
        s.append(KeepTogether([P(label(k), h3), fieldline('Principle', v['principle']), fieldline('Example', v['example'])]))
    # structure
    for pk, part in doc['book_structure'].items():
        s += [PageBreak(), P(f'Part {part["number"]}', kicker), P(part['title'], h1), P(part['duration'], kicker)]
        s += paras(part['overview'])
        for ck, ch in part['chapters'].items():
            s.append(P(f'Chapter {int(ch["number"])}: {ch["title"]}', h2))
            for k, v in ch.items():
                if k in ('number', 'title', 'sections', 'pages'): continue     # numbering and counts are metadata
                s += [P(label(k), h3), bullets(v)]
    # learning path
    lp = doc['learning_path']
    s += [PageBreak(), P('The 12-Week Learning Path', h1)]
    for wk, w in lp['week_by_week'].items():
        blk = [P(f'Week {int(wk.split("_")[1])}: {w["title"]}', h2),
               fieldline('Chapters', '; '.join(w['chapters'])), fieldline('Time commitment', w['time_commitment']),
               Paragraph('<b>Deliverables.</b>', body), bullets(w['deliverables'])]
        s.append(KeepTogether(blk))
    s.append(P('Milestones', h1 if False else h2))
    for mk, m in lp['milestones'].items():
        s.append(KeepTogether([P(f'Milestone {int(mk.split("_")[1])}, Week {m["week"]}: {m["title"]}', h3), bullets(m['criteria'])]))
    # success metrics, usage, resources
    s += [PageBreak(), P('Success Metrics', h1)]; generic(doc['success_metrics'], 2, s)
    s += [PageBreak(), P('How to Use This Book', h1)]; generic(doc['how_to_use_this_book'], 2, s)
    s += [PageBreak(), P('Additional Resources', h1)]; generic(doc['additional_resources'], 2, s)
    pdf = SimpleDocTemplate(dst, pagesize=A5, leftMargin=17 * mm, rightMargin=17 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=di['title'], author=di['author'], subject=di['subtitle'], creator='')
    pdf.build(s)

if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
