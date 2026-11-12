"""Independent check of a migrated section against its v1 source. Shares no code with convert.py.
Usage: check.py V1.yaml V2.yaml  -> prints a JSON verdict."""
import sys, re, json, yaml, difflib

ORDER = ['title','updated','version','authors','tags','section_info','lead','overview','learning_objectives',
         'prerequisites','prose_content','reference_materials','deliverables','artifacts','exercises',
         'common_mistakes','section_summary','next','connections']
BLOCK_TYPES = {'heading','prose','lead','list','definition','fields','table','quote','callout','code','figure',
               'steps','comparison','divider','toc','footnotes'}
V1_CODE_KEYS = {'code'}
STRUCTURAL = {'type','lang','variant','style','id','kind','target'}
STOP = {'a','an','the','and','or','of','in','on','at','to','for','vs','via'}
def label(k):
    w = str(k).replace('_', ' ').split()
    return ' '.join(x.capitalize() if i == 0 or x not in STOP else x for i, x in enumerate(w))

def norm_v1(t):
    t = t.replace("''", "'")
    t = re.sub(r'(?<=[A-Za-z0-9])-\n[ \t]*(?=[A-Za-z0-9])', '-', t)
    # Profile rule: a marker line is a list item only at the top of a paragraph, after a line ending
    # in ':', or after another item (or an indented continuation of one). Items' markers -> one token.
    M = re.compile(r'^([ \t]{0,4})(?:[-*•]|\d+[.)]|[a-z][.)])[ \t]+')
    out = []
    for para in re.split(r'(\n[ \t]*\n)', t):
        if re.fullmatch(r'\n[ \t]*\n', para): out.append(para); continue
        lines = para.split('\n'); prev = None; res = []
        for i, l in enumerate(lines):
            is_item = bool(M.match(l)) and (i == 0 or prev in ('item', 'cont') or lines[i-1].rstrip().endswith(':'))
            if is_item: res.append(M.sub(' \u2022 ', l)); prev = 'item'
            else:
                prev = 'cont' if (prev in ('item', 'cont') and l[:1] in (' ', '\t')) else ('text' if l.strip() else prev)
                res.append(l)
        out.append('\n'.join(res))
    return ''.join(out)

def words(t): return ['\u2022' if w == '-' else w for w in t.split()]   # a bare dash and a list marker are one token: YAML lists in code vs items in prose

def v1_stream(d):
    """Text of a v1 section in document order: every string except code, document_info and tags."""
    out = []
    d = {k: strip_ordinals(k, v) for k, v in d.items()}
    def w(n, k=None, path=''):
        if isinstance(n, dict):
            for kk, v in n.items():
                if path == '' and kk == 'document_info': continue
                if path == '.metadata' and kk == 'tags': continue
                if kk in V1_CODE_KEYS: continue
                w(v, kk, f'{path}.{kk}')
        elif isinstance(n, list):
            for v in n:
                if isinstance(v, str) or (isinstance(v, dict) and 'takeaway' in v): out.append('\u2022')
                w(v, k, path)
        elif isinstance(n, str): out.extend(words(norm_v1(n)))
        elif n is not None and not isinstance(n, bool): out.append(str(n))
    w(d); return out

def v2_stream(d):
    """Text of a v2 section in document order, minus frontmatter, section_info, profile-derived labels."""
    out = []
    def w(n, k=None, path=''):
        if isinstance(n, dict):
            derived_heading = 'id' in n and (n.get('heading') == label(n['id']) or n.get('subject') == label(n['id']))
            for kk, v in n.items():
                if path == '' and kk in ('title','updated','version','authors','tags','section_info'): continue
                if kk in STRUCTURAL and k != 'legacy': continue
                if k == 'legacy' and kk == 'id': continue                    # v1 id kept verbatim; checked in v1_ids_kept
                if kk == 'heading' and v == n.get('filename'): continue      # untitled deliverable: heading shows the filename
                if kk == 'text' and n.get('type') == 'code' and n.get('lang') != 'text':
                    out.extend(words(v)); continue                           # shell/YAML block: no list-marker normalisation
                if kk == 'code' and path.startswith('.deliverables'): continue
                if kk in ('heading', 'subject') and derived_heading and n.get(kk) == label(n['id']): continue
                if kk == 'label' and n.get('value') is not None: continue          # fields label = v1 key
                if kk == 'title' and n.get('type') == 'callout': continue          # callout title = v1 key
                if kk == 'groups' or (path.endswith('.groups')): pass
                w(v, kk, f'{path}.{kk}')
        elif isinstance(n, list):
            for v in n:
                if isinstance(v, str): out.append('\u2022')
                w(v, k, path)
        elif isinstance(n, str):
            if k == 'text' and '\n' in n: n = norm_v1(n).replace("'", "'")          # literal text keeps line-start markers
            out.extend(words(n))
        elif n is not None and not isinstance(n, bool): out.append(str(n))
    w(d); return out

def literal_paths(text):
    node = yaml.compose(text); bad = []
    def w(n, path):
        if isinstance(n, yaml.MappingNode):
            m = {k.value: v for k, v in n.value}
            for k, v in n.value: w(v, path + [k.value, m])
        elif isinstance(n, yaml.SequenceNode):
            for i, v in enumerate(n.value): w(v, path + [i, None])
        elif n.style == '|':
            key, parent = path[-2], path[-1]
            ok = (key == 'text' and parent.get('type') is not None and parent['type'].value == 'code') or \
                 (key == 'code' and 'deliverables' in path)
            if not ok: bad.append('.'.join(str(p) for p in path[::2]))
    w(node, []); return bad

def blocks_ok(d):
    errs = []
    def w(n, path):
        if isinstance(n, dict):
            if 'type' in n and isinstance(n['type'], str) and path.endswith('blocks[]'):
                if n['type'] not in BLOCK_TYPES: errs.append(f'{path}: unknown block {n["type"]}')
                req = {'prose': ['text'], 'list': ['style', 'items'], 'code': ['lang', 'text'], 'callout': ['variant', 'text'],
                       'fields': ['subject', 'entries'], 'table': ['columns', 'rows']}.get(n['type'], [])
                for r in req:
                    if r not in n: errs.append(f'{path}: {n["type"]} missing {r}')
            for k, v in n.items(): w(v, f'{path}.{k}')
        elif isinstance(n, list):
            for v in n: w(v, path + '[]')
    w(d, ''); return errs

def v1_slot(top, key, val, sc_family=None):
    """Which v2 slot (and sub-order) a v1 path feeds, per the profile's v1_sources. Independent of convert.py."""
    if top == 'section_overview': return ('lead', 0) if key == 'one_line_summary' else ('overview', 0)
    if top in ('learning_objectives', 'prerequisites', 'prose_content', 'reference_materials', 'common_mistakes'): return (top, 0)
    if top == 'implementations': return ('deliverables', 0)
    if top == 'deliverables': return ('artifacts', 0) if key == 'items' else (('legacy', 0) if key == 'count' else ('deliverables', 0))
    if top == 'section_summary': return ('section_summary', 1) if key == 'key_takeaways' else ('section_summary', 0)
    if top == 'key_takeaways': return ('legacy', 0) if key == 'count' else ('section_summary', 1)
    if top.startswith('preview_'): return ('next', 0)
    if top == 'metadata' and not isinstance(val, (list, dict)): return ('legacy', 0)   # counts and ids
    if top in ('metadata', 'connections'): return ('connections', 0)
    if top == 'section_content':
        if sc_family == 'subsections': return ('prose_content', 0)
        if key in ('overview', 'why_this_matters'): return ('overview', 1)
        if key == 'key_takeaways': return ('section_summary', 1)
        if key in ('learning_objectives', 'prerequisites', 'common_mistakes'): return (key, 0)
        return ('prose_content', 0)
    return ('UNMAPPED:' + top, 0)

def leaves(n, skip_num_keys=('number', 'count')):
    """(key, text) leaves in order; numeric ordering/count fields are form, handled as legacy/ordered lists."""
    out = []
    def w(n, k):
        if isinstance(n, dict):
            for kk, v in n.items():
                if kk in V1_CODE_KEYS: continue
                if kk == 'language' and 'code' in n: continue              # becomes lang; checked in deliverable_langs
                if kk == 'id' and isinstance(v, str): continue             # kept as an id; checked in v1_ids_kept
                w(v, kk)
        elif isinstance(n, list):
            for v in n:
                if isinstance(v, str) or (isinstance(v, dict) and 'takeaway' in v): out.append(['\u2022'])
                w(v, k)
        elif isinstance(n, str): out.append(words(norm_v1(n)))
        elif n is not None and not isinstance(n, bool) and k not in skip_num_keys: out.append([str(n)])
    w(n, None); return out

# List-shaped slots (chapters 9 and 12 summaries): each item carries its own number, which becomes its
# v2 id (prefix_N), stated here independently of convert.py and checked in list_item_ids.
LIST_ORDINAL = {'prose_content': ('part', 'part'), 'reference_materials': ('table', 'table'),
                'deliverables': ('id', 'deliverable'), 'implementations': ('id', 'deliverable'),
                'common_mistakes': ('id', 'mistake')}

def strip_ordinals(top, v):
    if top not in LIST_ORDINAL or not isinstance(v, list): return v
    key = LIST_ORDINAL[top][0]
    return [{k: x for k, x in it.items() if not (k == key and str(x).isdigit())} if isinstance(it, dict) else it for it in v]

def split_key_terms(d):
    """Profile map, restated: section_summary.key_terms given as "Term: definition" strings (chapter 13)
    is the chapter 11 term/definition list, split at the first colon. Returns (v1 as mapped, the strings)."""
    ss = d.get('section_summary')
    kt = ss.get('key_terms') if isinstance(ss, dict) else None
    if not (isinstance(kt, list) and kt and all(isinstance(x, str) and ':' in x for x in kt)): return d, None
    pairs = [{'term': x.split(':', 1)[0].strip(), 'definition': x.split(':', 1)[1].strip()} for x in kt]
    return dict(d, section_summary=dict(ss, key_terms=pairs)), kt

def v1_slots(d):
    slots = {}
    for top, v in d.items():
        if top == 'document_info': continue
        if top == 'metadata': v = {k: x for k, x in v.items() if k != 'tags'}
        v = strip_ordinals(top, v)
        fam = 'subsections' if top == 'section_content' and all(k.startswith('subsection_') for k in v) else None
        items = v.items() if isinstance(v, dict) else [(None, v)]
        for key, val in items:
            slot = v1_slot(top, key, val, fam)
            node = val if key is not None else v
            slots.setdefault(slot, []).extend(leaves({key: node} if key and slot[0] in ('overview','prose_content') and isinstance(node, str) else node))
    return slots

def v2_slot_streams(d):
    out = {}
    for k, v in d.items():
        if k in ('title','updated','version','authors','tags','section_info'): continue
        if k == 'section_summary' and isinstance(v, dict):
            for sub, i in (('compact', 0), ('key_takeaways', 1), ('key_terms', 0)):     # key_terms sits with compact, as in v1_slot
                if sub in v: out.setdefault((k, i), []).extend(v2_stream({sub: v[sub]}))
            continue
        out[(k, 0)] = v2_stream({k: v})
    return out

def main(a, b):
    v1 = [x for x in yaml.safe_load_all(open(a)) if x is not None]
    text = open(b).read()
    docs = list(yaml.safe_load_all(text)); res = {'file': b.split('/')[-1]}
    res['parses_single_document'] = len(docs) == 1
    v1, v2 = v1[0], docs[0]
    v1, kt_strings = split_key_terms(v1)
    if kt_strings is not None:     # each v2 term/definition must rejoin to its v1 string exactly
        got = [f"{x.get('term')}: {x.get('definition')}" for x in (v2.get('section_summary') or {}).get('key_terms') or []]
        want = [' '.join(s.replace("''", "'").split()) for s in kt_strings]
        res['key_terms_rejoin'] = 'match' if [' '.join(g.split()) for g in got] == want else {'v1': want, 'v2': got}
    keys = list(v2)
    res['layout_keys_in_profile_order'] = all(k in ORDER for k in keys) and keys == sorted(keys, key=ORDER.index)
    res['frontmatter_has_title_updated'] = 'title' in v2 and 'updated' in v2
    res['prose_literals_outside_code'] = literal_paths(text)
    res['block_shape_errors'] = blocks_ok(v2)
    # per-slot accounting: every v1 text leaf contiguous in its slot, and slot word multisets equal
    import collections
    s1slots, s2slots = v1_slots(v1), v2_slot_streams(v2)
    merged = {}
    for (slot, sub), lv in s1slots.items():
        if slot == 'legacy': continue
        merged.setdefault((slot, sub), []).extend(lv)
    acct = []
    for key in sorted(set(merged) | set(s2slots), key=str):
        if key[0] == 'overview': continue
        lv = merged.get(key, []); st = s2slots.get(key, [])
        w1 = collections.Counter(x for l in lv for x in l); w2 = collections.Counter(st)
        if w1 != w2: acct.append({'slot': key[0] + ('/' + str(key[1]) if key[1] else ''), 'missing_in_v2': dict((w1 - w2).most_common(12)), 'extra_in_v2': dict((w2 - w1).most_common(12))})
        joined = ' ' + ' '.join(st) + ' '
        for l in lv:
            if l and (' ' + ' '.join(l) + ' ') not in joined: acct.append({'slot': key[0], 'leaf_not_contiguous': ' '.join(l)[:160]})
    ov1 = [x for (sl, _), lv in merged.items() if sl == 'overview' for l in lv for x in l]
    ov2 = s2slots.get(('overview', 0), [])
    if collections.Counter(ov1) != collections.Counter(ov2): acct.append({'slot': 'overview', 'missing_in_v2': dict((collections.Counter(ov1) - collections.Counter(ov2)).most_common(12)), 'extra_in_v2': dict((collections.Counter(ov2) - collections.Counter(ov1)).most_common(12))})
    res['slot_accounting_problems'] = acct
    res['unmapped_v1_keys'] = sorted({k[0] for k in s1slots if k[0].startswith('UNMAPPED')})
    # text stream (whole document, order-sensitive; informative when slots reorder content)
    s1, s2 = v1_stream(v1), v2_stream(v2)
    res['text_words_v1'], res['text_words_v2'] = len(s1), len(s2)
    diffs = []
    if s1 != s2:
        sm = difflib.SequenceMatcher(None, s1, s2, autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op != 'equal':
                diffs.append({'op': op, 'v1': ' '.join(s1[max(0,i1-6):i2+6]), 'v2': ' '.join(s2[max(0,j1-6):j2+6])})
    res['text_differences_ordered'] = diffs if acct else ('none' if not diffs else f'{len(diffs)} order-only differences (slot reordering; per-slot accounting is clean)')
    # code
    def v1code(dl):
        if isinstance(dl, dict) and 'items' not in dl: return [x['code'] for x in dl.values() if isinstance(x, dict) and 'code' in x]
        if isinstance(dl, list): return [x['code'] for x in dl if 'code' in x]
        return []
    c1 = v1code(v1.get('implementations')) + v1code(v1.get('deliverables'))
    c2 = [d['code'] for d in v2.get('deliverables') or []]
    res['code_blocks'] = len(c1)
    res['code_count_match'] = len(c1) == len(c2)
    res['code_differences'] = []
    for i, (x, y) in enumerate(zip(c1, c2)):
        if x != y:
            xl, yl = x.split('\n'), y.split('\n')
            res['code_differences'].append({'deliverable': i + 1, 'lines': [
                {'line': n + 1, 'v1': p, 'v2': q} for n, (p, q) in enumerate(zip(xl, yl)) if p != q] +
                ([{'note': 'line count differs'}] if len(xl) != len(yl) else [])})
    def ids(n, out, top=True):
        if isinstance(n, dict):
            for kk, v in n.items():
                if top and kk == 'document_info': continue
                if kk == 'id' and isinstance(v, str): out.append(v)
                else: ids(v, out, False)
        elif isinstance(n, list):
            for v in n: ids(v, out, False)
        return out
    v2ids = ids(v2, [])
    res['v1_ids_kept'] = [i for i in ids(v1, []) if i not in v2ids] or 'all'
    lid = []
    for top, (key, prefix) in LIST_ORDINAL.items():
        v = v1.get(top)
        if not isinstance(v, list): continue
        slot = 'deliverables' if top == 'implementations' else top
        want = [f'{prefix}_{it[key]}' if str(it.get(key, '')).isdigit() else str(it.get(key, f'{prefix}_{i + 1}')) for i, it in enumerate(v)]
        got = [x.get('id') for x in v2.get(slot) or []]
        if want != got: lid.append({'slot': slot, 'expected': want, 'v2': got})
    res['list_item_ids'] = lid or 'match'
    def langs(dl):
        items = dl.values() if isinstance(dl, dict) else dl if isinstance(dl, list) else []
        return [str(x.get('language')).lower() for x in items if isinstance(x, dict) and 'code' in x and x.get('language')]
    l1 = langs(v1.get('implementations')) + langs(v1.get('deliverables'))
    res['deliverable_langs'] = 'match' if all(a == b.get('lang') for a, b in zip(l1, [x for x in v2.get('deliverables') or []])) else 'MISMATCH'
    res['title_identical'] = v2.get('title') == v1['document_info']['title'].replace("''", "'")
    res['updated_equals_created'] = str(v2.get('updated')) == str(v1['document_info']['created'])
    v1tags = list(v1['document_info'].get('tags') or []) + list((v1.get('metadata') or {}).get('tags') or [])
    res['tags_preserved'] = list(dict.fromkeys(v1tags)) == (v2.get('tags') or [])
    res['PASS'] = (res['parses_single_document'] and res['layout_keys_in_profile_order'] and not res['prose_literals_outside_code']
                   and not res['block_shape_errors'] and not acct and not res['unmapped_v1_keys'] and res['code_count_match'] and res['title_identical']
                   and res['updated_equals_created'] and res['tags_preserved'] and res['v1_ids_kept'] == 'all'
                   and res['deliverable_langs'] == 'match' and res['list_item_ids'] == 'match'
                   and res.get('key_terms_rejoin', 'match') == 'match')
    return res

if __name__ == '__main__':
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=1, ensure_ascii=False))
