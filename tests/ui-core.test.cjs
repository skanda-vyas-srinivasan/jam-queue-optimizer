const { test } = require("node:test");
const assert = require("node:assert/strict");
const ui = require("../music_queue/debug_panel/ui-core.js");

test("assigning a manual group leaves exactly one membership per track", () => {
  const groups = [
    { id: 0, name: "A", members: ["a", "b"] },
    { id: 1, name: "B", members: ["c"] },
  ];
  const after = ui.assignGroup(groups, ["a", "a"], 1);
  assert.deepEqual(
    after.map((g) => g.members),
    [["b"], ["c", "a"]],
  );
  assert.deepEqual(groups[0].members, ["a", "b"]);
});
test("ordinary dislike clears conflicting positives while blocks retain evidence", () => {
  const listener = {
    id: "u",
    liked: ["a"],
    accepted: ["a"],
    disliked: [],
    blocked: [],
  };
  const disliked = ui.addEvidence(listener, ["a"], "disliked");
  assert.deepEqual(disliked.liked, []);
  assert.deepEqual(disliked.accepted, []);
  const blocked = ui.addEvidence(listener, ["a"], "blocked");
  assert.deepEqual(blocked.liked, ["a"]);
  assert.deepEqual(blocked.blocked, ["a"]);
});
test("manual order is a copy of the same selection", () => {
  const queue = ["a", "b", "c"];
  assert.deepEqual(ui.moveQueue(queue, 1, -1), ["b", "a", "c"]);
  assert.deepEqual(queue, ["a", "b", "c"]);
  assert.deepEqual(ui.moveQueue(queue, 0, -1), queue);
});
test("seeking, pauses and time jumps cannot manufacture listening seconds", () => {
  assert.equal(ui.observedDelta(1, 2, 1, false, false), 1);
  assert.equal(ui.observedDelta(1, 90, 1, true, false), 0);
  assert.equal(ui.observedDelta(1, 90, 1, false, true), 0);
  assert.equal(ui.observedDelta(1, 90, 1, false, false), 1.25);
  assert.equal(ui.observedDelta(90, 1, 1, false, false), 0);
});
