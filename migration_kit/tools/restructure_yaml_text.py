"""Apply the chapters 5-6 rule "YAML written as text becomes headings, prose, lists and fields" to an
already-migrated section file, keeping every other value exactly as it is in that file (content fixes
included). It runs convert.py's own structuring step over the yaml code blocks of each subsection part,
so on an unedited form-commit file it reproduces the converter's output byte for byte.
Usage: restructure_yaml_text.py IN.yaml OUT.yaml REPORT.json"""
import sys, json, yaml
from collections import OrderedDict
import convert
from emit import Folded, Literal, emit

class StyledLoader(yaml.SafeLoader): pass

def load_styled(text):
    """Load a v2 file keeping key order and the folded/literal style of every block scalar."""
    loader = StyledLoader(text)
    def build(node):
        if isinstance(node, yaml.MappingNode):
            return OrderedDict((build(k), build(v)) for k, v in node.value)
        if isinstance(node, yaml.SequenceNode):
            return [build(v) for v in node.value]
        if node.style == '>':
            v = loader.construct_scalar(node); return Folded(v[:-1] if v.endswith('\n') else v)
        if node.style == '|':
            return Literal(loader.construct_scalar(node))
        return loader.construct_object(node, deep=True)
    try:
        return build(loader.get_single_node())
    finally:
        loader.dispose()

def restructure(doc):
    for p in doc.get('prose_content') or []:
        if not str(p.get('id', '')).startswith('subsection_') or not p.get('blocks'):
            continue
        cont = OrderedDict([('heading', p['heading']), ('id', f"section_content.{p['id']}.body")])
        for b in p['blocks']:
            if b.get('type') == 'code' and b.get('lang') == 'yaml':
                try: m = yaml.load(str(b['text']), Loader=yaml.BaseLoader)
                except yaml.YAMLError: m = None
                if isinstance(m, dict) and m and not convert._is_sigma(m):
                    convert.R.add('classified', path=cont['id'], kind='yaml-text->structure', text=str(b['text'])[:200])
                    convert._y_mapping_into(cont, m, cont['id'], 2)
                    continue
            convert._y_add(cont, ('block', b))
        rebuilt = OrderedDict()
        for k, v in p.items():
            if k == 'blocks':
                if cont.get('blocks'): rebuilt['blocks'] = cont['blocks']
                if cont.get('parts'): rebuilt['parts'] = cont['parts']
            elif k == 'parts':
                raise SystemExit(f"{p['id']}: part already has sub-parts")
            else:
                rebuilt[k] = v
        p.clear(); p.update(rebuilt)
    return doc

if __name__ == '__main__':
    src, dst, rep = sys.argv[1:4]
    text = open(src).read()
    header, _, body = text.partition('\n---\n') if text.startswith('#') else ('', '', text[4:] if text.startswith('---\n') else text)
    doc = load_styled(body)
    assert emit(doc) == body, 'file does not round-trip through emit unchanged; refusing to rewrite it'
    out = emit(restructure(doc))
    assert yaml.safe_load(out) is not None
    open(dst, 'w').write((header + '\n---\n' if header else '---\n') + out)
    json.dump(convert.R.items, open(rep, 'w'), indent=1, default=str)
    print(src.split('/')[-1], '->', {k: len(v) for k, v in convert.R.items.items() if v})
