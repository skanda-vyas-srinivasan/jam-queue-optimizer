from dataclasses import replace
import json

import numpy as np
import pytest

from music_queue.artifact_store import fit_transform,load_generation,publish_generation,schema
from music_queue.catalog import SongCatalog
from music_queue.domain import Track,fingerprint


def catalog(values=None,*,n_mfcc=40,tracks=None,transforms=None):
    if values is None:
        values=np.arange(3*schema(n_mfcc)['dimensions']).reshape(3,-1)
    values=np.asarray(values,float)
    n=len(values)
    tracks=tracks or tuple(Track(f't{i}',f's{i}','F') for i in range(n))
    return SongCatalog(values,values+1,values-1,np.array([t.title for t in tracks]),
                       np.array([t.folder for t in tracks]),tracks,schema(n_mfcc),transforms)


def test_nondefault_schema_and_shared_segment_coordinates():
    c=catalog(n_mfcc=20)
    assert c.embeddings.shape==(3,78)
    assert c.feature_schema['slices']['chroma']==[40,64]
    c=SongCatalog(np.zeros((2,118)),np.repeat([[10],[12]],118,axis=1),
                  np.repeat([[9],[10]],118,axis=1),np.array(['a','b']),np.array(['F','F']))
    assert c.transition_score('b','a')==pytest.approx(1.)


def test_missing_partial_mismatched_and_nonfinite_arrays_rejected():
    a=np.zeros((3,118)); names=np.array(['a','b','c']); folders=np.array(['F']*3)
    for intro,outro in ((None,a),(a,None),(a[:2],a),(a,np.full_like(a,np.nan))):
        with pytest.raises(ValueError):
            SongCatalog(a,intro,outro,names,folders)
    with pytest.raises(ValueError,match='schema'):
        SongCatalog(a[:,:78],a[:,:78],a[:,:78],names,folders)


def test_ambiguous_titles_remain_addressable_by_id():
    tracks=(Track('one','same','X'),Track('two','same','Y'),Track('three','SAME','Z'))
    c=catalog(tracks=tracks)
    assert c.song_index('two')==1
    with pytest.raises(ValueError,match='Ambiguous'):
        c.song_index('same')
    with pytest.raises(ValueError,match='Duplicate titles'):
        SongCatalog(c.embeddings,c.intro_embeddings,c.outro_embeddings,c.names,c.folders)


def test_frozen_transform_growth_and_row_permutation_invariance():
    a=np.repeat([[0.],[1.]],118,axis=1)
    t={'retrieval':fit_transform(a),'transition':fit_transform(np.vstack([a+1,a-1]))}
    before=catalog(a,transforms=t)
    after=catalog(np.vstack([a,np.full((1,118),100.)]),transforms=t)
    assert after.retrieval_similarity[0,1]==pytest.approx(before.retrieval_similarity[0,1])
    indices=[2,0,1]; original=catalog()
    reordered=SongCatalog(original.embeddings[indices],original.intro_embeddings[indices],
                         original.outro_embeddings[indices],original.names[indices],original.folders[indices],
                         tuple(original.tracks[i] for i in indices),original.feature_schema,original.transforms)
    assert reordered.transition_score('t0','t1')==pytest.approx(original.transition_score('t0','t1'))
    assert reordered.retrieval_similarity[reordered.song_index('t0'),reordered.song_index('t1')]==pytest.approx(original.retrieval_similarity[0,1])


def test_zero_neighbors_and_bad_counts():
    c=catalog()
    assert c.nearest_neighbors('t0',0).empty
    with pytest.raises(ValueError): c.nearest_neighbors('t0',-1)
    with pytest.raises(ValueError): c.nearest_neighbors('t0',True)


def test_atomic_generation_and_checksums(tmp_path,monkeypatch):
    c=catalog(n_mfcc=20)
    arrays={name:getattr(c,name) for name in ('embeddings','intro_embeddings','outro_embeddings')}
    first=publish_generation(tmp_path,arrays,c.tracks,c.feature_schema)
    loaded,tracks,m=load_generation(tmp_path)
    assert tracks==c.tracks and m['generation']==first['generation']
    assert np.array_equal(loaded['embeddings'],c.embeddings)
    original=np.save
    def fail(*args,**kwargs): raise OSError('interrupted writer')
    monkeypatch.setattr(np,'save',fail)
    with pytest.raises(OSError): publish_generation(tmp_path,arrays,c.tracks,c.feature_schema)
    assert load_generation(tmp_path)[2]['generation']==first['generation']
    monkeypatch.setattr(np,'save',original)
    directory=tmp_path/'generations'/first['generation']
    (directory/'intro_embeddings.npy').write_bytes(b'wrong-generation')
    with pytest.raises(ValueError,match='Checksum'):
        load_generation(tmp_path)


def test_legacy_migration_is_explicit_and_manifest_row_alignment(tmp_path):
    with pytest.raises(ValueError,match='migration'):
        load_generation(tmp_path)
    c=catalog(); arrays={n:getattr(c,n) for n in ('embeddings','intro_embeddings','outro_embeddings')}
    m=publish_generation(tmp_path,arrays,c.tracks,c.feature_schema)
    m['row_order']=list(reversed(m['row_order']))
    m.pop('manifest_hash'); m['manifest_hash']=fingerprint(m)
    text=json.dumps(m)
    (tmp_path/'manifest.json').write_text(text)
    (tmp_path/'generations'/m['generation']/'manifest.json').write_text(text)
    with pytest.raises(ValueError,match='row order'):
        load_generation(tmp_path)


def test_measured_boundary_cost_uses_declared_loudness_and_silence_units():
    tracks=tuple(Track(f't{i}',f's{i}','F',intro_rms_dbfs=-10.,outro_rms_dbfs=-20.,
                       leading_silence_seconds=.2,trailing_silence_seconds=.4) for i in range(3))
    c=catalog(tracks=tracks)
    assert c.transition_score('t0','t1','boundary_cost')==pytest.approx(-.8)
    assert c.transition_score('t0','t1','none')==0
