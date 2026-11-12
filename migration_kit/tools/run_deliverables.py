"""Extract a chapter's code deliverables from a set of section files and run each one.
Usage: run_deliverables.py OUTDIR SECTION.yaml... ; writes OUTDIR/results.json"""
import sys, os, json, yaml, glob, hashlib, subprocess, concurrent.futures as cf, time
out, files = sys.argv[1], sys.argv[2:]
os.makedirs(out, exist_ok=True)
PY = os.environ.get('PYTHON') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'venv', 'bin', 'python')  # set PYTHON to the interpreter with torch
jobs = []; seen = set()
for f in files:
    d = yaml.safe_load(open(f))
    dl = d['deliverables']
    items = dl.values() if isinstance(dl, dict) else dl
    for x in items:
        fn = x.get('filename') or x['name']          # v1 list-shaped deliverables (9.13, 12.18) use name
        if fn in seen:                               # same filename in two sections (14.01 and 14.12): the later one
            fn = os.path.join(os.path.splitext(os.path.basename(f))[0], fn)   # runs from its own subfolder
            os.makedirs(os.path.join(out, os.path.dirname(fn)), exist_ok=True)
        seen.add(fn)
        open(os.path.join(out, fn), 'w').write(x['code'])
        jobs.append((os.path.basename(f), fn))
before = {n for n in os.listdir(out)}
def run(job):
    sec, fn = job
    env = dict(os.environ, MPLBACKEND='Agg', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONHASHSEED='0',
               PYTHONPATH=os.path.abspath(out))     # a subfolder deliverable still imports its flat siblings
    t = time.time()
    try:
        r = subprocess.run([PY, os.path.basename(fn)], cwd=os.path.join(out, os.path.dirname(fn)), capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL, env=env)
        return dict(section=sec, file=fn, rc=r.returncode, stdout=r.stdout, stderr=r.stderr, secs=round(time.time() - t, 1))
    except subprocess.TimeoutExpired as e:
        return dict(section=sec, file=fn, rc='timeout', stdout=(e.stdout or b'').decode() if isinstance(e.stdout, bytes) else (e.stdout or ''), stderr='', secs=900)
with cf.ThreadPoolExecutor(max_workers=int(os.environ.get('JOBS', '6'))) as ex:
    res = list(ex.map(run, jobs))
after = {}
for n in sorted(os.listdir(out)):
    p = os.path.join(out, n)
    if os.path.isfile(p) and n != 'results.json' and n not in before:
        after[n] = hashlib.sha256(open(p, 'rb').read()).hexdigest()
json.dump({'runs': res, 'created_files': after}, open(os.path.join(out, 'results.json'), 'w'), indent=1)
print(len(res), 'runs;', sum(1 for r in res if r['rc'] == 0), 'exit 0;', len(after), 'files created')
