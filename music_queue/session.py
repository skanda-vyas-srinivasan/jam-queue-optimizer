"""Revision-checked rolling sessions. Only confirmed playback advances history."""
from __future__ import annotations

from dataclasses import asdict,dataclass,field,replace
import threading

from .domain import Listener,QueueResult,Status
from .preferences import normalize_request
from .queueing import generate_queue


@dataclass
class ServiceHistory:
    played_seconds: float = 0.
    accepted_seconds: float = 0.
    disliked_seconds: float = 0.
    wait_seconds: float = 0.
    debt_seconds: float = 0.


@dataclass
class SessionState:
    id: str
    revision: int = 0
    active_listeners: tuple[Listener,...] = ()
    histories: dict[str,ServiceHistory] = field(default_factory=dict)
    played_tracks: list[str] = field(default_factory=list)
    played_artists: list[str | None] = field(default_factory=list)
    current_track: str | None = None
    promised_next: str | None = None
    queue: tuple[str,...] = ()
    repeat_window: int = 20
    artist_cooldown: int = 0
    _lock: threading.RLock = field(default_factory=threading.RLock,repr=False)

    def snapshot(self):
        with self._lock:
            return {'id':self.id,'revision':self.revision,
                    'listeners':[asdict(l) for l in self.active_listeners],
                    'histories':{u:asdict(h) for u,h in self.histories.items()},
                    'played_tracks':list(self.played_tracks),'current_track':self.current_track,
                    'promised_next':self.promised_next,'queue':self.queue,
                    'repeat_window':self.repeat_window,'artist_cooldown':self.artist_cooldown}

    def set_membership(self,catalog,listeners,expected_revision):
        from .domain import SessionRequest
        normalized=normalize_request(catalog,SessionRequest(tuple(listeners),queue_len=1))
        with self._lock:
            self._check_revision(expected_revision)
            self.active_listeners=normalized.listeners
            for listener in self.active_listeners:
                self.histories.setdefault(listener.id,ServiceHistory())
            self.revision+=1

    def _check_revision(self,expected):
        if type(expected) is not int:
            raise ValueError('Session revision must be an integer')
        if expected!=self.revision:
            raise ValueError(f'Stale session revision {expected}; current revision is {self.revision}')

    def replan(self,catalog,request):
        with self._lock:
            self._check_revision(request.revision)
            request=normalize_request(catalog,request)
            if request.listeners!=self.active_listeners:
                return QueueResult(Status.INVALID_REQUEST,request.queue_len,
                                   termination_reason='Apply session listeners and evidence explicitly before replanning')
            if self.promised_next and request.locked_prefix and request.locked_prefix[0]!=self.promised_next:
                return QueueResult(Status.INVALID_REQUEST,request.queue_len,
                                   termination_reason='Promised next track requires an explicit override')
            locked=request.locked_prefix or ((self.promised_next,) if self.promised_next else ())
            repeats=self.played_tracks[-self.repeat_window:] if self.repeat_window else []
            cooled={artist for artist in self.played_artists[-self.artist_cooldown:] if artist is not None} if self.artist_cooldown else set()
            excluded=set(request.excluded)|set(repeats)|{t.id for t in catalog.tracks if t.artist in cooled}
            if self.current_track:
                excluded.add(self.current_track)
            revision=self.revision
            req=replace(request,listeners=self.active_listeners,locked_prefix=locked,
                        current_track=self.current_track,excluded=tuple(excluded),incumbent=self.queue)
            # Debt uses seconds beyond an equal share of affirmative exposure,
            # normalized to 180-second units. It persists for departing listeners.
            debt={u:h.debt_seconds/180. for u,h in self.histories.items()}
        result=generate_queue(catalog,req,debt)
        with self._lock:
            if self.revision!=revision:
                return QueueResult(Status.STALE_RESULT,request.queue_len,
                                   termination_reason='A newer membership/playback/feedback action superseded this solve',
                                   revision=self.revision)
            if result.valid_incumbent:
                self.queue=result.queue
                self.promised_next=result.queue[0]
                self.revision+=1
                result.revision=self.revision
            return result

    def override_promise(self,expected_revision):
        with self._lock:
            self._check_revision(expected_revision)
            self.promised_next=None
            self.queue=()
            self.revision+=1

    def record_playback(self,catalog,track_id,seconds,expected_revision):
        import math
        if type(seconds) not in (float,int) or not math.isfinite(seconds) or seconds<=0:
            raise ValueError('Playback duration must be finite and positive')
        track=catalog.tracks[catalog.song_index(track_id)]
        if seconds>track.duration+1e-6:
            raise ValueError('Played seconds exceed track duration')
        with self._lock:
            self._check_revision(expected_revision)
            if self.promised_next and track.id!=self.promised_next:
                raise ValueError('Playback differs from promised next track; explicitly override first')
            if track.id in self.played_tracks[-self.repeat_window:] and self.repeat_window:
                raise ValueError('Recent track replay requires a different session repeat policy')
            active_count=len(self.active_listeners)
            for listener in self.active_listeners:
                history=self.histories[listener.id]
                history.played_seconds+=seconds
                accepted=track.id in set(listener.accepted)|set(listener.liked)
                if accepted:
                    history.accepted_seconds+=seconds
                    history.wait_seconds=0.
                else:
                    history.wait_seconds+=seconds
                if track.id in listener.disliked:
                    history.disliked_seconds+=seconds
                history.debt_seconds=max(0.,history.debt_seconds+seconds/max(1,active_count)-(seconds if accepted else 0.))
            self.played_tracks.append(track.id)
            self.played_artists.append(track.artist)
            self.current_track=track.id
            if self.queue and self.queue[0]==track.id:
                self.queue=self.queue[1:]
            self.promised_next=self.queue[0] if self.queue else None
            self.revision+=1

    def feedback(self,catalog,listener_id,track_id,label,expected_revision):
        if label not in {'accept','like','dislike','block','clear'}:
            raise ValueError('Unknown feedback label')
        track_id=catalog.track_id(track_id)
        with self._lock:
            self._check_revision(expected_revision)
            if listener_id not in {l.id for l in self.active_listeners}:
                raise ValueError('Unknown active listener')
            listeners=[]
            for listener in self.active_listeners:
                if listener.id!=listener_id:
                    listeners.append(listener);continue
                values={f:set(getattr(listener,f)) for f in ('liked','accepted','disliked','blocked')}
                if label!='block':
                    values={f:v-{track_id} for f,v in values.items()}
                if label!='clear':
                    target={'accept':'accepted','like':'liked','dislike':'disliked','block':'blocked'}[label]
                    values[target].add(track_id)
                candidate=replace(listener,**{f:tuple(sorted(v)) for f,v in values.items()})
                from .domain import SessionRequest
                normalized=normalize_request(catalog,SessionRequest((candidate,),queue_len=1)).listeners[0]
                listeners.append(normalized)
            self.active_listeners=tuple(listeners)
            self.revision+=1
