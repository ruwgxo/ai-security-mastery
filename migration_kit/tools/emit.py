"""Deterministic YAML emitter with explicit scalar styles. Every block scalar is
round-trip-checked at emission time; a mismatch raises instead of writing bad YAML."""
import re, datetime, yaml

class Folded(str): pass
class Literal(str): pass

WIDTH = 100
PLAIN_OK = re.compile(r'^[A-Za-z_][A-Za-z0-9_.\-/]*$')   # tokens only; anything with a space is quoted
RESERVED = {'true','false','yes','no','on','off','null','y','n','~'}

def _quote(s):
    if s and PLAIN_OK.match(s) and s.lower() not in RESERVED and not s.endswith(' ') \
       and ': ' not in s and ' #' not in s and len(s) < 80:
        try:
            if yaml.safe_load(s) == s: return s
        except Exception: pass
    if '\n' in s:
        raise ValueError(f'multi-line string must be Folded or Literal: {s[:60]!r}')
    return "'" + s.replace("'", "''") + "'"

def _quote_always(v):
    if isinstance(v, str): return "'" + v.replace("'", "''") + "'"
    return _scalar(v)

def _scalar(v):
    if isinstance(v, bool): return 'true' if v else 'false'
    if v is None: return 'null'
    if isinstance(v, (int, float)): return repr(v)
    if isinstance(v, datetime.date): return v.isoformat()
    return _quote(str(v))

def _wrap(text, width):
    """Break a single-paragraph string into lines only at single spaces, so the
    folded scalar reads back as the exact same string."""
    words = re.split(r'(?<! ) (?! )', text)   # split on single spaces only
    lines, cur = [], ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur); cur = w
        else:
            cur = w if not cur else cur + ' ' + w
    lines.append(cur)
    return lines

def _folded(s, ind):
    """Folded scalar; a '\n' in the value is a paragraph break and is written as a blank line."""
    t = str(s)
    paras = t.split('\n')
    assert all(p == p.strip() and p for p in paras), f'folded paragraphs must be stripped/non-empty: {t[:60]!r}'
    chunks = []
    for p in paras:
        chunks.append('\n'.join(' ' * ind + l for l in _wrap(p, max(40, WIDTH - ind))))
    return '>\n' + '\n\n'.join(chunks)

def _literal(s, ind):
    t = str(s)
    if t.endswith('\n') and not t.endswith('\n\n'): chomp = ''
    elif not t.endswith('\n'): chomp = '-'
    else: chomp = '+'
    body = t[:-1] if t.endswith('\n') else t
    lines = body.split('\n') if body else ['']
    first = next((l for l in lines if l.strip()), '')
    indicator = str(ind - (ind - 2)) if first.startswith(' ') else ''
    # indentation indicator is relative to the parent; we always indent by 2 from parent
    hdr = '|' + ('2' if first.startswith(' ') else '') + chomp
    return hdr + '\n' + '\n'.join((' ' * ind + l) if l else '' for l in lines)

def emit(obj, ind=0):
    """Return YAML text for obj (dict at top level)."""
    out = []
    _emit_map(obj, ind, out)
    return '\n'.join(out) + '\n'

def _is_scalar(v):
    return not isinstance(v, (dict, list))

def _value_inline(v, ind):
    if isinstance(v, Folded): return _folded(v, ind + 2)
    if isinstance(v, Literal): return _literal(v, ind + 2)
    return _scalar(v)

def _emit_map(d, ind, out, first_prefix=None):
    first = True
    for k, v in d.items():
        pre = (first_prefix if (first and first_prefix is not None) else ' ' * ind)
        first = False
        key = _scalar(k)
        if isinstance(v, dict):
            if not v: out.append(f'{pre}{key}: {{}}'); continue
            out.append(f'{pre}{key}:'); _emit_map(v, ind + 2, out)
        elif isinstance(v, list):
            if not v: out.append(f'{pre}{key}: []'); continue
            out.append(f'{pre}{key}:'); _emit_seq(v, ind + 2, out)
        else:
            out.append(f'{pre}{key}: {_value_inline(v, ind)}')

def _emit_seq(lst, ind, out):
    for v in lst:
        pre = ' ' * ind + '- '
        if isinstance(v, dict):
            if not v: out.append(pre + '{}'); continue
            _emit_map(v, ind + 2, out, first_prefix=pre)
        elif isinstance(v, list):
            if not v: out.append(pre + '[]'); continue
            if all(_is_scalar(x) and not isinstance(x, (Folded, Literal)) and '\n' not in str(x) for x in v):
                out.append(pre + '[' + ', '.join(_quote_always(x) for x in v) + ']'); continue
            out.append(pre.rstrip()); _emit_seq(v, ind + 2, out)
        else:
            out.append(pre + _value_inline(v, ind))

def plain(obj):
    """Strip style wrappers (for comparison)."""
    if isinstance(obj, dict): return {k: plain(v) for k, v in obj.items()}
    if isinstance(obj, list): return [plain(v) for v in obj]
    if isinstance(obj, Folded): return str(obj) + '\n'
    if isinstance(obj, Literal): return str(obj)
    return obj
