from dataclasses import replace

import numpy as np
import pytest

from music_queue import Listener,Policy,SessionRequest,Status,Track
from music_queue.domain import Deadline
from music_queue.preferences import normalize_request,predict_affinity,parse_request
from music_queue.queueing import generate_queue
from music_queue.candidates import build_instance
from tests.test_artifacts import catalog


def test_display_name_collisions_duplicates_empty_profiles_and_strings():
    c=catalog()
    payload={'listeners':[{'id':'one','name':'room_score','liked':['t0']},
                          {'id':'two','name':'room_score','liked':['t2']}],
             'queue_len':2,'method':'dp'}
    result=generate_queue(c,payload)
    assert result.valid_incumbent and set(result.per_listener)=={'one','two'}
    assert result.requested_length==2
    payload['listeners'][1]['name']='song'
    assert generate_queue(c,payload).queue==result.queue
    for invalid in ([], 's0', None):
        payload['listeners'][1]['liked']=invalid
        assert generate_queue(c,payload).status==Status.INVALID_REQUEST
    payload['listeners'][1].update(id='one',liked=['t2'])
    assert generate_queue(c,payload).status==Status.INVALID_REQUEST


def test_duplicate_alias_seeds_and_known_positives_survive_opposite_pockets():
    c=catalog(np.repeat([[1.],[-1.]],118,axis=1))
    a=normalize_request(c,SessionRequest((Listener('a','A',('t0','t1')),),queue_len=1))
    b=normalize_request(c,replace(a,listeners=(Listener('a','A',('s0.mp3','t1','t0','s0')),)))
    assert a==b
    assert predict_affinity(c,a.listeners[0],'t0')[0]==1.
    constant=catalog(np.ones((2,118)))
    r=generate_queue(constant,{'room':{'A':['s0']},'queue_len':1,'method':'dp'})
    assert r.objective_components['listener_utilities']==[1.]


def test_full_ranking_preserves_minority_before_shortlist_and_shared_cover():
    c=catalog(np.repeat([[1.]]*60+[[-1.]],118,axis=1))
    request=SessionRequest((Listener('A','A',tuple(f't{i}' for i in range(60))),
                            Listener('B','B',tuple(f't{i}' for i in range(60))),
                            Listener('C','C',('t60',))),queue_len=2,candidate_limit=2,method='dp')
    r=generate_queue(c,request)
    assert r.valid_incumbent and 't60' in r.queue
    assert r.per_listener['C']['accepted_count']==1
    assert r.provenance['full_eligible_count']==61
    assert len(r.provenance['ranked_rows'])==61
    # One shared affirmative choice credits A and B simultaneously.
    assert r.per_listener['A']['accepted_count']>=1 and r.per_listener['B']['accepted_count']>=1


def test_explicit_caps_and_blocks_return_joint_conflict():
    c=catalog()
    request=SessionRequest((Listener('A','A',('t0',)),Listener('B','B',('t1',))),
                           queue_len=2,policy=Policy(folder_cap=1,discovery_budget=2),method='dp')
    result=generate_queue(c,request)
    assert result.status==Status.HARD_INFEASIBLE and result.conflicts
    block=replace(request,policy=Policy(discovery_budget=2),listeners=(
        Listener('A','A',('t0',),blocked=('t1',)),Listener('B','B',('t1',))))
    assert generate_queue(c,block).status==Status.HARD_INFEASIBLE


@pytest.mark.parametrize('field,value',[('queue_len',0),('queue_len',1.5),('candidate_limit',31),
    ('time_limit',float('nan')),('time_limit',0),('time_limit',True),('relative_gap',-1),
    ('locked_prefix','t0'),('method','bad')])
def test_invalid_request_boundaries(field,value):
    payload={'room':{'A':['s0']},'queue_len':1,field:value}
    assert generate_queue(catalog(),payload).status==Status.INVALID_REQUEST


def test_negative_affinity_is_not_affirmative_acceptance_and_discovery_is_opt_in():
    c=catalog()
    request=SessionRequest((Listener('A','A',('t0',)),),queue_len=2,method='dp')
    assert generate_queue(c,request).status==Status.HARD_INFEASIBLE
    r=generate_queue(c,replace(request,policy=Policy(discovery_budget=1)))
    assert r.valid_incumbent and r.per_listener['A']['accepted_count']==1
    for row in r.provenance['ranked_rows']:
        if row['track_id']!='t0':
            assert row['evidence']['A']=='predicted_acoustic_affinity'


def test_candidate_expansion_keeps_incumbent_and_frozen_coefficients():
    c=catalog()
    req=normalize_request(c,SessionRequest((Listener('A','A',('t0','t1','t2')),),queue_len=1,candidate_limit=1,
                                           incumbent=('t2',),method='dp'))
    small,_=build_instance(c,req,Deadline(5))
    bigger,_=build_instance(c,replace(req,candidate_limit=3),Deadline(5))
    assert 't2' in {t.id for t in small.tracks}
    assert {t.id for t in small.tracks}<={t.id for t in bigger.tracks}
    assert small.model_hash==bigger.model_hash and small.evidence_hash==bigger.evidence_hash
