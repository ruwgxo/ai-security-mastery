"""Write edited deliverable code back into section YAMLs, replacing only the literal code block (added for chapter 13).
Usage: writeback.py FIXDIR SECTION.yaml...   (FIXDIR holds <filename>.py for each edited deliverable)
Afterwards checks that nothing but deliverables[].code changed, and that the code equals the file."""
import sys, os, copy, yaml

fixdir, files = sys.argv[1], sys.argv[2:]
for f in files:
    text = open(f).read()
    before = yaml.safe_load(text)
    lines = text.split('\n')
    changed = []
    for d in before.get('deliverables') or []:
        fn = d.get('filename')
        p = os.path.join(fixdir, fn or '')
        if not fn or not os.path.exists(p): continue
        new = open(p).read().rstrip('\n') + '\n'
        if new == d['code']: continue
        i = lines.index(f'    filename: {fn}')
        j = next(k for k in range(i, len(lines)) if lines[k] == '    code: |')
        k = j + 1
        while k < len(lines) and (lines[k] == '' or lines[k].startswith('      ')): k += 1
        while lines[k - 1] == '': k -= 1                    # keep the blank line(s) before the next key
        lines[j + 1:k] = [('      ' + l) if l else '' for l in new.rstrip('\n').split('\n')]
        changed.append(fn)
    if not changed: continue
    out = '\n'.join(lines)
    after = yaml.safe_load(out)
    a, b = copy.deepcopy(before), copy.deepcopy(after)
    for x in a['deliverables']: x.pop('code')
    for x in b['deliverables']: x.pop('code')
    assert a == b, f'{f}: something other than deliverables[].code changed'
    for x in after['deliverables']:
        if x.get('filename') in changed:
            assert x['code'] == open(os.path.join(fixdir, x['filename'])).read().rstrip('\n') + '\n', x['filename']
    open(f, 'w').write(out)
    print(os.path.basename(f), 'code replaced:', changed)
