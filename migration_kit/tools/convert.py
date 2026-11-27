"""v1 section -> profile layout. Usage: convert.py IN.yaml OUT.yaml REPORT.json
Implements 20261012__AI_Security_Mastery_Book_Profile (draft 0.1.0)."""
import sys, re, json, yaml, io, tokenize, datetime
from collections import OrderedDict
from emit import Folded, Literal, emit, plain

STOP = {'a','an','the','and','or','of','in','on','at','to','for','vs','via'}
def label(key):                      # v1 site's nice_label, verbatim behaviour
    words = str(key).replace('_', ' ').split()
    return ' '.join(w.capitalize() if i == 0 or w not in STOP else w for i, w in enumerate(words))

CODE_KEYS = {'code','numpy_implementation','numpy_example','implementation','complete_feature_extractor',
             'python_example','example_code','numpy_code','handle_missing','solution_code','script',
             'implementation_code','complete_implementation','practical_implementation'}
EXT_LANG = {'.py':'python','.yml':'yaml','.yaml':'yaml','.json':'json','.sh':'bash','.sql':'sql','.md':'markdown'}

class Report:
    def __init__(s): s.items = {k: [] for k in ('apostrophe_text','apostrophe_code','classified','unmapped',
                                                 'legacy','defects','notes','inline_collisions','hyphen_join','wrap_marker_kept_as_text')}
    def add(s, k, **kw): s.items[k].append(kw)
R = Report()

# ── apostrophes ───────────────────────────────────────────────────────────────
def fix_text_apos(t, path):
    if "''" not in t: return t
    for m in re.finditer(r"''", t):
        R.add('apostrophe_text', path=path, context=t[max(0, m.start()-25):m.end()+25].replace('\n', ' '))
    return t.replace("''", "'")

def fix_code_apos(code, path):
    """Fix only genuine bugs: glued string tokens, and '' between word chars in comments/strings."""
    if "''" not in code: return code
    try: toks = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except Exception as e:
        R.add('notes', path=path, note=f'code not tokenizable as Python ({e.__class__.__name__}); no apostrophe fix attempted'); return code
    lines = code.split('\n'); edits = []   # (row, col_start, col_end, replacement)
    prev = None
    for t in toks:
        if (t.type == tokenize.STRING and prev is not None and prev.type == tokenize.STRING and prev.end == t.start
                and prev.string.endswith("'") and t.string.startswith("'") and prev.start[0] == t.start[0]):
            # 'Track 7''s' is two glued literals; the apostrophe is meant inside one single-quoted string,
            # so it is written escaped ('Track 7\'s'), as the chapter 9 migration did.
            edits.append((t.start[0], t.start[1] - 1, t.start[1] + 1, "\\'", 'STRCAT', prev.string + t.string))
        if t.type in (tokenize.COMMENT, tokenize.STRING) and t.start[0] == t.end[0]:
            for m in re.finditer(r"(?<=\w)''(?=\w)", t.string):
                if t.type == tokenize.STRING and t.string[:1] == "'" and not t.string.startswith("'''"): continue
                c = t.start[1] + m.start()
                edits.append((t.start[0], c, c + 2, "'", 'COMMENT' if t.type == tokenize.COMMENT else 'STRBODY', t.string))
        if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT): prev = t
    for row, a, b, rep, kind, ctx in sorted(edits, key=lambda e: (e[0], -e[1])):
        L = lines[row - 1]; lines[row - 1] = L[:a] + rep + L[b:]
        R.add('apostrophe_code', path=path, line=row, kind=kind, before=ctx.strip()[:140])
    return '\n'.join(lines)

# ── literal text -> standard blocks ───────────────────────────────────────────
BUL = re.compile(r'^( {0,4})([-*•]|\d+[.)]|[a-z][.)])\s+(.*)$')
DIAG = re.compile(r'[─│┌┐└┘├┤┬┴┼═║╔╗╚╝↓↑▼▲]|^\s*\|.*\|\s*$|-->|==>|^\s*(→|->)')

def _line_kind(l):
    if not l.strip(): return 'blank'
    if BUL.match(l): return 'item'
    if DIAG.search(l.replace('-->', '') if '<!--' in l else l): return 'pre'     # chapter 6: <!-- and --> named in prose is not an arrow
    if l.startswith((' ', '\t')): return 'indent'
    return 'text'

FORMULA = re.compile(r'[=≈≤≥∑√∂∇]|\^|_\{|\|\|')

def _para_kinds(lines):
    """Per-line kinds with wrap artifacts resolved: a marker line is a list item only at the top of
    the paragraph, after a line ending in ':', or after another item/continuation."""
    kinds = []
    for i, l in enumerate(lines):
        k = _line_kind(l)
        if k == 'item' and i > 0 and kinds[-1] not in ('item', 'cont') and not lines[i-1].rstrip().endswith(':'):
            R.add('wrap_marker_kept_as_text', line=l.strip()[:80])
            k = 'text'
        if k == 'indent' and kinds and kinds[-1] in ('item', 'cont'): k = 'cont'
        kinds.append(k)
    return kinds

def _wrap_width(lines, path):
    """The width a paragraph was wrapped at. One line far longer than every other (an in-place edit that
    was never re-wrapped) does not set the width; the next-longest does, and the line is reported."""
    ws = sorted((len(l.rstrip()) for l in lines), reverse=True)
    if len(ws) >= 3 and ws[0] > 1.3 * ws[1]:
        R.add('classified', path=path, kind='overlong-line-ignored-for-wrap-width', text=max(lines, key=len)[:200])
        return ws[1]
    return ws[0]

FENCE = re.compile(r'^\s*```[\w-]*\s*$')
ARROW_LEAD = re.compile(r'^\s*(→|->)\s*')

def _para_to_blocks(para, path):
    lines = para.split('\n')
    if len(lines) >= 3 and FENCE.match(lines[0]) and FENCE.match(lines[-1]):
        # chapter 7: a fenced example quoted in prose stays verbatim, fences included (they are part of the quote)
        R.add('classified', path=path, kind='fenced-paragraph->code(text)', text=para[:400])
        return [{'type': 'code', 'lang': 'text', 'text': Literal(_dedent(lines) + '\n')}]
    kinds = _para_kinds(lines)
    pre = [i for i, k in enumerate(kinds) if k == 'pre']
    if (pre and set(kinds) <= {'text', 'pre'} and all(i > 0 and lines[i][:1] not in (' ', '\t') and not lines[i - 1].rstrip().endswith(':')
            and not DIAG.search(ARROW_LEAD.sub('', lines[i])) for i in pre)):
        # chapter 7: a wrapped prose line that only starts with an arrow (a flow written as a sentence)
        w = _wrap_width(lines, path)
        if not any(len(l.rstrip()) < 0.6 * w for l in lines[:-1]):
            R.add('classified', path=path, kind='arrow-led-wrap-line-kept-as-prose', text=para[:400])
            kinds = ['text'] * len(lines)
    ks = set(kinds)
    if ks <= {'text'}:
        width = _wrap_width(lines, path)
        short = [i for i, l in enumerate(lines[:-1]) if len(l.rstrip()) < 0.6 * width]
        if not short:
            return [{'type': 'prose', 'text': Folded(join_lines(lines, path))}]
        if len(lines) >= 2 and len(short) >= max(1, 2 * (len(lines) - 1) / 3):
            R.add('classified', path=path, kind='line-structured->code(text)', text=para[:400])
            return [{'type': 'code', 'lang': 'text', 'text': Literal(para.rstrip() + '\n')}]
        R.add('classified', path=path, kind='short-lines-folded-into-prose (v3 candidate: math or list block)', text=para[:400])
        return [{'type': 'prose', 'text': Folded(join_lines(lines, path))}]
    if 'item' in ks and ks <= {'text', 'item', 'cont'}:
        first = kinds.index('item')
        if all(k == 'text' for k in kinds[:first]) and all(k in ('item', 'cont') for k in kinds[first:]):
            out = []
            if first: out.append({'type': 'prose', 'text': Folded(join_lines(lines[:first], path))})
            out.append(_list_block(lines[first:], path))
            return out
    emb = _embedded_code(lines, kinds, path)
    if emb: return emb
    R.add('classified', path=path, kind='line-structured->code(text)', text=para[:400])
    return [{'type': 'code', 'lang': 'text', 'text': Literal(_dedent(lines) + '\n')}]

SHELL_CMDS = ('sigma ', 'sigmac ', 'pip ', 'pip3 ', 'python ', 'python3 ', 'git ', 'curl ', 'docker ', 'kubectl ',
              'export ', 'cd ', 'mkdir ', 'make ', 'npm ', 'yamllint ', 'pytest ', '$ ')
YAML_LINE = re.compile(r'^(- |[A-Za-z_][\w.|-]*:( |$))')

def _code_lang(ls):
    """Language of an indented block embedded in prose, or None. Only unambiguous shapes:
    a shell script (shebang) or command lines, or a YAML mapping (Sigma rules and fragments)."""
    body = [l for l in ls if l.strip()]
    if body[0].startswith('#!'):
        return 'sh' if re.match(r'#!\S*/(env +)?sh\b', body[0]) else 'bash' if 'bash' in body[0] else None
    cont = False; ok = True
    for l in body:
        if not cont and not l.startswith(SHELL_CMDS): ok = False; break
        cont = l.rstrip().endswith('\\')
    if ok: return 'bash'
    top = [l for l in body if not l.startswith((' ', '\t'))]
    if top and all(YAML_LINE.match(l) for l in top) and ':' in body[0]:
        try: v = yaml.safe_load('\n'.join(ls))
        except Exception: return None
        if isinstance(v, dict) and len(body) >= 2: return 'yaml'
    return None

def _embedded_code(lines, kinds, path):
    """A paragraph whose lines are all indented (or a prose lead-in ending in ':' followed only by
    indented lines) and whose indented part is shell or YAML becomes [prose lead-in] + code block in
    that language, lines exactly as written apart from the common indentation."""
    first = next((i for i, l in enumerate(lines) if l[:1] in (' ', '\t')), None)
    if first is None or not all(l[:1] in (' ', '\t') for l in lines[first:]): return None
    if first and (not lines[first - 1].rstrip().endswith(':') or any(k != 'text' for k in kinds[:first])): return None
    code = _dedent(lines[first:]).split('\n')
    lang = _code_lang(code)
    if not lang: return None
    R.add('classified', path=path, kind=f'embedded-code->code({lang})' + (' with prose lead-in' if first else ''), text='\n'.join(lines)[:400])
    out = [{'type': 'prose', 'text': Folded(join_lines(lines[:first], path))}] if first else []
    return out + [{'type': 'code', 'lang': lang, 'text': Literal('\n'.join(code) + '\n')}]

YAML_KEY = re.compile(r'^[a-z_][a-z0-9_]*:(\s|$)')

def _yaml_runs(t, path):
    """Chapter 5: a YAML mapping written out inside prose (often a whole subsection) spans several
    paragraphs - a key line, then indented children separated by blank lines. Split per paragraph, the
    key and its children land in separate blocks and the nesting is lost. A run of paragraphs that starts
    at an unindented snake_case key line, continues through paragraphs that are indented or start with
    such a key, and parses as one YAML mapping stays one yaml code block, verbatim (blank lines kept).
    Yields those blocks (dicts) and every other paragraph (str) in order."""
    seps = list(re.finditer(r'\n[ \t]*\n', t))
    spans, a = [], 0
    for m in seps: spans.append((a, m.start())); a = m.end()
    spans.append((a, len(t)))
    i = 0
    while i < len(spans):
        p = t[spans[i][0]:spans[i][1]]
        best = None
        if YAML_KEY.match(p):
            j = i + 1
            while True:
                chunk = t[spans[i][0]:spans[j - 1][1]]
                try: ok = isinstance(yaml.safe_load(chunk), dict)
                except Exception: ok = False
                if ok and (j - i > 1 or re.match(r'[a-z_][a-z0-9_]*:[ \t]*\n[ \t]', chunk)): best = j     # one paragraph: a bare key opening a mapping
                if j >= len(spans): break
                q = t[spans[j][0]:spans[j][1]]
                if not (q[:1] in (' ', '\t') or YAML_KEY.match(q)): break
                j += 1
        if best:
            chunk = t[spans[i][0]:spans[best - 1][1]]
            R.add('classified', path=path, kind='yaml-run->code(yaml)', text=chunk[:400])
            yield {'type': 'code', 'lang': 'yaml', 'text': Literal(chunk + '\n')}
            i = best
        else:
            yield p; i += 1

def text_to_blocks(t, path):
    """Split a v1 prose value into standard blocks, paragraph by paragraph. Prose is the default;
    line-structured paragraphs stay literal; consecutive literal paragraphs merge into one block."""
    t = fix_text_apos(t, path)
    blocks = []
    for para in _yaml_runs(t.strip('\n'), path):
        if isinstance(para, dict): blocks.append(para); continue
        if not para.strip(): continue
        ind = min(len(l) - len(l.lstrip()) for l in para.split('\n') if l.strip())
        for b in _para_to_blocks(para, path):
            if (b['type'] == 'code' and blocks and blocks[-1]['type'] == 'code' and blocks[-1]['lang'] == 'text'
                    and b['lang'] == 'text'):
                blocks[-1]['text'] = Literal(str(blocks[-1]['text']) + '\n' + str(b['text']))
            elif (b['type'] == 'code' and b['lang'] == 'yaml' and ind and blocks and blocks[-1].get('_yaml_indent') == ind):
                # chapter 5: sibling entries of one indented mapping, separated by blank lines -> one block
                R.add('classified', path=path, kind='indented-yaml-siblings-merged', text=str(b['text'])[:200])
                blocks[-1]['text'] = Literal(str(blocks[-1]['text']) + '\n' + str(b['text']))
            else:
                if b['type'] == 'code' and b['lang'] == 'yaml' and ind and _all_indented(para):
                    b['_yaml_indent'] = ind
                blocks.append(b)
    for b in blocks: b.pop('_yaml_indent', None)
    return blocks

def _all_indented(para):
    return all(l[:1] in (' ', '\t') for l in para.split('\n') if l.strip())

def join_lines(ls, path):
    """Fold wrapped lines into one paragraph. A word hyphen-wrapped across lines (first-/order)
    is rejoined without a space; a suspended hyphen before and/or is kept with a space and flagged."""
    out = ''
    for l in (x.strip() for x in ls):
        if not l: continue
        if out and re.search(r'[A-Za-z0-9]-$', out) and re.match(r'[A-Za-z0-9]', l):
            if re.match(r'(and|or|to)(\s|$)', l) and not re.search(r'-to-$|[A-Za-z]-to$', out):
                R.add('classified', path=path, kind='suspended-hyphen-kept-with-space', text=(out[-30:] + ' ' + l[:30]))
                out += ' ' + l
            else:
                R.add('hyphen_join', path=path, joined=re.search(r'\S*$', out).group(0) + l.split(' ')[0])
                out += l
        else:
            out = l if not out else out + ' ' + l
    return re.sub(r'\s+', ' ', out).strip()

def _dedent(ls):
    ind = min(len(l) - len(l.lstrip()) for l in ls if l.strip())
    return '\n'.join(l[ind:] for l in ls)

def _broken_lines(ls):
    if len(ls) < 2: return False
    width = max(len(l.rstrip()) for l in ls)
    return any(len(l.rstrip()) < 0.6 * width for l in ls[:-1])

def _list_block(ls, path):
    items, ordered = [], None; base = None
    for l in ls:
        m = BUL.match(l)
        if m and (base is None or len(m.group(1)) <= base + 1):
            base = len(m.group(1)) if base is None else base
            is_num = bool(re.match(r'\d+[.)]|[a-z][.)]', m.group(2)))
            ordered = is_num if ordered is None else ordered
            if ordered != is_num: R.add('classified', path=path, kind='mixed-list-markers', text='\n'.join(ls)[:300])
            items.append(m.group(3).strip())
        elif m:                                     # nested item
            if not items or not isinstance(items[-1], list): items.append([])
            items[-1].append(m.group(3).strip())
        else:
            tgt = items[-1] if not isinstance(items[-1], list) else None
            if tgt is None: items[-1][-1] = join_lines([items[-1][-1], l], path)
            else: items[-1] = join_lines([items[-1], l], path)
    return {'type': 'list', 'style': 'ordered' if ordered else 'bullet', 'items': items}

def prose_value(t, path):
    """A value the profile defines as prose in a single slot (descriptions, notes, summaries, fields
    values). Paragraph breaks are kept: a folded scalar with blank lines between paragraphs."""
    t = fix_text_apos(str(t), path)
    paras = [p for p in re.split(r'\n[ \t]*\n', t.strip('\n')) if p.strip()]
    for p in paras:
        if set(_para_kinds(p.split('\n'))) & {'item', 'pre', 'indent', 'cont'}:
            R.add('classified', path=path, kind='structured-text-in-single-prose-slot', text=p[:300])
    joined = [join_lines(p.split('\n'), path) for p in paras]
    if len(joined) > 1: R.add('notes', path=path, note=f'{len(joined)} paragraphs kept in one folded scalar')
    s = '\n'.join(joined)
    return Folded(s) if len(s) > 90 or '\n' in t.strip() else s

def short(t, path):
    t = str(t)
    if "''" in t: t = fix_text_apos(t, path)
    if '\n' in t.strip(): return prose_value(t, path)
    return t.strip() if t.strip() != t and not t.endswith('\n') else t.rstrip('\n')

def str_list(lst, path):
    return [short(x, f'{path}[{i}]') if isinstance(x, str) else x for i, x in enumerate(lst)]

def slot_exercises(a, path):
    """v1 assessment (chapters 16 and 17: title, description, questions, answers) -> the exercises slot,
    one item shaped like a list-shaped reference_materials item, keeping the v1 key as its id."""
    it = OrderedDict([('heading', short(a['title'], f'{path}.title')), ('id', path)])
    for k, v in a.items():
        if k == 'title': continue
        if k == 'description': it['description'] = prose_value(v, f'{path}.{k}')
        elif k in ('questions', 'answers') and isinstance(v, list): it[k] = str_list(v, f'{path}.{k}')
        else: R.add('unmapped', path=f'{path}.{k}', keys=[k]); it.setdefault('extra', OrderedDict())[k] = v
    return [it]

# ── generic resolution for keys outside named slots ──────────────────────────
def generic_part(key, val, path, level=2):
    part = OrderedDict([('heading', label(key)), ('id', str(key))])
    if isinstance(val, str):
        if key in CODE_KEYS or _looks_code(val):
            part['blocks'] = [code_block(val, path, None)]
        elif key.startswith('security_'):
            part = None; return {'callout': callout('security', label(key), val, path)}
        elif key == 'key_point':
            return {'callout': callout('note', 'Key Point', val, path)}
        else:
            part['blocks'] = text_to_blocks(val, path)
    elif isinstance(val, list) and all(isinstance(x, str) for x in val):
        part['blocks'] = [{'type': 'list', 'style': 'bullet', 'items': str_list(val, path)}]
    elif isinstance(val, dict):
        if _simple_dict(val):
            part['blocks'] = [fields_block(label(key), val, path, key=key)]
            return {'fields_only': part['blocks'][0], 'id': key}
        blocks, subs = [], []
        for k, v in val.items():
            r = generic_part(k, v, f'{path}.{k}', level + 1)
            if 'callout' in r: blocks.append(r['callout']) if not subs else subs[-1].setdefault('blocks', []).append(r['callout'])
            elif 'fields_only' in r:
                (blocks if not subs else subs[-1].setdefault('blocks', [])).append(r['fields_only'])
            else: subs.append(r['part'])
        if blocks: part['blocks'] = blocks
        if subs:
            if level >= 4: R.add('defects', path=path, issue='nesting deeper than heading level 4')
            part['parts'] = subs
    elif isinstance(val, list):
        part['blocks'] = [fields_block(_item_subject(x, i), x, f'{path}[{i}]') if isinstance(x, dict)
                          else {'type': 'prose', 'text': prose_value(str(x), path)} for i, x in enumerate(val)]
    else:
        part['blocks'] = [{'type': 'prose', 'text': str(val)}]
    return {'part': part}

def _looks_code(t):
    lines = t.strip().splitlines()
    pats = ('import ', 'from ', 'def ', 'class ', '>>> ', '$ ')
    n = sum(1 for l in lines if l.lstrip().startswith(pats))
    return n >= 3 or (len(lines) > 1 and lines[0].lstrip().startswith(('import ', '#!/')))

def _simple_dict(d):
    if not d or not all(isinstance(v, (str, int, float)) for v in d.values()): return False
    for v in d.values():
        if isinstance(v, str):
            s = v.strip('\n')
            if re.search(r'\n[ \t]*\n', s): return False
            if any(_line_kind(l) in ('item', 'pre', 'indent') for l in s.split('\n')): return False
            if '\n' in s and _broken_lines(s.split('\n')): return False
    return True

def _item_subject(x, i):
    for k in ('title', 'name', 'mistake', 'description', 'id'):
        if isinstance(x.get(k), str): return x[k]
    return f'Item {i + 1}'

def fields_block(subject, d, path, skip=(), key=None):
    entries = []
    for k, v in d.items():
        if k in skip: continue
        if isinstance(v, list):
            R.add('notes', path=f'{path}.{k}', note='fields entry value is a list (standard expects a string); kept as a list')
            v = str_list(v, f'{path}.{k}')
        entries.append({'label': label(k), 'value': prose_value(v, f'{path}.{k}') if isinstance(v, str) else v})
    b = OrderedDict([('type', 'fields'), ('subject', short(subject, path) if isinstance(subject, str) else subject)])
    if key is not None: b['id'] = str(key)
    b['entries'] = entries
    return b

def callout(variant, title, text, path):
    return {'type': 'callout', 'variant': variant, 'title': title, 'text': prose_value(text, path)}

def code_block(code, path, lang, caption=None):
    src = code
    code = fix_code_apos(code, path) if lang in (None, 'python') else code
    b = OrderedDict([('type', 'code'), ('lang', lang or ('python' if _looks_code(src) else 'text'))])
    if caption: b['caption'] = caption
    b['text'] = Literal(code)
    return b

# ── slot builders (family A: chapters 8-18) ──────────────────────────────────
def slot_overview(so, path):
    parts = []
    for k, v in so.items():
        if k in ('one_line_summary', 'title'): continue     # title (chapter 8) restates the section title -> legacy
        parts.append(generic_part(k, v, f'{path}.{k}')['part'])
    return parts

def groups(d, path):
    out = OrderedDict()
    for k, v in d.items():
        if isinstance(v, list): out[k] = str_list(v, f'{path}.{k}')
        else: out[k] = prose_value(v, f'{path}.{k}')
    return out

def slot_objectives(lo, path):
    if isinstance(lo, list): return {'groups': {'objectives': str_list(lo, path)}}
    o = OrderedDict()
    if 'primary' in lo: o['intro'] = prose_value(lo['primary'], f'{path}.primary')
    o['groups'] = groups({k: v for k, v in lo.items() if k != 'primary'}, path)
    return o

def slot_parts(pc, path):
    parts = []
    items = pc.items() if isinstance(pc, dict) else ((f'part_{x.get("part", i+1)}', x) for i, x in enumerate(pc))
    for k, v in items:
        p = OrderedDict()
        if isinstance(v, dict) and ('body' in v or 'content' in v):
            head = v.get('title') or v.get('heading')
            if v.get('title') and v.get('heading'): R.add('defects', path=f'{path}.{k}', issue='both title and heading')
            if 'number' in v: p['number'] = str(v['number'])
            p['heading'] = short(head, f'{path}.{k}.title')
            p['id'] = k
            body = v.get('body', v.get('content'))
            p['blocks'] = text_to_blocks(body, f'{path}.{k}.body')
            for kk, vv in v.items():
                if kk in ('title', 'heading', 'body', 'content', 'number', 'part'): continue
                r = generic_part(kk, vv, f'{path}.{k}.{kk}', 3)
                if 'callout' in r: p['blocks'].append(r['callout'])
                elif 'fields_only' in r: p['blocks'].append(r['fields_only'])
                else: p.setdefault('parts', []).append(r['part'])
        else:
            p = generic_part(k, v, f'{path}.{k}')
            p = p.get('part') or {'heading': label(k), 'id': k, 'blocks': [p.get('callout') or p.get('fields_only')]}
        parts.append(p)
    return parts

def list_id(prefix, x, i, key):
    """Id of an item in a list-shaped slot: prefix_N from its own number (key), else its position."""
    n = x.get(key, i + 1) if isinstance(x, dict) else i + 1
    return f'{prefix}_{n}' if str(n).isdigit() else str(n)

def _uniform_records(v):
    """A list of mappings that all have the same keys, in the same order, with scalar values: a table."""
    return (isinstance(v, list) and v and all(isinstance(r, dict) for r in v) and len({tuple(r) for r in v}) == 1
            and all(isinstance(x, (str, int, float)) and not isinstance(x, bool) for r in v for x in r.values()))

def _records_table(v, path):
    keys = list(v[0])
    return OrderedDict([('columns', [label(c) for c in keys]),
                        ('rows', [[short(r[c], path) if isinstance(r[c], str) else r[c] for c in keys] for r in v])]), keys

def _record_fields(v, path, legacy):
    """Records that do not form a table (lists in cells, keys differing between records): one fields block
    per record, its subject the first field's value; the first key is kept in legacy as subject_key."""
    firsts = [next(iter(r)) for r in v]
    if len(set(firsts)) > 1: R.add('notes', path=path, note=f'records start with different keys {sorted(set(firsts))}; subject_key kept per record')
    legacy[f'{path}.subject_key'] = firsts[0] if len(set(firsts)) == 1 else firsts
    blocks = []
    for i, r in enumerate(v):
        k0 = next(iter(r))
        blocks.append(fields_block(r[k0], r, f'{path}[{i}]', skip=(k0,)))
    return blocks

def _record_item(e, t, k, path, legacy):
    """Chapter 8: a reference item with no columns/rows - title, description and one or more named bodies.
    One body that is a uniform record list -> the item's table (column headings from the keys, which go to
    legacy as row_keys, as chapter 9 did); otherwise each body is a part headed by its key: uniform records
    -> a table block, other records -> fields blocks, anything else as generic_part resolves it."""
    body = [b for b in t if b not in ('title', 'description')]
    if len(body) == 1 and _uniform_records(t[body[0]]):
        e['table'], keys = _records_table(t[body[0]], f'{path}.{k}.{body[0]}')
        legacy[f'{path}.{k}.{body[0]}.row_keys'] = keys
        return
    parts = []
    for b in body:
        v, bp = t[b], f'{path}.{k}.{b}'
        if _uniform_records(v):
            tb, keys = _records_table(v, bp); legacy[f'{bp}.row_keys'] = keys
            parts.append(OrderedDict([('heading', label(b)), ('id', b), ('blocks', [OrderedDict([('type', 'table')] + list(tb.items()))])]))
        elif isinstance(v, list) and v and all(isinstance(r, dict) for r in v):
            parts.append(OrderedDict([('heading', label(b)), ('id', b), ('blocks', _record_fields(v, bp, legacy))]))
        else:
            r = generic_part(b, v, bp, 3)
            parts.append(r.get('part') or OrderedDict([('heading', label(b)), ('id', b), ('blocks', [r.get('callout') or r.get('fields_only')])]))
    e['parts'] = parts

def slot_tables(rm, path, legacy=None):
    out = []
    items = rm.items() if isinstance(rm, dict) else ((list_id('table', t, i, 'table'), t) for i, t in enumerate(rm))
    for k, t in items:
        e = OrderedDict([('heading', short(t['title'], f'{path}.{k}.title')), ('id', k)])
        if t.get('description'): e['description'] = prose_value(t['description'], f'{path}.{k}.description')
        if 'columns' not in t and 'rows' not in t:
            _record_item(e, t, k, path, legacy if legacy is not None else OrderedDict()); out.append(e); continue
        e['table'] = OrderedDict([('columns', [short(c, path) if isinstance(c, str) else c for c in t['columns']]),
                                  ('rows', [[short(c, path) if isinstance(c, str) else c for c in r] for r in t['rows']])])
        widths = {len(r) for r in t['rows']}
        if widths != {len(t['columns'])}:
            R.add('defects', path=f'{path}.{k}', issue=f'{len(t["columns"])} columns but row widths {sorted(widths)}; migrated as written')
        extra = set(t) - {'title', 'description', 'columns', 'rows'} - ({'table'} if not isinstance(rm, dict) else set())
        if extra: R.add('unmapped', path=f'{path}.{k}', keys=sorted(extra))
        out.append(e)
    return out

def lang_for(d):
    if d.get('language'): return str(d['language']).lower()
    fn = d.get('filename') or ''
    m = re.search(r'\.[A-Za-z0-9]+$', fn)
    if m and m.group(0).lower() in EXT_LANG: return EXT_LANG[m.group(0).lower()]
    R.add('notes', path=fn or '?', note='language not derivable from filename'); return None

def slot_deliverables(dl, path):
    out = []
    listed = not isinstance(dl, dict)
    for k, d in (dl.items() if not listed else ((list_id('deliverable', d, i, 'id'), d) for i, d in enumerate(dl))):
        fn = d.get('filename') or (d.get('name') if listed and re.search(r'\.[A-Za-z0-9]+$', str(d.get('name') or '')) else None)
        if fn and not d.get('filename'): d = dict(d, filename=fn)
        e = OrderedDict([('heading', short(d.get('title') or d.get('filename') or d.get('name'), f'{path}.{k}.title')), ('id', str(k))])
        if d.get('filename'): e['filename'] = d['filename']
        lang = lang_for(d); e['lang'] = lang
        if d.get('description'): e['description'] = prose_value(d['description'], f'{path}.{k}.description')
        elif d.get('purpose'): e['description'] = prose_value(d['purpose'], f'{path}.{k}.purpose')   # chapter 5: purpose is the description
        if d.get('implementation_notes'): e['notes'] = prose_value(d['implementation_notes'], f'{path}.{k}.implementation_notes')
        if d.get('dependencies'): e['dependencies'] = str_list(d['dependencies'], f'{path}.{k}.dependencies')
        e['code'] = Literal(fix_code_apos(d['code'], f'{path}.{k}.code') if lang == 'python' else d['code'])
        extra = set(d) - {'title', 'filename', 'language', 'description', 'implementation_notes', 'dependencies', 'code'}
        if d.get('purpose') and not d.get('description'): extra.discard('purpose')
        if listed: extra -= {'id'} | ({'name'} if d.get('name') in (d.get('filename'), d.get('title')) else set())
        for x in sorted(extra): R.add('legacy', path=f'{path}.{k}.{x}', value=d[x])
        if extra: e['legacy'] = {x: d[x] for x in d if x in extra}
        out.append(e)
    return out

def slot_mistakes(cm, path):
    out = []; sets = []
    listed = not isinstance(cm, dict)
    for k, m in (cm.items() if not listed else ((list_id('mistake', m, i, 'id'), m) for i, m in enumerate(cm))):
        cands = ('title', 'description', 'mistake', 'name', 'error')
        subj_key = next(iter(m)) if next(iter(m)) in cands else next(x for x in cands if x in m)
        e = OrderedDict([('subject', prose_value(m[subj_key], f'{path}.{k}.{subj_key}')), ('id', str(k))])
        e['entries'] = [{'label': label(f), 'value': prose_value(v, f'{path}.{k}.{f}') if isinstance(v, str)
                         else (str_list(v, f'{path}.{k}.{f}') if isinstance(v, list) else v)}
                        for f, v in m.items() if f not in (subj_key, 'id')]
        for f, v in m.items():
            if isinstance(v, list): R.add('notes', path=f'{path}.{k}.{f}', note='fields entry value is a list (standard expects a string); kept as a list')
        if 'id' in m and not listed: e['id'] = str(m['id'])
        sets.append(tuple(x['label'] for x in e['entries'])); out.append(e)
    if len(set(sets)) > 1: R.add('defects', path=path, issue=f'sibling mistakes have different field sets: {sorted(set(sets))}')
    return out

def slot_summary(ss, path):
    o = OrderedDict()
    if isinstance(ss, str): o['compact'] = prose_value(ss, path); return o
    for k, v in ss.items():
        if k in ('compact', 'one_paragraph', 'what_you_learned'):
            if 'compact' in o: R.add('defects', path=f'{path}.{k}', issue='more than one compact summary source')
            o['compact'] = prose_value(v, f'{path}.{k}')
        elif k == 'key_terms' and isinstance(v, list) and all(isinstance(x, dict) and set(x) == {'term', 'definition'} for x in v):
            o['key_terms'] = [OrderedDict([('term', short(x['term'], f'{path}.{k}[{i}].term')),
                                           ('definition', prose_value(x['definition'], f'{path}.{k}[{i}].definition'))]) for i, x in enumerate(v)]
        elif k == 'key_terms' and isinstance(v, list) and v and all(isinstance(x, str) and ':' in x for x in v):
            # chapter 13: "Term: definition" strings -> the same term/definition list, split at the first colon
            o['key_terms'] = []
            for i, x in enumerate(v):
                t, dfn = x.split(':', 1)
                R.add('classified', path=f'{path}.{k}[{i}]', kind='key-term-string-split-at-first-colon', text=x[:200])
                o['key_terms'].append(OrderedDict([('term', short(t.strip(), f'{path}.{k}[{i}].term')),
                                                   ('definition', prose_value(dfn.strip(), f'{path}.{k}[{i}].definition'))]))
        elif k == 'key_takeaways': o['key_takeaways'] = str_list(v, f'{path}.{k}') if isinstance(v, list) else groups(v, f'{path}.{k}')
        else: R.add('unmapped', path=f'{path}.{k}', keys=[k]); o.setdefault('extra', OrderedDict())[k] = v
    return o

def slot_next(key, v, path):
    m = re.match(r'preview_(section|chapter|part|next)_?(.*)$', key)
    o = OrderedDict([('kind', m.group(1) if m.group(1) != 'next' else 'section')])
    if m.group(2): o['target'] = m.group(2)
    o['title'] = short(v['title'], f'{path}.title')
    src = [x for x in ('summary', 'preview', 'teaser', 'connection') if x in v]     # connection: chapter 8
    if len(src) > 1: R.add('defects', path=path, issue=f'more than one preview text: {src}')
    o['summary'] = prose_value(v[src[0]], f'{path}.{src[0]}')
    extra = set(v) - {'title', 'summary', 'preview', 'teaser', 'connection'}
    if extra: R.add('unmapped', path=path, keys=sorted(extra))
    return o

def next_section(v, path):
    """Chapter 5: section_summary.next_section is a heading line ("Section 5.2 — Title") and a preview
    paragraph -> the next slot, title the heading line as written, target from its section number."""
    head, _, body = v.strip('\n').partition('\n')
    m = re.match(r'Section (\d+)\.(\d+)\b', head)
    o = OrderedDict([('kind', 'section')])
    if m: o['target'] = f'{int(m.group(1)):02d}_{int(m.group(2)):02d}'
    else: R.add('defects', path=path, issue='next_section heading has no section number')
    o['title'] = short(head, f'{path}.title')
    o['summary'] = prose_value(body, f'{path}.summary')
    return o

# ── family C (chapter 7: content / code_examples / exercises / cross_references) ──
def _multi_para(v):
    return isinstance(v, str) and bool(re.search(r'\n[ \t]*\n', v.strip('\n')))

def records_part(key, v, path, legacy):
    """A list of records inside content: a table when the records share one key order, hold only scalars
    and no value runs to more than one paragraph (chapter 8's rule); otherwise one fields block per record,
    subject the first field's value (subject_key in legacy)."""
    if _uniform_records(v) and not any(_multi_para(x) for r in v for x in r.values()):
        tb, keys = _records_table(v, path); legacy[f'{path}.row_keys'] = keys
        blocks = [OrderedDict([('type', 'table')] + list(tb.items()))]
    else:
        blocks = _record_fields(v, path, legacy)
    return OrderedDict([('heading', label(key)), ('id', key), ('blocks', blocks)])

def _as_part(k, v, path, level=2):
    r = generic_part(k, v, path, level)
    return r.get('part') or OrderedDict([('heading', label(k)), ('id', k), ('blocks', [r.get('callout') or r.get('fields_only')])])

def _stats_record(v):
    """A mapping of counts and one-line labels (7.15 chapter_statistics): metadata, not prose."""
    return isinstance(v, dict) and v and all(isinstance(x, (int, float)) or (isinstance(x, str) and '\n' not in x.strip()) for x in v.values())

def named_part(key, val, path, legacy):
    """A top-level mapping beside content (7.13 catalog_design): one part headed by its key, a sub-part per
    entry; numbers are counts and go to legacy. A mapping of counts only goes to legacy whole."""
    if _stats_record(val):
        for k, v in val.items(): legacy[f'{path}.{k}'] = v
        return None
    subs = []
    for k, v in val.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool): legacy[f'{path}.{k}'] = v; continue
        subs.append(_as_part(k, v, f'{path}.{k}', 3))
    return OrderedDict([('heading', label(key)), ('id', key), ('parts', subs)]) if subs else None

def _ex_value(v, path):
    if isinstance(v, str): return prose_value(v, path)
    if isinstance(v, list):
        return [OrderedDict((k, prose_value(x, f'{path}[{i}].{k}') if isinstance(x, str) else x) for k, x in r.items())
                if isinstance(r, dict) else (short(r, f'{path}[{i}]') if isinstance(r, str) else r) for i, r in enumerate(v)]
    return v

def slot_exercise_list(ex, path):
    """Chapter 7 exercises (id, title, type, description, deliverable, time_estimate, ...) -> the exercises
    slot: heading from title, the v1 id, every other key kept in v1 order. type is a block marker in the
    layout, so it is written exercise_type."""
    out = []
    for i, x in enumerate(ex):
        it = OrderedDict([('heading', short(x['title'], f'{path}[{i}].title')), ('id', str(x['id']))])
        for k, v in x.items():
            if k in ('title', 'id'): continue
            it['exercise_type' if k == 'type' else k] = _ex_value(v, f'{path}[{i}].{k}')
        out.append(it)
    return out

FAMILY_C = ('content', 'code_examples', 'exercises', 'cross_references', 'section_metadata', 'key_takeaways', 'document_info')

def family_c(d, out, legacy, handled):
    prose, overview = [], []
    for top, v in d.items():
        if top == 'content':
            for k, x in v.items():
                p = f'content.{k}'
                if k == 'opening': overview.append(generic_part(k, x, p)['part'])
                elif k == 'subsections': prose += slot_parts(x, p)
                elif k == 'common_mistakes': out['common_mistakes'] = slot_mistakes(x, p)
                elif re.fullmatch(r'chapter_\d+_preview', k) and isinstance(x, str):
                    out['next'] = OrderedDict([('kind', 'chapter'), ('target', k.split('_')[1]), ('summary', prose_value(x, p))])
                elif isinstance(x, list) and x and all(isinstance(r, dict) for r in x): prose.append(records_part(k, x, p, legacy))
                else: prose.append(_as_part(k, x, p))
        elif top == 'code_examples': out['deliverables'] = slot_deliverables(v, top)
        elif top == 'exercises': out['exercises'] = slot_exercise_list(v, top)
        elif top == 'cross_references':
            con = out.setdefault('connections', OrderedDict())
            for k, x in v.items():
                con[k] = [OrderedDict((kk, short(vv, f'{top}.{k}') if isinstance(vv, str) else vv) for kk, vv in r.items())
                          if isinstance(r, dict) else short(r, f'{top}.{k}') for r in x] if isinstance(x, list) else x
        elif top == 'section_metadata':
            for k, x in v.items(): legacy[f'{top}.{k}'] = x       # counts, file lists, status: metadata
        elif top in FAMILY_C: continue
        elif isinstance(v, dict):
            np_ = named_part(top, v, top, legacy)
            if np_: prose.append(np_)
        else: continue
        handled.add(top)
    if overview: out['overview'] = out.get('overview', []) + overview
    if prose: out['prose_content'] = prose

# ── top level ────────────────────────────────────────────────────────────────
SECTION_INFO_KEYS = ['chapter', 'section', 'section_code', 'part', 'created', 'estimated_pages',
                     'estimated_reading_time', 'license', 'github', 'book']

def convert(src_path):
    docs = [d for d in yaml.safe_load_all(open(src_path)) if d is not None]
    if len(docs) != 1: raise SystemExit(f'{src_path}: {len(docs)} non-empty documents')
    d = docs[0]; di = d.get('document_info', {})
    fm = re.match(r'.*section_(\d+)_(\d+)', src_path)
    out = OrderedDict()
    out['title'] = short(di['title'], 'document_info.title')
    out['updated'] = datetime.date.fromisoformat(str(di['created']))
    if 'version' in di: out['version'] = str(di['version'])
    out['authors'] = [di['author']]
    tags = list(di.get('tags') or []) + list((d.get('metadata') or {}).get('tags') or [])
    if tags: out['tags'] = list(OrderedDict.fromkeys(tags))
    si = OrderedDict(); legacy = OrderedDict()
    for k in SECTION_INFO_KEYS:
        if k not in di: continue
        v = di[k]
        if k in ('chapter', 'section'):
            n = int(str(v).split('.')[-1])
            if str(v) != str(n): legacy[f'document_info.{k}'] = v
            v = n
        si['repository' if k == 'github' else k] = v
    for k in di:
        if k == 'prerequisites' and isinstance(di[k], list) and 'prerequisites' not in d:     # chapter 7
            out['prerequisites'] = str_list(di[k], 'document_info.prerequisites'); continue
        if k == 'leads_to' and isinstance(di[k], list):                                     # chapter 7
            out.setdefault('connections', OrderedDict())['leads_to'] = str_list(di[k], 'document_info.leads_to'); continue
        if k.endswith('_note') and isinstance(di[k], str) and len(di[k].split()) > 12:          # chapter 5 (5.7): a note to the reader
            out.setdefault('overview', []).append(_as_part(k, di[k], f'document_info.{k}')); continue
        if k not in SECTION_INFO_KEYS + ['title', 'version', 'author', 'tags']:
            legacy[f'document_info.{k}'] = di[k]
    out['section_info'] = si
    so = d.get('section_overview') or {}
    if 'title' in so: legacy['section_overview.title'] = so['title']
    if so.get('one_line_summary'): out['lead'] = prose_value(so['one_line_summary'], 'section_overview.one_line_summary')
    if so: ov = slot_overview(so, 'section_overview'); ov and out.__setitem__('overview', ov + out.get('overview', []))
    if 'learning_objectives' in d: out['learning_objectives'] = slot_objectives(d['learning_objectives'], 'learning_objectives')
    if 'prerequisites' in d:
        p = d['prerequisites']; out['prerequisites'] = str_list(p, 'prerequisites') if isinstance(p, list) else {'groups': groups(p, 'prerequisites')}
    handled = {'document_info', 'section_overview', 'learning_objectives', 'prerequisites'}
    if isinstance(d.get('content'), dict) and 'code_examples' in d: family_c(d, out, legacy, handled)   # chapter 7
    summary_extra = OrderedDict()
    if 'prose_content' in d: out['prose_content'] = slot_parts(d['prose_content'], 'prose_content'); handled.add('prose_content')
    if 'section_content' in d:                      # chapters 1-2 (free-form) and 5-6 (subsection_N)
        sc = d['section_content']; handled.add('section_content')
        if all(k.startswith('subsection_') for k in sc):
            out['prose_content'] = slot_parts(sc, 'section_content')
        else:
            ov, parts = [], []
            for k, v in sc.items():
                path = f'section_content.{k}'
                if k in ('overview', 'why_this_matters'): ov.append(generic_part(k, v, path)['part'])
                elif k == 'learning_objectives': out['learning_objectives'] = slot_objectives(v, path)
                elif k == 'prerequisites': out['prerequisites'] = str_list(v, path) if isinstance(v, list) else {'groups': groups(v, path)}
                elif k == 'key_takeaways': summary_extra['key_takeaways'] = str_list(v, path) if isinstance(v, list) else groups(v, path)
                elif k == 'common_mistakes': out['common_mistakes'] = slot_mistakes(v, path)
                else:
                    r = generic_part(k, v, path)
                    parts.append(r.get('part') or OrderedDict([('heading', label(k)), ('id', k), ('blocks', [r.get('callout') or r.get('fields_only')])]))
            if ov: out['overview'] = out.get('overview', []) + ov
            if parts: out['prose_content'] = parts
        # keep slot order stable
        for k in ('learning_objectives', 'prerequisites'):
            if k in out: out.move_to_end(k); 
        for k in ('overview',):
            pass
    if 'reference_materials' in d: out['reference_materials'] = slot_tables(d['reference_materials'], 'reference_materials', legacy); handled.add('reference_materials')
    if 'implementations' in d:
        out['deliverables'] = slot_deliverables(d['implementations'], 'implementations'); handled.add('implementations')
    if 'deliverables' in d:
        dl = d['deliverables']; handled.add('deliverables')
        if isinstance(dl, dict) and 'items' in dl:   # chapters 5-6: produced outputs, not code
            # chapter 6: an item's own id (D01 ...) is the block id, not a fields entry
            out['artifacts'] = [fields_block(x.get('title', x.get('id')), x, f'deliverables.items[{i}]',
                                             skip=('title', 'id') if isinstance(x.get('id'), str) else ('title',),
                                             key=x['id'] if isinstance(x.get('id'), str) else None) for i, x in enumerate(dl['items'])]
            for kk in dl:
                if kk != 'items': out['section_info'].setdefault('legacy', OrderedDict())[f'deliverables.{kk}'] = dl[kk]
        elif isinstance(dl, dict) and dl and all(isinstance(x, dict) and 'code' not in x and 'artifact' in x for x in dl.values()):
            # chapter 8: deliverables that describe an artifact (artifact, purpose, format/inputs/outputs ...)
            # and carry no code -> artifacts, one fields block per item, subject the artifact, id the v1 key
            out['artifacts'] = [fields_block(x['artifact'], x, f'deliverables.{kk}', skip=('artifact',), key=kk) for kk, x in dl.items()]
        elif isinstance(dl, dict) and dl and all(isinstance(x, dict) and 'code' not in x and 'title' in x for x in dl.values()):
            # chapter 5: deliverable_NN records naming produced outputs (title, files/file/content, format,
            # generated_by, completion_criteria) with no code -> artifacts, subject the title, id the v1 key
            out['artifacts'] = [fields_block(x['title'], x, f'deliverables.{kk}', skip=('title',), key=kk) for kk, x in dl.items()]
        else:
            out['deliverables'] = slot_deliverables(dl, 'deliverables')
    if 'assessment' in d: out['exercises'] = slot_exercises(d['assessment'], 'assessment'); handled.add('assessment')
    if 'common_mistakes' in d: out['common_mistakes'] = slot_mistakes(d['common_mistakes'], 'common_mistakes'); handled.add('common_mistakes')
    if 'section_summary' in d:
        ss = d['section_summary']; handled.add('section_summary')
        if isinstance(ss, dict) and isinstance(ss.get('next_section'), str):
            out['next'] = next_section(ss['next_section'], 'section_summary.next_section')
            ss = OrderedDict((k, v) for k, v in ss.items() if k != 'next_section')
        if ss: out['section_summary'] = slot_summary(ss, 'section_summary')
    if 'key_takeaways' in d:
        kt = d['key_takeaways']; handled.add('key_takeaways')
        if isinstance(kt, dict) and 'items' in kt:
            nums = [x.get('number') for x in kt['items']]
            if nums != list(range(1, len(nums) + 1)): R.add('defects', path='key_takeaways.items', issue=f'numbers not 1..n: {nums}')
            summary_extra['key_takeaways'] = {'style': 'ordered', 'items': [prose_value(x['takeaway'], f'key_takeaways.items[{i}].takeaway') for i, x in enumerate(kt['items'])]}
            for kk in kt:
                if kk != 'items': out['section_info'].setdefault('legacy', OrderedDict())[f'key_takeaways.{kk}'] = kt[kk]
        elif isinstance(kt, dict) and kt and all(re.fullmatch(r'takeaway_\d+', k) and isinstance(v, str) for k, v in kt.items()):
            # chapter 5: takeaway_01..takeaway_NN strings -> an ordered list (the keys are the positions)
            nums = [int(k.split('_')[1]) for k in kt]
            if nums != list(range(1, len(nums) + 1)): R.add('defects', path='key_takeaways', issue=f'numbers not 1..n: {nums}')
            summary_extra['key_takeaways'] = {'style': 'ordered', 'items': [prose_value(v, f'key_takeaways.{k}') for k, v in kt.items()]}
        else:
            summary_extra['key_takeaways'] = str_list(kt, 'key_takeaways') if isinstance(kt, list) else groups(kt, 'key_takeaways')
    if summary_extra:
        ss = out.setdefault('section_summary', OrderedDict())
        for k, v in summary_extra.items():
            if k in ss: R.add('defects', path=k, issue='key_takeaways present twice')
            ss[k] = v
    if 'connections' in d:
        handled.add('connections')
        con = out.setdefault('connections', OrderedDict())
        for k, v in d['connections'].items():
            if isinstance(v, str):
                con[k] = callout('security', label(k), v, f'connections.{k}') if k.startswith('security_') else prose_value(v, f'connections.{k}')
            elif isinstance(v, list): con[k] = [short(x, f'connections.{k}') if isinstance(x, str) else
                                                OrderedDict((kk, short(vv, f'connections.{k}') if isinstance(vv, str) else vv) for kk, vv in x.items()) for x in v]
            else: con[k] = v
    for k in d:
        if k.startswith('preview_'):
            if 'next' in out: R.add('defects', path=k, issue='more than one preview key')
            out['next'] = slot_next(k, d[k], k); handled.add(k)
    if 'metadata' in d:
        md = d['metadata']; handled.add('metadata')
        for k, v in md.items():
            if k == 'tags': continue
            if isinstance(v, (list, dict)): out.setdefault('connections', OrderedDict())[k] = str_list(v, f'metadata.{k}') if isinstance(v, list) else v
            else: legacy[f'metadata.{k}'] = v           # counts, ids, numbers: metadata, not connections
    for k in d:                                     # chapter 5 (5.15): a closing note beside section_content
        if k not in handled and isinstance(d[k], str) and 'section_content' in d and len(d[k].split()) > 12:
            out.setdefault('prose_content', []).append(_as_part(k, d[k], k)); handled.add(k)
    for k in d:
        if k not in handled: R.add('unmapped', path=k, keys=[k], note='no slot yet for this family')
    if legacy: out['section_info'].setdefault('legacy', OrderedDict()).update(legacy)
    ORDER = ['title','updated','version','authors','tags','section_info','lead','overview','learning_objectives',
             'prerequisites','prose_content','reference_materials','deliverables','artifacts','exercises',
             'common_mistakes','section_summary','next','connections']
    out = OrderedDict((k, out[k]) for k in ORDER if k in out)
    if 'section_summary' in out and isinstance(out['section_summary'], dict):
        ss = out['section_summary']; out['section_summary'] = OrderedDict((k, ss[k]) for k in ['compact', 'key_takeaways', 'key_terms', 'extra'] if k in ss)
    for k, v in legacy.items(): R.add('legacy', path=k, value=v)
    return out

def collisions(obj, path=''):
    pats = {'subscript': r'~[^~\s][^~\n]*?~', 'superscript': r'\^[^\^\s][^\^\n]*?\^', 'math': r'\$[^$\n]+?\$',
            'highlight': r'==[^=\n]+?==', 'italic': r'(?<![\*\w])\*(?=\S)[^*\n]+?(?<=\S)\*(?!\*)', 'keyboard': r'\[\[[^\]]+\]\]'}
    if isinstance(obj, dict):
        if obj.get('type') == 'code' or isinstance(obj.get('code'), Literal):
            obj = {k: v for k, v in obj.items() if k not in ('text', 'code')}
        for k, v in obj.items(): collisions(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj): collisions(v, f'{path}[{i}]')
    elif isinstance(obj, str) and not isinstance(obj, Literal):
        for name, p in pats.items():
            for m in re.finditer(p, obj):
                R.add('inline_collisions', path=path, kind=name, span=m.group(0), context=obj[max(0, m.start()-30):m.end()+30])

if __name__ == '__main__':
    src, dst, rep = sys.argv[1:4]
    out = convert(src)
    collisions(out)
    header = open(src).read().split('\n', 1)[0]
    text = (header + '\n\n---\n' if header.startswith('#') else '---\n') + emit(out)
    back = yaml.safe_load(text)
    if back != plain(out):
        import pprint
        def diff(a, b, p=''):
            if type(a) != type(b) and not (isinstance(a, str) and isinstance(b, str)): print('TYPE', p, type(a), type(b)); return
            if isinstance(a, dict):
                for k in set(a) | set(b): diff(a.get(k), b.get(k), f'{p}.{k}')
            elif isinstance(a, list):
                if len(a) != len(b): print('LEN', p); return
                for i, (x, y) in enumerate(zip(a, b)): diff(x, y, f'{p}[{i}]')
            elif a != b: print('VAL', p, repr(a)[:200], '|', repr(b)[:200])
        diff(back, plain(out)); raise SystemExit('round-trip mismatch')
    open(dst, 'w').write(text)
    json.dump(R.items, open(rep, 'w'), indent=1, default=str)
    print(src.split('/')[-1], '->', {k: len(v) for k, v in R.items.items() if v})
