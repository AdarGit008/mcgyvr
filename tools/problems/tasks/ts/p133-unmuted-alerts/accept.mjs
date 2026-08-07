import assert from "node:assert/strict";
import { unmutedAlerts } from "./solution.ts";

const alert = (id, resource, severity) => ({ id, resource, severity });

assert.deepEqual(
  unmutedAlerts([alert("db1", "db", 2), alert("web1", "web", 5)]),
  ["web1", "db1"],
  "muting is per resource, so the quieter resource still shows its alert",
);
assert.deepEqual(
  unmutedAlerts([alert("low", "db", 2), alert("high", "db", 4)]),
  ["high"],
  "a strictly higher severity on the same resource mutes the lower one",
);
assert.deepEqual(
  unmutedAlerts([alert("b", "db", 3), alert("a", "db", 3)]),
  ["a", "b"],
  "equal severities never mute each other and tie-break by id",
);
assert.deepEqual(
  unmutedAlerts([alert("a", "r1", 2), alert("z", "r2", 9)]),
  ["z", "a"],
  "the shortlist orders by severity descending, not by id",
);
assert.deepEqual(
  unmutedAlerts([
    alert("m", "r1", 1),
    alert("n", "r1", 7),
    alert("p", "r2", 7),
    alert("q", "r3", 4),
  ]),
  ["n", "p", "q"],
  "three resources keep their own winners, ties by id",
);
assert.deepEqual(unmutedAlerts([]), [], "no alerts yields an empty shortlist");
assert.deepEqual(
  unmutedAlerts([alert("solo", "cache", 1)]),
  ["solo"],
  "a lone alert is never muted",
);
assert.throws(
  () => unmutedAlerts([alert("dup", "db", 2), alert("dup", "web", 3)]),
  Error,
  "a shared id is rejected",
);
assert.throws(
  () => unmutedAlerts([alert("x", "db", 0)]),
  Error,
  "severity 0 is rejected",
);
assert.throws(
  () => unmutedAlerts([alert("x", "db", 2.5)]),
  Error,
  "a fractional severity is rejected",
);
console.log("ok");
