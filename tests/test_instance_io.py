import json
import pytest
from music_queue.instance_io import read_instance,write_instance
from tests.test_solvers import instance


def test_frozen_instance_roundtrip_and_checksum(tmp_path):
    path=tmp_path/'instance.json';ins=instance()
    write_instance(ins,path)
    assert read_instance(path)==ins
    data=json.loads(path.read_text());data['instance']['utilities'][0][0]+=1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='checksum'):
        read_instance(path)
