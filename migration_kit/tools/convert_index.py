"""v1 chapter index -> v2: frontmatter from document_info, every other key kept as written,
prose scalars folded (paragraphs kept), line-structured text kept literal, apostrophes fixed."""
import sys, re, json, datetime, yaml
from collections import OrderedDict
import convert as C
from emit import Folded, Literal, emit, plain

def value(v, path):
    if isinstance(v, dict): return OrderedDict((k, value(x, f'{path}.{k}')) for k, x in v.items())
    if isinstance(v, list): return [value(x, f'{path}[{i}]') for i, x in enumerate(v)]
    if not isinstance(v, str): return v
    if '\n' not in v.strip():
        return C.fix_text_apos(v, path).strip() if "''" in v else v.rstrip('\n') if v.endswith('\n') else v
    t = C.fix_text_apos(v, path)
    paras = [p for p in re.split(r'\n[ \t]*\n', t.strip('\n')) if p.strip()]
    structured = []
    for p in paras:
        ls = p.split('\n'); ks = set(C._para_kinds(ls))
        width = max(len(l.rstrip()) for l in ls)
        short = [l for l in ls[:-1] if len(l.rstrip()) < 0.6 * width]
        if ks & {'item', 'pre', 'indent', 'cont'} or (len(ls) >= 2 and len(short) >= 2 * (len(ls) - 1) / 3):
            structured.append(p)
    if structured:
        C.R.add('classified', path=path, kind='index value kept literal (line-structured)', text=structured[0][:300])
        return Literal(t if t.endswith('\n') else t + '\n')
    return C.prose_value(t, path)

MOVES = []                           # (v1 path, v2 path) for every value the topic-list layout moves

def topic_layout(d):
    """An index in the topic-list layout (chapter_topics, chapter_deliverables, frameworks_covered,
    sections keyed section_NN_MM) is mapped onto the layout of the other chapter indexes. Values are
    moved, never rewritten; a key with no counterpart keeps its v1 name. Returns (index, extra tags)."""
    di = OrderedDict(d['document_info']); co = d.get('chapter_overview') or {}
    out = OrderedDict([('document_info', di)])
    def mv(a, b): MOVES.append((a, b))
    o = OrderedDict()
    ren = {'position_in_book': 'position', 'why_this_chapter_exists': 'purpose'}
    for k, v in co.items():
        if k == 'one_line_summary':                # the index's one-line description, as section_info.description elsewhere
            di['description'] = v; mv('chapter_overview.one_line_summary', 'section_info.description')
        else:
            o[ren.get(k, k)] = v; mv(f'chapter_overview.{k}', f'chapter_overview.{ren.get(k, k)}')
    if 'chapter_topics' in d: o['chapter_topics'] = d['chapter_topics']; mv('chapter_topics', 'chapter_overview.chapter_topics')
    if 'frameworks_covered' in d: o['frameworks_covered'] = d['frameworks_covered']; mv('frameworks_covered', 'chapter_overview.frameworks_covered')
    st = OrderedDict()
    for k in ('total_sections', 'estimated_pages', 'estimated_reading_time'):
        if k in di: st[k] = di.pop(k); mv(f'document_info.{k}', f'chapter_overview.structure.{k}')
    if st: o['structure'] = st
    if 'chapter_deliverables' in d: o['key_deliverables'] = d['chapter_deliverables']; mv('chapter_deliverables', 'chapter_overview.key_deliverables')
    out['chapter_overview'] = o
    secs = []
    for i, (key, v) in enumerate(d['sections'].items()):
        m = re.fullmatch(r'section_(\d+)_(\d+)', key)
        assert m and int(m.group(1)) == di['chapter'] and str(v.get('filename', '')).startswith(key + '_'), key
        e = OrderedDict([('section_number', int(m.group(2)))]); mv(f'sections.{key} (key)', f'sections[{i}].section_number')
        order = ['title', 'filename', 'note', 'estimated_pages', 'topics', 'key_concepts', 'deliverables', 'security_preview']
        for kk in sorted(v, key=lambda x: order.index(x) if x in order else len(order)):
            e[kk] = v[kk]; mv(f'sections.{key}.{kk}', f'sections[{i}].{kk}')
        secs.append(e)
    out['sections'] = secs
    tags = []
    for k, v in d.items():
        if k in ('document_info', 'chapter_overview', 'chapter_topics', 'frameworks_covered', 'chapter_deliverables', 'sections'): continue
        if k == 'metadata' and isinstance(v, dict) and 'tags' in v:
            tags = list(v['tags']); v = OrderedDict((x, y) for x, y in v.items() if x != 'tags'); mv('metadata.tags', 'tags')
        out[k] = v; mv(k, k)
    C.R.add('notes', path='(index)', note='topic-list index layout mapped onto the chapter index layout', moves=MOVES)
    return out, tags

def convert(src):
    d = [x for x in yaml.safe_load_all(open(src)) if x is not None]
    assert len(d) == 1; d = d[0]
    extra_tags = []
    if 'chapter_topics' in d and isinstance(d.get('sections'), dict): d, extra_tags = topic_layout(d)
    di = d['document_info']
    out = OrderedDict()
    out['title'] = C.short(di['title'], 'document_info.title')
    out['updated'] = datetime.date.fromisoformat(str(di['created']))
    if 'version' in di: out['version'] = str(di['version'])
    out['authors'] = [di['author']]
    if di.get('tags') or extra_tags: out['tags'] = list(OrderedDict.fromkeys(list(di.get('tags') or []) + extra_tags))
    si = OrderedDict()
    for k, v in di.items():
        if k in ('title', 'version', 'author', 'tags'): continue
        si['repository' if k == 'github' else k] = value(v, f'document_info.{k}')
    out['section_info'] = si
    for k, v in d.items():
        if k != 'document_info': out[k] = value(v, k)
    return out

if __name__ == '__main__':
    src, dst, rep = sys.argv[1:4]
    out = convert(src)
    header = open(src).read().split('\n', 1)[0]
    text = (header + '\n\n---\n' if header.startswith('#') else '---\n') + emit(out)
    assert yaml.safe_load(text) == plain(out), 'round-trip mismatch'
    open(dst, 'w').write(text)
    json.dump(C.R.items, open(rep, 'w'), indent=1, default=str)
    print(src.split('/')[-1], '->', {k: len(v) for k, v in C.R.items.items() if v})
