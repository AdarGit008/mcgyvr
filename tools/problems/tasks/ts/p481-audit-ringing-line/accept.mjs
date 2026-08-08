import assert from "node:assert/strict";
import { auditRingingLine } from "./solution.ts";

assert.deepEqual(
  auditRingingLine([
    [1, 2, 3, 4],
    [2, 1, 4, 3],
    [2, 4, 1, 3],
    [4, 2, 3, 1],
    [4, 3, 2, 1],
    [3, 4, 1, 2],
    [3, 1, 4, 2],
    [1, 3, 2, 4],
    [1, 2, 3, 4],
  ]),
  { ok: true, fault: "", row: 0 },
  "a line that comes round cleanly is clean",
);

assert.deepEqual(
  auditRingingLine([
    [1, 2, 3, 4],
    [3, 1, 2, 4],
  ]),
  { ok: false, fault: "jump", row: 2 },
  "a bell shifting two places is a jump even though the bells are all there",
);

assert.deepEqual(
  auditRingingLine([
    [1, 2, 3, 4],
    [1, 2, 3, 3],
  ]),
  { ok: false, fault: "shape", row: 2 },
  "a row holding a bell twice is faulted on shape",
);

assert.deepEqual(
  auditRingingLine([
    [1, 2, 3, 4],
    [2, 1, 3, 4],
    [1, 2, 3, 4],
    [2, 1, 3, 4],
  ]),
  { ok: false, fault: "repeat", row: 3 },
  "rounds partway through a line is a repeat",
);

assert.deepEqual(
  auditRingingLine([
    [1, 2, 3, 4],
    [2, 1, 3, 4],
    [1, 2, 3, 4],
  ]),
  { ok: true, fault: "", row: 0 },
  "rounds as the last row written is where a line ends",
);

assert.deepEqual(
  auditRingingLine([[1, 2]]),
  { ok: true, fault: "", row: 0 },
  "a line of rounds alone has nothing to fault",
);

assert.deepEqual(
  auditRingingLine([
    [1, 2, 3, 4],
    [1, 2, 3],
  ]),
  { ok: false, fault: "shape", row: 2 },
  "a row shorter than the opening one is faulted on shape",
);

assert.deepEqual(
  auditRingingLine([
    [1, 2, 3, 4],
    [2, 1, 3, 4],
    [2, 1, 4, 3],
    [4, 2, 1, 3],
  ]),
  { ok: false, fault: "jump", row: 4 },
  "the fault is numbered from the opening row",
);

assert.deepEqual(
  auditRingingLine([
    [1, 2, 3, 4],
    [2, 1, 4, 3],
    [2, 4, 1, 3],
    [1, 2, 3, 4],
  ]),
  { ok: false, fault: "jump", row: 4 },
  "coming round at the end still has to be reached one place at a time",
);

assert.throws(
  () => auditRingingLine("1234"),
  Error,
  "a rows argument that is not a list is rejected",
);
assert.throws(
  () => auditRingingLine([]),
  Error,
  "an empty rows argument is rejected",
);
assert.throws(
  () => auditRingingLine([[1, 2], "21"]),
  Error,
  "a row that is not a list is rejected",
);
assert.throws(
  () => auditRingingLine([[1, 2], [2, 1.5]]),
  Error,
  "a row entry that is not whole is rejected",
);
assert.throws(
  () => auditRingingLine([[1]]),
  Error,
  "an opening row of one bell is rejected",
);
assert.throws(
  () => auditRingingLine([[2, 1]]),
  Error,
  "an opening row that is not rounds is rejected",
);
console.log("ok");
