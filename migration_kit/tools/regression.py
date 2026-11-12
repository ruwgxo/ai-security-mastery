"""Regression check: the converter must still turn every reference chapter's v1 files into exactly
the output its migration used (regression/chNN_v1 -> regression/chNN_expected; chapters 10 to 16).
Run after every converter change, before converting a new chapter. Usage (from the bundle root):
python3 tools/regression.py"""
import os, sys, glob, subprocess, tempfile, filecmp
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, 'tools')
out = tempfile.mkdtemp()
bad = []; total = 0; chapters = []
for V1 in sorted(glob.glob(os.path.join(ROOT, 'regression', 'ch*_v1'))):
    ch = os.path.basename(V1)[:-3]; EXP = os.path.join(ROOT, 'regression', ch + '_expected'); chapters.append(ch)
    for src in sorted(glob.glob(os.path.join(V1, '*.yaml'))):
        name = os.path.basename(src); total += 1
        tool = 'convert_index.py' if name.startswith('chapter_') else 'convert.py'
        dst = os.path.join(out, name)
        r = subprocess.run([sys.executable, tool, src, dst, dst + '.json'], cwd=TOOLS, capture_output=True, text=True)
        if r.returncode or not filecmp.cmp(dst, os.path.join(EXP, name), shallow=False):
            bad.append(name + ('' if not r.returncode else ' (converter error: ' + r.stderr.strip().split('\n')[-1] + ')'))
if bad:
    print(f'REGRESSION: {len(bad)} of {total} files changed:'); [print('  ', b) for b in bad]; sys.exit(1)
print(f'OK: all {total} files ({", ".join(chapters)}) reproduce byte for byte')
