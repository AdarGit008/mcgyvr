import assert from "node:assert/strict";
import { sirenMinutes } from "./solution.ts";

const raise = (at, id, channel, severity) => ({
  at,
  kind: "raise",
  id,
  channel,
  severity,
});
const clear = (at, id) => ({ at, kind: "clear", id });

assert.deepEqual(
  sirenMinutes([raise(0, "a", "ops", 3)], 10),
  [["a", 10]],
  "a lone alert sounds until the horizon",
);
assert.deepEqual(
  sirenMinutes([raise(0, "a", "ops", 2), raise(4, "b", "ops", 5)], 10),
  [
    ["a", 4],
    ["b", 6],
  ],
  "a higher severity takes over its channel",
);
assert.deepEqual(
  sirenMinutes([raise(0, "a", "ops", 3), raise(2, "b", "ops", 3)], 10),
  [
    ["a", 10],
    ["b", 0],
  ],
  "on a severity tie the earlier raise keeps sounding and the loser reports 0",
);
assert.deepEqual(
  sirenMinutes([raise(0, "a", "east", 1), raise(1, "b", "west", 5)], 5),
  [
    ["a", 5],
    ["b", 4],
  ],
  "channels sound independently",
);
assert.deepEqual(
  sirenMinutes(
    [raise(0, "a", "ops", 2), raise(2, "b", "ops", 5), clear(6, "b")],
    10,
  ),
  [
    ["a", 6],
    ["b", 4],
  ],
  "clearing the louder alert lets the suppressed one sound again",
);
assert.deepEqual(
  sirenMinutes(
    [raise(0, "a", "ops", 1), clear(3, "a"), raise(5, "a", "ops", 2)],
    8,
  ),
  [["a", 6]],
  "a re-raised id accumulates across both activations",
);
assert.deepEqual(sirenMinutes([], 5), [], "no events, no pairs");
assert.deepEqual(
  sirenMinutes([raise(0, "z", "one", 2), raise(1, "a", "two", 2)], 3),
  [
    ["a", 2],
    ["z", 3],
  ],
  "pairs come back sorted by id, not by raise order",
);
assert.throws(
  () => sirenMinutes([raise(0, "a", "ops", 2), raise(1, "a", "ops", 3)], 5),
  Error,
  "raising an active id is rejected",
);
assert.throws(
  () => sirenMinutes([clear(0, "ghost")], 5),
  Error,
  "clearing an inactive id is rejected",
);
assert.throws(
  () => sirenMinutes([raise(3, "a", "ops", 2), raise(3, "b", "ops", 2)], 5),
  Error,
  "equal event times are rejected",
);
assert.throws(
  () => sirenMinutes([raise(9, "a", "ops", 2)], 5),
  Error,
  "an event past the horizon is rejected",
);
assert.throws(
  () => sirenMinutes([raise(0, "a", "ops", 6)], 5),
  Error,
  "severity 6 is rejected",
);
assert.throws(
  () => sirenMinutes([{ at: 0, kind: "ack", id: "a" }], 5),
  Error,
  "an unknown kind is rejected",
);
assert.throws(
  () => sirenMinutes([raise(0, "a", "ops", 2)], "10"),
  Error,
  "a non-integer horizon is rejected",
);
console.log("ok");
