"""Explicitly wrap saved baseline arrays; never pretend these are regenerated audio."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import soundfile as sf
from music_queue.artifact_store import publish_generation, schema
from music_queue.domain import Track
from music_queue.paths import ARTIFACT_DIR, SONGS_DIR


def migrate(artifact_dir=ARTIFACT_DIR, song_root=SONGS_DIR):
    artifact_dir, song_root = Path(artifact_dir), Path(song_root)
    arrays = {n:np.load(artifact_dir/f'{n}.npy',allow_pickle=False)
              for n in ('embeddings','intro_embeddings','outro_embeddings')}
    names=np.load(artifact_dir/'song_names.npy',allow_pickle=False)
    folders=np.load(artifact_dir/'song_folders.npy',allow_pickle=False)
    tracks=[]
    for title,folder in zip(names,folders):
        matches=[p for p in (song_root/str(folder)).iterdir() if p.stem == title]
        if len(matches)!=1:
            raise ValueError(f'Cannot uniquely map legacy row: {folder}/{title}')
        path=matches[0]
        source=path.relative_to(song_root).as_posix()
        content_hash=hashlib.sha256(path.read_bytes()).hexdigest()
        info=sf.info(path)
        tracks.append(Track('trk_'+hashlib.sha256(source.encode()).hexdigest()[:24],str(title),str(folder),
                            source,info.duration,recording_family='audio_'+content_hash,content_hash=content_hash))
    return publish_generation(artifact_dir,arrays,tracks,schema(),provenance={
        'origin':'explicit_legacy_migration','audio_regenerated':False,
        'parameters':'Baseline source defaults; original files did not carry extraction metadata',
        'reviewed_commit':'e637be5f78567ea24f04cf0734286f357fef7d74'})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifact-dir',type=Path,default=ARTIFACT_DIR)
    p.add_argument('--songs-dir',type=Path,default=SONGS_DIR)
    args=p.parse_args()
    m=migrate(args.artifact_dir,args.songs_dir)
    print(f'Migrated {len(m["tracks"])} legacy rows to generation {m["generation"]}; audio was not regenerated.')
