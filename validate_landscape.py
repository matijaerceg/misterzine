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

print('ERRORS:' if errs else 'OK - all references and chains resolve.')
print('\n'.join(errs))
print('options reaching yc (any path):',
      sorted(oid for oid, have in grown_eff.items() if 'yc' in have))
print('options reaching yc-active-filtered:',
      sorted(oid for oid, have in grown_eff.items() if 'yc-active-filtered' in have))
