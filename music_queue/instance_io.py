"""Portable frozen synthetic instances; no audio files are needed for reproduction."""
from dataclasses import asdict
import json
from pathlib import Path

from .domain import Listener,Policy,QueueInstance,Track,fingerprint


def write_instance(instance,path):
    Path(path).write_text(json.dumps({'format_version':1,'instance':asdict(instance),
                                     'instance_hash':instance.hash},indent=2,allow_nan=False)+'\n')


def read_instance(path):
    payload=json.loads(Path(path).read_text())
    if payload.get('format_version')!=1:
        raise ValueError('Unsupported instance format')
    values=payload['instance']
    if fingerprint(values)!=payload['instance_hash']:
        raise ValueError('Instance checksum mismatch')
    values['tracks']=tuple(Track(**t) for t in values['tracks'])
    values['listeners']=tuple(Listener(**l) for l in values['listeners'])
    values['policy']=Policy(**values['policy'])
    instance=QueueInstance(**values)
    return instance
