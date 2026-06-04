#!/usr/bin/env python3
"""build_site_v2.py — AI Security Mastery book site generator
Run from repo root: python3 build_site_v2.py
Outputs docs/index.html — enable GitHub Pages on /docs folder.
"""

import glob, json, re, yaml
from pathlib import Path
from html import escape

BOOK_DIR = Path('book')
OUT_DIR  = Path('docs')

# ── YAML loader ───────────────────────────────────────────────────────────────

def load_yaml(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        raw = f.read()
    try:
        docs = list(yaml.safe_load_all(raw))
        merged = {}
        for d in docs:
            if isinstance(d, dict):
                merged.update(d)
        return merged
    except Exception:
        return {}

# ── Content extraction ────────────────────────────────────────────────────────

SKIP_KEYS = {
    'document_info','version','author','github','license','created','chapter',
    'section','part','book','filename','status','language','estimated_pages',
    'reading_time','estimated_reading_time','section_id','notebook','tags',
    'dependencies','requirements','deliverable_files','word_count_estimate',
    'code_line_count','exercise_count','schema_version','establishes_section_schema',
    'url','arxiv','source','delivery','book_version','estimated_word_count',
    'section_file','format','schema','section_metadata','cross_references',
    'connections','reference_materials','external_references','forward','backward',
    'exercises','deliverables','prerequisites','leads_to','metadata',
    'preview_section_02','preview_section_03',
}

# Keys whose *parent heading* we suppress (too obvious / redundant)
SUPPRESS_HEADING = {
    'section_content','document_info','section_overview','learning_objectives',
    'section_summary','prose_content','content',
}

CODE_KEYS = {
    'code','numpy_implementation','numpy_example','implementation','complete_feature_extractor',
    'python_example','example_code','numpy_code','handle_missing','solution_code',
    'script','implementation_code',
}

def is_code_text(text):
    if not isinstance(text, str): return False
    lines = text.strip().splitlines()
    if not lines: return False
    code_patterns = ('import ','from ','def ','class ','# ','>>> ','$ ')
    code_line_count = sum(1 for l in lines if any(l.lstrip().startswith(p) for p in code_patterns)
                         or l.startswith('    ') or l.startswith('\t'))
    return code_line_count >= 3 or (len(lines) > 1 and lines[0].lstrip().startswith('import '))

def nice_label(key):
    key = str(key)
    stop = {'a','an','the','and','or','of','in','on','at','to','for','vs','via'}
    words = key.replace('_',' ').split()
    return ' '.join(w.capitalize() if i==0 or w not in stop else w
                    for i,w in enumerate(words))

def extract(d, depth=0, parent_key=''):
    """Walk any YAML node → flat list of dicts with type/text/level."""
    if depth > 14:
        return []
    out = []

    if isinstance(d, str):
        text = d.strip()
        if isinstance(text, str) and len(text) >= 50:
            out.append({'type': 'code' if is_code_text(text) else 'prose',
                        'text': text, 'level': depth})
        return out

    if isinstance(d, list):
        bullets = []
        for item in d:
            if isinstance(item, str) and item.strip():
                bullets.append(item.strip())
            elif isinstance(item, dict):
                # Subsection-as-list-item (Ch7 schema)
                num   = item.get('number','')
                title = item.get('title', item.get('name',''))
                body  = item.get('body', item.get('content', item.get('text','')))
                subs  = item.get('subsections', [])
                if body and isinstance(body, str) and len(body) > 40:
                    label = f'{num} {title}'.strip() if title else ''
                    if label:
                        out.append({'type':'subheading','text':label,'level':depth})
                    out.append({'type': 'code' if is_code_text(body) else 'prose',
                                'text': body.strip(), 'level': depth})
                if subs:
                    out.extend(extract(subs, depth+1))
                if not body and not subs:
                    for v in item.values():
                        if isinstance(v, str) and len(v.strip()) > 10:
                            bullets.append(v.strip())
        if bullets:
            out.append({'type':'list','text':bullets,'level':depth})
        return out

    if isinstance(d, dict):
        for k, v in d.items():
            if k in SKIP_KEYS:
                continue
            is_code_k = k in CODE_KEYS
            suppress   = k in SUPPRESS_HEADING or depth == 0

            if isinstance(v, str):
                text = v.strip()
                if not isinstance(text, str) or len(text) < 40:
                    continue
                if not suppress:
                    out.append({'type':'subheading','text':nice_label(k),'level':depth})
                out.append({'type': 'code' if (is_code_k or is_code_text(text)) else 'prose',
                            'text': text, 'level': depth})

            elif isinstance(v, list):
                sub = extract(v, depth+1, k)
                if sub:
                    if not suppress and any(s['type'] in ('prose','code') for s in sub):
                        out.append({'type':'subheading','text':nice_label(k),'level':depth})
                    out.extend(sub)
                else:
                    strs = [str(i).strip() for i in v
                            if isinstance(i,str) and str(i).strip() and len(str(i).strip())>5]
                    if strs:
                        if not suppress:
                            out.append({'type':'subheading','text':nice_label(k),'level':depth})
                        out.append({'type':'list','text':strs,'level':depth})

            elif isinstance(v, dict):
                sub = extract(v, depth+1, k)
                if sub:
                    if not suppress:
                        out.append({'type':'subheading','text':nice_label(k),'level':depth})
                    out.extend(sub)

    return out

# ── Section renderer ──────────────────────────────────────────────────────────

def get(doc, *keys, default=''):
    for k in keys:
        for dk, dv in doc.items():
            if dk == k or dk.endswith('.'+k):
                if isinstance(dv, str) and dv.strip():
                    return dv.strip()
    # Try nested
    def _dig(d, target):
        if not isinstance(d, dict): return ''
        if target in d and isinstance(d[target], str): return d[target].strip()
        for v in d.values():
            r = _dig(v, target)
            if r: return r
        return ''
    for k in keys:
        r = _dig(doc, k)
        if r: return r
    return default

def get_list(doc, *keys):
    def _dig(d, target):
        if not isinstance(d, dict): return []
        if target in d and isinstance(d[target], list): return d[target]
        for v in d.values():
            r = _dig(v, target)
            if r: return r
        return []
    for k in keys:
        r = _dig(doc, k)
        if r: return [str(i).strip() for i in r if isinstance(i,str) and str(i).strip()]
    return []

def render_section(path):
    doc  = load_yaml(path)
    info = doc.get('document_info', {})
    m    = re.match(r'section_(\d+)_(\d+)', path.stem)
    ch_n = info.get('chapter', m.group(1) if m else '?')
    sec_n = info.get('section', m.group(2) if m else '?')
    try: ch_n = int(str(ch_n)); sec_n = int(str(sec_n).lstrip('0') or '0')
    except: pass

    title = get(doc, 'title', default=path.stem)
    title = re.sub(r"^Section \d+\.\d+[:\-]\s*", '', title).strip("'\"")

    tags   = [str(t) for t in info.get('tags', [])[:6]]
    pages  = info.get('estimated_pages', info.get('estimated_pages',''))
    rtime  = get(doc, 'estimated_reading_time', 'reading_time')

    # Objectives: try multiple locations
    objs = get_list(doc, 'by_end_of_section')
    if not objs:
        objs = get_list(doc, 'knowledge')
    if not objs:
        primary = get(doc, 'primary')
        if primary:
            objs = [s.strip() for s in primary.splitlines() if len(s.strip()) > 20][:6]

    # Strip metadata from content before extracting
    content = {k: v for k, v in doc.items() if k != 'document_info'}
    blocks = extract(content)

    # ── Build HTML ──
    H = escape
    html = ['<article>']

    # Header
    html.append('<header class="sec-header">')
    html.append(f'<div class="badge">Chapter {ch_n} · Section {sec_n}'
                + (f' · ~{pages} pages' if pages else '')
                + (f' · {H(rtime)}' if rtime else '') + '</div>')
    html.append(f'<h1>{H(title)}</h1>')
    if tags:
        html.append('<div class="tags">'
                    + ''.join(f'<span class="tag">{H(t)}</span>' for t in tags)
                    + '</div>')
    html.append('</header>')

    # Objectives box
    if objs:
        html.append('<div class="box objectives">'
                    '<div class="box-label">By the end of this section</div><ul>')
        for o in objs[:8]:
            html.append(f'<li>{H(str(o))}</li>')
        html.append('</ul></div>')

    # Deduplicate blocks (title often repeats)
    seen_texts = set()
    deduped = []
    for b in blocks:
        sig = b['text'][:80] if isinstance(b['text'], str) else str(b['text'])[:80]
        if sig not in seen_texts:
            seen_texts.add(sig)
            deduped.append(b)
    blocks = deduped

    # Render blocks
    for b in blocks:
        t = b['type']
        lvl = b['level']
        txt = b['text']

        if t == 'subheading':
            tag = 'h2' if lvl <= 1 else 'h3' if lvl <= 3 else 'h4'
            html.append(f'<{tag} class="sh{min(lvl,3)}">{H(txt)}</{tag}>')

        elif t == 'prose':
            html.append(f'<p class="prose">{H(txt)}</p>')

        elif t == 'code':
            html.append(f'<pre class="code"><code>{H(txt)}</code></pre>')

        elif t == 'list':
            if isinstance(txt, list):
                html.append('<ul class="blist">')
                for item in txt:
                    html.append(f'<li>{H(str(item))}</li>')
                html.append('</ul>')

    html.append('</article>')
    return '\n'.join(html)

# ── TOC builder ───────────────────────────────────────────────────────────────

CH_TITLES = {
    1:'ML Fundamentals', 2:'Deep Learning', 3:'NLP & Language Models',
    4:'Modern LLMs', 5:'AI Security Landscape', 6:'Prompt Injection',
    7:'Jailbreaks', 8:'Data Poisoning', 9:'Model Extraction', 10:'Adversarial Examples'
}

def build_toc():
    files = sorted(BOOK_DIR.glob('section_*.yaml'))
    ch_map = {}
    for f in files:
        m = re.match(r'section_(\d+)_(\d+)', f.name)
        if not m: continue
        ch, sec = int(m.group(1)), int(m.group(2))
        with open(f, encoding='utf-8', errors='replace') as fh:
            raw600 = fh.read(600)
        tm = re.search(r"title:\s*['\"]?(.+?)['\"]?\s*$", raw600, re.MULTILINE)
        title = tm.group(1).strip().strip("\"'") if tm else f.stem
        title = re.sub(r"^Section \d+\.\d+[:\-]\s*", '', title).strip("'")
        sid = f's{ch:02d}_{sec:02d}'
        ch_map.setdefault(ch, []).append({'sec':sec,'title':title,'sid':sid,'file':f.name})
    for ch in ch_map:
        ch_map[ch].sort(key=lambda x: x['sec'])
    return [{'num':ch,'title':CH_TITLES.get(ch,f'Chapter {ch}'),'sections':ch_map[ch]}
            for ch in sorted(ch_map)]

# ── HTML shell ────────────────────────────────────────────────────────────────

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#fff;--bg2:#f7f6f3;--bg3:#eeecea;
  --txt:#1a1a1a;--txt2:#4a4a4a;--txt3:#888;
  --border:#e2dfd8;--acc:#1a56db;--acc-bg:#eff4ff;
  --code-bg:#1e1e2e;--code-txt:#cdd6f4;
  --serif:Georgia,'Times New Roman',serif;
  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --mono:'SFMono-Regular',Consolas,'Liberation Mono',monospace;
  --sidebar:270px;--max-prose:700px;
}
@media(prefers-color-scheme:dark){
  :root{
    --bg:#131313;--bg2:#1c1c1c;--bg3:#222;
    --txt:#e4e2dc;--txt2:#a8a8a8;--txt3:#666;
    --border:#2e2e2e;--acc:#6ea8fe;--acc-bg:#172040;
    --code-bg:#0d0d1a;
  }
}
html,body{height:100%;background:var(--bg3);color:var(--txt);font-family:var(--sans)}
a{color:var(--acc);text-decoration:none}

/* Layout */
.shell{display:flex;height:100vh;overflow:hidden}
.sidebar{width:var(--sidebar);min-width:var(--sidebar);background:var(--bg);
  border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.main{flex:1;overflow-y:auto;background:var(--bg3)}

/* Sidebar top */
.s-top{padding:1.1rem 1rem .9rem;border-bottom:1px solid var(--border);flex-shrink:0}
.s-title{font-size:13px;font-weight:600;color:var(--txt);margin-bottom:2px}
.s-sub{font-size:11px;color:var(--txt3)}
.s-search{padding:8px 10px;border-bottom:1px solid var(--border);flex-shrink:0}
.s-search input{width:100%;padding:6px 9px;font-size:12px;border:1px solid var(--border);
  border-radius:6px;background:var(--bg2);color:var(--txt);outline:none}
.s-search input:focus{border-color:var(--acc)}
.s-scroll{flex:1;overflow-y:auto}
.s-foot{padding:.6rem 1rem;border-top:1px solid var(--border);flex-shrink:0;
  display:flex;flex-direction:column;gap:4px}
.s-foot a{font-size:11px;color:var(--txt3)}
.s-foot a:hover{color:var(--acc)}

/* TOC */
.ch-group{border-bottom:1px solid var(--border)}
.ch-btn{width:100%;padding:.6rem 1rem;font-size:12.5px;font-weight:500;color:var(--txt2);
  background:none;border:none;cursor:pointer;display:flex;align-items:center;
  gap:6px;text-align:left}
.ch-btn:hover{background:var(--bg2);color:var(--txt)}
.ch-num{font-size:10px;color:var(--txt3);font-weight:400;min-width:24px}
.ch-arr{font-size:9px;color:var(--txt3);margin-left:auto;transition:transform .15s}
.ch-btn.open .ch-arr{transform:rotate(90deg)}
.sec-list{display:none;padding:3px 0 6px}
.sec-list.open{display:block}
.sec-btn{width:100%;padding:.33rem .9rem .33rem 1.5rem;font-size:12px;color:var(--txt3);
  background:none;border:none;border-left:2px solid transparent;cursor:pointer;
  text-align:left;line-height:1.4;white-space:normal}
.sec-btn:hover{background:var(--bg2);color:var(--txt)}
.sec-btn.active{border-left-color:var(--acc);color:var(--acc);background:var(--acc-bg)}
.sec-num{font-size:10px;margin-right:4px;color:var(--txt3)}

/* Reading progress */
#rbar{height:2px;background:var(--acc);position:fixed;top:0;left:var(--sidebar);
  z-index:100;pointer-events:none;transition:width .15s}

/* Content */
.c-outer{max-width:calc(var(--max-prose) + 4rem);margin:0 auto;padding:2.5rem 2rem 8rem}
article{}

/* Section header */
.sec-header{margin-bottom:2rem;padding-bottom:1.5rem;border-bottom:1px solid var(--border)}
.badge{font-size:11px;color:var(--txt3);font-weight:500;text-transform:uppercase;
  letter-spacing:.05em;margin-bottom:.5rem;font-family:var(--sans)}
h1{font-family:var(--serif);font-size:2rem;font-weight:400;line-height:1.2;
  color:var(--txt);margin-bottom:.75rem;letter-spacing:-.01em}
.tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:.6rem}
.tag{font-size:11px;padding:2px 7px;background:var(--bg2);border:1px solid var(--border);
  border-radius:4px;color:var(--txt3);font-family:var(--sans)}

/* Objectives */
.box{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
  padding:1.1rem 1.4rem;margin-bottom:2rem}
.box-label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;
  color:var(--txt3);margin-bottom:.7rem;font-family:var(--sans)}
.objectives ul{list-style:none}
.objectives li{display:flex;gap:8px;font-size:14px;line-height:1.5;color:var(--txt2);
  padding:.25rem 0;font-family:var(--sans)}
.objectives li::before{content:'→';color:var(--acc);flex-shrink:0;margin-top:1px}

/* Body content */
.sh0,.sh1{font-family:var(--serif);font-size:1.35rem;font-weight:400;color:var(--txt);
  margin:2.2rem 0 .8rem;padding-top:1.5rem;border-top:1px solid var(--border)}
.sh2{font-family:var(--sans);font-size:1rem;font-weight:600;color:var(--txt);
  margin:1.6rem 0 .5rem}
.sh3{font-family:var(--sans);font-size:.9rem;font-weight:600;color:var(--txt2);
  margin:1.2rem 0 .4rem;text-transform:uppercase;letter-spacing:.04em}
.prose{font-family:var(--serif);font-size:17px;line-height:1.85;color:var(--txt);
  margin-bottom:1.2rem;white-space:pre-wrap;word-break:break-word}
.code{background:var(--code-bg);color:var(--code-txt);font-family:var(--mono);
  font-size:13px;line-height:1.6;padding:1.1rem 1.3rem;border-radius:8px;
  overflow-x:auto;margin:1rem 0 1.5rem;white-space:pre}
.blist{margin:0 0 1.2rem 1.2rem}
.blist li{font-family:var(--sans);font-size:15px;line-height:1.6;color:var(--txt2);
  padding:.2rem 0}

/* Welcome */
.welcome{padding:3rem 2rem}
.welcome h1{font-family:var(--serif);font-size:2.4rem;font-weight:400;margin-bottom:.4rem}
.welcome .tag-line{font-family:var(--serif);font-size:1.1rem;color:var(--txt2);
  font-style:italic;margin-bottom:2rem}
.w-meta{font-size:13px;color:var(--txt3);display:flex;flex-wrap:wrap;gap:1rem;
  margin-bottom:2rem;font-family:var(--sans)}
.w-meta span+span::before{content:'·';margin-right:1rem}
.w-body{font-family:var(--serif);font-size:16px;line-height:1.8;color:var(--txt2);
  max-width:540px;margin-bottom:1.5rem}
.start{display:inline-block;padding:.65rem 1.4rem;background:var(--acc);color:#fff;
  border-radius:6px;font-size:14px;font-weight:500;cursor:pointer;border:none;
  font-family:var(--sans)}
.start:hover{opacity:.9}

/* Mobile */
.menu-fab{display:none;position:fixed;bottom:1rem;right:1rem;z-index:200;
  padding:8px 14px;background:var(--bg);border:1px solid var(--border);
  border-radius:8px;font-size:13px;color:var(--txt2);cursor:pointer;
  box-shadow:0 2px 12px rgba(0,0,0,.15)}
@media(max-width:768px){
  .sidebar{position:fixed;left:0;top:0;height:100%;z-index:150;
    transform:translateX(-110%);transition:transform .2s;width:280px}
  .sidebar.open{transform:translateX(0)}
  #rbar{left:0}
  .menu-fab{display:block}
  .c-outer{padding:1.5rem 1rem 6rem}
  h1{font-size:1.5rem}
  .prose{font-size:15px}
}
"""

JS = """
const TOC=__TOC__;
const SECS=__SECS__;
let active=null;

function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

function buildToc(){
  const el=document.getElementById('toc');
  TOC.forEach(ch=>{
    const grp=document.createElement('div');
    grp.className='ch-group';
    const btn=document.createElement('button');
    btn.className='ch-btn';
    btn.innerHTML=`<span class="ch-num">Ch ${ch.num}</span><span style="flex:1">${esc(ch.title)}</span><span class="ch-arr">▶</span>`;
    const list=document.createElement('div');
    list.className='sec-list';
    ch.sections.forEach(s=>{
      const b=document.createElement('button');
      b.className='sec-btn';
      b.dataset.sid=s.sid;
      b.innerHTML=`<span class="sec-num">${ch.num}.${String(s.sec).padStart(2,'0')}</span>${esc(s.title)}`;
      b.addEventListener('click',()=>{load(s.sid);closeMobile();});
      list.appendChild(b);
    });
    btn.addEventListener('click',()=>{btn.classList.toggle('open');list.classList.toggle('open');});
    grp.appendChild(btn);grp.appendChild(list);
    el.appendChild(grp);
  });
}

function load(sid){
  const html=SECS[sid];
  if(!html)return;
  document.getElementById('content').innerHTML='<div class="c-outer">'+html+'</div>';
  const main=document.getElementById('main');
  main.scrollTop=0;
  if(active)active.classList.remove('active');
  const btn=document.querySelector('.sec-btn[data-sid="'+sid+'"]');
  if(btn){
    btn.classList.add('active');active=btn;
    btn.scrollIntoView({block:'nearest'});
    const list=btn.closest('.sec-list');
    if(list&&!list.classList.contains('open')){
      list.classList.add('open');
      list.previousElementSibling?.classList.add('open');
    }
  }
  document.getElementById('rbar').style.width='0';
}

document.getElementById('main').addEventListener('scroll',function(){
  const pct=this.scrollTop/(this.scrollHeight-this.clientHeight)||0;
  document.getElementById('rbar').style.width=Math.round(pct*100)+'%';
});

document.getElementById('search').addEventListener('input',function(){
  const q=this.value.toLowerCase();
  document.querySelectorAll('.sec-btn').forEach(b=>{
    b.style.display=!q||b.textContent.toLowerCase().includes(q)?'':'none';
  });
  document.querySelectorAll('.ch-group').forEach(g=>{
    const vis=[...g.querySelectorAll('.sec-btn')].some(b=>b.style.display!=='none');
    g.style.display=vis?'':'none';
    if(q&&vis){g.querySelector('.sec-list')?.classList.add('open');g.querySelector('.ch-btn')?.classList.add('open');}
  });
});

function toggleSidebar(){document.getElementById('sidebar').classList.toggle('open');}
function closeMobile(){if(window.innerWidth<=768)document.getElementById('sidebar').classList.remove('open');}

buildToc();
"""

SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Security Mastery — Raghav Dinesh</title>
<meta name="description" content="AI Security Mastery: From ML Fundamentals to Production Detection Systems. Free open-source book, 182 sections.">
<link rel="alternate" type="text/plain" href="/llms.txt">
<style>{CSS}</style>
</head>
<body>
<div id="rbar"></div>
<button class="menu-fab" onclick="toggleSidebar()">☰ Menu</button>
<div class="shell">
  <nav class="sidebar" id="sidebar">
    <div class="s-top">
      <div class="s-title">AI Security Mastery</div>
      <div class="s-sub">Raghav Dinesh · github.com/ruwgxo</div>
    </div>
    <div class="s-search"><input id="search" type="search" placeholder="Search sections…"></div>
    <div class="s-scroll" id="toc"></div>
    <div class="s-foot">
      <a href="/" >← ruwgxo.com</a>
      <a href="https://github.com/ruwgxo/ai-security-mastery" target="_blank">GitHub ↗</a>
      <a href="/llms.txt">llms.txt ↗</a>
    </div>
  </nav>
  <main class="main" id="main">
    <div id="content">
      <div class="c-outer welcome">
        <h1>AI Security Mastery</h1>
        <p class="tag-line">From ML Fundamentals to Production Detection Systems</p>
        <div class="w-meta">
          <span>18 chapters</span>
          <span>182 sections</span>
          <span>~1,080 pages</span>
          <span>90-day path</span>
          <span>Free &amp; open source</span>
        </div>
        <p class="w-body">Practical guide to securing AI systems — from ML basics through prompt injection, jailbreaks, data poisoning, model extraction, and production detection engineering. No black boxes. Pure implementation. Security-first.</p>
        <button class="start" onclick="load(TOC[0].sections[0].sid)">Start reading →</button>
      </div>
    </div>
  </main>
</div>
<script>
{JS}
</script>
</body>
</html>"""

# ── Build ─────────────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(exist_ok=True)
    toc = build_toc()
    files = sorted(BOOK_DIR.glob('section_*.yaml'))
    print(f"Building {len(files)} sections…")

    secs = {}
    errors = []
    for i, f in enumerate(files, 1):
        m = re.match(r'section_(\d+)_(\d+)', f.name)
        if not m: continue
        sid = f's{int(m.group(1)):02d}_{int(m.group(2)):02d}'
        try:
            secs[sid] = render_section(f)
        except Exception as e:
            errors.append((f.name, str(e)))
            secs[sid] = f'<article><p style="color:red">Error: {escape(str(e))}</p></article>'
        if i % 30 == 0:
            print(f"  {i}/{len(files)}…")

    toc_json = json.dumps(toc, separators=(',',':'))
    secs_json = json.dumps(secs, separators=(',',':'))

    html = SHELL.replace('{CSS}', CSS) \
               .replace('{JS}', JS.replace('__TOC__', toc_json).replace('__SECS__', secs_json))

    out = OUT_DIR / 'index.html'
    out.write_text(html, encoding='utf-8')
    kb = out.stat().st_size // 1024
    print(f"\n✓ {out} — {kb} KB, {len(secs)} sections, {len(errors)} errors")
    for n, e in errors[:5]:
        print(f"  ! {n}: {e}")
    print("\nDeploy:")
    print("  git add docs/index.html && git commit -m 'build: full content render' && git push")
    print("  ruwgxo.github.io → copy to book.html with ← ruwgxo.com link")

if __name__ == '__main__':
    main()
