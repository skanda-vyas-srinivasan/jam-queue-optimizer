"""Test the proposed continuous-transition formulation on synthetic instances.
This builds an independent SciPy/HiGHS model, not the repository's PuLP/CBC model.
The objective uses an explicit, unscaled adjacency penalty consistently.
Run: python formulation_checks.py
"""
from __future__ import annotations
import itertools
import json
from pathlib import Path
import numpy as np
import scipy
from scipy.optimize import milp, Bounds, LinearConstraint

rng = np.random.default_rng(42)
results = []
for case in range(10):
    n, k = 5, 3
    xkeys = [(a,t) for a in range(n) for t in range(k)]
    ykeys = [(a,b,t) for a in range(n) for b in range(n) if a!=b for t in range(k-1)]
    xi = {key:i for i,key in enumerate(xkeys)}
    yi = {key:i+len(xkeys) for i,key in enumerate(ykeys)}
    d = len(xkeys)+len(ykeys)
    relevance = rng.uniform(-1,1,n)
    transitions = rng.uniform(-1,1,(n,n))
    folders = np.array([0,0,1,1,2])
    representations = [{0,1},{3,4}]
    weight, penalty = .25, .1
    obj = np.zeros(d)
    for (a,t),j in xi.items(): obj[j]=relevance[a]
    for (a,b,t),j in yi.items(): obj[j]=weight*transitions[a,b]-penalty*(folders[a]==folders[b])
    rows, lows, highs = [],[],[]
    def add(terms, low, high):
        row=np.zeros(d)
        for idx,coef in terms: row[idx]+=coef
        rows.append(row); lows.append(low); highs.append(high)
    for t in range(k): add([(xi[a,t],1) for a in range(n)],1,1)
    for a in range(n): add([(xi[a,t],1) for t in range(k)],0,1)
    for folder in set(folders):
        add([(xi[a,t],1) for a in range(n) if folders[a]==folder for t in range(k)],0,2)
    for rep in representations:
        add([(xi[a,t],1) for a in rep for t in range(k)],1,np.inf)
    for a in range(n):
        for t in range(k-1):
            add([(yi[a,b,t],1) for b in range(n) if b!=a]+[(xi[a,t],-1)],0,0)
    for b in range(n):
        for t in range(k-1):
            add([(yi[a,b,t],1) for a in range(n) if a!=b]+[(xi[b,t+1],-1)],0,0)
    feasible=[]
    for q in itertools.permutations(range(n),k):
        if any(sum(folders[a]==f for a in q)>2 for f in set(folders)): continue
        if any(not set(q)&r for r in representations): continue
        value=sum(relevance[a] for a in q)+sum(weight*transitions[a,b]-penalty*(folders[a]==folders[b]) for a,b in zip(q,q[1:]))
        feasible.append((float(value),q))
    oracle=max(feasible)[0]
    checks={}
    for mode in ['all_binary','continuous_y']:
        integrality=np.ones(d,dtype=int)
        if mode=='continuous_y': integrality[len(xkeys):]=0
        sol=milp(-obj,integrality=integrality,bounds=Bounds(np.zeros(d),np.ones(d)),
                 constraints=LinearConstraint(np.vstack(rows),np.array(lows),np.array(highs)),
                 options={'time_limit':5.,'mip_rel_gap':0.})
        if not sol.success: raise AssertionError(f'Case {case}: {mode}: {sol.message}')
        assert np.isclose(-sol.fun,oracle,atol=1e-7)
        assert np.allclose(sol.x[len(xkeys):],np.round(sol.x[len(xkeys):]),atol=1e-7)
        checks[mode]=float(-sol.fun)
    results.append({'case':case,'exhaustive_optimum':oracle,**checks})
result={'scope':'Independent synthetic equivalent core formulations; not original repository CBC benchmarks.',
        'scipy':scipy.__version__,'cases':results,'passed':len(results)}
Path(__file__).with_name('formulation_results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
