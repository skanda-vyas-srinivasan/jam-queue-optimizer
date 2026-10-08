/* DOM and media-event simulation; this does not render or open a real browser. */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const panel = path.join(__dirname, "../music_queue/debug_panel");
const tick = () => new Promise((resolve) => setImmediate(resolve));
async function settled() {
  for (let i = 0; i < 12; i++) await tick();
}
async function app() {
  const html = fs
    .readFileSync(path.join(panel, "index.html"), "utf8")
    .replace(/<script[\s\S]*?<\/script>/g, "");
  const dom = new JSDOM(html, {
    url: "http://127.0.0.1:8765",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const w = dom.window,
    calls = [];
  let clock = 0,
    revision = 1,
    currentSession = null;
  w.structuredClone = structuredClone;
  w.scrollTo = () => {};
  Object.defineProperty(w.performance, "now", { value: () => clock });
  Object.defineProperty(w.HTMLMediaElement.prototype, "paused", {
    get() {
      return this._paused ?? true;
    },
  });
  w.HTMLMediaElement.prototype.play = async function () {
    this._paused = false;
    this.dispatchEvent(new w.Event("playing"));
  };
  w.HTMLMediaElement.prototype.pause = function () {
    this._paused = true;
    this.dispatchEvent(new w.Event("pause"));
  };
  w.HTMLMediaElement.prototype.load = function () {
    this.currentTime = 0;
    this._paused = true;
  };
  w.Plotly = {
    react: async (id) => {
      const el = w.document.getElementById(id);
      el._events = {};
      el.on = (name, fn) => {
        el._events[name] = fn;
      };
      el.removeAllListeners = (name) => {
        delete el._events[name];
      };
    },
    Plots: { resize: () => {} },
    purge: (id) => {
      w.document.getElementById(id).innerHTML = "";
    },
  };
  const songs = Array.from({ length: 6 }, (_, i) => ({
    track_id: `t${i}`,
    song: i === 0 ? "Song <zero>" : "Song " + i,
    folder: i < 3 ? "A" : "B",
    duration: 180,
    audio_available: true,
  }));
  const listeners = [
    {
      id: "u",
      name: "Alex",
      liked: ["t0", "t1"],
      accepted: [],
      disliked: [],
      blocked: [],
    },
    {
      id: "v",
      name: "Alex",
      liked: ["t2", "t3"],
      accepted: [],
      disliked: [],
      blocked: [],
    },
  ];
  const groups = [
    { id: 0, name: "Cluster 1", members: ["t0", "t1", "t2"] },
    { id: 1, name: "Cluster 2", members: ["t3", "t4", "t5"] },
  ];
  const provenance = {
    full_eligible_count: 6,
    requested_shortlist_size: 3,
    actual_shortlist_size: 3,
    exclusions: [],
    expanded_for_feasibility: false,
    selection_reasons: {
      t0: ["joint_feasible_cover"],
      t2: ["joint_feasible_cover"],
      t4: ["full_catalog_rank"],
    },
    ranked_rows: songs.map((s, i) => ({
      ...s,
      room_score: 1 - i * 0.1,
      listener_scores: { u: 1 - i * 0.1, v: i * 0.1 },
      evidence: {
        u: i < 2 ? "known_like" : "predicted_acoustic",
        v: i === 2 ? "known_like" : "predicted_acoustic",
      },
    })),
  };
  const prepared = {
    status: "FEASIBLE_NOT_PROVEN",
    snapshot_token: "frozen",
    instance_hash: "frozen-hash",
    candidate_scope_hash: "candidate-hash",
    provenance,
    listeners,
    candidates: ["t0", "t2", "t4"],
    transition_matrix: [
      [0, 0.2, 0.3],
      [0.4, 0, 0.2],
      [0.1, 0.2, 0],
    ],
  };
  const result = (queue = ["t0", "t2"], optimal = true, session = null) => ({
    queue,
    queue_rows: queue.map((id, i) => ({
      ...songs.find((s) => s.track_id === id),
      slot: i + 1,
    })),
    status: optimal ? "OPTIMAL" : "FEASIBLE_NOT_PROVEN",
    valid_incumbent: true,
    proven_optimal: optimal,
    returned_length: 2,
    requested_length: 2,
    termination_reason: optimal
      ? "All phases proven"
      : "Manual order independently validated",
    phases: [],
    transition_rows: [],
    per_listener: {
      u: {
        display_name: "Alex",
        accepted_count: 1,
        accepted_seconds: 180,
        first_acceptable_wait_seconds: 0,
        representation_deficit: 0,
      },
    },
    objective_components: {},
    timings: { total: 0.1 },
    provenance,
    snapshot_token: "frozen",
    instance_hash: "frozen-hash",
    session,
  });
  w.fetch = async (url, options = {}) => {
    const body = options.body ? JSON.parse(options.body) : undefined;
    calls.push({ url, body });
    let data;
    if (url === "/api/catalog")
      data = { count: songs.length, songs, model_hash: "model" };
    else if (url === "/api/sample-room")
      data = { listeners: structuredClone(listeners) };
    else if (url === "/api/explore")
      data = {
        groups: structuredClone(groups),
        actual_clusters: 2,
        dimensions: body.dimensions,
        space: body.space,
        family: body.family,
        explained_variance: [0.6, 0.2],
        points: songs.map((s, i) => ({
          ...s,
          cluster: i < 3 ? 0 : 1,
          coordinates: [i, i, 0],
        })),
      };
    else if (url.startsWith("/api/song-details"))
      data = { neighbors: [{ track_id: "t4", song: "Song 4", score: 0.5 }] };
    else if (url === "/api/retrieve")
      data = { rows: [{ ...songs[4], score: 0.7, nearest_seed: "t0" }] };
    else if (url === "/api/pipeline") data = structuredClone(prepared);
    else if (url === "/api/sequence") data = result();
    else if (url === "/api/order") data = result(body.queue, false);
    else if (url === "/api/session/create") {
      currentSession = {
        id: "session",
        revision,
        listeners,
        histories: {
          u: {
            played_seconds: 0,
            accepted_seconds: 0,
            disliked_seconds: 0,
            wait_seconds: 0,
            debt_seconds: 0,
          },
        },
        played_tracks: [],
        promised_next: null,
        current_track: null,
      };
      data = structuredClone(currentSession);
    } else if (url === "/api/simulate") {
      revision++;
      currentSession = {
        ...currentSession,
        revision,
        promised_next: "t0",
        queue: ["t0", "t2"],
      };
      data = result(["t0", "t2"], true, structuredClone(currentSession));
    } else if (url === "/api/session/playback") {
      assert.equal(body.revision, revision);
      revision++;
      currentSession = {
        ...currentSession,
        revision,
        promised_next: "t2",
        played_tracks: [body.track_id],
        histories: {
          u: {
            played_seconds: body.seconds,
            accepted_seconds: body.seconds,
            disliked_seconds: 0,
            wait_seconds: 0,
            debt_seconds: 0,
          },
        },
      };
      data = structuredClone(currentSession);
    } else throw new Error("Unhandled endpoint " + url);
    return { ok: true, json: async () => data };
  };
  w.eval(fs.readFileSync(path.join(panel, "ui-core.js"), "utf8"));
  w.eval(fs.readFileSync(path.join(panel, "app.js"), "utf8"));
  await settled();
  const get = (id) => w.document.getElementById(id);
  const click = async (el) => {
    (typeof el === "string" ? get(el) : el).click();
    await settled();
  };
  return {
    dom,
    w,
    get,
    click,
    calls,
    playSeconds: async (seconds) => {
      clock += seconds * 1000;
      get("audio").currentTime += seconds;
      get("audio").dispatchEvent(new w.Event("timeupdate"));
      await settled();
    },
  };
}

test("navigation, escaped titles, selection and manual clusters work together", async (t) => {
  const a = await app();
  t.after(() => a.dom.window.close());
  assert.match(a.get("catalog-count").textContent, /6 tracks/);
  assert.equal(a.get("library-table").querySelector("zero"), null);
  await a.click(a.w.document.querySelector('[data-select-group="0"]'));
  assert.match(a.get("selection-count").textContent, /3 selected/);
  await a.click("new-cluster");
  assert.equal(a.get("clusters").querySelectorAll(".cluster-row").length, 3);
  assert.equal(
    a.get("library-table").querySelectorAll("input:checked").length,
    3,
  );
  await a.click(a.w.document.querySelector('[data-view="profiles"]'));
  assert.equal(a.get("view-profiles").hidden, false);
  assert.equal(a.get("view-library").hidden, true);
  assert.equal(a.get("users").querySelectorAll(".user-card").length, 2);
});
test("retrieval evidence is explicit and uses the selected listener", async (t) => {
  const a = await app();
  t.after(() => a.dom.window.close());
  a.get("retrieval-listener").value = "v";
  await a.click("use-profile-seeds");
  await a.click("retrieve");
  assert.deepEqual(a.calls.find((c) => c.url === "/api/retrieve").body.seeds, [
    "t2",
    "t3",
  ]);
  await a.click(a.w.document.querySelector('[data-neighbor-like="t4"]'));
  assert.match(
    a.get("users").querySelector('[data-listener="1"]').textContent,
    /liked · Song 4/,
  );
  assert.doesNotMatch(
    a.get("users").querySelector('[data-listener="0"]').querySelector(".chips")
      .textContent,
    /Song 4/,
  );
});
test("prepared snapshot survives method choice; manual reordering drops proof; edits invalidate it", async (t) => {
  const a = await app();
  t.after(() => a.dom.window.close());
  assert.equal(a.get("run").disabled, true);
  await a.click("prepare");
  a.get("method").value = "dp";
  await a.click("run");
  assert.equal(
    a.calls.find((c) => c.url === "/api/sequence").body.snapshot_token,
    "frozen",
  );
  assert.match(a.get("summary").textContent, /Proved on shortlist/);
  assert.equal(a.get("queue").querySelectorAll(".queue-row").length, 2);
  await a.click(
    a.w.document.querySelector('[data-move-queue="1"][data-direction="-1"]'),
  );
  assert.deepEqual(a.calls.find((c) => c.url === "/api/order").body.queue, [
    "t2",
    "t0",
  ]);
  assert.match(a.get("summary").textContent, /No complete proof/);
  a.get("discovery-budget").value = "1";
  a.get("discovery-budget").dispatchEvent(new a.w.Event("change"));
  assert.equal(a.get("run").disabled, true);
  assert.equal(a.get("play-queue").disabled, true);
});
test("static queue advances on media end and preserves a single local player", async (t) => {
  const a = await app();
  t.after(() => a.dom.window.close());
  await a.click("prepare");
  await a.click("run");
  await a.click("play-queue");
  assert.match(a.get("audio").src, /track_id=t0/);
  a.get("audio").dispatchEvent(new a.w.Event("ended"));
  await settled();
  assert.match(a.get("audio").src, /track_id=t2/);
  a.get("audio").dispatchEvent(new a.w.Event("ended"));
  await settled();
  assert.equal(a.get("audio").getAttribute("src"), null);
  assert.equal(
    a.calls.filter((c) => c.url === "/api/session/playback").length,
    0,
  );
});
test("session skip logs observed playing time, and zero-time stop keeps the next promise", async (t) => {
  const a = await app();
  t.after(() => a.dom.window.close());
  await a.click("start-session");
  await a.click("run");
  await a.click("play-queue");
  await a.playSeconds(2);
  await a.click("next");
  const playback = a.calls.find((c) => c.url === "/api/session/playback");
  assert.equal(playback.body.track_id, "t0");
  assert.equal(playback.body.seconds, 2);
  assert.match(a.get("audio").src, /track_id=t2/);
  await a.click("stop");
  assert.equal(
    a.calls.filter((c) => c.url === "/api/session/playback").length,
    1,
  );
  assert.match(a.get("session-state").textContent, /promised next: Song 2/);
  assert.equal(a.get("audio").getAttribute("src"), null);
});

test("native pause and seek events do not add unheard time to a session", async (t) => {
  const a = await app();
  t.after(() => a.dom.window.close());
  await a.click("start-session");
  await a.click("run");
  await a.click("play-queue");
  await a.playSeconds(1);
  a.get("audio").pause();
  await a.playSeconds(3); // paused media cannot count as exposure
  a.get("audio").dispatchEvent(new a.w.Event("seeking"));
  a.get("audio").currentTime = 90;
  a.get("audio").dispatchEvent(new a.w.Event("seeked"));
  await a.get("audio").play();
  await a.playSeconds(2);
  await a.click("stop");
  const playback = a.calls.find((c) => c.url === "/api/session/playback");
  assert.equal(playback.body.seconds, 3);
});
