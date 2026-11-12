"""Independent check for a migrated index: every v1 key path and value survives, document_info
excepted (checked field by field), with whitespace/hyphen/apostrophe normalisation only."""
import sys, re, json, yaml, collections
from check import norm_v1
def leaves(n, p=''):
    if isinstance(n, dict):
        for k, v in n.items(): yield from leaves(v, f'{p}.{k}')
    elif isinstance(n, list):
        for i, v in enumerate(n): yield from leaves(v, f'{p}[{i}]')
    else: yield p, n
def nt(v, src):
    if not isinstance(v, str): return str(v)
    return ' '.join((norm_v1(v) if src else v).split())
a = [x for x in yaml.safe_load_all(open(sys.argv[1])) if x][0]; b = yaml.safe_load(open(sys.argv[2]))
res = {'file': sys.argv[2].split('/')[-1]}
TOPIC = 'chapter_topics' in a and isinstance(a.get('sections'), dict)
def topic_path(p):
    """Where a v1 leaf of a topic-list index is expected in v2 (stated here independently of the converter)."""
    fixed = [(r'^\.chapter_overview\.one_line_summary$', '.section_info.description'),
             (r'^\.chapter_overview\.position_in_book$', '.chapter_overview.position'),
             (r'^\.chapter_overview\.why_this_chapter_exists$', '.chapter_overview.purpose'),
             (r'^\.chapter_topics', '.chapter_overview.chapter_topics'),
             (r'^\.frameworks_covered', '.chapter_overview.frameworks_covered'),
             (r'^\.chapter_deliverables', '.chapter_overview.key_deliverables'),
             (r'^\.document_info\.(total_sections|estimated_pages|estimated_reading_time)$', r'.chapter_overview.structure.\1'),
             (r'^\.metadata\.tags', '.tags')]
    for pat, rep in fixed:
        if re.match(pat, p): return re.sub(pat, rep, p)
    m = re.match(r'^\.sections\.section_\d+_(\d+)(\..*)$', p)
    if m: return f'.sections[{int(m.group(1)) - 1}]{m.group(2)}'
    return p
if TOPIC:
    import copy
    keys = list(a['sections'])
    res['section_keys_to_numbers'] = all(b['sections'][i]['section_number'] == int(k.rsplit('_', 1)[1]) and b['sections'][i]['filename'].startswith(k + '_')
                                         and int(k.split('_')[1]) == a['document_info']['chapter'] for i, k in enumerate(keys)) and len(keys) == len(b['sections'])
    la_all = dict((topic_path(p), nt(v, True)) for p, v in leaves(a))
    lb_all = dict((p, nt(v, False)) for p, v in leaves({k: v for k, v in b.items() if k not in ('title', 'updated', 'version', 'authors')}))
    lb_all.update({'.document_info.title': nt(b['title'], False), '.document_info.created_as_updated': str(b['updated']),
                   '.document_info.version': nt(b['version'], False), '.document_info.author': nt(b['authors'][0], False)})
    la_all['.document_info.created_as_updated'] = str(a['document_info']['created'])
    ren = {'.document_info.github': '.section_info.repository'}
    la_all = {(ren.get(p) or re.sub(r'^\.document_info\.(?!title$|version$|author$|created_as_updated$)', '.section_info.', p)): v for p, v in la_all.items()}
    derived = {p for p in lb_all if re.fullmatch(r'\.sections\[\d+\]\.section_number', p)}
    res['v1_leaves'] = len(la_all); res['v2_leaves'] = len(lb_all) - len(derived)
    res['missing_or_changed'] = [{'path': p, 'v1': v[:120], 'v2': lb_all.get(p, '<missing>')[:120]} for p, v in la_all.items() if lb_all.get(p) != v]
    res['v2_without_v1_source'] = sorted(set(lb_all) - set(la_all) - derived)
    res['PASS'] = res['section_keys_to_numbers'] and not res['missing_or_changed'] and not res['v2_without_v1_source']
    print(json.dumps(res, indent=1, ensure_ascii=False)); sys.exit(0)
di = a.pop('document_info'); si = b.get('section_info', {})
res['frontmatter_ok'] = (b['title'] == di['title'].replace("''", "'") and str(b['updated']) == str(di['created'])
    and b['authors'] == [di['author']] and b.get('tags', []) == list(di.get('tags') or []) and str(b.get('version')) == str(di.get('version')))
res['document_info_rest_ok'] = all(nt(si.get('repository' if k == 'github' else k), False) == nt(v, True)
    for k, v in di.items() if k not in ('title', 'version', 'author', 'tags'))
body_b = {k: v for k, v in b.items() if k not in ('title', 'updated', 'version', 'authors', 'tags', 'section_info')}
la = dict((p, nt(v, True)) for p, v in leaves(a)); lb = dict((p, nt(v, False)) for p, v in leaves(body_b))
res['keys_identical'] = list(la) == list(lb)
res['value_differences'] = [{'path': p, 'v1': la[p][:120], 'v2': lb.get(p, '<missing>')[:120]} for p in la if la[p] != lb.get(p)]
res['PASS'] = res['frontmatter_ok'] and res['document_info_rest_ok'] and res['keys_identical'] and not res['value_differences']
print(json.dumps(res, indent=1))
