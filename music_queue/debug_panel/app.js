"use strict";
const $ = (id) => document.getElementById(id);
const ui = JamUI;
const colors = [
  "#38846c",
  "#c68055",
  "#668ab3",
  "#b89e4e",
  "#ab7495",
  "#7b9c54",
  "#7564a8",
  "#5e9c9d",
  "#b76768",
  "#8b9775",
  "#8d704e",
  "#618270",
];
const state = {
  catalog: [],
  trackMap: new Map(),
  modelHash: "",
  listeners: [],
  groups: [],
  selected: new Set(),
  exploration: null,
  inspection: null,
  querySeeds: [],
  retrieval: null,
  pipeline: null,
  result: null,
  session: null,
  view: "library",
  busy: false,
  projectKey: "jam-workbench-v2",
  plotRevision: 0,
};
const player = {
  queue: [],
  index: 0,
  sessionId: null,
  sessionRevision: null,
  played: 0,
  lastTime: null,
  lastWall: null,
  lastWasPlaying: false,
  busy: false,
};
const audio = $("audio");
const e = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        ch
      ],
  );
const track = (id) => state.trackMap.get(id);
const title = (id) => track(id)?.song ?? id;
const num = (value) => (value == null ? "—" : Number(value).toFixed(3));
const duration = (value) =>
  `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, "0")}`;
const policyIds = [
  "queue-len",
  "candidate-limit",
  "representation",
  "required-count",
  "discovery-budget",
  "folder-cap",
  "predictor",
  "objective",
  "transition-model",
  "transition-weight",
  "folder-penalty",
  "preference-tolerance",
  "artist-cap",
  "family-cap",
];
const savedSettingIds = [
  ...policyIds,
  "method",
  "time-limit",
  "beam-width",
  "embedding-space",
  "feature-family",
  "cluster-count",
  "map-dimensions",
  "color-by",
  "retrieval-aggregation",
  "retrieval-limit",
];
function message(text, error = false) {
  $("message").textContent = text;
  $("message").className = error ? "error" : "notice";
}
async function api(path, payload) {
  const response = await fetch(
    path,
    payload === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
  );
  const result = await response.json();
  if (!response.ok)
    throw new Error(result.error ?? `Request failed (${response.status})`);
  return result;
}
function guarded(fn) {
  return async (...args) => {
    try {
      await fn(...args);
    } catch (error) {
      message(error.message, true);
    }
  };
}
async function busy(label, fn) {
  if (state.busy)
    throw new Error("Let the current pipeline operation finish first.");
  const controls = [
    ...document.querySelectorAll(
      "main input, main select, main button, #load-sample, #import-project",
    ),
  ];
  const disabled = controls.map((el) => el.disabled);
  state.busy = true;
  syncButtons();
  message(label);
  controls.forEach((el) => {
    el.disabled = true;
  });
  try {
    return await fn();
  } finally {
    controls.forEach((el, i) => {
      el.disabled = disabled[i];
    });
    state.busy = false;
    syncButtons();
  }
}
function syncButtons() {
  for (const id of [
    "recluster",
    "retrieve",
    "prepare",
    "start-session",
    "apply-membership",
    "override",
    "run",
  ])
    $(id).disabled = state.busy;
  $("run").disabled = state.busy || (!state.pipeline && !state.session);
  $("apply-membership").disabled = state.busy || !state.session;
  $("override").disabled = state.busy || !state.session?.promised_next;
  $("leave-session").disabled = !state.session;
  $("play-queue").disabled =
    !state.result?.valid_incumbent || state.busy || player.busy;
  $("export-queue").disabled = !state.result?.valid_incumbent;
}
function empty(text) {
  return `<p class="empty">${e(text)}</p>`;
}
function stats(id, values) {
  $(id).innerHTML = values
    .map(
      ([label, value]) =>
        `<div class="stat"><span>${e(label)}</span><strong>${e(value)}</strong></div>`,
    )
    .join("");
}
function table(id, rows, columns, noRows = "No rows for this stage.") {
  $(id).innerHTML = rows.length
    ? `<div class="scroll-table"><table><thead><tr>${columns.map(([label]) => `<th>${e(label)}</th>`).join("")}</tr></thead><tbody>${rows.map((row, i) => `<tr>${columns.map(([, render]) => `<td>${render(row, i)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
    : empty(noRows);
}
function listenButton(id) {
  return `<button class="table-button" data-preview="${e(id)}" ${track(id)?.audio_available ? "" : "disabled"} aria-label="Preview ${e(title(id))}">▶</button>`;
}
function trackCell(id) {
  return `<div class="track-name" title="${e(title(id))}">${e(title(id))}</div><small>${e(track(id)?.folder ?? "")}</small>`;
}
function showView(view, scroll = true) {
  if (!["library", "profiles", "ranking", "sequence"].includes(view))
    view = "library";
  state.view = view;
  for (const el of document.querySelectorAll(".stage"))
    el.hidden = el.id !== `view-${view}`;
  for (const el of document.querySelectorAll(".nav-item"))
    el.classList.toggle("active", el.dataset.view === view);
  const labels = {
    library: [
      "01 / EXPLORE",
      "Your listening landscape",
      "Find connections, shape clusters, and discover your next seed.",
    ],
    profiles: [
      "02 / LISTENERS",
      "A room with different tastes",
      "Give every person a profile and a voice in the queue.",
    ],
    ranking: [
      "03 / CANDIDATES",
      "From a seed to a shortlist",
      "Follow acoustic retrieval, room ranking, and protected selection.",
    ],
    sequence: [
      "04 / LISTEN",
      "Make the queue yours",
      "Inspect the order, compare methods, and press play.",
    ],
  }[view];
  [
    $("stage-label").textContent,
    $("view-title").textContent,
    $("view-subtitle").textContent,
  ] = labels;
  history.replaceState(null, "", `#${view}`);
  if (scroll) window.scrollTo({ top: 0, behavior: "smooth" });
  if (view === "library" && state.exploration)
    Plotly.Plots.resize("embedding-plot");
  if (view === "sequence" && state.pipeline?.transition_matrix)
    renderTransitionMap();
}
function project() {
  return {
    version: 2,
    model_hash: state.modelHash,
    listeners: state.listeners,
    groups: state.groups,
    query_seeds: state.querySeeds,
    settings: Object.fromEntries(
      savedSettingIds.map((id) => [id, $(id).value]),
    ),
  };
}
function save() {
  try {
    localStorage.setItem(state.projectKey, JSON.stringify(project()));
    $("save-state").textContent = "Saved in this browser";
  } catch {
    $("save-state").textContent =
      "Browser storage unavailable · export to save";
  }
}
function loadProject(data) {
  if (
    data?.version !== 2 ||
    !Array.isArray(data.listeners) ||
    data.listeners.length > 8
  )
    throw new Error("This is not a compatible Jam workspace.");
  const fields = ["liked", "accepted", "disliked", "blocked"];
  const used = new Set();
  for (const listener of data.listeners) {
    if (
      !listener ||
      typeof listener.id !== "string" ||
      !listener.id ||
      used.has(listener.id) ||
      typeof listener.name !== "string" ||
      !listener.name.trim() ||
      listener.name.length > 100
    )
      throw new Error("Invalid listener in workspace.");
    used.add(listener.id);
    for (const key of fields)
      if (
        !Array.isArray(listener[key]) ||
        listener[key].some((id) => !state.trackMap.has(id))
      )
        throw new Error(
          "Workspace contains missing track IDs. Use a matching catalog.",
        );
  }
  const groups = data.groups ?? [],
    memberIds = [];
  if (!Array.isArray(groups) || groups.length > 40)
    throw new Error("Invalid groups in workspace.");
  const groupIds = new Set();
  for (const group of groups) {
    if (
      !Number.isInteger(group.id) ||
      groupIds.has(group.id) ||
      typeof group.name !== "string" ||
      !Array.isArray(group.members) ||
      group.members.some((id) => !state.trackMap.has(id))
    )
      throw new Error("Invalid cluster membership in workspace.");
    groupIds.add(group.id);
    memberIds.push(...group.members);
  }
  if (
    groups.length &&
    (new Set(memberIds).size !== memberIds.length ||
      memberIds.length !== state.catalog.length)
  )
    throw new Error("Every catalog track must belong to exactly one group.");
  if (
    !Array.isArray(data.query_seeds ?? []) ||
    (data.query_seeds ?? []).some((id) => !state.trackMap.has(id))
  )
    throw new Error("Invalid query seeds.");
  state.listeners = structuredClone(data.listeners);
  state.groups = structuredClone(groups);
  state.querySeeds = ui.unique(data.query_seeds ?? []);
  for (const id of savedSettingIds)
    if (data.settings && typeof data.settings[id] === "string")
      $(id).value = data.settings[id];
  if (data.model_hash !== state.modelHash)
    message(
      "Catalog model changed. Saved evidence was restored by ID; rebuild clusters and candidates to use the current features.",
    );
}
function download(name, value) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function invalidate(
  text = "Profiles or policy changed. Prepare candidates again.",
) {
  state.pipeline = null;
  state.result = null;
  $("snapshot-note").textContent =
    "Needs preparation · profiles or policy changed";
  $("solve-context").textContent = state.session
    ? "Rolling session · apply profile edits explicitly before building a new queue."
    : text;
  $("pipeline-summary").innerHTML = empty(text);
  $("ranking-table").innerHTML = "";
  $("exclusions").innerHTML = "";
  $("queue").innerHTML = empty(
    "Build a fresh queue from the current profiles and policy.",
  );
  for (const id of [
    "summary",
    "coverage",
    "phases",
    "transitions",
    "result-json",
  ])
    $(id).textContent = "";
  Plotly.purge("transition-map");
  syncButtons();
  save();
}
function listenerSelectors() {
  for (const id of ["library-listener", "retrieval-listener"]) {
    const el = $(id),
      old = el.value;
    el.innerHTML = state.listeners
      .map(
        (l) =>
          `<option value="${e(l.id)}">${e(l.name)} · ${e(l.id.slice(-5))}</option>`,
      )
      .join("");
    if (state.listeners.some((l) => l.id === old)) el.value = old;
  }
}
function renderListeners() {
  $("users").innerHTML =
    state.listeners
      .map(
        (listener, index) =>
          `<article class="card user-card" data-listener="${index}"><div class="user-heading"><span class="avatar" style="background:${colors[index % colors.length]}22;color:${colors[index % colors.length]}">${e(listener.name.slice(0, 1).toUpperCase())}</span><input data-name="${index}" aria-label="Listener name" value="${e(listener.name)}"><button class="icon-button" data-remove="${index}" aria-label="Remove ${e(listener.name)}">×</button></div><span class="tiny">${new Set([...listener.liked, ...listener.accepted]).size} affirmative tracks · ID ${e(listener.id.slice(-8))}</span><div class="chips">${["liked", "accepted", "disliked", "blocked"].flatMap((field) => listener[field].map((id) => `<span class="chip ${field}"><span title="${e(title(id))}">${e(field)} · ${e(title(id))}</span><button data-remove-evidence="${index}" data-field="${field}" data-track="${e(id)}" aria-label="Remove evidence for ${e(title(id))}">×</button></span>`)).join("") || '<span class="tiny">Choose some favorites below or add a selection from the map.</span>'}</div><div class="evidence-controls"><input data-search="${index}" type="search" placeholder="Find a track…" aria-label="Search for ${e(listener.name)}"><select data-label="${index}" aria-label="Evidence type"><option value="liked">Liked seed</option><option value="accepted">Accepted</option><option value="disliked">Disliked</option><option value="blocked">Do not play</option></select></div><div data-results="${index}" class="song-results"></div><button class="subtle" data-profile-library="${e(listener.id)}">Choose a group on the map ↗</button></article>`,
      )
      .join("") || empty("Add a listener to begin building the room.");
  state.listeners.forEach((_, i) => renderProfileSongs(i, ""));
  listenerSelectors();
  save();
}
function renderProfileSongs(index, query) {
  const target = document.querySelector(`[data-results="${index}"]`);
  const rows = state.catalog
    .filter((t) =>
      `${t.song} ${t.folder}`.toLowerCase().includes(query.toLowerCase()),
    )
    .slice(0, 12);
  target.innerHTML =
    rows
      .map(
        (t) =>
          `<div class="song-action"><div><strong>${e(t.song)}</strong><small>${e(t.folder)}</small></div><div class="toolbar">${listenButton(t.track_id)}<button class="table-button" data-add="${index}" data-track="${e(t.track_id)}" aria-label="Add ${e(t.song)}">+</button></div></div>`,
      )
      .join("") || empty("No matching tracks.");
}
function addEvidence(index, ids, field) {
  if (!ids.length) throw new Error("Select at least one track.");
  if (!state.listeners[index])
    throw new Error("Add or choose a listener first.");
  state.listeners[index] = ui.addEvidence(state.listeners[index], ids, field);
  renderListeners();
  invalidate();
  message(
    `Added ${ids.length} ${field} track${ids.length === 1 ? "" : "s"} to ${state.listeners[index].name}.`,
  );
}
function groupOf(id) {
  return state.groups.find((g) => g.members.includes(id));
}
function renderGroups() {
  $("clusters").innerHTML = state.groups
    .map(
      (g, index) =>
        `<div class="cluster-row"><span class="color-dot" style="background:${colors[index % colors.length]}"></span><input data-group-name="${g.id}" value="${e(g.name)}" aria-label="Group name"><button data-select-group="${g.id}" title="Select all tracks in this group">${g.members.length}</button></div>`,
    )
    .join("");
  const options = state.groups
    .map(
      (g) =>
        `<option value="${g.id}">${e(g.name)} (${g.members.length})</option>`,
    )
    .join("");
  const filter = $("library-cluster").value,
    assignment = $("assign-cluster").value;
  $("library-cluster").innerHTML =
    '<option value="">All groups</option>' + options;
  $("assign-cluster").innerHTML = options;
  if (state.groups.some((g) => String(g.id) === filter))
    $("library-cluster").value = filter;
  if (state.groups.some((g) => String(g.id) === assignment))
    $("assign-cluster").value = assignment;
}
function visibleTracks() {
  const query = $("library-search").value.toLowerCase(),
    folder = $("library-folder").value,
    group = $("library-cluster").value;
  return state.catalog.filter(
    (t) =>
      `${t.song} ${t.folder}`.toLowerCase().includes(query) &&
      (!folder || t.folder === folder) &&
      (group === "" || groupOf(t.track_id)?.id === Number(group)),
  );
}
function renderLibrary() {
  const rows = visibleTracks();
  $("library-count").textContent = `${rows.length} tracks`;
  table(
    "library-table",
    rows,
    [
      [
        "",
        (t) =>
          `<input type="checkbox" data-select-track="${e(t.track_id)}" aria-label="Select ${e(t.song)}" ${state.selected.has(t.track_id) ? "checked" : ""}>`,
      ],
      [
        "Track",
        (t) =>
          `<button class="subtle track-name" data-inspect="${e(t.track_id)}">${e(t.song)}</button><small>${e(t.folder)}</small>`,
      ],
      ["Group", (t) => e(groupOf(t.track_id)?.name ?? "—")],
      ["Length", (t) => duration(t.duration)],
      ["Listen", (t) => listenButton(t.track_id)],
    ],
    "No matching tracks. Clear the search or group filter.",
  );
  $("selection-count").textContent = `${state.selected.size} selected`;
}
function renderPlot() {
  if (!state.exploration) return;
  const revision = ++state.plotRevision;
  const dim = state.exploration.dimensions,
    grouped = new Map();
  for (const p of state.exploration.points) {
    const group =
      $("color-by").value === "folder"
        ? p.folder
        : (groupOf(p.track_id)?.name ?? "Ungrouped");
    // Group identity stays distinct even when two groups have the same name.
    const key =
      $("color-by").value === "folder" ? p.folder : groupOf(p.track_id)?.id;
    if (!grouped.has(key)) grouped.set(key, { name: group, points: [] });
    grouped.get(key).points.push(p);
  }
  const traces = [...grouped.values()].map((group, i) => {
    const points = group.points;
    return {
      type: dim === 3 ? "scatter3d" : "scattergl",
      mode: "markers",
      name: group.name,
      x: points.map((p) => p.coordinates[0]),
      y: points.map((p) => p.coordinates[1]),
      ...(dim === 3 ? { z: points.map((p) => p.coordinates[2]) } : {}),
      customdata: points.map((p) => p.track_id),
      text: points.map((p) => `${e(p.song)}<br>${e(p.folder)}`),
      hovertemplate: "%{text}<extra></extra>",
      marker: {
        size: points.map((p) =>
          state.selected.has(p.track_id)
            ? dim === 3
              ? 9
              : 15
            : dim === 3
              ? 5
              : 9,
        ),
        color: colors[i % colors.length],
        opacity: 0.85,
        line: { width: 1, color: "#fff" },
      },
      ...(dim === 2
        ? {
            selectedpoints: points.flatMap((p, j) =>
              state.selected.has(p.track_id) ? [j] : [],
            ),
            unselected: {
              marker: { opacity: state.selected.size ? 0.25 : 0.85 },
            },
          }
        : {}),
    };
  });
  const layout = {
    paper_bgcolor: "#fff",
    plot_bgcolor: "#fff",
    font: { family: "system-ui", size: 11, color: "#77807a" },
    margin: { l: 35, r: 12, t: 15, b: 45 },
    showlegend: true,
    legend: { orientation: "h", y: -0.12 },
    uirevision: `${state.exploration.space}-${state.exploration.family}-${dim}`,
    dragmode: dim === 3 ? "orbit" : "pan",
    xaxis: { title: "PC 1", gridcolor: "#edf0e9", zeroline: false },
    yaxis: { title: "PC 2", gridcolor: "#edf0e9", zeroline: false },
    scene: {
      xaxis: { title: "PC 1" },
      yaxis: { title: "PC 2" },
      zaxis: { title: "PC 3" },
    },
  };
  Plotly.react("embedding-plot", traces, layout, {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["toImage"],
  })
    .then(() => {
      if (revision !== state.plotRevision) return;
      const plot = $("embedding-plot");
      plot.removeAllListeners("plotly_click");
      plot.removeAllListeners("plotly_selected");
      plot.on("plotly_click", (event) => {
        const id = event.points[0]?.customdata;
        if (id) inspect(id);
      });
      plot.on("plotly_selected", (event) => {
        if (!event?.points) return;
        state.selected = new Set(event.points.map((p) => p.customdata));
        renderLibrary();
        renderPlot();
      });
    })
    .catch((error) => message(error.message, true));
  $("map-summary").textContent =
    `${state.groups.length} groups · ${(100 * state.exploration.explained_variance.reduce((a, b) => a + b, 0)).toFixed(1)}% variance in view`;
}
async function cluster(reset = true) {
  await busy("Building the acoustic map…", async () => {
    const response = await api("/api/explore", {
      space: $("embedding-space").value,
      family: $("feature-family").value,
      clusters: Number($("cluster-count").value),
      dimensions: Number($("map-dimensions").value),
    });
    state.exploration = response;
    if (reset || !state.groups.length) state.groups = response.groups;
    renderGroups();
    renderLibrary();
    renderPlot();
    save();
    if (reset)
      message(
        `Formed ${response.actual_clusters} acoustic groups. Rename them or move selected tracks to make them your own.`,
      );
  });
}
let inspectionVersion = 0;
async function inspect(id) {
  const version = ++inspectionVersion;
  state.inspection = id;
  const t = track(id);
  $("track-inspector").innerHTML =
    `<span class="eyebrow">TRACK INSPECTOR</span><h3>${e(t.song)}</h3><p>${e(t.folder)} · ${duration(t.duration)}<br>${e(groupOf(id)?.name ?? "")}</p><button class="primary" data-preview="${e(id)}" ${t.audio_available ? "" : "disabled"}>▶ Preview track</button><button data-toggle-selection="${e(id)}">${state.selected.has(id) ? "Deselect" : "Select"} track</button><button data-query="${e(id)}">Use as retrieval seed →</button><div class="neighbor-mini"><span class="tiny">CLOSEST ACOUSTIC NEIGHBORS</span><div id="inspector-neighbors">Loading…</div></div>`;
  const data = await api(
    `/api/song-details?song=${encodeURIComponent(id)}&neighbors=5`,
  );
  if (version !== inspectionVersion) return;
  $("inspector-neighbors").innerHTML = data.neighbors
    .map(
      (row) =>
        `<button data-inspect="${e(row.track_id)}"><span>${e(row.song)}</span><span class="score">${num(row.score)}</span></button>`,
    )
    .join("");
}
function renderQuerySeeds() {
  $("retrieval-seeds").innerHTML =
    state.querySeeds
      .map(
        (id) =>
          `<span class="chip"><span>${e(title(id))}</span><button data-remove-query="${e(id)}" aria-label="Remove retrieval seed">×</button></span>`,
      )
      .join("") ||
    '<span class="tiny">No query seeds. Select tracks on the map or use a listener’s likes.</span>';
  save();
}
function setQuery(ids) {
  state.querySeeds = ui.unique(ids);
  state.retrieval = null;
  renderQuerySeeds();
  $("retrieval-table").innerHTML = empty(
    "Query changed. Retrieve to see the new neighbors.",
  );
  showView("ranking");
}
function renderRetrieval() {
  table(
    "retrieval-table",
    state.retrieval?.rows ?? [],
    [
      ["Rank", (_, i) => String(i + 1)],
      ["Neighbor", (r) => trackCell(r.track_id)],
      ["Acoustic score", (r) => `<span class="score">${num(r.score)}</span>`],
      ["Closest seed", (r) => e(title(r.nearest_seed))],
      ["Listen", (r) => listenButton(r.track_id)],
      [
        "Evidence",
        (r) =>
          `<button class="table-button" data-neighbor-like="${e(r.track_id)}">Like for chosen listener</button>`,
      ],
    ],
    "No neighbors outside this query’s seeds.",
  );
}
function nullable(id) {
  return $(id).value === "" ? null : Number($(id).value);
}
function request() {
  return {
    listeners: state.listeners,
    queue_len: Number($("queue-len").value),
    candidate_limit: Number($("candidate-limit").value),
    method: $("method").value,
    time_limit: Number($("time-limit").value),
    beam_width: Number($("beam-width").value),
    policy: {
      representation: $("representation").value,
      required_count: Number($("required-count").value),
      discovery_budget: Number($("discovery-budget").value),
      folder_cap: nullable("folder-cap"),
      artist_cap: nullable("artist-cap"),
      family_cap: nullable("family-cap"),
      predictor: $("predictor").value,
      objective: $("objective").value,
      transition_model: $("transition-model").value,
      transition_weight: Number($("transition-weight").value),
      same_folder_penalty: Number($("folder-penalty").value),
      preference_tolerance: Number($("preference-tolerance").value),
    },
    ...(state.session
      ? { session_id: state.session.id, revision: state.session.revision }
      : {}),
  };
}
function renderRanking() {
  if (!state.pipeline) return;
  const p = state.pipeline.provenance,
    query = $("ranking-search").value.toLowerCase();
  const candidates = new Set(state.pipeline.candidates);
  const rows = p.ranked_rows.filter(
    (r) =>
      ($("ranking-scope").value !== "shortlist" ||
        candidates.has(r.track_id)) &&
      `${r.song} ${r.folder} ${Object.values(r.evidence).join(" ")}`
        .toLowerCase()
        .includes(query),
  );
  table("ranking-table", rows, [
    ["Rank", (r) => String(p.ranked_rows.indexOf(r) + 1)],
    ["Track", (r) => trackCell(r.track_id)],
    ["Room mean", (r) => `<span class="score">${num(r.room_score)}</span>`],
    ...state.pipeline.listeners.map((l) => [
      l.name,
      (r) =>
        `<span class="score">${num(r.listener_scores[l.id])}</span><small class="evidence-label ${r.evidence[l.id].startsWith("predicted") ? "predicted" : ""}">${e(r.evidence[l.id])}</small>`,
    ]),
    [
      "Shortlist",
      (r) =>
        candidates.has(r.track_id)
          ? `<span class="badge">Included</span><small>${e((p.selection_reasons[r.track_id] ?? []).join(" · "))}</small>`
          : '<span class="tiny">Outside shortlist</span>',
    ],
    ["Listen", (r) => listenButton(r.track_id)],
  ]);
  stats("pipeline-summary", [
    ["Full eligible catalog", p.full_eligible_count],
    ["Shortlist target", p.requested_shortlist_size],
    ["Actual protected shortlist", p.actual_shortlist_size],
    ["Excluded by hard rules", p.exclusions.length],
  ]);
  $("exclusions").innerHTML = p.exclusions.length
    ? `<details class="advanced"><summary>${p.exclusions.length} excluded tracks</summary>${p.exclusions.map((r) => `<p class="tiny">${e(title(r.track_id))} · ${e(r.reason)}</p>`).join("")}</details>`
    : "";
  $("snapshot-note").textContent =
    `Frozen instance ${state.pipeline.instance_hash.slice(0, 12)} · ${p.expanded_for_feasibility ? "expanded to retain a feasible covering set" : "rules preserved"}`;
  $("solve-context").textContent =
    `${p.actual_shortlist_size} candidates · frozen policy and listener evidence · ${state.pipeline.instance_hash.slice(0, 12)}`;
}
function renderTransitionMap() {
  if (!state.pipeline?.transition_matrix) return;
  const ids = state.pipeline.candidates,
    names = ids.map((id) => title(id));
  Plotly.react(
    "transition-map",
    [
      {
        type: "heatmap",
        x: names,
        y: names,
        z: state.pipeline.transition_matrix.map((row, a) =>
          row.map((v, b) => (a === b ? null : v)),
        ),
        colorscale: [
          [0, "#b4785e"],
          [0.5, "#f0f2e8"],
          [1, "#34745b"],
        ],
        hovertemplate: "From %{y}<br>To %{x}<br>Signal %{z:.3f}<extra></extra>",
        colorbar: { thickness: 10 },
      },
    ],
    {
      margin: { l: 90, b: 85, r: 25, t: 10 },
      font: { size: 9, family: "system-ui" },
      xaxis: { tickangle: -40 },
      yaxis: { autorange: "reversed" },
      paper_bgcolor: "#fff",
    },
    { responsive: true, displaylogo: false },
  );
}
function renderSession() {
  const s = state.session;
  $("session-state").textContent = s
    ? `Session ${s.id.slice(-6)} · revision ${s.revision} · promised next: ${s.promised_next ? title(s.promised_next) : "none"} · previously played: ${s.played_tracks.length} tracks`
    : "Static mode · no listening history yet.";
  table(
    "history",
    Object.entries(s?.histories ?? {}).map(([id, h]) => ({ id, ...h })),
    [
      [
        "Listener",
        (r) => e(state.listeners.find((l) => l.id === r.id)?.name ?? r.id),
      ],
      ["Played", (r) => duration(r.played_seconds)],
      ["Accepted", (r) => duration(r.accepted_seconds)],
      ["Disliked", (r) => duration(r.disliked_seconds)],
      ["Waiting", (r) => duration(r.wait_seconds)],
      ["Debt", (r) => duration(r.debt_seconds)],
    ],
    "Start a rolling session to retain confirmed playback history.",
  );
  syncButtons();
}
function renderQueue() {
  const result = state.result;
  if (!result?.queue_rows.length) {
    $("queue").innerHTML = empty(
      "No valid queue. Inspect the result’s conflict or termination explanation below.",
    );
    return;
  }
  $("queue").classList.remove("empty");
  $("queue").innerHTML = result.queue_rows
    .map(
      (row, i) =>
        `<article class="queue-row ${player.queue[player.index] === row.track_id ? "playing" : ""}"><span class="slot">${String(i + 1).padStart(2, "0")}</span><span class="queue-art">♫</span><div class="queue-info"><strong>${e(row.song)}</strong><small>${e(row.folder)} · ${duration(row.duration)}${state.session?.promised_next === row.track_id ? " · promised next" : ""}</small></div><div class="queue-actions"><button data-preview="${e(row.track_id)}" ${track(row.track_id)?.audio_available ? "" : "disabled"} aria-label="Preview ${e(row.song)}">▶</button><button data-move-queue="${i}" data-direction="-1" ${i === 0 || state.session ? "disabled" : ""} aria-label="Move track earlier">↑</button><button data-move-queue="${i}" data-direction="1" ${i === result.queue_rows.length - 1 || state.session ? "disabled" : ""} aria-label="Move track later">↓</button></div></article>`,
    )
    .join("");
}
function renderResult(result) {
  state.result = result;
  if (result.session) state.session = result.session;
  renderSession();
  renderQueue();
  syncButtons();
  stats("summary", [
    ["Outcome", result.status],
    ["Queue length", `${result.returned_length} / ${result.requested_length}`],
    [
      "Optimality",
      result.proven_optimal ? "Proved on shortlist" : "No complete proof",
    ],
    ["Total computation", `${num(result.timings.total)} s`],
  ]);
  table(
    "coverage",
    Object.values(result.per_listener),
    [
      ["Listener", (r) => e(r.display_name)],
      ["Accepted", (r) => `${r.accepted_count} tracks`],
      ["Planned exposure", (r) => duration(r.accepted_seconds)],
      ["First wait", (r) => duration(r.first_acceptable_wait_seconds ?? 0)],
      ["Deficit", (r) => e(r.representation_deficit)],
    ],
    "No feasible queue to inspect.",
  );
  table("phases", result.phases, [
    ["Priority", (r) => e(r.name)],
    ["Value", (r) => num(r.value)],
    ["Proof", (r) => e(r.proven)],
    ["Termination", (r) => e(r.termination)],
    ["Start accepted", (r) => e(r.warm_start_accepted)],
  ]);
  table("transitions", result.transition_rows, [
    ["From", (r) => e(r.from_song)],
    ["To", (r) => e(r.to_song)],
    ["Signal", (r) => num(r.selected_transition_value)],
    ["Weighted edge", (r) => num(r.weighted_edge)],
  ]);
  $("result-json").textContent = JSON.stringify(result, null, 2);
  message(result.termination_reason, !result.valid_incumbent);
}
function assertSessionIdle() {
  if (player.sessionId && player.queue.length)
    throw new Error(
      "Stop the session queue first to record its observed playback before changing or replanning the session.",
    );
}
function renderPlayer() {
  const id = player.queue[player.index],
    t = track(id);
  $("playing-title").textContent = t?.song ?? "Ready when you are";
  $("playing-detail").textContent = t
    ? `${t.folder} · ${player.index + 1}/${player.queue.length} · ${player.sessionId ? "session time is recorded" : "preview / static listening"}`
    : "Preview a track or play a generated queue";
  $("playing-mode").textContent = player.sessionId
    ? "SESSION QUEUE"
    : player.queue.length > 1
      ? "STATIC QUEUE"
      : "PREVIEW";
  $("previous").disabled =
    player.busy || !!player.sessionId || player.index <= 0;
  $("next").disabled = player.busy || !player.queue.length;
  $("stop").disabled = player.busy || !player.queue.length;
  if (state.result) renderQueue();
}
function observe() {
  const now = performance.now() / 1000;
  if (player.lastWall != null)
    player.played += ui.observedDelta(
      player.lastTime,
      audio.currentTime,
      now - player.lastWall,
      audio.seeking,
      !player.lastWasPlaying,
    );
  player.lastTime = audio.currentTime;
  player.lastWall = now;
  player.lastWasPlaying = !audio.paused;
}
async function finishTrack(advancing = true) {
  observe();
  audio.pause();
  if (player.sessionId && player.played > 0.05) {
    if (
      !state.session ||
      state.session.id !== player.sessionId ||
      state.session.revision !== player.sessionRevision
    )
      throw new Error(
        "Session changed during playback. Playback was stopped; refresh session history before continuing.",
      );
    state.session = await api("/api/session/playback", {
      session_id: player.sessionId,
      revision: player.sessionRevision,
      track_id: player.queue[player.index],
      seconds: Math.min(
        player.played,
        track(player.queue[player.index]).duration,
      ),
    });
    player.sessionRevision = state.session.revision;
    renderSession();
  } else if (player.sessionId && advancing) {
    throw new Error(
      "Play at least a moment of the promised track before advancing a session. Release its promise explicitly to omit it.",
    );
  }
  player.played = 0;
  player.lastTime = null;
  player.lastWall = null;
}
async function loadPlayerTrack() {
  const id = player.queue[player.index],
    t = track(id);
  if (!t?.audio_available)
    throw new Error(`Local audio unavailable: ${title(id)}.`);
  player.played = 0;
  player.lastTime = null;
  player.lastWall = null;
  audio.src = `/api/audio?track_id=${encodeURIComponent(id)}`;
  audio.load();
  renderPlayer();
  try {
    await audio.play();
  } catch {
    message("Playback is ready. Press Play in the audio controls to continue.");
  }
}
async function playerOperation(fn) {
  if (player.busy) return;
  player.busy = true;
  renderPlayer();
  syncButtons();
  try {
    await fn();
  } finally {
    player.busy = false;
    renderPlayer();
    syncButtons();
  }
}
async function stopPlayer() {
  await playerOperation(async () => {
    if (player.queue.length && player.sessionId) await finishTrack(false);
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    player.queue = [];
    player.sessionId = null;
    player.played = 0;
  });
}
async function startPlayback(ids, session = null) {
  if (!ids.length) throw new Error("There are no tracks to play.");
  if (player.queue.length) await stopPlayer();
  await playerOperation(async () => {
    player.queue = [...ids];
    player.index = 0;
    player.sessionId = session?.id ?? null;
    player.sessionRevision = session?.revision ?? null;
    await loadPlayerTrack();
  });
}
async function advance(direction = 1) {
  await playerOperation(async () => {
    if (!player.queue.length) return;
    if (direction < 0 && player.sessionId)
      throw new Error(
        "Previous-track replay is disabled in session mode to preserve repeat rules.",
      );
    if (player.sessionId) await finishTrack();
    else audio.pause();
    player.index += direction;
    if (player.index >= player.queue.length) {
      audio.removeAttribute("src");
      audio.load();
      player.queue = [];
      player.sessionId = null;
      message(
        "Queue finished. Session history is retained; build the next tail when ready.",
      );
      return;
    }
    await loadPlayerTrack();
  });
}
for (const event of ["timeupdate", "playing"])
  audio.addEventListener(event, observe);
audio.addEventListener("seeking", () => {
  player.lastTime = null;
  player.lastWall = null;
});
audio.addEventListener("seeked", () => {
  player.lastTime = audio.currentTime;
  player.lastWall = performance.now() / 1000;
  player.lastWasPlaying = !audio.paused;
});
audio.addEventListener("pause", observe);
audio.addEventListener(
  "ended",
  guarded(() => advance()),
);
audio.addEventListener("error", () => {
  if (audio.getAttribute("src"))
    message(
      "Audio could not be played. Verify the local music root and browser format support.",
      true,
    );
});
window.addEventListener("beforeunload", (event) => {
  if (player.sessionId && player.queue.length && player.played > 0.05) {
    event.preventDefault();
    event.returnValue = "";
  }
});

document.addEventListener(
  "click",
  guarded(async (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    if (button.dataset.view) showView(button.dataset.view);
    if (button.dataset.preview) await startPlayback([button.dataset.preview]);
    if (button.dataset.inspect) {
      showView("library", false);
      await inspect(button.dataset.inspect);
    }
    if (button.dataset.selectGroup !== undefined) {
      const g = state.groups.find(
        (g) => g.id === Number(button.dataset.selectGroup),
      );
      state.selected = new Set(g.members);
      renderLibrary();
      renderPlot();
    }
    if (button.dataset.toggleSelection) {
      const id = button.dataset.toggleSelection;
      state.selected.has(id)
        ? state.selected.delete(id)
        : state.selected.add(id);
      renderLibrary();
      renderPlot();
      await inspect(id);
    }
    if (button.dataset.query) setQuery([button.dataset.query]);
    if (button.dataset.profileLibrary) {
      $("library-listener").value = button.dataset.profileLibrary;
      showView("library");
      message(
        "Select tracks or a group, then use Add evidence below the library.",
      );
    }
    if (button.dataset.remove !== undefined) {
      state.listeners.splice(Number(button.dataset.remove), 1);
      renderListeners();
      invalidate();
    }
    if (button.dataset.add !== undefined) {
      const i = Number(button.dataset.add);
      addEvidence(
        i,
        [button.dataset.track],
        document.querySelector(`[data-label="${i}"]`).value,
      );
    }
    if (button.dataset.removeEvidence !== undefined) {
      const i = Number(button.dataset.removeEvidence);
      state.listeners[i][button.dataset.field] = state.listeners[i][
        button.dataset.field
      ].filter((id) => id !== button.dataset.track);
      renderListeners();
      invalidate();
    }
    if (button.dataset.neighborLike)
      addEvidence(
        state.listeners.findIndex(
          (l) => l.id === $("retrieval-listener").value,
        ),
        [button.dataset.neighborLike],
        "liked",
      );
    if (button.dataset.removeQuery)
      setQuery(
        state.querySeeds.filter((id) => id !== button.dataset.removeQuery),
      );
    if (button.dataset.moveQueue !== undefined) {
      assertSessionIdle();
      if (state.session)
        throw new Error(
          "Release the session promise and use static mode before manually changing an order.",
        );
      if (player.queue.length) await stopPlayer();
      const queue = ui.moveQueue(
        state.result.queue,
        Number(button.dataset.moveQueue),
        Number(button.dataset.direction),
      );
      await busy("Validating manual order…", async () =>
        renderResult(
          await api("/api/order", {
            snapshot_token: state.result.snapshot_token,
            queue,
          }),
        ),
      );
    }
  }),
);
$("library-table").addEventListener("change", (event) => {
  const id = event.target.dataset.selectTrack;
  if (id) {
    event.target.checked ? state.selected.add(id) : state.selected.delete(id);
    $("selection-count").textContent = `${state.selected.size} selected`;
    renderPlot();
  }
});
$("clusters").addEventListener("input", (event) => {
  if (event.target.dataset.groupName !== undefined) {
    state.groups.find(
      (g) => g.id === Number(event.target.dataset.groupName),
    ).name = event.target.value;
    renderLibrary();
    save();
  }
});
$("clusters").addEventListener("change", () => {
  renderGroups();
  renderPlot();
});
$("users").addEventListener("input", (event) => {
  if (event.target.dataset.name !== undefined) {
    state.listeners[Number(event.target.dataset.name)].name =
      event.target.value;
    listenerSelectors();
    invalidate();
  }
  if (event.target.dataset.search !== undefined)
    renderProfileSongs(Number(event.target.dataset.search), event.target.value);
});
for (const id of ["library-search", "library-folder", "library-cluster"])
  $(id).addEventListener("input", renderLibrary);
for (const id of ["ranking-search", "ranking-scope"])
  $(id).addEventListener("input", renderRanking);
for (const id of policyIds)
  $(id).addEventListener("change", () => invalidate());
for (const id of [
  "method",
  "time-limit",
  "beam-width",
  "retrieval-aggregation",
  "retrieval-limit",
])
  $(id).addEventListener("change", save);
$("color-by").addEventListener("change", () => {
  renderPlot();
  save();
});
for (const id of ["embedding-space", "feature-family", "map-dimensions"])
  $(id).addEventListener(
    "change",
    guarded(() => cluster(false)),
  );
$("recluster").addEventListener(
  "click",
  guarded(() => cluster(true)),
);
$("clear-selection").addEventListener("click", () => {
  state.selected.clear();
  renderLibrary();
  renderPlot();
});
$("select-visible").addEventListener("click", () => {
  for (const t of visibleTracks()) state.selected.add(t.track_id);
  renderLibrary();
  renderPlot();
});
$("move-cluster").addEventListener(
  "click",
  guarded(() => {
    if (!state.selected.size)
      throw new Error("Select tracks on the map or in the library first.");
    state.groups = ui.assignGroup(
      state.groups,
      [...state.selected],
      Number($("assign-cluster").value),
    );
    renderGroups();
    renderLibrary();
    renderPlot();
    save();
  }),
);
$("new-cluster").addEventListener(
  "click",
  guarded(() => {
    if (!state.selected.size) throw new Error("Select tracks to form a group.");
    if (state.groups.length >= 40)
      throw new Error("The workspace supports up to 40 editable groups.");
    const id = Math.max(-1, ...state.groups.map((g) => g.id)) + 1;
    state.groups.push({ id, name: `My group ${id + 1}`, members: [] });
    state.groups = ui.assignGroup(state.groups, [...state.selected], id);
    renderGroups();
    renderLibrary();
    renderPlot();
    save();
  }),
);
$("query-selection").addEventListener(
  "click",
  guarded(() => {
    if (!state.selected.size)
      throw new Error("Select one or more query seeds first.");
    setQuery([...state.selected]);
  }),
);
$("add-selected").addEventListener(
  "click",
  guarded(() =>
    addEvidence(
      state.listeners.findIndex((l) => l.id === $("library-listener").value),
      [...state.selected],
      $("library-evidence").value,
    ),
  ),
);
$("add-user").addEventListener(
  "click",
  guarded(() => {
    if (state.listeners.length >= 8)
      throw new Error("A room supports up to eight listeners.");
    state.listeners.push({
      id: crypto.randomUUID(),
      name: `Listener ${state.listeners.length + 1}`,
      liked: [],
      accepted: [],
      disliked: [],
      blocked: [],
    });
    renderListeners();
    invalidate();
  }),
);
$("load-sample").addEventListener(
  "click",
  guarded(async () => {
    assertSessionIdle();
    if (state.session)
      throw new Error(
        "Use static mode before loading demo profiles, or edit and apply the existing session’s profiles.",
      );
    state.listeners = (await api("/api/sample-room")).listeners;
    renderListeners();
    invalidate();
    message(
      "Demo profiles loaded. They are example seeds, not independent judgments.",
    );
  }),
);
$("add-query").addEventListener("click", () =>
  setQuery([...state.querySeeds, $("query-track").value]),
);
$("use-profile-seeds").addEventListener(
  "click",
  guarded(() => {
    const l = state.listeners.find(
      (l) => l.id === $("retrieval-listener").value,
    );
    if (!l?.liked.length)
      throw new Error(
        "Choose a listener with liked seeds in the retrieval Listener control.",
      );
    setQuery(l.liked);
  }),
);
$("retrieve").addEventListener(
  "click",
  guarded(() =>
    busy("Retrieving acoustic neighbors…", async () => {
      state.retrieval = await api("/api/retrieve", {
        seeds: state.querySeeds,
        limit: Number($("retrieval-limit").value),
        aggregation: $("retrieval-aggregation").value,
      });
      renderRetrieval();
      message(
        `${state.retrieval.rows.length} neighbors ranked. Adding a result as liked is your explicit decision.`,
      );
    }),
  ),
);
$("prepare").addEventListener(
  "click",
  guarded(() =>
    busy(
      "Ranking the full catalog and protecting feasible candidates…",
      async () => {
        if (state.session)
          throw new Error(
            "Use static mode for a frozen pipeline preview; session generation accounts for rolling history directly.",
          );
        const response = await api("/api/pipeline", request());
        if (!response.snapshot_token) {
          invalidate();
          $("result-json").textContent = JSON.stringify(response, null, 2);
          message(response.termination_reason, true);
          return;
        }
        state.pipeline = response;
        state.result = null;
        renderRanking();
        syncButtons();
        message(
          "Shortlist prepared. Continue to Sequence & play, or inspect each score first.",
        );
      },
    ),
  ),
);
$("run").addEventListener(
  "click",
  guarded(() =>
    busy("Sequencing your candidates…", async () => {
      assertSessionIdle();
      let result;
      if (state.session) {
        result = await api("/api/simulate", request());
        if (result.provenance?.ranked_rows) {
          state.pipeline = {
            provenance: result.provenance,
            listeners: state.listeners,
            candidates: Object.keys(result.provenance.selection_reasons),
            instance_hash: result.instance_hash,
          };
          /* Session map uses fresh pair values only after a frozen static preparation. */ $(
            "transition-map",
          ).innerHTML = empty(
            "Inspect returned session edges in the details below.",
          );
        }
      } else {
        if (!state.pipeline)
          throw new Error("Prepare candidates in stage 03 first.");
        result = await api("/api/sequence", {
          snapshot_token: state.pipeline.snapshot_token,
          method: $("method").value,
          time_limit: Number($("time-limit").value),
          beam_width: Number($("beam-width").value),
        });
      }
      renderResult(result);
    }),
  ),
);
$("start-session").addEventListener(
  "click",
  guarded(() =>
    busy("Starting a rolling session…", async () => {
      assertSessionIdle();
      state.session = await api("/api/session/create", request());
      invalidate(
        "Session mode · Build queue uses current promises and service history.",
      );
      renderSession();
      message("Session started. Build a queue to promise its next track.");
    }),
  ),
);
$("apply-membership").addEventListener(
  "click",
  guarded(() =>
    busy("Updating session profiles…", async () => {
      assertSessionIdle();
      state.session = await api("/api/session/membership", request());
      invalidate();
      renderSession();
      message("Profiles applied; service histories retained.");
    }),
  ),
);
$("override").addEventListener(
  "click",
  guarded(() =>
    busy("Releasing the promise…", async () => {
      assertSessionIdle();
      state.session = await api("/api/session/override", {
        session_id: state.session.id,
        revision: state.session.revision,
      });
      invalidate();
      renderSession();
      message("Next-track promise released. Build a new tail.");
    }),
  ),
);
$("leave-session").addEventListener(
  "click",
  guarded(() => {
    assertSessionIdle();
    state.session = null;
    invalidate();
    renderSession();
    message(
      "Static mode selected. Existing session history remains in the local server.",
    );
  }),
);
$("play-queue").addEventListener(
  "click",
  guarded(async () => {
    if (!state.result?.valid_incumbent) return;
    if (player.sessionId && player.queue.length) {
      await audio.play();
      message("Resumed the loaded session queue.");
      return;
    }
    if (
      state.session &&
      (state.result.session?.id !== state.session.id ||
        state.result.session?.revision !== state.session.revision)
    )
      throw new Error(
        "The session advanced. Build a fresh tail before loading another queue.",
      );
    await startPlayback(state.result.queue, state.session);
  }),
);
$("previous").addEventListener(
  "click",
  guarded(() => advance(-1)),
);
$("next").addEventListener(
  "click",
  guarded(() => advance(1)),
);
$("stop").addEventListener("click", guarded(stopPlayer));
$("export-queue").addEventListener("click", () =>
  download("jam-queue.json", state.result),
);
$("export-project").addEventListener("click", () =>
  download("jam-workspace.json", project()),
);
$("import-project").addEventListener("click", () => $("import-file").click());
$("import-file").addEventListener(
  "change",
  guarded(async () => {
    const file = $("import-file").files[0];
    if (!file) return;
    if (file.size > 1000000) throw new Error("Workspace file exceeds 1 MB.");
    assertSessionIdle();
    if (state.session)
      throw new Error("Use static mode before importing a workspace.");
    loadProject(JSON.parse(await file.text()));
    invalidate();
    renderListeners();
    renderGroups();
    renderLibrary();
    renderQuerySeeds();
    await cluster(false);
    save();
    message("Workspace imported. Prepare a fresh pipeline before sequencing.");
    $("import-file").value = "";
  }),
);
window.addEventListener("hashchange", () => showView(location.hash.slice(1)));
document.addEventListener(
  "DOMContentLoaded",
  guarded(async () => {
    message("Loading your local catalog…");
    const catalog = await api("/api/catalog");
    state.catalog = catalog.songs;
    state.trackMap = new Map(catalog.songs.map((t) => [t.track_id, t]));
    state.modelHash = catalog.model_hash;
    $("catalog-count").textContent =
      `${catalog.count} tracks · ${catalog.songs.filter((t) => t.audio_available).length} playable`;
    const schema = catalog.feature_schema;
    $("catalog-model").textContent = schema
      ? `${schema.dimensions} features: ${schema.n_mfcc} MFCCs plus chroma and spectral contrast, each pooled as means and standard deviations. Extraction at ${schema.sample_rate} Hz; stored endpoint windows ${schema.segment_seconds} seconds. Origin: ${catalog.feature_provenance?.origin ?? "synthetic"}. Model ${catalog.model_hash.slice(0, 16)}. PCA and editable clusters are views of these features; retrieval uses the frozen full-feature coordinates.`
      : "Synthetic feature catalog.";
    $("cluster-count").max = String(Math.min(20, catalog.count));
    $("cluster-count").value = String(Math.min(6, catalog.count));
    $("retrieval-limit").max = String(catalog.count);
    $("retrieval-limit").value = String(Math.min(20, catalog.count));
    $("library-folder").innerHTML =
      '<option value="">All folders</option>' +
      [...new Set(state.catalog.map((t) => t.folder))]
        .sort()
        .map((folder) => `<option value="${e(folder)}">${e(folder)}</option>`)
        .join("");
    $("query-track").innerHTML = state.catalog
      .map(
        (t) =>
          `<option value="${e(t.track_id)}">${e(t.song)} · ${e(t.folder)}</option>`,
      )
      .join("");
    let stored;
    try {
      stored = localStorage.getItem(state.projectKey);
    } catch {}
    if (stored) {
      try {
        loadProject(JSON.parse(stored));
      } catch (error) {
        message(`${error.message} Starting a new workspace.`, true);
        state.listeners = (await api("/api/sample-room")).listeners;
      }
    } else state.listeners = (await api("/api/sample-room")).listeners;
    renderListeners();
    renderGroups();
    renderLibrary();
    renderQuerySeeds();
    renderSession();
    showView(location.hash.slice(1), false);
    await cluster(false);
    message(
      "Ready. Explore the map, choose listener evidence, then prepare and play a queue.",
    );
  }),
);
