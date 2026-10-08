"""Prepare local blinded instruments. Blank ratings are never replaced by model labels."""
from __future__ import annotations
import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import numpy as np
import soundfile as sf

from music_queue import load_catalog
from music_queue.paths import SONGS_DIR
from music_queue.boundary import signal_metrics,read_endpoints,track_boundary_metadata

SONG_FIELDS=['group_id','session_id','listener_id','trial_id','track_id','session_acceptance',
             'ordinary_dislike','do_not_play','familiarity','preference_strength_0_to_5','context','consent','split']
TRANSITION_FIELDS=['group_id','session_id','listener_id','trial_id','boundary_quality_1_to_5','comment','consent','split']
SESSION_FIELDS=['group_id','session_id','listener_id','trial_id','overall_acceptance_1_to_5',
                'strongly_unwanted_seconds','first_acceptable_wait_seconds','skips','manual_edits',
                'curation_seconds','discovery_acceptance','comment','consent','split']
ORDER_FIELDS=['group_id','session_id','listener_id','trial_id','order_quality_1_to_5','comment','consent','split']


def boundary_metrics(audio,sr):
    return signal_metrics(audio,sr)


def render_hard_cut(first,second,output,seconds=8.,sample_rate=22050):
    """Actual audible tail->head, no padding, fades, loudness normalization or gap."""
    import librosa
    _,outgoing,out_sr=read_endpoints(first,seconds)
    incoming,_,in_sr=read_endpoints(second,seconds)
    tail=librosa.resample(outgoing.mean(axis=1),orig_sr=out_sr,target_sr=sample_rate) if out_sr!=sample_rate else outgoing.mean(axis=1)
    head=librosa.resample(incoming.mean(axis=1),orig_sr=in_sr,target_sr=sample_rate) if in_sr!=sample_rate else incoming.mean(axis=1)
    sr=sample_rate
    if not len(tail) or not len(head): raise ValueError('Empty transition audio')
    sf.write(output,np.concatenate([tail,head]),sr,subtype='PCM_16')
    outgoing,incoming=boundary_metrics(tail,sr),boundary_metrics(head,sr)
    return {'operator':'hard_cut','requested_excerpt_seconds_per_track':seconds,
            'cut_sample':len(tail),'sample_rate':sr,'duration_seconds':(len(tail)+len(head))/sr,
            'outgoing':outgoing,'incoming':incoming,'loudness_jump_db':incoming['rms_dbfs']-outgoing['rms_dbfs']}


def _write_csv(path,fields,rows):
    with Path(path).open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def prepare(output,catalog,render_audio=False,seed=20261008,song_root=SONGS_DIR):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    rng=random.Random(seed)
    track_ids=[t.id for t in catalog.tracks];rng.shuffle(track_ids)
    tracks={t.id:t for t in catalog.tracks}
    # Sampling is a pilot-instrument choice, not a power calculation.
    sample=track_ids[:min(24,len(track_ids))]
    song_rows=[{'trial_id':f'song_{i:03}','track_id':id} for i,id in enumerate(sample)]
    pairs=list(zip(sample[::2],sample[1::2]));rng.shuffle(pairs)
    transitions=[];key=[]
    for i,(a,b) in enumerate(pairs):
        trial=f'boundary_{i:03}'
        row={'trial_id':trial};transitions.append(row)
        record={'trial_id':trial,'first_track_id':a,'second_track_id':b,'operator':'hard_cut',
                'method_label_hidden':True,'predicted_pooled_affinity':catalog.transition_score(a,b)}
        if render_audio:
            sources=[]
            for id in (a,b):
                source=(Path(song_root)/tracks[id].source).resolve()
                if not source.is_relative_to(Path(song_root).resolve()):
                    raise ValueError('Source escapes local audio catalog')
                sources.append(source)
            filename=f'{trial}.wav'
            record['audio_file']=filename
            record['boundary_metrics']=render_hard_cut(*sources,output/filename)
        key.append(record)
    _write_csv(output/'song_judgments.csv',SONG_FIELDS,song_rows)
    _write_csv(output/'transition_judgments.csv',TRANSITION_FIELDS,transitions)
    _write_csv(output/'session_judgments.csv',SESSION_FIELDS,[{'trial_id':'session_trial_000'}])
    # Hold selection fixed to isolate order quality. An artificial zero-utility
    # listener is a mathematical scaffold, not an invented human preference.
    from dataclasses import replace
    from music_queue import Track,Listener,Policy,QueueInstance
    from music_queue.domain import Deadline
    from music_queue.queueing import solve_instance
    fixed_tracks=tuple(tracks[id] for id in sample[:min(4,len(sample))])
    if len(fixed_tracks)>=2:
        indices=[catalog.song_index(t.id) for t in fixed_tracks]
        _,_,pooled=catalog.transition_block(indices)
        n=len(fixed_tracks)
        scaffold=QueueInstance(fixed_tracks,(Listener('order_control','Order control',()),),((0.,)*n,),
                              ((False,)*n,),tuple(tuple(float(v) for v in row) for row in pooled),n,
                              Policy(required_count=0,discovery_budget=n,objective='affinity'))
        pooled_queue=solve_instance(scaffold,'dp',Deadline(5.)).queue
        ordered={'pooled_affinity':pooled_queue}
        shuffled=list(t.id for t in fixed_tracks);rng.shuffle(shuffled)
        ordered['no_sequencing']=tuple(shuffled)
        if render_audio:
            from music_queue.boundary import simple_boundary_cost
            measured=tuple(replace(t,**track_boundary_metadata(Path(song_root)/t.source)) for t in fixed_tracks)
            costs=tuple(tuple(simple_boundary_cost(a,b) for b in measured) for a in measured)
            boundary_instance=replace(scaffold,tracks=measured,transitions=costs)
            ordered['simple_boundary_cost']=solve_instance(boundary_instance,'dp',Deadline(5.)).queue
        methods=list(ordered);rng.shuffle(methods);order_trials=[]
        for i,method in enumerate(methods):
            trial=f'order_{i:03}'
            q=ordered[method]
            assert set(q)=={t.id for t in fixed_tracks}
            entry={'trial_id':trial,'hidden_method':method,'queue':q,'selection_held_fixed':True,'excerpts':[]}
            if render_audio:
                for edge,(a,b) in enumerate(zip(q,q[1:])):
                    file=f'{trial}-edge-{edge}.wav'
                    render_hard_cut(Path(song_root)/tracks[a].source,Path(song_root)/tracks[b].source,output/file)
                    entry['excerpts'].append(file)
            key.append(entry);order_trials.append({'trial_id':trial})
        _write_csv(output/'fixed_selection_order_judgments.csv',ORDER_FIELDS,order_trials)
    (output/'private_study_key.json').write_text(json.dumps({'seed':seed,'model_hash':catalog.model_hash,
        'scope':'Independent judgments still required. Do not show prediction values to raters.',
        'pairs':key,'tracks':[{'track_id':id,'title':tracks[id].title,'recording_family':tracks[id].recording_family}
                              for id in sample]},indent=2)+'\n')
    (output/'study_manifest.json').write_text(json.dumps({'protocol_version':'pilot-v1','seed':seed,
        'model_hash':catalog.model_hash,'playback_operator':'hard_cut','audio_rendered':render_audio,
        'judgments_collected':False,'song_trials':len(song_rows),'transition_trials':len(transitions),
        'rating_fields_are_blank':True,'methods':['round_robin','shared_approval','beam','milp'],
        'order_comparisons':'Fixed selected tracks: pooled affinity, no sequencing, and measured boundary cost when audio is rendered',
        'evaluation_unit':'group/session','splits':'Freeze transforms/weights; reserve held-out listeners or recording families for the declared generalization claim'},indent=2)+'\n')


def read_judgments(path):
    with Path(path).open(newline='') as stream: rows=list(csv.DictReader(stream))
    completed=[]
    for row in rows:
        if not row.get('session_acceptance'): continue
        if row['session_acceptance'] not in {'yes','no','unknown'}: raise ValueError('Invalid acceptance judgment')
        if row.get('consent')!='yes': raise ValueError('Completed judgment requires explicit consent')
        if not all(row.get(field) for field in ('group_id','session_id','listener_id','track_id','split')):
            raise ValueError('Completed judgment requires anonymous group/session/listener identity and split')
        if row['split'] not in {'train','test','pilot'}:
            raise ValueError('Split must be train, test or pilot')
        for field in ('ordinary_dislike','do_not_play','familiarity'):
            if row.get(field) not in {'yes','no','unknown'}: raise ValueError(f'Invalid {field}')
        strength=row.get('preference_strength_0_to_5')
        if strength and (not strength.isdigit() or not 0<=int(strength)<=5):
            raise ValueError('Preference strength must be from 0 to 5')
        completed.append(row)
    return completed


def evaluate_judgments(catalog,path):
    from music_queue.preferences import predict_affinity
    from music_queue import Listener
    rows=read_judgments(path)
    if not rows:
        return {'status':'NO_JUDGMENTS','completed':0,'claim':'No preference validity or listener benefit established'}
    groups={}
    for row in rows:
        key=(row['listener_id'],row['session_id'])
        groups.setdefault(key,[]).append(row)
    predictions=[]
    for (listener,session),observations in groups.items():
        training=tuple(sorted({catalog.track_id(row['track_id']) for row in observations
                               if row['split']=='train' and row['session_acceptance']=='yes'}))
        if not training: continue
        profile=Listener(listener,'Anonymous',training)
        for row in observations:
            id=catalog.track_id(row['track_id'])
            if row['split']!='test' or row['session_acceptance']=='unknown' or id in training: continue
            value={method:predict_affinity(catalog,profile,id,method)[0]
                   for method in ('maximum','top_two','pockets')}
            predictions.append({'listener_id':listener,'session_id':session,'track_id':id,
                                'accepted':row['session_acceptance']=='yes','predictions':value,
                                'profile_size':len(training)})
    # Export raw held-out predictions for group-level analysis. No probability
    # calibration or significance is fabricated from a tiny convenience sample.
    return {'status':'RAW_HELD_OUT_PREDICTIONS','completed':len(rows),'test_predictions':predictions,
            'claim':'Inspect participant/session-level uncertainty before drawing conclusions'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('output/study'))
    p.add_argument('--render-audio',action='store_true');p.add_argument('--evaluate',type=Path)
    args=p.parse_args();c=load_catalog()
    if args.evaluate:
        print(json.dumps(evaluate_judgments(c,args.evaluate),indent=2))
    else:
        prepare(args.output,c,args.render_audio);print(f'Prepared blank instruments at {args.output}; no listener evidence collected.')
