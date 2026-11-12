"""Render a profile-layout section to Markdown, following the standard's markdown target.
Usage: render_md.py SECTION.yaml > OUT.md"""
import sys, yaml

def esc_cell(c): return str(c).replace('|', '\\|').replace('\n', ' ')
def t(x): return str(x).strip()

def blocks(bs, lvl, out):
    for b in bs or []:
        ty = b.get('type')
        if ty == 'prose': out += [t(b['text']), '']
        elif ty == 'lead': out += [f'*{t(b["text"])}*', '']
        elif ty == 'list': lst(b['items'], b.get('style') == 'ordered', out); out.append('')
        elif ty == 'code': out += [f'```{b.get("lang", "")}', str(b['text']).rstrip('\n'), '```', '']
        elif ty == 'callout':
            kind = {'security': 'CAUTION', 'note': 'NOTE', 'tip': 'TIP', 'warning': 'WARNING', 'danger': 'CAUTION'}.get(b['variant'], 'NOTE')
            out.append(f'> [!{kind}]')
            out.append(f'> **{b["variant"].capitalize()}' + (f' — {b["title"]}**' if b.get('title') else '**'))
            out += ['>', '> ' + t(b['text']), '']
        elif ty == 'fields': fields(b, lvl, out)
        elif ty == 'table': table(b['columns'], b['rows'], out)
        else: out += [t(b.get('text', b)), '']   # unknown blocks degrade to their text

def lst(items, ordered, out, depth=0):
    n = 0
    for it in items:
        if isinstance(it, list): lst(it, ordered, out, depth + 1); continue
        n += 1
        out.append('  ' * depth + (f'{n}. ' if ordered else '- ') + t(it))

def fields(b, lvl, out):
    out += [f'**{t(b["subject"])}**', '']
    for e in b['entries']:
        v = e['value']
        if isinstance(v, list): out.append(f'- *{e["label"]}:*'); [out.append(f'  - {t(x)}') for x in v]
        else: out.append(f'- *{e["label"]}:* {t(v)}')
    out.append('')

def table(cols, rows, out):
    out.append('| ' + ' | '.join(esc_cell(c) for c in cols) + ' |')
    out.append('|' + '---|' * len(cols))
    for r in rows: out.append('| ' + ' | '.join(esc_cell(c) for c in r) + ' |')
    out.append('')

def part(p, lvl, out):
    h = (f'{p["number"]} ' if p.get('number') else '') + t(p['heading'])
    out += ['#' * lvl + ' ' + h, '']
    blocks(p.get('blocks'), lvl, out)
    for sp in p.get('parts') or []: part(sp, min(lvl + 1, 4), out)

def groups(g, out, lvl=3, ordered=False):
    for k, v in g.items():
        out += ['#' * lvl + ' ' + label(k), '']
        if isinstance(v, dict) and 'items' in v: lst(v['items'], v.get('style') == 'ordered', out)
        elif isinstance(v, list): lst(v, ordered, out)
        else: out.append(t(v))
        out.append('')

STOP = {'a','an','the','and','or','of','in','on','at','to','for','vs','via'}
def label(k):
    w = str(k).replace('_', ' ').split()
    return ' '.join(x.capitalize() if i == 0 or x not in STOP else x for i, x in enumerate(w))

def render(d):
    out = []; si = d.get('section_info', {})
    out += [f'# {t(d["title"])}', '']
    badge = [f'Chapter {si.get("chapter")} · Section {si.get("section")}']
    if si.get('estimated_pages'): badge.append(f'~{si["estimated_pages"]} pages')
    if si.get('estimated_reading_time'): badge.append(str(si['estimated_reading_time']))
    badge.append(f'updated {d["updated"]}')
    out += ['<sub>' + ' · '.join(badge) + '</sub>', '']
    if d.get('lead'): out += [f'*{t(d["lead"])}*', '']
    for p in d.get('overview') or []: part(p, 2, out)
    lo = d.get('learning_objectives')
    if lo:
        out += ['## Learning Objectives', '']
        if lo.get('intro'): out += [t(lo['intro']), '']
        groups(lo.get('groups', {}), out)
    pr = d.get('prerequisites')
    if pr:
        out += ['## Prerequisites', '']
        if isinstance(pr, list): lst(pr, False, out); out.append('')
        else: groups(pr['groups'], out)
    for p in d.get('prose_content') or []: part(p, 2, out)
    if d.get('reference_materials'):
        out += ['## Reference Tables', '']
        for tb in d['reference_materials']:
            out += [f'### {t(tb["heading"])}', '']
            if tb.get('description'): out += [t(tb['description']), '']
            table(tb['table']['columns'], tb['table']['rows'], out)
    if d.get('deliverables'):
        out += ['## Deliverables', '']
        for dl in d['deliverables']:
            out += [f'### {t(dl["heading"])}', '']
            if dl.get('description'): out += [t(dl['description']), '']
            if dl.get('notes'): out += [f'*Implementation notes:* {t(dl["notes"])}', '']
            if dl.get('dependencies'): out.append('*Dependencies:*'); lst(dl['dependencies'], False, out); out.append('')
            out += [f'`{dl.get("filename", "")}`', '', f'```{dl.get("lang") or ""}', str(dl['code']).rstrip('\n'), '```', '']
    if d.get('artifacts'):
        out += ['## Artifacts', '']
        for f in d['artifacts']: fields(f, 3, out)
    if d.get('common_mistakes'):
        out += ['## Common Mistakes', '']
        for m in d['common_mistakes']: fields(m, 3, out)
    ss = d.get('section_summary')
    if ss:
        out += ['## Summary', '']
        if ss.get('compact'): out += [t(ss['compact']), '']
        kt = ss.get('key_takeaways')
        if kt:
            out += ['### Key Takeaways', '']
            if isinstance(kt, list): lst(kt, False, out); out.append('')
            elif 'items' in kt: lst(kt['items'], kt.get('style') == 'ordered', out); out.append('')
            else: groups(kt, out, 4)
    nx = d.get('next')
    if nx: out += ['---', '', '> [!NOTE]', f'> **Next — {t(nx["title"])}**', '>', '> ' + t(nx['summary']), '']
    con = d.get('connections')
    if con:
        out += ['## Connections', '']
        for k, v in con.items():
            if isinstance(v, dict) and v.get('type') == 'callout': blocks([v], 3, out); continue
            out += [f'### {label(k)}', '']
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, dict): out.append(f'- **{t(x.get("section", ""))}** — {t(x.get("link", ""))}')
                    else: out.append(f'- {t(x)}')
            else: out.append(t(v))
            out.append('')
    return '\n'.join(out)

if __name__ == '__main__':
    print(render(yaml.safe_load(open(sys.argv[1]))))
