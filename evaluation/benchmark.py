"""New synthetic matched-rule experiments, not reproduction of PDF listener results."""
from __future__ import annotations
import argparse
from dataclasses import asdict,replace
import hashlib
import itertools
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import numpy as np
import pulp
from music_queue import Listener,Policy,QueueInstance,Track,Status
from music_queue.domain import Deadline
from music_queue.instance_io import write_instance
from music_queue.objective import choose_final,components
from music_queue.queueing import solve_instance
from music_queue.validation import validate_queue


def make_instance(n,k,users,seed,objective='affinity',overlap=False,conflict=False):
    rng=np.random.default_rng(seed)
    tracks=tuple(Track(f'track_{a:02}',f'Synthetic track {a}',f'folder_{a//2}',
                       duration=90+30*(a%5),artist=f'artist_{a//2}',recording_family=f'recording_{a}') for a in range(n))
    listeners=tuple(Listener(f'listener_{u}',f'Listener {u}',(tracks[min(u,n-1)].id,)) for u in range(users))
    acceptance=tuple(tuple((a==u or a==n-1) if overlap else (a%users==u) for a in range(n)) for u in range(users))
    if conflict: acceptance=tuple(tuple(a==u for a in range(n)) for u in range(users))
    utilities=tuple(tuple(1. if acceptance[u][a] else float(rng.uniform(-1,1)) for a in range(n)) for u in range(users))
    return QueueInstance(tracks,listeners,utilities,acceptance,
                         tuple(tuple(float(v) for v in row) for row in rng.uniform(-1,1,(n,n))),k,
                         Policy(folder_cap=1 if conflict else 2,discovery_budget=k,objective=objective,
                                same_folder_penalty=.13),model_hash='frozen-synthetic-'+str(seed))


def cases():
    result=[]
    for seed in range(10):
        result.append((f'exhaustive_{seed}',make_instance(5,3,2,seed,objective='fair' if seed%2 else 'affinity',overlap=seed%3==0)))
    result.extend((f'scale_{n}_{u}',make_instance(n,5,u,100+n+u,overlap=u==3)) for n in (8,10,12) for u in (2,3))
    result.append(('joint_conflict',make_instance(5,3,2,999,conflict=True)))
    result.append(('locked_history',replace(make_instance(8,4,3,2026,objective='fair',overlap=True),
        locked_prefix=('track_00',),anchor_values=(.2,-.1,.3,-.2,0.,.4,0.,-.1),service_debt=(1.,0.,.5))))
    return result


def run(output,repeats=3,budget=2.):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    (output/'instances').mkdir(exist_ok=True);(output/'logs').mkdir(exist_ok=True)
    binary=Path(pulp.PULP_CBC_CMD().path)
    rows=[]
    for name,instance in cases():
        write_instance(instance,output/'instances'/f'{name}.json')
        reference=solve_instance(instance,'dp',Deadline(max(5.,budget)))
        expected=None
        if len(instance.tracks)==5:
            feasible=[q for q in itertools.permutations([t.id for t in instance.tracks],instance.queue_len)
                      if not validate_queue(instance,q)]
            expected=choose_final(instance,feasible)
            if expected:
                assert components(instance,expected)['weighted_edges' if instance.policy.objective=='fair' else 'affinity_objective']==reference.objective_components['weighted_edges' if instance.policy.objective=='fair' else 'affinity_objective']
            else: assert reference.status==Status.HARD_INFEASIBLE
        for method in ('greedy','beam','dp','milp','binary_y_milp','round_robin','shared_approval'):
            for repetition in range(repeats):
                started=time.perf_counter()
                result=solve_instance(instance,'milp' if method=='binary_y_milp' else method,Deadline(budget),
                                      binary_y=True if method=='binary_y_milp' else False) if method in {'milp','binary_y_milp'} else solve_instance(instance,method,Deadline(budget))
                elapsed=time.perf_counter()-started
                logs=result.solver.pop('logs',[])
                for phase,log in enumerate(logs):
                    (output/'logs'/f'{name}-{method}-{repetition}-{phase}.log').write_text(log['log'])
                if result.valid_incumbent: assert not validate_queue(instance,result.queue)
                if reference.valid_incumbent and result.proven_optimal:
                    term='weighted_edges' if instance.policy.objective=='fair' else 'affinity_objective'
                    assert abs(result.objective_components[term]-reference.objective_components[term])<1e-5,(name,method,term)
                gap=None
                if reference.valid_incumbent and result.valid_incumbent and instance.policy.objective=='affinity':
                    gap=reference.objective_components['affinity_objective']-result.objective_components['affinity_objective']
                rows.append({'case':name,'method':method,'repeat':repetition,'seconds':elapsed,
                             'budget_seconds':budget,'budget_overhead':max(0.,elapsed-budget),
                             'reference_status':reference.status,'absolute_affinity_gap':gap,
                             'priority_difference':({term:reference.objective_components[term]-result.objective_components[term]
                                for term in ('max_deficit','total_deficit','worst_listener_utility','room_utility','weighted_edges')}
                                if reference.valid_incumbent and result.valid_incumbent else None),
                             'result':result.to_dict()})
        print(name,'done',flush=True)
    summary={}
    for method in sorted({r['method'] for r in rows}):
        selected=[r for r in rows if r['method']==method]
        summary[method]={'runs':len(selected),'valid_incumbents':sum(r['result']['valid_incumbent'] for r in selected),
                         'proven_optimal':sum(r['result']['proven_optimal'] for r in selected),
                         'median_seconds':float(np.median([r['seconds'] for r in selected])),
                         'maximum_seconds':max(r['seconds'] for r in selected),
                         'maximum_absolute_affinity_gap':max((r['absolute_affinity_gap'] for r in selected if r['absolute_affinity_gap'] is not None),default=None),
                         'outcomes':{status:sum(r['result']['status']==status for r in selected) for status in sorted({r['result']['status'] for r in selected})}}
    metadata={'scope':'Synthetic frozen instances; no listening judgments; new benchmark, not the six unavailable PDF experiments',
              'python':platform.python_version(),'platform':platform.platform(),'numpy':np.__version__,'pulp':pulp.__version__,
              'cbc_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'seed_protocol':'Exact matrices in instances; generator is checked in',
              'repeats':repeats,'budget_seconds':budget,'cases':len(cases()),'summary':summary,'runs':rows}
    (output/'benchmark.json').write_text(json.dumps(metadata,indent=2,allow_nan=False)+'\n')
    return metadata

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('evaluation/results/rebuild-benchmark'))
    p.add_argument('--repeats',type=int,default=3);p.add_argument('--budget',type=float,default=2.)
    args=p.parse_args(); run(args.output,args.repeats,args.budget)
