"""Synthetic checks on isolated, transcribed source extracts.
No saved music catalog, audio, CBC solve, or listener experiment is executed.
Run: python diagnostics.py
"""
from __future__ import annotations
import itertools, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, help='Optional local checkout of the reviewed commit. Executes actual upstream functions instead of source extracts.')
args = parser.parse_args()
source_mode = 'isolated_source_extracts'
if args.repo:
    import subprocess
    ref = subprocess.run(['git', '-C', str(args.repo), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if ref != 'e637be5f78567ea24f04cf0734286f357fef7d74':
        raise SystemExit(f'Expected reviewed commit e637be5; found {ref}. Use a separate checkout, without modifying your working project.')
    sys.path.insert(0, str(args.repo.resolve()))
    from music_queue import queueing as _q
    from music_queue.catalog import SongCatalog
    for _name in ('user_score','room_score','rank_room_candidates','build_retrieval_frame',
                  'effective_max_songs_per_folder','select_candidate_shortlist_with_details',
                  'user_representation_feasible','user_representation_sets','ranked_user_columns',
                  'solve_queue_beam','score_queue','validate_room'):
        globals()[_name] = getattr(_q, _name)
    class Catalog(SongCatalog):
        def __init__(self, embeddings, names, folders, intro=None, outro=None):
            super().__init__(embeddings=embeddings, names=names, folders=folders,
                             intro_embeddings=intro, outro_embeddings=outro)
    source_mode = 'actual_upstream_functions_at_reviewed_commit'
else:
    from source_extracts import *

findings=[]
def record(case, kind, observation):
    findings.append({'case':case,'kind':kind,'observation':observation})
def simple(values, names=None, folders=None, **kwargs):
    names=names or [f's{i}' for i in range(len(values))]
    return Catalog(np.repeat(np.asarray(values,dtype=float)[:,None],118,axis=1),names,folders or ['F']*len(values),**kwargs)

# Existing-report findings: independent small constructed inputs, not its scripts.
c=simple([1]*60+[-1]); seeds=c.names[:60].tolist()
ret,rank=rank_room_candidates(c,{'A':seeds,'B':seeds,'minority':['s60']})
assert 's60' in set(ret.song) and 's60' not in set(rank.song)
record('E1','independent counterexample to same mechanism',{'catalog_songs':61,'ranked':len(rank),'minority_seed_retrieved':True,'minority_seed_ranked':False,'best_remaining_minority_affinity':float(rank['minority'].max())})

cap_df=pd.DataFrame({'song':['a','b'],'folder':['X','X'],'room_score':[1.,1.]})
assert effective_max_songs_per_folder(cap_df,2,1) is None
record('E2','reproduced pure-function behavior',{'requested_cap':1,'effective_cap':None})
reps={'A':{0},'B':{1}}; folders=['X','X','Y']
rep_ok=user_representation_feasible(reps,3,2)
joint_ok=any(all(set(ss)&s for s in reps.values()) and max([sum(folders[i]==f for i in ss) for f in set(folders)])<=1 for ss in itertools.combinations(range(3),2))
assert rep_ok and not joint_ok
record('E3','pure feasibility function plus independent exhaustive check',{'representation_only_feasible':rep_ok,'jointly_feasible':joint_ok})
neg=pd.DataFrame({'song':['a','b','c'],'folder':['X','Y','Z'],'room_score':[-.8,-.9,-1.],'A':[-.8,-.9,-1.]})
assert user_representation_sets(neg,1)=={'A':{0}}
record('E4','reproduced pure-function behavior',{'represented_candidate_score':-.8,'warning':'Negative affinity is not a verified dislike.'})
assert not user_representation_feasible(reps,2,1)
record('E5','representation check only; downstream omission checked in source',{'representation_check':False})
intro=np.repeat(np.array([[10.],[11.]]),118,axis=1)
outro=np.repeat(np.array([[9.],[10.]]),118,axis=1)
c=simple([0,1],intro=intro,outro=outro)
assert np.array_equal(outro[1],intro[0]) and np.isclose(c.transition_score('s1','s0'),-1)
record('E6','normalization/transition adapter counterexample',{'identical_raw_segments':True,'transition':c.transition_score('s1','s0')})
c=simple([1,-1]); before=user_score(c,['s0'],'s0'); after=user_score(c,['s0','s1'],'s0')
assert np.isclose(before,1) and np.isclose(after,0)
record('E7','reproduced pure-function behavior',{'one_seed_score':before,'two_opposite_seeds_score':after})
record('E9','objective algebra; not CBC runtime',{'weight':.25,'penalty':.1,'IP_subtracts':.025,'shared_scorer_subtracts':.1,'difference':.075})

# Additional issues.
_,rank=rank_room_candidates(c,{'room_score':['s0'],'B':['s1']})
a=rank.loc[rank.song=='s0'].iloc[0]
truth=room_score(c,{'room_score':['s0'],'B':['s1']},'s0')[0]
assert not np.isclose(float(a.room_score),truth)
_,corrupt=rank_room_candidates(c,{'song':['s0'],'B':['s1']})
record('N1','reserved listener names collide with metadata',{'correct_group_mean':truth,'stored_room_score':float(a.room_score),'song_values_with_listener_named_song':corrupt.song.tolist(),'protected_user_columns':ranked_user_columns(rank)})
dup=user_score(c,['s0','s1','s0'],'s0')
assert np.isclose(dup,1) and np.isclose(after,0)
record('N2','duplicate seed changes weight without new evidence',{'unique_seeds':after,'duplicated_positive_seed':dup})

coverage=pd.DataFrame({'song':['shared','redundant','minority'],'folder':['X','Y','Z'],'room_score':[.66,.60,.98/3],'A':[.99,.90,0.],'B':[.99,.90,0.],'C':[0.,0.,.98]})
sl,why=select_candidate_shortlist_with_details(coverage,2,preserve_user_fraction=1)
assert set(sl.song)=={'shared','redundant'}
record('N3','preservation spends distinct-song budget on already-covered users',{'chosen':sl.song.tolist(),'selection_reasons':why,'alternative_covering_everyone':['shared','minority'],'explicit_test_acceptance_cutoff':.9})

collision=simple([1,-1],names=['same','same'],folders=['X','Y'])
assert collision.song_index('same')==1
case_collision=simple([1,-1],names=['Song','song'])
assert case_collision.song_index('song')==0
record('N4','track identity alias collisions',{'identical_names_resolve_to_index':collision.song_index('same'),'case_distinct_second_track_resolves_to_index':case_collision.song_index('song')})
assert len(c.nearest_neighbors('s0',k=0))==1
record('N5','zero-neighbor boundary',{'requested':0,'returned':len(c.nearest_neighbors('s0',k=0))})

try:
    Catalog(np.array([[0.]*78,[1.]*78]),['a','b'],['F','F'],intro=np.array([[0.]*78,[1.]*78]),outro=np.array([[1.]*78,[0.]*78]))
except ValueError as exc:
    record('N6','feature schema mismatch for n_mfcc=20',{'error':str(exc).split('\n')[0],'features':78,'hardcoded_chroma_slice':[80,104]})
else:
    raise AssertionError('Expected empty chroma slice failure')

mismatch=simple([0,1,2],intro=intro,outro=outro)
assert mismatch.transition_similarity.shape==(2,2)
try:
    mismatch.transition_score('s2','s0')
except IndexError as exc:
    record('N7','unvalidated transition row counts',{'catalog_songs':3,'transition_shape':[2,2],'lookup_error':type(exc).__name__})
else:
    raise AssertionError('Expected mismatched row lookup failure')
partial=simple([0,1],intro=intro,outro=None)
assert np.array_equal(partial.transition_similarity,partial.retrieval_similarity)
record('N8','missing one segment array silently changes algorithm',{'fallback_equals_retrieval':True})

small=simple([0,1]); grown=simple([0,1,100])
assert np.isclose(small.retrieval_similarity[0,1],-1) and np.isclose(grown.retrieval_similarity[0,1],1)
record('N9','catalog-dependent transform changes unchanged pair',{'pair_before_catalog_growth':float(small.retrieval_similarity[0,1]),'pair_after_catalog_growth':float(grown.retrieval_similarity[0,1]),'interpretation':'A calibration/stability concern, not necessarily invalid for an explicitly transductive model.'})

start=time.perf_counter(); assert user_representation_feasible({'A':{19}},20,1); elapsed=time.perf_counter()-start
record('N10','exponential subset scan on a trivial feasible instance',{'songs':20,'required_song_index':19,'target_len':1,'subsets_visited':2**19+1,'seconds_this_isolated_run':elapsed,'same_problem_required_index_0_subsets':2})

r1=build_retrieval_frame(c,{'s0':{'A':.7}}).retrieval_score.iloc[0]
r2=build_retrieval_frame(c,{'s0':{'A':.7,'B':-.2}}).retrieval_score.iloc[0]
record('N11','sparse retrieval sums treat absent and negative evidence differently',{'score_before_more_retrieval_evidence':float(r1),'score_after_more_retrieval_evidence':float(r2)})

# A beam initial solution need not satisfy the IP's representation constraints.
c = simple([0,1,2], names=['a','b','c'], folders=['X','Y','Z'])
rank = pd.DataFrame({'song':['a','b','c'], 'folder':['X','Y','Z'],
                     'room_score':[1.,.9,.2], 'A':[1.,.9,0.], 'B':[0.,0.,1.]})
bq = solve_queue_beam(c, rank, queue_len=2, candidate_limit=3,
                      transition_weight=0., max_songs_per_folder=1)
reps = user_representation_sets(rank,1)
selected = {int(rank.index[rank.song == song][0]) for song in bq}
assert not all(selected & candidates for candidates in reps.values())
record('N12','beam initial solution misses an IP representation rule',
       {'beam_queue':bq,'unrepresented_users':[u for u,r in reps.items() if not selected&r]})

# The API accepts strings as profiles when each character is a valid song name.
c = simple([0,1], names=['a','b'])
validate_room(c, {'A':'ab'})
record('N13','missing room profile type validation',{'profile':'ab','accepted_as_two_seed_tracks':True})

# Current source clamps the queue length rather than reporting short supply.
bq = solve_queue_beam(c, pd.DataFrame({'song':['a','b'],'folder':['F','F'],'room_score':[1.,1.]}),
                      queue_len=5, candidate_limit=2, transition_weight=0.)
assert len(bq)==2
record('N14','unreported queue truncation',{'requested_length':5,'returned_length':len(bq)})

# A fixed pair can be dropped by relevance-only shortlisting despite its transition value.
c = simple([0,1,2], names=['a','b','bridge'], folders=['X','Y','Z'])
c.transition_similarity = np.array([[1.,-1.,1.],[-1.,1.,-1.],[1.,-1.,1.]])
rank = pd.DataFrame({'song':['a','b','bridge'],'folder':['X','Y','Z'],'room_score':[.51,.50,.49]})
qs = solve_queue_beam(c,rank,queue_len=2,candidate_limit=2,preserve_user_fraction=0.,max_songs_per_folder=1)
qf = solve_queue_beam(c,rank,queue_len=2,candidate_limit=3,preserve_user_fraction=0.,max_songs_per_folder=1)
rs = dict(zip(rank.song,rank.room_score))
small_score, full_score = score_queue(c,qs,rs), score_queue(c,qf,rs)
assert full_score > small_score
record('N15','candidate ranking misses useful transition endpoints',{'two_candidate_queue':qs,'three_candidate_queue':qf,'two_candidate_objective':small_score,'three_candidate_objective':full_score})

# A completely constant catalog maps a known seed to the zero standardized vector.
c = simple([1,1])
assert np.isclose(user_score(c,['s0'],'s0'),0.)
record('N16','constant features erase acoustic self-affinity',{'known_seed_user_affinity':user_score(c,['s0'],'s0'),'retrieval_still_injects_seed_similarity':1.})

out={'source_mode':source_mode,'scope':'Synthetic diagnostics on source extracts unless --repo is supplied. No saved catalog, original benchmark scripts, CBC run, or listener judgments.','commit':'e637be5f78567ea24f04cf0734286f357fef7d74','python':sys.version.split()[0],'numpy':np.__version__,'pandas':pd.__version__,'results':findings}
Path(__file__).with_name('diagnostic_results.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
