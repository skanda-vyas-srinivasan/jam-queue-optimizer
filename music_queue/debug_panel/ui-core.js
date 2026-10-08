/* Shared state operations, independent of browser APIs. */
(function (root) {
  "use strict";
  const unique = (values) => [...new Set(values)];
  function addEvidence(listener, ids, field) {
    if (!["liked", "accepted", "disliked", "blocked"].includes(field))
      throw new Error("Unknown evidence label");
    const result = { ...listener };
    for (const key of ["liked", "accepted", "disliked", "blocked"])
      result[key] = [...(listener[key] || [])];
    result[field] = unique([...result[field], ...ids]);
    if (field === "disliked")
      for (const positive of ["liked", "accepted"])
        result[positive] = result[positive].filter((id) => !ids.includes(id));
    if (["liked", "accepted"].includes(field))
      result.disliked = result.disliked.filter((id) => !ids.includes(id));
    return result;
  }
  function assignGroup(groups, ids, target) {
    if (!groups.some((g) => g.id === target)) throw new Error("Choose a group");
    return groups.map((g) => ({
      ...g,
      members: unique([
        ...g.members.filter((id) => !ids.includes(id)),
        ...(g.id === target ? ids : []),
      ]),
    }));
  }
  function moveQueue(queue, index, direction) {
    const copy = [...queue],
      next = index + direction;
    if (index < 0 || index >= copy.length || next < 0 || next >= copy.length)
      return copy;
    [copy[index], copy[next]] = [copy[next], copy[index]];
    return copy;
  }
  function observedDelta(
    previousTime,
    currentTime,
    wallSeconds,
    seeking,
    paused,
  ) {
    if (seeking || paused || previousTime == null || wallSeconds < 0) return 0;
    return Math.max(
      0,
      Math.min(currentTime - previousTime, wallSeconds * 1.25),
    );
  }
  const api = { unique, addEvidence, assignGroup, moveQueue, observedDelta };
  root.JamUI = api;
  if (typeof module !== "undefined") module.exports = api;
})(globalThis);
