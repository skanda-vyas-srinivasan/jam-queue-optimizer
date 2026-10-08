"""Isolated source extracts from e637be5f78567ea24f04cf0734286f357fef7d74.
Copied from the GitHub connector for synthetic diagnostics. Import wiring and type
annotations are simplified; the tested function bodies preserve the fetched logic.
This is not the complete repository and does not include a CBC installation.
"""
from __future__ import annotations
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import ceil, inf
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

BASE_RANK_COLUMNS = {"song", "folder", "room_score"}
DEFAULT_PRESERVE_USER_FRACTION = 0.30
DEFAULT_MAX_PRESERVED_PER_USER = 2

def standardize(matrix):
    feature_means = matrix.mean(axis=0)
    feature_stds = matrix.std(axis=0)
    feature_stds[feature_stds == 0.0] = 1.0
    return (matrix - feature_means) / feature_stds

class Catalog:
    """Test adapter retaining catalog lookup, normalization and similarity behavior.
    The 80:104 slice matches the production DEFAULT_N_MFCC=40 chroma slice.
    """
    def __init__(self, embeddings, names, folders, intro=None, outro=None):
        if len(embeddings) != len(names) or len(names) != len(folders):
            raise ValueError("Embeddings, names, and folders must have the same length")
        self.embeddings = np.asarray(embeddings)
        self.names = np.asarray(names, dtype=str)
        self.folders = np.asarray(folders, dtype=str)
        self.retrieval_similarity = cosine_similarity(standardize(self.embeddings))
        if intro is not None and outro is not None:
            ni, no = standardize(np.asarray(intro)), standardize(np.asarray(outro))
            self.transition_similarity = .85*cosine_similarity(no,ni)+.15*cosine_similarity(no[:,80:104],ni[:,80:104])
        else:
            self.transition_similarity = self.retrieval_similarity
        self.song_to_idx = {name: idx for idx, name in enumerate(self.names)}
        self.name_aliases = {}
        for name in self.names:
            for alias in {name, Path(name).stem}:
                self.name_aliases.setdefault(alias.casefold(), name)
    def resolve_song_name(self, song_name):
        raw_name = str(song_name).strip()
        for alias in (raw_name, Path(raw_name).stem):
            resolved = self.name_aliases.get(alias.casefold())
            if resolved is not None:
                return str(resolved)
        raise KeyError(f"Unknown song: {song_name}")
    def has_song(self, song_name):
        try:
            self.resolve_song_name(song_name)
        except KeyError:
            return False
        return True
    def song_index(self, song_name):
        resolved_name = self.resolve_song_name(song_name)
        return self.song_to_idx[resolved_name]
    def get_folder(self, song_name):
        return str(self.folders[self.song_index(song_name)])
    def transition_score(self, prev_song, next_song):
        return float(self.transition_similarity[self.song_index(prev_song),self.song_index(next_song)])
    def nearest_neighbors(self, song_name, k=10):
        resolved_name = self.resolve_song_name(song_name)
        idx = self.song_index(resolved_name)
        scores = self.retrieval_similarity[idx]
        order = np.argsort(scores)[::-1]
        rows = []
        for neighbor_idx in order:
            if neighbor_idx == idx:
                continue
            rows.append({"song":str(self.names[neighbor_idx]),"folder":str(self.folders[neighbor_idx]),"score":float(scores[neighbor_idx])})
            if len(rows) >= k:
                break
        return pd.DataFrame(rows)

def validate_room(catalog, room):
    if not room:
        raise ValueError("Room must include at least one user")
    for user, liked_songs in room.items():
        if not liked_songs:
            raise ValueError(f"User {user!r} must have at least one liked song")
        for song in liked_songs:
            if not catalog.has_song(song):
                raise ValueError(f"Unknown song in room for {user!r}: {song}")

def retrieve_candidates(catalog, room, neighbors_per_seed=10):
    validate_room(catalog, room)
    candidates = {}
    for user, liked_songs in room.items():
        for song in liked_songs:
            song = catalog.resolve_song_name(song)
            neighbors = catalog.nearest_neighbors(song, k=neighbors_per_seed)
            for _, row in neighbors.iterrows():
                candidate = row["song"]
                similarity = float(row["score"])
                if candidate not in candidates:
                    candidates[candidate] = {}
                previous = candidates[candidate].get(user, -1.0)
                candidates[candidate][user] = max(previous, similarity)
            if song not in candidates:
                candidates[song] = {}
            candidates[song][user] = max(candidates[song].get(user, -1.0), 1.0)
    return candidates

def build_retrieval_frame(catalog, retrieved):
    rows=[]
    for song, user_sims in retrieved.items():
        rows.append({"song":song,"folder":catalog.get_folder(song),"retrieval_score":float(sum(user_sims.values())),"user_coverage":len(user_sims),"users_retrieved":list(user_sims.keys()),"retrieval_details":user_sims})
    if not rows:
        return pd.DataFrame(columns=["song","folder","retrieval_score","user_coverage","users_retrieved","retrieval_details"])
    return pd.DataFrame(rows).sort_values("retrieval_score",ascending=False)

def user_score(catalog,user_liked_songs,candidate_song,top_k=2):
    candidate_idx=catalog.song_index(candidate_song)
    scores=[]
    for liked_song in user_liked_songs:
        liked_idx=catalog.song_index(liked_song)
        scores.append(float(catalog.retrieval_similarity[candidate_idx,liked_idx]))
    scores.sort(reverse=True)
    limit=max(1,min(top_k,len(scores)))
    return float(np.mean(scores[:limit]))

def room_score(catalog,room,candidate_song,top_k=2):
    per_user={}
    for user,liked_songs in room.items():
        per_user[user]=user_score(catalog,liked_songs,candidate_song,top_k=top_k)
    average_score=float(np.mean(list(per_user.values())))
    return average_score,per_user

def rank_room_candidates(catalog,room,neighbors_per_seed=10,top_k=2,candidate_pool_size=40):
    retrieved=retrieve_candidates(catalog,room,neighbors_per_seed=neighbors_per_seed)
    retrieval_df=build_retrieval_frame(catalog,retrieved)
    top_candidates=retrieval_df.head(candidate_pool_size)["song"].tolist()
    rows=[]
    for song in top_candidates:
        score,per_user=room_score(catalog,room,song,top_k=top_k)
        rows.append({"song":song,"folder":catalog.get_folder(song),"room_score":score,**per_user})
    ranked_df=(pd.DataFrame(rows).sort_values("room_score",ascending=False).reset_index(drop=True) if rows else pd.DataFrame(columns=["song","folder","room_score"]))
    return retrieval_df.reset_index(drop=True),ranked_df

def ranked_user_columns(ranked_df):
    return [column for column in ranked_df.columns if column not in BASE_RANK_COLUMNS]

def effective_max_songs_per_folder(candidate_df,target_len,max_songs_per_folder):
    if target_len<=0:
        return None
    cap=max_songs_per_folder
    if cap is None:
        cap=max(1,ceil(target_len/2))
    if cap<=0:
        return None
    folder_counts=candidate_df["folder"].value_counts().to_numpy()
    if int(np.minimum(folder_counts,cap).sum())<target_len:
        return None
    return cap

def select_candidate_shortlist_with_details(ranked_df,shortlist_size,preserve_user_fraction=.30,max_preserved_per_user=2):
    if ranked_df.empty or shortlist_size<=0:
        return ranked_df.head(0).copy(),{}
    candidate_df=ranked_df.copy().reset_index(drop=True)
    shortlist_size=min(shortlist_size,len(candidate_df))
    user_columns=ranked_user_columns(candidate_df)
    if not user_columns or preserve_user_fraction<=0.0 or max_preserved_per_user<=0:
        shortlist_df=candidate_df.head(shortlist_size).copy().reset_index(drop=True)
        reasons={song:["global_rank"] for song in shortlist_df["song"].tolist()}
        return shortlist_df,reasons
    preserve_budget=min(shortlist_size,len(candidate_df),max(1,int(round(shortlist_size*preserve_user_fraction))))
    user_priority=sorted(user_columns,key=lambda user:float(candidate_df[user].max()),reverse=True)
    user_rankings={user:candidate_df.sort_values(user,ascending=False).index.to_list() for user in user_columns}
    selected=[]
    selected_set=set()
    reason_map={}
    user_counts={user:0 for user in user_columns}
    user_positions={user:0 for user in user_columns}
    def add_next_for_user(user):
        ranking=user_rankings[user]
        while user_positions[user]<len(ranking):
            row_idx=int(ranking[user_positions[user]])
            user_positions[user]+=1
            if row_idx in selected_set:
                continue
            selected.append(row_idx)
            selected_set.add(row_idx)
            reason_map.setdefault(row_idx,[]).append(f"preserved:{user}")
            user_counts[user]+=1
            return True
        return False
    for user in user_priority:
        if len(selected)>=preserve_budget:
            break
        add_next_for_user(user)
    while len(selected)<preserve_budget:
        made_progress=False
        for user in user_priority:
            if user_counts[user]>=max_preserved_per_user:
                continue
            if len(selected)>=preserve_budget:
                break
            made_progress=add_next_for_user(user) or made_progress
        if not made_progress:
            break
    for row_idx in candidate_df.sort_values("room_score",ascending=False).index.to_list():
        if len(selected)>=shortlist_size:
            break
        if row_idx in selected_set:
            continue
        selected.append(int(row_idx))
        selected_set.add(int(row_idx))
        reason_map.setdefault(int(row_idx),[]).append("global_rank")
    shortlist_df=candidate_df.loc[selected].sort_values("room_score",ascending=False).reset_index(drop=True)
    shortlist_reasons={str(row["song"]):reason_map.get(int(original_idx),["global_rank"]) for original_idx,row in candidate_df.loc[selected].sort_values("room_score",ascending=False).iterrows()}
    return shortlist_df,shortlist_reasons

def user_representation_sets(candidate_df,top_k):
    if top_k is None or top_k<=0 or candidate_df.empty:
        return {}
    top_k=min(top_k,len(candidate_df))
    representation_sets={}
    for user in ranked_user_columns(candidate_df):
        top_indices=candidate_df.nlargest(top_k,user).index.to_list()
        if top_indices:
            representation_sets[user]={int(idx) for idx in top_indices}
    return representation_sets

def user_representation_feasible(representation_sets,n_songs,target_len):
    if not representation_sets:
        return True
    users=list(representation_sets)
    full_cover=(1<<len(users))-1
    cover_masks=[0]*n_songs
    for user_idx,user in enumerate(users):
        for song_idx in representation_sets[user]:
            if 0<=song_idx<n_songs:
                cover_masks[song_idx]|=1<<user_idx
    for subset in range(1<<n_songs):
        if subset.bit_count()>target_len:
            continue
        covered=0
        for song_idx in range(n_songs):
            if subset&(1<<song_idx):
                covered|=cover_masks[song_idx]
        if covered==full_cover:
            return True
    return False


def select_candidate_shortlist(ranked_df,shortlist_size,preserve_user_fraction=.30,max_preserved_per_user=2):
    return select_candidate_shortlist_with_details(ranked_df,shortlist_size,preserve_user_fraction,max_preserved_per_user)[0]


def score_queue(catalog, queue, room_score_map, transition_weight=.25, same_folder_penalty=0.):
    total = 0.0
    for idx, song in enumerate(queue):
        total += float(room_score_map[song])
        if idx == 0:
            continue
        prev_song = queue[idx - 1]
        total += transition_weight * catalog.transition_score(prev_song, song)
        if catalog.get_folder(prev_song) == catalog.get_folder(song):
            total -= same_folder_penalty
    return total


def solve_queue_beam(catalog, ranked_df, queue_len=5, candidate_limit=10,
                     transition_weight=.25, same_folder_penalty=0., beam_width=64,
                     max_songs_per_folder=None, preserve_user_fraction=.30,
                     max_preserved_per_user=2):
    candidate_df = select_candidate_shortlist(
        ranked_df, shortlist_size=candidate_limit,
        preserve_user_fraction=preserve_user_fraction,
        max_preserved_per_user=max_preserved_per_user,
    )
    if candidate_df.empty or queue_len <= 0:
        return []
    songs = candidate_df['song'].tolist()
    room_score_map = dict(zip(candidate_df['song'], candidate_df['room_score']))
    target_len = min(queue_len, len(songs))
    effective_folder_cap = effective_max_songs_per_folder(
        candidate_df, target_len=target_len, max_songs_per_folder=max_songs_per_folder,
    )
    states = [(0.0, [], set())]
    for _ in range(target_len):
        expanded = []
        for _, queue, used in states:
            for song in songs:
                if song in used:
                    continue
                if effective_folder_cap is not None:
                    song_folder = catalog.get_folder(song)
                    folder_count = sum(1 for queued_song in queue
                                       if catalog.get_folder(queued_song) == song_folder)
                    if folder_count >= effective_folder_cap:
                        continue
                new_queue = queue + [song]
                new_used = set(used)
                new_used.add(song)
                new_score = score_queue(catalog=catalog, queue=new_queue,
                                        room_score_map=room_score_map,
                                        transition_weight=transition_weight,
                                        same_folder_penalty=same_folder_penalty)
                expanded.append((new_score, new_queue, new_used))
        if not expanded:
            break
        expanded.sort(key=lambda item: item[0], reverse=True)
        states = expanded[:beam_width]
    return states[0][1] if states else []
