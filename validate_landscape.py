import json, sys

d = json.load(open(sys.argv[1], encoding='utf-8'))
caps = set(d['capabilities']); parts = d['parts']; opts = {o['id']: o for o in d['options']}
lanes = {l['id'] for l in d['lanes']}; errs = []

def toks(ts, where):
    for t in ts:
        if t not in caps: errs.append(f'{where}: undefined token {t}')

for pid, p in parts.items():
    toks(p['provides'], f'part {pid}.provides'); toks(p['requires'], f'part {pid}.requires')
for o in d['options']:
    if o['lane'] not in lanes: errs.append(f"option {o['id']}: bad lane {o['lane']}")
    toks(o['provides'], f"option {o['id']}.provides")
    toks(o.get('provides_unverified', []), f"option {o['id']}.provides_unverified")
    for ref in o['includes'] + o['to_complete']:
        if ref not in parts and ref not in opts:
            errs.append(f"option {o['id']}: unknown include/to_complete id {ref}")

def effective(o, seen=None):
    seen = seen or set(); out = set(o['provides'])
    for ref in o['includes']:
        if ref in seen: continue
        seen.add(ref)
        if ref in parts: out |= set(parts[ref]['provides'])
        else: out |= effective(opts[ref], seen)
    return out

eff = {oid: effective(o) for oid, o in opts.items()}
# grow each option's capability set by adding any part whose requires are met (transitive chains)
grown_eff = {}
for oid, have in eff.items():
    have = set(have); grown = True
    while grown:
        grown = False
        for pid, p in parts.items():
            if set(p['requires']) <= have and not set(p['provides']) <= have:
                have |= set(p['provides']); grown = True
    grown_eff[oid] = have

for pid, p in parts.items():
    if not any(set(p['requires']) <= have for have in grown_eff.values()):
        errs.append(f"part {pid}: requires {p['requires']} satisfiable from NO option (even with chains)")

EFFORTS = {'none', 'some', 'diy'}
STOCKS = {'now', 'waves', 'scarce', 'na'}
for o in d['options']:
    if o.get('effort') not in EFFORTS:
        errs.append(f"option {o['id']}: effort must be one of {sorted(EFFORTS)}")
    if o.get('stock') not in STOCKS:
        errs.append(f"option {o['id']}: stock must be one of {sorted(STOCKS)}")
    if o.get('stock') == 'na' and o['status'] == 'orderable':
        errs.append(f"option {o['id']}: orderable options need a real stock value, not na")
    for fld in ('what', 'advice'):
        if not (o.get(fld) or '').strip():
            errs.append(f"option {o['id']}: missing editorial field '{fld}'")
    for v in o.get('variants', []):
        toks(v.get('adds', []), f"option {o['id']} variant {v.get('id')}.adds")
        if not isinstance(v.get('price_delta'), (int, float)):
            errs.append(f"option {o['id']} variant {v.get('id')}: price_delta must be a number")
for q in d.get('interview', []):
    seen_a = set()
    for a in q['answers']:
        if a['id'] in seen_a: errs.append(f"interview {q['id']}: duplicate answer id {a['id']}")
        seen_a.add(a['id'])
        for grp in a.get('require', []):
            toks(grp, f"interview {q['id']}.{a['id']}.require")
        for e in a.get('effort', []):
            if e not in EFFORTS: errs.append(f"interview {q['id']}.{a['id']}: bad effort {e}")
        for s in a.get('stock', []):
            if s not in STOCKS: errs.append(f"interview {q['id']}.{a['id']}: bad stock {s}")

print('ERRORS:' if errs else 'OK - all references and chains resolve.')
print('\n'.join(errs))
print('options reaching yc (any path):',
      sorted(oid for oid, have in grown_eff.items() if 'yc' in have))
print('options reaching yc-active-filtered:',
      sorted(oid for oid, have in grown_eff.items() if 'yc-active-filtered' in have))
