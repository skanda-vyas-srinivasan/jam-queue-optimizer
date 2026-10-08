"use strict";
const state = {catalog: [], listeners: [], session: null, result: null};
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const title = id => state.catalog.find(t => t.track_id === id)?.song ?? id;
const number = value => value == null ? "Unavailable" : Number(value).toFixed(3);
function message(text, error = false) { $("message").textContent = text; $("message").className = error ? "error" : "notice"; }
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error ?? `Request failed (${response.status})`);
  return result;
}
function guarded(fn) { return async (...args) => { try { await fn(...args); } catch (error) { message(error.message, true); } }; }
function evidence(listener) { return ["liked", "accepted", "disliked", "blocked"].flatMap(field => (listener[field] ?? []).map(id => ({field, id}))); }
function renderListeners() {
  $("users").innerHTML = state.listeners.map((listener, index) => `<article class="user-card" data-listener="${index}">
    <div class="section-heading"><label>Display name<input data-name="${index}" value="${escapeHtml(listener.name)}"></label><button data-remove="${index}">Remove listener</button></div>
    <div class="chips">${evidence(listener).map(({field,id}) => `<span class="chip ${field}">${escapeHtml(field)} · ${escapeHtml(title(id))}<button aria-label="Remove evidence" data-remove-evidence="${index}" data-field="${field}" data-track="${escapeHtml(id)}">×</button></span>`).join("") || '<span class="muted">No affirmative evidence yet.</span>'}</div>
    <div class="evidence-controls"><input data-search="${index}" placeholder="Search catalog" aria-label="Search songs for ${escapeHtml(listener.name)}"><select data-label="${index}" aria-label="Evidence label"><option value="liked">Liked</option><option value="accepted">Accepted this session</option><option value="disliked">Ordinary dislike</option><option value="blocked">Do not play</option></select></div><div class="song-results" data-results="${index}"></div></article>`).join("");
  state.listeners.forEach((_, index) => renderSongs(index, ""));
}
function renderSongs(index, query) {
  const target = document.querySelector(`[data-results="${index}"]`);
  const rows = state.catalog.filter(t => `${t.song} ${t.folder}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())).slice(0, 20);
  target.innerHTML = rows.map(t => `<button class="song-action" data-add="${index}" data-track="${escapeHtml(t.track_id)}">${escapeHtml(t.song)} <small>${escapeHtml(t.folder)}</small></button>`).join("");
}
function addEvidence(index, id, field) {
  const listener = state.listeners[index];
  listener[field] ??= [];
  if (!listener[field].includes(id)) listener[field].push(id);
  if (["liked", "accepted"].includes(field)) listener.disliked = (listener.disliked ?? []).filter(t => t !== id);
  if (field === "disliked") for (const positive of ["liked", "accepted"]) listener[positive] = (listener[positive] ?? []).filter(t => t !== id);
  renderListeners();
}
function nullable(id) { return $(id).value === "" ? null : Number($(id).value); }
function request() {
  return {listeners: state.listeners.map(({id,name,liked,accepted,disliked,blocked}) => ({id,name,liked,accepted,disliked,blocked})),
    queue_len: Number($("queue-len").value), candidate_limit: Number($("candidate-limit").value), method: $("method").value,
    time_limit: Number($("time-limit").value), revision: state.session?.revision ?? 0, session_id: state.session?.id,
    policy: {representation: $("representation").value, required_count: Number($("required-count").value),
      folder_cap: nullable("folder-cap"), discovery_budget: Number($("discovery-budget").value),
      transition_weight: Number($("transition-weight").value), same_folder_penalty: Number($("folder-penalty").value),
      preference_tolerance: Number($("preference-tolerance").value), objective: $("objective").value, predictor: $("predictor").value}};
}
function table(target, rows, columns) {
  $(target).innerHTML = rows.length ? `<div class="table-wrap"><table><thead><tr>${columns.map(([key,label]) => `<th>${escapeHtml(label)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${columns.map(([key]) => `<td>${escapeHtml(typeof row[key] === "number" ? number(row[key]) : row[key] ?? "Unavailable")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : '<p class="muted">No result for this stage.</p>';
}
function renderSession() {
  const session = state.session;
  $("apply-membership").disabled = !session; $("override").disabled = !session?.promised_next;
  $("session-state").textContent = session ? `Revision ${session.revision} · Promised next: ${session.promised_next ? title(session.promised_next) : "None"} · Current track: ${session.current_track ? title(session.current_track) : "None"}` : "Static request. Start a session to retain service history.";
  table("history", Object.entries(session?.histories ?? {}).map(([id,h]) => ({id, ...h})), [["id","Listener ID"],["played_seconds","Played seconds"],["accepted_seconds","Affirmative exposure seconds"],["disliked_seconds","Disliked seconds"],["wait_seconds","Current wait seconds"],["debt_seconds","Service debt seconds"]]);
}
function renderResult(result) {
  state.result = result;
  if (result.session) { state.session = result.session; renderSession(); }
  const stats = [["Status", result.status], ["Length", `${result.returned_length}/${result.requested_length}`], ["Proof", result.proven_optimal ? "Optimal over this shortlist" : "No complete proof"], ["Total seconds", number(result.timings.total)], ["Worst listener affinity", number(result.objective_components.worst_listener_utility)]];
  $("summary").innerHTML = stats.map(([label,value]) => `<div class="stat"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  $("queue").innerHTML = result.queue_rows.map(row => `<article class="queue-card"><span class="eyebrow">SLOT ${row.slot}</span><h3>${escapeHtml(row.song)}</h3><p>${escapeHtml(row.folder)} · ${Math.round(row.duration)} seconds</p>${state.session?.promised_next === row.track_id ? `<button class="accent" data-play="${escapeHtml(row.track_id)}" data-duration="${row.duration}">Confirm played (${Math.round(row.duration)}s)</button>` : ""}</article>`).join("");
  table("coverage", Object.entries(result.per_listener).map(([id,row]) => ({id,...row})), [["display_name","Listener"],["id","Stable ID"],["accepted_count","Confirmed accepted tracks"],["accepted_seconds","Planned accepted seconds"],["first_acceptable_wait_seconds","Planned first wait (s)"],["representation_deficit","Explicit deficit"],["affinity_sum","Internal affinity sum"]]);
  table("phases", result.phases, [["name","Priority"],["value","Internal value"],["proven","Proven"],["termination","Termination"],["warm_start_accepted","CBC accepted start"]]);
  table("transitions", result.transition_rows, [["from_song","From"],["to_song","To"],["boundary_acoustic_affinity","Pooled acoustic affinity"]]);
  $("result-json").textContent = JSON.stringify(result, null, 2);
  message(result.termination_reason, !result.valid_incumbent);
}
async function renderPlot() {
  const fig = await api(`/api/embedding?space=${encodeURIComponent($("embedding-space").value)}`);
  await Plotly.react("embedding-plot", fig.data, fig.layout, {responsive:true, displaylogo:false});
}
document.addEventListener("DOMContentLoaded", guarded(async () => {
  const catalog = await api("/api/catalog"); state.catalog = catalog.songs;
  $("catalog-count").textContent = `${catalog.count} local tracks`;
  state.listeners = (await api("/api/sample-room")).listeners; renderListeners(); renderSession(); await renderPlot();
}));
$("add-user").addEventListener("click", () => { state.listeners.push({id:crypto.randomUUID(), name:`Listener ${state.listeners.length + 1}`, liked:[],accepted:[],disliked:[],blocked:[]}); renderListeners(); });
$("load-sample").addEventListener("click", guarded(async () => { if (state.session) throw new Error("The rolling session retains history. Apply sample evidence explicitly or reload the page for a static room."); state.listeners = (await api("/api/sample-room")).listeners; renderListeners(); }));
$("users").addEventListener("input", event => { if (event.target.dataset.name !== undefined) state.listeners[Number(event.target.dataset.name)].name = event.target.value; if (event.target.dataset.search !== undefined) renderSongs(Number(event.target.dataset.search), event.target.value); });
$("users").addEventListener("click", event => {
  const button = event.target.closest("button"); if (!button) return;
  if (button.dataset.remove !== undefined) { state.listeners.splice(Number(button.dataset.remove), 1); renderListeners(); }
  if (button.dataset.add !== undefined) { const index=Number(button.dataset.add); addEvidence(index,button.dataset.track,document.querySelector(`[data-label="${index}"]`).value); }
  if (button.dataset.removeEvidence !== undefined) { const listener=state.listeners[Number(button.dataset.removeEvidence)]; listener[button.dataset.field]=listener[button.dataset.field].filter(id=>id!==button.dataset.track);renderListeners(); }
});
$("run").addEventListener("click", guarded(async () => { $("run").disabled=true; message("Solving within the total request budget…"); try { renderResult(await api("/api/simulate",request())); } finally { $("run").disabled=false; } }));
$("start-session").addEventListener("click", guarded(async () => { state.session=await api("/api/session/create",request()); renderSession(); message("New session started. Earlier session histories remain in the local process."); }));
$("apply-membership").addEventListener("click", guarded(async () => { state.session=await api("/api/session/membership",request()); renderSession(); message("Listeners and evidence updated; service histories preserved."); }));
$("override").addEventListener("click", guarded(async () => { state.session=await api("/api/session/override",{session_id:state.session.id,revision:state.session.revision}); renderSession(); $("queue").innerHTML=""; message("Promise explicitly released. Generate a new queue."); }));
$("queue").addEventListener("click", guarded(async event => { const button=event.target.closest("[data-play]"); if(!button)return; state.session=await api("/api/session/playback",{session_id:state.session.id,revision:state.session.revision,track_id:button.dataset.play,seconds:Number(button.dataset.duration)});renderSession();$("queue").innerHTML=""; message("Actual playback recorded. Generate the remaining tail."); }));
$("embedding-space").addEventListener("change", guarded(renderPlot));
