"""Edit prose in a v2 section file: replace a phrase inside a folded scalar paragraph (re-wrapped
with the emitter's own _wrap at the block's indentation) or, failing that, on a single line.
Usage from Python: sub(path, old, new, n=1). old must occur once (n identical single lines with n).
Used for chapter 17's content and deliverable-note commits; re-wrapping an unchanged block reproduces it."""
import re, sys, yaml
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from emit import _wrap, WIDTH


def _blocks(lines):
    """Yield (start, end, indent) of each folded scalar's content lines (end exclusive)."""
    i = 0
    while i < len(lines):
        if re.search(r'(:|^\s*-)\s*>$', lines[i].rstrip()) or re.search(r': >$', lines[i].rstrip()):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines):
                break
            ind = len(lines[j]) - len(lines[j].lstrip())
            k = j
            while k < len(lines) and (not lines[k].strip() or len(lines[k]) - len(lines[k].lstrip()) >= ind):
                k += 1
            while k > j and not lines[k - 1].strip():
                k -= 1
            yield j, k, ind
            i = k
        else:
            i += 1


def sub(path, old, new, n=1):
    lines = open(path).read().split('\n')
    hits = []
    for s, e, ind in _blocks(lines):
        paras, cur = [], []
        for l in lines[s:e]:
            if l.strip():
                cur.append(l.strip())
            else:
                paras.append(cur); cur = []
        paras.append(cur)
        texts = [' '.join(p) for p in paras]
        for pi, t in enumerate(texts):
            if old in t:
                hits.append((s, e, ind, texts, pi))
    if len(hits) > 1 or (hits and sum(t.count(old) for t in hits[0][3]) > 1):
        raise SystemExit(f'ambiguous: {old[:60]!r} in {path}')
    if hits:
        s, e, ind, texts, pi = hits[0]
        texts[pi] = texts[pi].replace(old, new)
        out = []
        for t in texts:
            if out:
                out.append('')
            out += [' ' * ind + l for l in _wrap(t, max(40, WIDTH - ind))]
        lines[s:e] = out
    else:
        idx = [i for i, l in enumerate(lines) if old in l]
        if len(idx) != n:
            raise SystemExit(f'{len(idx)} line hits for {old[:60]!r} in {path}')
        for i in idx:
            lines[i] = lines[i].replace(old, new)
    text = '\n'.join(lines)
    yaml.safe_load(text)
    open(path, 'w').write(text)
