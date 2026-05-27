const state = {
  catalog: [],
  folders: [],
  users: [],
  nextUserId: 1,
  sampleRoom: {},
  embeddingSpace: "normalized",
  results: null,
};

const tableColumns = {
  shortlist: ["song", "folder", "room_score", "selection_reason"],
  ranked: ["song", "folder", "room_score"],
  retrieval: ["song", "folder", "retrieval_score", "user_coverage", "users_retrieved"],
  transitions: [
    "from_song",
    "to_song",
    "segment_transition",
    "harmonic_transition",
    "combined_transition",
  ],
};

document.addEventListener("DOMContentLoaded", async () => {
  bindStaticControls();
  await loadCatalog();
  await loadSampleRoom();
  await renderEmbeddingPlot();
  if (Object.keys(state.sampleRoom).length) {
    applyRoom(state.sampleRoom);
  } else {
    addUserCard();
  }
});

function bindStaticControls() {
  document.getElementById("embedding-space").addEventListener("change", async (event) => {
    state.embeddingSpace = event.target.value;
    await renderEmbeddingPlot();
  });

  document.getElementById("add-user").addEventListener("click", () => addUserCard());
  document.getElementById("load-sample-room").addEventListener("click", () => applyRoom(state.sampleRoom));
  document.getElementById("run-simulation").addEventListener("click", runSimulation);
  document.getElementById("users-container").addEventListener("input", handleUsersInput);
  document.getElementById("users-container").addEventListener("click", handleUsersClick);
}

async function loadCatalog() {
  const response = await fetch("/api/catalog");
  const payload = await response.json();
  state.catalog = payload.songs;
  state.folders = Object.keys(payload.folders || {}).sort();
  document.getElementById("catalog-count").textContent = `${payload.count} songs loaded`;
}

async function loadSampleRoom() {
  const response = await fetch("/api/sample-room");
  const payload = await response.json();
  state.sampleRoom = payload.room || {};
}

async function renderEmbeddingPlot() {
  const response = await fetch(`/api/embedding?space=${encodeURIComponent(state.embeddingSpace)}`);
  const figure = await response.json();
  Plotly.react("embedding-plot", figure.data, figure.layout, {
    responsive: true,
    displaylogo: false,
  });
}

function addUserCard(seed = {}) {
  state.users.push({
    id: state.nextUserId++,
    name: seed.name || `user_${state.nextUserId - 1}`,
    search: "",
    folderFilter: "",
    selectedSongs: [...(seed.selectedSongs || [])],
  });
  renderUsers();
}

function removeUserCard(userId) {
  state.users = state.users.filter((user) => user.id !== userId);
  if (!state.users.length) {
    addUserCard();
    return;
  }
  renderUsers();
}

function updateUserName(userId, value) {
  const user = state.users.find((entry) => entry.id === userId);
  if (!user) return;
  user.name = value;
}

function updateUserSearch(userId, value) {
  const user = state.users.find((entry) => entry.id === userId);
  if (!user) return;
  user.search = value;
  renderUserLists(userId);
}

function updateUserFolderFilter(userId, value) {
  const user = state.users.find((entry) => entry.id === userId);
  if (!user) return;
  user.folderFilter = value;
  renderUserLists(userId);
}

function addSongToUser(userId, song) {
  const user = state.users.find((entry) => entry.id === userId);
  if (!user || user.selectedSongs.includes(song)) return;
  user.selectedSongs.push(song);
  renderUserLists(userId);
}

function removeSongFromUser(userId, song) {
  const user = state.users.find((entry) => entry.id === userId);
  if (!user) return;
  user.selectedSongs = user.selectedSongs.filter((value) => value !== song);
  renderUserLists(userId);
}

function applyRoom(room) {
  state.users = [];
  Object.entries(room || {}).forEach(([name, songs]) => {
    state.users.push({
      id: state.nextUserId++,
      name,
      search: "",
      folderFilter: "",
      selectedSongs: [...songs],
    });
  });
  if (!state.users.length) {
    addUserCard();
    return;
  }
  renderUsers();
}

function renderUsers() {
  const container = document.getElementById("users-container");
  container.innerHTML = "";

  for (const user of state.users) {
    const card = document.createElement("article");
    card.className = "user-card";
    card.dataset.userId = String(user.id);

    card.innerHTML = `
      <div class="user-card-header">
        <label>
          <span>User Name</span>
          <input type="text" value="${escapeAttribute(user.name)}" data-user-name="${user.id}" />
        </label>
        <button class="ghost-button" type="button" data-remove-user="${user.id}">Remove</button>
      </div>
      <div class="selected-songs" data-user-selected="${user.id}"></div>
      <div class="user-add-controls">
        <label>
          <span>Search Songs</span>
          <input type="text" value="${escapeAttribute(user.search)}" data-user-search="${user.id}" placeholder="Search by song or folder" />
        </label>
        <label>
          <span>Category</span>
          <select data-user-folder-filter="${user.id}">
            <option value="">All</option>
            ${state.folders
              .map(
                (folder) =>
                  `<option value="${escapeAttribute(folder)}" ${
                    user.folderFilter === folder ? "selected" : ""
                  }>${escapeHtml(folder)}</option>`,
              )
              .join("")}
          </select>
        </label>
      </div>
      <div class="song-results" data-user-results="${user.id}"></div>
    `;

    container.appendChild(card);
    renderUserLists(user.id);
  }
}

function renderUserLists(userId) {
  const user = state.users.find((entry) => entry.id === userId);
  if (!user) return;

  const selectedContainer = document.querySelector(`[data-user-selected="${userId}"]`);
  const resultsContainer = document.querySelector(`[data-user-results="${userId}"]`);
  if (!selectedContainer || !resultsContainer) return;

  const filteredSongs = state.catalog
    .filter((row) => {
      const query = user.search.trim().toLowerCase();
      if (user.folderFilter && row.folder !== user.folderFilter) return false;
      if (!query) return !user.selectedSongs.includes(row.song);
      return (
        !user.selectedSongs.includes(row.song) &&
        (row.song.toLowerCase().includes(query) || row.folder.toLowerCase().includes(query))
      );
    })
    .slice(0, 30);

  selectedContainer.innerHTML = user.selectedSongs.length
    ? user.selectedSongs
        .map(
          (song) => `
            <span class="song-chip">
              <span>${escapeHtml(song)}</span>
              <button type="button" data-remove-song="${user.id}::${encodeURIComponent(song)}">×</button>
            </span>
          `,
        )
        .join("")
    : `<div class="empty-state">No liked songs selected yet.</div>`;

  if (!filteredSongs.length) {
    resultsContainer.innerHTML = `<div class="empty-state">No matching songs available.</div>`;
    return;
  }

  const groupedSongs = groupSongsByFolder(filteredSongs);
  resultsContainer.innerHTML = Object.entries(groupedSongs)
    .map(
      ([folder, songs]) => `
        <section class="song-group">
          <div class="song-group-title">${escapeHtml(folder)}</div>
          ${songs
            .map(
              (row) => `
                <button class="song-action" type="button" data-add-song="${user.id}::${encodeURIComponent(row.song)}">
                  ${escapeHtml(row.song)}
                  <small> · ${escapeHtml(row.folder)}</small>
                </button>
              `,
            )
            .join("")}
        </section>
      `,
    )
    .join("");
}

function handleUsersInput(event) {
  if (event.target.matches("[data-user-name]")) {
    updateUserName(Number(event.target.dataset.userName), event.target.value);
    return;
  }
  if (event.target.matches("[data-user-search]")) {
    updateUserSearch(Number(event.target.dataset.userSearch), event.target.value);
    return;
  }
  if (event.target.matches("[data-user-folder-filter]")) {
    updateUserFolderFilter(Number(event.target.dataset.userFolderFilter), event.target.value);
  }
}

function handleUsersClick(event) {
  const target = event.target.closest("button");
  if (!target) return;

  if (target.dataset.removeUser) {
    removeUserCard(Number(target.dataset.removeUser));
    return;
  }
  if (target.dataset.addSong) {
    const [userId, encodedSong] = target.dataset.addSong.split("::");
    addSongToUser(Number(userId), decodeURIComponent(encodedSong));
    return;
  }
  if (target.dataset.removeSong) {
    const [userId, encodedSong] = target.dataset.removeSong.split("::");
    removeSongFromUser(Number(userId), decodeURIComponent(encodedSong));
  }
}

async function runSimulation() {
  const room = {};
  for (const user of state.users) {
    const songs = user.selectedSongs.filter(Boolean);
    if (user.name.trim() && songs.length) {
      room[user.name.trim()] = songs;
    }
  }

  if (!Object.keys(room).length) {
    window.alert("Add at least one user with liked songs before running the simulation.");
    return;
  }

  const payload = {
    room,
    method: readValue("method"),
    queue_len: Number(readValue("queue-len")),
    candidate_pool_size: Number(readValue("candidate-pool-size")),
    candidate_limit: Number(readValue("candidate-limit")),
    transition_weight: Number(readValue("transition-weight")),
    time_limit: Number(readValue("time-limit")),
    relative_gap: nullableNumber("relative-gap"),
    same_folder_penalty: nullableNumber("same-folder-penalty"),
    max_songs_per_folder: nullableInteger("max-songs-per-folder"),
    user_representation_top_k: nullableInteger("user-representation-top-k"),
    preserve_user_fraction: Number(readValue("preserve-user-fraction")),
    max_preserved_per_user: Number(readValue("max-preserved-per-user")),
  };

  const response = await fetch("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    window.alert(result.error || "Simulation failed.");
    return;
  }

  state.results = result;
  renderResults(result);
}

function renderResults(result) {
  const summary = document.getElementById("result-summary");
  const queueStrip = document.getElementById("queue-strip");

  summary.innerHTML = `
    ${statCard("Queue Score", result.queue_score?.toFixed(4) ?? "n/a")}
    ${statCard("Retrieved", result.meta.retrieved_candidates)}
    ${statCard("Ranked", result.meta.ranked_candidates)}
    ${statCard("Shortlist", result.meta.shortlist_size)}
    ${statCard("Method", result.meta.method.toUpperCase())}
  `;

  queueStrip.innerHTML = result.queue_rows
    .map(
      (row) => `
        <article class="queue-card">
          <span class="slot">Slot ${row.slot}</span>
          <h4>${escapeHtml(row.song)}</h4>
          <p><strong>Folder:</strong> ${escapeHtml(row.folder)}</p>
          <p><strong>Room Score:</strong> ${formatNumber(row.room_score)}</p>
          <p><strong>Transition:</strong> ${formatNumber(row.transition_from_prev)}</p>
        </article>
      `,
    )
    .join("");

  renderTable("shortlist-table", result.shortlist_rows, tableColumns.shortlist);
  renderTable("ranked-table", result.ranked_rows, inferColumns(result.ranked_rows));
  renderTable("retrieval-table", result.retrieval_rows, tableColumns.retrieval);
  renderTable(
    "queue-affinity-table",
    result.queue_affinity_rows,
    inferColumns(result.queue_affinity_rows),
  );
  renderTable("transition-table", result.transition_rows, tableColumns.transitions);
  renderUserSummaryGrid(result.user_summary_rows);
  renderSeedNeighbors(result.seed_neighbor_rows);
}

function renderTable(targetId, rows, columns) {
  const target = document.getElementById(targetId);
  if (!rows.length) {
    target.innerHTML = `<div class="empty-state">No rows to show.</div>`;
    return;
  }

  const header = columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((column) => `<td>${renderCell(row[column])}</td>`)
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");

  target.innerHTML = `
    <table>
      <thead><tr>${header}</tr></thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function inferColumns(rows) {
  if (!rows.length) return [];
  return Object.keys(rows[0]);
}

function statCard(label, value) {
  return `
    <article class="stat-card">
      <span class="stat-label">${escapeHtml(label)}</span>
      <span class="stat-value">${escapeHtml(String(value))}</span>
    </article>
  `;
}

function renderCell(value) {
  if (Array.isArray(value)) {
    return escapeHtml(value.join(", "));
  }
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "number") {
    return formatNumber(value);
  }
  return escapeHtml(String(value));
}

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return Number(value).toFixed(4);
}

function readValue(id) {
  return document.getElementById(id).value;
}

function nullableNumber(id) {
  const value = readValue(id).trim();
  return value ? Number(value) : null;
}

function nullableInteger(id) {
  const value = readValue(id).trim();
  return value ? Number.parseInt(value, 10) : null;
}

function groupSongsByFolder(rows) {
  const grouped = {};
  for (const row of rows) {
    if (!grouped[row.folder]) {
      grouped[row.folder] = [];
    }
    grouped[row.folder].push(row);
  }
  return grouped;
}

function renderUserSummaryGrid(rows) {
  const target = document.getElementById("user-summary-grid");
  if (!target) return;
  if (!rows.length) {
    target.innerHTML = `<div class="empty-state">Run a simulation to inspect user-level diagnostics.</div>`;
    return;
  }
  target.innerHTML = rows
    .map(
      (row) => `
        <article class="user-summary-card">
          <h4>${escapeHtml(row.user)}</h4>
          <div class="summary-block">
            <span class="summary-label">Liked Songs</span>
            <div class="selected-songs">
              ${row.liked_songs.map((song) => `<span class="song-chip">${escapeHtml(song)}</span>`).join("")}
            </div>
          </div>
          <div class="summary-block">
            <span class="summary-label">Top Ranked For This User</span>
            <div class="mini-list">
              ${(row.top_candidates || [])
                .map(
                  (entry) => `
                    <div class="mini-row">
                      <strong>${escapeHtml(entry.song)}</strong>
                      <span>${escapeHtml(entry.folder)} · ${formatNumber(entry.user_score)}</span>
                    </div>
                  `,
                )
                .join("")}
            </div>
          </div>
          <div class="summary-block">
            <span class="summary-label">Best Queue Matches</span>
            <div class="mini-list">
              ${(row.queue_matches || [])
                .map(
                  (entry) => `
                    <div class="mini-row">
                      <strong>${escapeHtml(entry.song)}</strong>
                      <span>${escapeHtml(entry.folder)} · ${formatNumber(entry.user_score)}</span>
                    </div>
                  `,
                )
                .join("")}
            </div>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderSeedNeighbors(rows) {
  const target = document.getElementById("seed-neighbors-grid");
  if (!target) return;
  if (!rows.length) {
    target.innerHTML = `<div class="empty-state">Run a simulation to inspect seed-song neighborhoods.</div>`;
    return;
  }
  target.innerHTML = rows
    .map(
      (row) => `
        <article class="seed-card">
          <h4>${escapeHtml(row.user)}</h4>
          <p class="muted-inline">${escapeHtml(row.seed_song)} · ${escapeHtml(row.seed_folder)}</p>
          <div class="mini-list" style="margin-top: 12px;">
            ${(row.neighbors || [])
              .map(
                (entry) => `
                  <div class="mini-row">
                    <strong>${escapeHtml(entry.song)}</strong>
                    <span>${escapeHtml(entry.folder)} · ${formatNumber(entry.score)}</span>
                  </div>
                `,
              )
              .join("")}
          </div>
        </article>
      `,
    )
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}
