"""Full eligible ranking plus an explicit, jointly feasible protected shortlist."""
from __future__ import annotations

from dataclasses import asdict,replace
import time

from .domain import QueueInstance,QueueResult,Status,fingerprint
from .objective import edge_value
from .preferences import predict_affinity
from .solvers.milp import feasible_selection
from .validation import conflict_details


def subset_instance(instance,track_ids):
    wanted=set(track_ids)
    indices=[a for a,t in enumerate(instance.tracks) if t.id in wanted]
    return replace(instance,tracks=tuple(instance.tracks[a] for a in indices),
                   utilities=tuple(tuple(row[a] for a in indices) for row in instance.utilities),
                   acceptance=tuple(tuple(row[a] for a in indices) for row in instance.acceptance),
                   transitions=tuple(tuple(instance.transitions[a][b] for b in indices) for a in indices),
                   anchor_values=tuple(instance.anchor_values[a] for a in indices) if instance.anchor_values else (),
                   candidate_provenance=tuple((t,reasons) for t,reasons in instance.candidate_provenance if t in wanted))


def build_instance(catalog,request,deadline,service_debt=None):
    started=time.perf_counter()
    blocked=set(request.excluded)|{t for l in request.listeners for t in l.blocked}
    eligible=[t for t in catalog.tracks if t.playable and t.id not in blocked]
    eligible.sort(key=lambda t:t.id)
    exclusions=[{'track_id':t.id,'reason':'explicit_block_or_session_exclusion' if t.id in blocked else 'unplayable'}
                for t in catalog.tracks if t not in eligible]
    if len(eligible)<request.queue_len or any(t not in {x.id for x in eligible} for t in request.locked_prefix):
        return None,QueueResult(Status.HARD_INFEASIBLE,request.queue_len,
                               termination_reason='Eligibility or locked-prefix conflict',
                               conflicts=[{'eligible_count':len(eligible),'exclusions':exclusions,
                                           'locked_prefix':request.locked_prefix}])
    values=[];labels=[];acceptance=[]
    for listener in request.listeners:
        row=[predict_affinity(catalog,listener,t.id,request.policy.predictor) for t in eligible]
        values.append(tuple(v for v,_ in row)); labels.append([label for _,label in row])
        acceptance.append(tuple(t.id in listener.accepted for t in eligible))
    indices=[catalog.song_index(t.id) for t in eligible]
    if deadline.expired:
        return None,QueueResult(Status.TIMEOUT_NO_SOLUTION,request.queue_len,termination_reason='Budget expired in ranking')
    # Candidate feasibility depends on selection rules, not sequencing. Avoid
    # building full-catalog transition blocks for a small final shortlist.
    transitions=((0.,)*len(eligible),)*len(eligible)
    anchor=()
    if request.current_track:
        previous=catalog.tracks[catalog.song_index(request.current_track)]
        anchor=tuple(request.policy.transition_weight*catalog.transition_score(previous.id,t.id,request.policy.transition_model)
                     -request.policy.same_folder_penalty*(previous.folder==t.folder) for t in eligible)
    debt=tuple((service_debt or {}).get(l.id,0.) for l in request.listeners)
    instance=QueueInstance(tuple(eligible),request.listeners,tuple(values),tuple(acceptance),
                            tuple(tuple(float(v) for v in row) for row in transitions),request.queue_len,
                            request.policy,request.locked_prefix,anchor,debt,catalog.model_hash,
                            fingerprint([asdict(l) for l in request.listeners]),revision=request.revision)
    # Full ranking is the reference. No sparse retrieval score can erase evidence.
    ranking=sorted(range(len(eligible)),key=lambda a:(-sum(row[a] for row in values),eligible[a].id))
    chosen={eligible[a].id for a in ranking[:max(request.candidate_limit,request.queue_len)]}
    cover,status=feasible_selection(instance,deadline)
    if not cover:
        return None,QueueResult(status,request.queue_len,termination_reason=(
            'Full eligible catalog conflicts with joint mandatory rules' if status==Status.HARD_INFEASIBLE else
            'Budget expired before a feasible covering selection; infeasibility is unknown'),
            conflicts=conflict_details(instance))
    chosen.update(cover)
    chosen.update(request.locked_prefix)
    # Keep valid previous choices during nested expansion, never change coefficients.
    chosen.update(t for t in request.incumbent if t in {x.id for x in eligible})
    if len(chosen)>30:
        return None,QueueResult(Status.RESOURCE_LIMIT,request.queue_len,
                               termination_reason='Protected shortlist exceeds 30-candidate request limit')
    reasons={}
    for t in chosen:
        reasons[t]=[]
        if t in cover: reasons[t].append('joint_feasible_cover')
        if t in request.locked_prefix: reasons[t].append('locked_prefix')
        if t in request.incumbent: reasons[t].append('retained_incumbent')
        if not reasons[t]: reasons[t].append('full_catalog_rank')
    instance=replace(instance,candidate_provenance=tuple(sorted((t,tuple(r)) for t,r in reasons.items())))
    shortlist=subset_instance(instance,chosen)
    shortlist_indices=[catalog.song_index(t.id) for t in shortlist.tracks]
    _,_,transition_block=catalog.transition_block(shortlist_indices,request.policy.transition_model)
    shortlist=replace(shortlist,transitions=tuple(tuple(float(v) for v in row) for row in transition_block))
    provenance={'full_eligible_count':len(eligible),'requested_shortlist_size':request.candidate_limit,
                'policy':asdict(request.policy),'transition_model':request.policy.transition_model,
                'actual_shortlist_size':len(chosen),'expanded_for_feasibility':len(chosen)>request.candidate_limit,
                'reference':'full_catalog_ranking','exclusions':exclusions,'cover':cover,
                'ranked_rows':[{'track_id':eligible[a].id,'song':eligible[a].title,'folder':eligible[a].folder,
                    'room_score':sum(row[a] for row in values)/len(values),
                    'listener_scores':{l.id:values[u][a] for u,l in enumerate(request.listeners)},
                    'evidence':{l.id:labels[u][a] for u,l in enumerate(request.listeners)}} for a in ranking],
                'selection_reasons':reasons,'preprocessing_seconds':time.perf_counter()-started,
                'feature_provenance':catalog.manifest.get('provenance',{}),
                'transition_signal':catalog.feature_schema.get('transition_signal','synthetic')}
    return shortlist,provenance
