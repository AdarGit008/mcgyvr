import assert from "node:assert/strict";
import { buildOnCallRota } from "./solution.ts";

assert.deepEqual(
  buildOnCallRota(["ana", "bo", "cy"], [[], [], [], [], [], []]),
  ["ana", "bo", "cy", "ana", "bo", "cy"],
  "an unhindered week cycles the roster",
);
assert.deepEqual(
  buildOnCallRota(["ana", "bo", "cy"], [["ana"], [], []]),
  ["bo", "ana", "cy"],
  "a block on the opening shift shuffles the order",
);
assert.deepEqual(
  buildOnCallRota(["ana", "bo", "cy"], [[], [], [], []]),
  ["ana", "bo", "cy", "ana"],
  "four shifts across three people",
);
assert.deepEqual(
  buildOnCallRota(
    ["ana", "bo", "cy"],
    [[], ["ana", "cy"], [], ["bo"], []],
  ),
  ["ana", "bo", "cy", "ana", "bo"],
  "blocks in the middle still balance out",
);
assert.deepEqual(
  buildOnCallRota(["ana", "bo"], [[], [], []]),
  ["ana", "bo", "ana"],
  "the ceiling of two lets ana stand twice",
);
assert.deepEqual(
  buildOnCallRota(["ana", "bo"], [[]]),
  ["ana"],
  "a lone shift goes to the first of the roster",
);
assert.deepEqual(
  buildOnCallRota(["ana", "bo"], [[], ["bo"], []]),
  [],
  "no one may follow ana, so the rota is impossible",
);
assert.deepEqual(
  buildOnCallRota(["ana"], [[], []]),
  [],
  "one person cannot stand two shifts in a row",
);
assert.deepEqual(
  buildOnCallRota(["ana", "bo"], [["ana", "bo"]]),
  [],
  "a shift everyone is blocked from is impossible",
);
assert.throws(
  () => buildOnCallRota([], [[]]),
  Error,
  "an empty roster is rejected",
);
assert.throws(
  () => buildOnCallRota(["ana", "ana"], [[]]),
  Error,
  "a repeated roster name is rejected",
);
assert.throws(
  () => buildOnCallRota(["ana", ""], [[]]),
  Error,
  "an empty roster name is rejected",
);
assert.throws(
  () => buildOnCallRota(["ana", "bo"], []),
  Error,
  "having no shifts at all is rejected",
);
assert.throws(
  () => buildOnCallRota(["ana", "bo"], [["dee"]]),
  Error,
  "blocking a stranger is rejected",
);
assert.throws(
  () => buildOnCallRota(["ana", "bo"], [["ana", "ana"]]),
  Error,
  "blocking one name twice is rejected",
);
assert.throws(
  () => buildOnCallRota(["ana", "bo"], ["ana"]),
  Error,
  "a blocked entry that is not a list is rejected",
);
console.log("ok");
