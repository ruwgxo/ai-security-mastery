"""Carry YAML comments (outside scalars) from a v1 file into its converted output: each comment
block is placed before the same key it preceded in v1, at the same indentation."""
import re, yaml
def comment_blocks(src):
    spans = set()
    def w(n):
        if isinstance(n, yaml.MappingNode):
            for k, v in n.value: w(k); w(v)
        elif isinstance(n, yaml.SequenceNode):
            for v in n.value: w(v)
        elif isinstance(n, yaml.ScalarNode): spans.update(range(n.start_mark.line + 1, n.end_mark.line))
    for d in yaml.compose_all(src):
        if d: w(d)
    lines = src.split('\n'); blocks = []; cur = []
    for i, l in enumerate(lines):
        if i in spans: cur = []; continue
        s = l.strip()
        if s.startswith('#'): cur.append(l.rstrip()); continue
        if not s: continue
        if s == '---': continue
        m = re.match(r'^(\s*)([A-Za-z0-9_]+):', l)
        if cur and m: blocks.append((m.group(1), m.group(2), cur))
        cur = []
    return blocks
def apply(src, out, skip_first_header=True, rename=None):
    rename = rename or {}
    blocks = comment_blocks(src)
    if skip_first_header and blocks and blocks[0][2][:1] and src.startswith(blocks[0][2][0]):
        first = blocks[0][2][1:]
        blocks = ([(blocks[0][0], blocks[0][1], first)] if first else []) + blocks[1:]
    lines = out.split('\n'); pos = 0; placed = 0; missing = []
    for ind, key, com in blocks:
        key = rename.get(key, key)
        pat = re.compile(r'^' + re.escape(ind) + re.escape(key) + r':')
        for j in range(pos, len(lines)):
            if pat.match(lines[j]):
                ins = ([''] if j > 0 and lines[j - 1].strip() else []) + com
                lines[j:j] = ins; pos = j + len(ins) + 1; placed += len(com); break
        else: missing.append((key, com))
    return '\n'.join(lines), placed, missing
