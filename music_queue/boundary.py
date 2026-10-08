"""Measured hard-cut endpoints; simple costs are unvalidated listening baselines."""
from __future__ import annotations

import numpy as np
import soundfile as sf


def signal_metrics(audio,sr):
    mono=audio.mean(axis=1) if audio.ndim==2 else audio
    if not len(mono): raise ValueError('Empty boundary audio')
    rms=float(np.sqrt(np.mean(mono**2)))
    frame=max(1,int(sr*.05))
    active=[float(np.sqrt(np.mean(mono[i:i+frame]**2)))>10**(-50/20)
            for i in range(0,len(mono),frame)]
    first=next((i for i,value in enumerate(active) if value),len(active))
    last=next((i for i,value in enumerate(reversed(active)) if value),len(active))
    return {'rms_dbfs':float(20*np.log10(max(rms,1e-12))),
            'leading_silence_seconds':min(len(mono)/sr,first*.05),
            'trailing_silence_seconds':min(len(mono)/sr,last*.05),
            'silence_threshold_dbfs':-50,'peak':float(np.max(np.abs(mono)))}


def read_endpoints(path,seconds=2.):
    with sf.SoundFile(path) as audio:
        count=max(1,int(audio.samplerate*seconds))
        intro=audio.read(min(count,len(audio)),dtype='float32',always_2d=True)
        audio.seek(max(0,len(audio)-count))
        outro=audio.read(count,dtype='float32',always_2d=True)
        return intro,outro,audio.samplerate


def track_boundary_metadata(path):
    intro,outro,sr=read_endpoints(path)
    a,b=signal_metrics(intro,sr),signal_metrics(outro,sr)
    return {'intro_rms_dbfs':a['rms_dbfs'],'outro_rms_dbfs':b['rms_dbfs'],
            'leading_silence_seconds':a['leading_silence_seconds'],
            'trailing_silence_seconds':b['trailing_silence_seconds']}


def simple_boundary_cost(previous,next_track):
    if previous.outro_rms_dbfs is None or next_track.intro_rms_dbfs is None:
        raise ValueError('boundary_cost needs measured endpoint metadata; explicitly migrate/rebuild artifacts')
    # Stated diagnostic scales, not learned or independently calibrated weights.
    jump=abs(previous.outro_rms_dbfs-next_track.intro_rms_dbfs)/20.
    silence=(previous.trailing_silence_seconds+next_track.leading_silence_seconds)/2.
    return -jump-silence
