from dataclasses import replace
import pytest

from music_queue import Listener,Policy,SessionRequest,Status
from music_queue.preferences import normalize_request
from music_queue.session import SessionState
from tests.test_artifacts import catalog


def setup_session():
    c=catalog()
    listeners=(Listener('a','Alex',('t0','t2')),Listener('b','Alex',('t1','t2')))
    state=SessionState('session',repeat_window=20)
    state.set_membership(c,listeners,0)
    return c,state


def test_rolling_history_membership_and_promises_persist():
    c,s=setup_session()
    req=SessionRequest(s.active_listeners,queue_len=2,method='dp',revision=s.revision)
    r=s.replan(c,req)
    assert r.valid_incumbent and s.promised_next==r.queue[0]
    history_before=s.snapshot()['histories']
    r2=s.replan(c,replace(req,revision=s.revision))
    assert r2.queue[0]==r.queue[0] and s.snapshot()['histories']==history_before
    first=r.queue[0]
    s.record_playback(c,first,120.,s.revision)
    assert all(h.played_seconds==120 for h in s.histories.values())
    old=s.snapshot()['histories']
    s.set_membership(c,(s.active_listeners[0],Listener('new','New',('t2',))),s.revision)
    assert s.snapshot()['histories']['a']==old['a'] and s.snapshot()['histories']['b']==old['b']
    assert s.histories['new'].played_seconds==0
    r3=s.replan(c,SessionRequest(s.active_listeners,queue_len=1,revision=s.revision,method='dp'))
    assert not r3.valid_incumbent or first not in r3.queue


def test_stale_revision_and_explicit_promise_override():
    c,s=setup_session()
    r=s.replan(c,SessionRequest(s.active_listeners,queue_len=1,revision=s.revision,method='dp'))
    with pytest.raises(ValueError,match='Stale'):
        s.override_promise(0)
    wrong=next(t.id for t in c.tracks if t.id!=s.promised_next)
    with pytest.raises(ValueError,match='override'):
        s.record_playback(c,wrong,10.,s.revision)
    s.override_promise(s.revision)
    s.record_playback(c,wrong,10.,s.revision)
    assert s.current_track==wrong


def test_feedback_updates_evidence_and_invalidates_old_results(monkeypatch):
    import music_queue.session as module
    c,s=setup_session()
    original=module.generate_queue
    def changed(catalog,request,debt):
        s.feedback(c,'a','t1','accept',s.revision)
        return original(catalog,request,debt)
    monkeypatch.setattr(module,'generate_queue',changed)
    r=s.replan(c,SessionRequest(s.active_listeners,queue_len=1,revision=s.revision,method='dp'))
    assert r.status==Status.STALE_RESULT and not s.queue
    assert 't1' in s.active_listeners[0].accepted


def test_service_debt_and_disliked_seconds_use_actual_playback():
    c,s=setup_session()
    s.feedback(c,'b','t0','dislike',s.revision)
    s.record_playback(c,'t0',90,s.revision)
    assert s.histories['b'].debt_seconds==45 and s.histories['b'].disliked_seconds==90
    assert s.histories['a'].accepted_seconds==90
    s.record_playback(c,'t1',60,s.revision)
    assert s.histories['a'].debt_seconds==30 and s.histories['b'].debt_seconds==15
