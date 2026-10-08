# Rolling-session behavior

The local panel starts with static generation. **Start session** explicitly creates fresh history; **Apply profile changes** updates membership/evidence while retaining histories for current and departing people. Display names may repeat. History belongs to stable IDs, so returning listeners recover their prior record.

A successful session solve promises its next track. Replanning locks that promise and uses the current track as the first transition anchor. A conflicting explicit block returns a conflict; it does not silently replace the promise. **Release next promise** is the explicit escape. Artist cooldown and recent-track exclusion are independent of folder categories; the session API accepts `artist_cooldown` and `repeat_window` in track counts when creating a session. Unknown artists are not treated as one artist.

Only confirmed playback events advance played/accepted/disliked seconds. The [interactive workbench](WORKBENCH.md) submits observed playing time at session queue track end/skip/stop; previews do not affect history. External confirmed playback can also use the playback API. A partial playback event can specify fewer seconds than the track duration. Accepted service reduces debt; other listening accrues an equal-share debt in seconds. The solver uses this debt in 180-second units when improving the least-served listener. Count representation and duration exposure are displayed separately. The policy is provisional and needs the listening pilot.

Every mutation and solve includes a revision. A solve runs against a snapshot and is discarded if newer membership, playback or feedback changes the state. Evidence edits must be explicitly applied; the server cannot silently ignore edited listener inputs.

The workbench stores sessions in memory only. Restarting the process loses this local session state. Durable multi-device sessions, authentication, and a production playback integration are outside the present release gate. Neither queue generation nor study preparation claims that audio was actually played or that humans rated it.
