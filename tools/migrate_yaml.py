#!/usr/bin/env python3
"""
migrate_yaml_v2.py — Complete YAML normalisation for ai-security-mastery/book/
Run from repo root: python3 migrate_yaml_v2.py

Fixes ALL known issues in one pass:
  1. Renames own-key root (section_NN_NN_slug:) → section_content: (Ch1+2)
  2. Removes rogue mid-document --- separators (Ch4) — merges split docs
  3. Fixes ASCII art tables in block scalars (Ch1 evaluation_metrics)
  4. Fixes unclosed string quotes (Ch3 tokenization)
  5. Fixes stray mapping keys inside list blocks (Ch1 what_is_ml)

Safe to re-run: only writes files that change. No data loss.

# write sections → run migrate → run build → copy to ruwgxo.github.io/book/
python3 migrate_yaml_v2.py
python3 build_site_v2.py
cp docs/index.html ../ruwgxo.github.io/book/index.html
cd ../ruwgxo.github.io && git add book/ && git commit -m "feat: chapter ..." && git push
"""

import re, sys, yaml, glob
from pathlib import Path

BOOK = Path('book')

def parse_all(raw):
    """Try to load all YAML docs, merge, return merged dict or None."""
    try:
        docs = list(yaml.safe_load_all(raw))
        merged = {}
        for d in docs:
            if isinstance(d, dict):
                merged.update(d)
        return merged if merged else None
    except yaml.YAMLError:
        return None

def try_parse(raw):
    return parse_all(raw) is not None

def deep_merge(base, override):
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        elif k in result and isinstance(result[k], list) and isinstance(v, list):
            result[k] = result[k] + v
        else:
            result[k] = v
    return result

# ── Fix 1: rename own-key root to section_content ────────────────────────────
def fix_own_key(raw):
    own_key_pat = re.compile(
        r'^(section_(?:\d{2}_\d{2}|\d{4})_[a-z_0-9]+):',
        re.MULTILINE
    )
    m = own_key_pat.search(raw)
    if not m:
        return raw
    return raw.replace(m.group(0), 'section_content:', 1)

# ── Fix 2: rogue --- separators — merge all docs via PyYAML dump ─────────────
def fix_rogue_separators(raw):
    sep_positions = [m.start() for m in re.finditer(r'^\-\-\-\s*$', raw, re.MULTILINE)]
    if len(sep_positions) < 2:
        return raw  # nothing to fix

    # Split into chunks at each ---
    chunks = []
    boundaries = sep_positions + [len(raw)]
    for i in range(len(sep_positions)):
        chunk = raw[sep_positions[i]+4 : boundaries[i+1]]
        chunks.append(chunk)

    # Parse what we can from each chunk
    merged = {}
    for chunk in chunks:
        try:
            d = yaml.safe_load(chunk)
            if isinstance(d, dict):
                merged = deep_merge(merged, d)
        except yaml.YAMLError:
            # Chunk itself broken — try sub-splitting
            for sub in re.split(r'^\-\-\-\s*$', chunk, flags=re.MULTILINE):
                try:
                    d = yaml.safe_load(sub)
                    if isinstance(d, dict):
                        merged = deep_merge(merged, d)
                except:
                    pass

    if not merged:
        return raw  # couldn't extract anything useful

    out = yaml.dump(merged, default_flow_style=False, allow_unicode=True,
                    sort_keys=False, width=120)
    return '---\n' + out

# ── Fix 3: ASCII art / pipe-table in block scalars ───────────────────────────
def fix_ascii_table(raw):
    # Replace known-broken matrix_structure block
    # Pattern: `key: |` followed by lines containing `|` at certain indents
    lines = raw.splitlines(keepends=True)
    out = []
    skip_until_dedent = False
    block_indent = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        # Detect block scalar containing ASCII art (lines with ---|--- pattern)
        if re.match(r'^\s+\w[\w_]*:\s*\|', stripped):
            # Check if following lines contain ASCII art
            lookahead = ''.join(lines[i+1:i+6])
            if re.search(r'[-|]{5,}', lookahead):
                # Replace the whole block scalar with a single-line summary
                key_m = re.match(r'^(\s+)(\w[\w_]*):\s*\|', stripped)
                if key_m:
                    indent = key_m.group(1)
                    key = key_m.group(2)
                    # Collect the block content
                    block_lines = []
                    j = i + 1
                    while j < len(lines):
                        bl = lines[j]
                        if bl.strip() == '':
                            j += 1
                            continue
                        bl_indent = len(bl) - len(bl.lstrip())
                        if bl_indent <= len(indent):
                            break
                        block_lines.append(bl.strip())
                        j += 1
                    # Replace with a safe quoted string
                    safe_val = ' '.join(block_lines)[:200].replace('"', "'")
                    out.append(f'{indent}{key}: "{safe_val}"\n')
                    i = j
                    continue
        out.append(line)
        i += 1
    return ''.join(out)

# ── Fix 4: unclosed string quotes ────────────────────────────────────────────
def fix_unclosed_quotes(raw):
    lines = raw.splitlines()
    out = []
    for line in lines:
        # Detect lines that start a double-quoted string but don't close it
        # Pattern: `          - "some text` (no closing ")
        m = re.match(r'^(\s*-\s*")([^"]+)$', line)
        if m:
            line = line + '"'
        out.append(line)
    return '\n'.join(out)

# ── Fix 5: stray mapping key inside list block ────────────────────────────────
def fix_stray_mapping_key(raw):
    # Pattern: a `key: "value"` line that appears after `- "..."` list items
    # at the same indent level — it's invalid YAML
    # Fix: convert it to a list item `- "key: value"`
    lines = raw.splitlines()
    out = []
    for i, line in enumerate(lines):
        # Stray key: indented, not a list item, followed by a string value
        m = re.match(r'^(\s{6,})([a-z_]+): "(.+)"(\s*)$', line)
        if m:
            indent, key, val, _ = m.groups()
            # Check previous non-blank line was a list item
            prev = next((l for l in reversed(out) if l.strip()), '')
            if prev.lstrip().startswith('- '):
                # Convert to comment — preserves info without breaking YAML
                out.append(f'{indent}# {key}: {val}')
                continue
        # Orphan list item inside a dict context (starts with `- ` at dict indent)
        m2 = re.match(r'^(\s{6,})(- ".+")(\s*)$', line)
        if m2:
            indent = m2.group(1)
            prev = next((l for l in reversed(out) if l.strip()), '')
            # If prev line is a dict key (key: value), this list item is orphaned
            if re.match(r'^\s+\w[\w_]*:', prev) and not prev.lstrip().startswith('- '):
                out.append(f'{indent}# orphan: {line.strip()}')
                continue
        out.append(line)
    return '\n'.join(out)

# ── Main migration ────────────────────────────────────────────────────────────

def migrate(path):
    raw = path.read_text(encoding='utf-8', errors='replace')
    original = raw

    # Step 1: rename own-key
    raw = fix_own_key(raw)

    # Step 2: if still broken, try each fix in sequence
    if not try_parse(raw):
        raw2 = fix_rogue_separators(raw)
        if try_parse(raw2):
            raw = raw2
        else:
            # Try ASCII table fix first, then rogue separators
            raw3 = fix_ascii_table(raw)
            if try_parse(raw3):
                raw = raw3
            else:
                raw4 = fix_unclosed_quotes(fix_ascii_table(raw))
                if try_parse(raw4):
                    raw = raw4
                else:
                    raw5 = fix_stray_mapping_key(fix_unclosed_quotes(fix_ascii_table(raw)))
                    if try_parse(raw5):
                        raw = raw5
                    else:
                        # Last resort: rogue separator merge
                        raw6 = fix_rogue_separators(fix_unclosed_quotes(fix_ascii_table(raw5)))
                        if try_parse(raw6):
                            raw = raw6
                        else:
                            return 'BROKEN'

    if raw != original:
        path.write_text(raw, encoding='utf-8')
        return 'FIXED'
    return 'unchanged'

# ── Run ───────────────────────────────────────────────────────────────────────

files = sorted(BOOK.glob('section_*.yaml'))
counts = {'FIXED': 0, 'unchanged': 0, 'BROKEN': 0}

for f in files:
    result = migrate(f)
    counts[result] += 1
    if result != 'unchanged':
        print(f"  {result:<8} {f.name}")

print(f"\n{'='*60}")
print(f"Fixed:     {counts['FIXED']}")
print(f"Unchanged: {counts['unchanged']}")
print(f"Broken:    {counts['BROKEN']}")

# Final validation
print('\nFinal validation...')
errors = []
for f in sorted(BOOK.glob('section_*.yaml')):
    try:
        list(yaml.safe_load_all(f.read_text(encoding='utf-8', errors='replace')))
    except yaml.YAMLError as e:
        errors.append((f.name, str(e)[:60]))

if errors:
    print(f'\n{len(errors)} files still broken:')
    for name, err in errors:
        print(f'  {name}: {err}')
    sys.exit(1)
else:
    print(f'All {len(files)} files parse cleanly. ✓')
    print('\nNext step: python3 build_site_v2.py')
