"""Measured local catalog diagnostics with completely specified artificial rooms."""
from __future__ import annotations
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from music_queue import Listener,Policy,SessionRequest,load_catalog
from music_queue.candidates import build_instance
from music_queue.domain import Deadline
from music_queue.instance_io import write_instance
from music_queue.preferences import normalize_request
from music_queue.queueing import solve_instance
from music_queue.validation import validate_queue


def run(output,budget=2.):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    (output/'instances').mkdir(exist_ok=True);(output/'logs').mkdir(exist_ok=True)
    catalog=load_catalog();rng=np.random.default_rng(42);rooms=[]
    rooms.append(tuple(Listener(f'user_{u}',f'Artificial listener {u}',tuple(catalog.tracks[a].id for a in group))
                       for u,group in enumerate(((0,1,2),(10,11,12),(20,21,22)))))
    for _ in range(5):
        indices=rng.choice(len(catalog),size=(3,3),replace=False)
        rooms.append(tuple(Listener(f'user_{u}',f'Artificial listener {u}',tuple(catalog.tracks[a].id for a in group))
                           for u,group in enumerate(indices)))
    runs=[];requests=[]
    for room_index,room in enumerate(rooms):
        for limit in (10,20):
            request=normalize_request(catalog,SessionRequest(room,queue_len=5,candidate_limit=limit,
                         policy=Policy(objective='fair'),time_limit=budget))
            started=time.perf_counter();instance,provenance=build_instance(catalog,request,Deadline(budget))
            prep=time.perf_counter()-started
            from dataclasses import asdict
            requests.append({'room':room_index,'shortlist_limit':limit,'request':asdict(request),'preprocessing_seconds':prep})
            if instance is None:
                runs.append({'room':room_index,'shortlist_limit':limit,'construction_result':provenance.to_dict()});continue
            name=f'room_{room_index}-limit_{limit}'
            write_instance(instance,output/'instances'/f'{name}.json')
            for method in ('greedy','beam','dp','milp'):
                for repeat in range(2):
                    started=time.perf_counter();result=solve_instance(instance,method,Deadline(max(0.,budget-prep)))
                    total=prep+time.perf_counter()-started
                    if result.valid_incumbent: assert not validate_queue(instance,result.queue)
                    for phase,log in enumerate(result.solver.pop('logs',[])):
                        (output/'logs'/f'{name}-{method}-{repeat}-{phase}.log').write_text(log['log'])
                    runs.append({'room':room_index,'shortlist_limit':limit,'actual_shortlist':len(instance.tracks),
                                 'method':method,'repeat':repeat,'budget_seconds':budget,'total_seconds':total,
                                 'budget_overhead':max(0.,total-budget),'result':result.to_dict()})
            print(name,'done',flush=True)
    report={'scope':'Artificial sampled likes, saved audio features, no independent listener labels. Not reproduction of the PDF experiments.',
            'model_hash':catalog.model_hash,'artifact_provenance':catalog.manifest['provenance'],
            'requests':requests,'runs':runs,'budget_seconds':budget}
    (output/'catalog-benchmark.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('evaluation/results/catalog-benchmark'));p.add_argument('--budget',type=float,default=2.)
    args=p.parse_args();run(args.output,args.budget)
