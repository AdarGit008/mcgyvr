import assert from "node:assert/strict";
import { replayRingLog } from "./solution.ts";

assert.deepEqual(
  replayRingLog(2, "overwrite", [
    ["push", "a"],
    ["push", "b"],
    ["push", "c"],
    ["pop"],
    ["pop"],
  ]),
  {
    contents: [],
    journal: ["stored", "stored", "evicted a", "took b", "took c"],
    lost: 1,
  },
  "overwrite drops the oldest label and names it in the journal",
);
assert.deepEqual(
  replayRingLog(2, "refuse", [
    ["push", "a"],
    ["push", "b"],
    ["push", "c"],
    ["pop"],
    ["pop"],
  ]),
  {
    contents: [],
    journal: ["stored", "stored", "refused", "took a", "took b"],
    lost: 1,
  },
  "refuse leaves the seated labels untouched and turns the new one away",
);
assert.deepEqual(
  replayRingLog(1, "overwrite", [
    ["push", "x"],
    ["push", "y"],
    ["peek"],
    ["pop"],
    ["peek"],
  ]),
  {
    contents: [],
    journal: ["stored", "evicted x", "front y", "took y", "bare"],
    lost: 1,
  },
  "a one-seat ring always evicts, and a drained ring reads bare",
);
assert.deepEqual(
  replayRingLog(3, "overwrite", [
    ["push", "a"],
    ["push", "b"],
    ["push", "c"],
    ["push", "d"],
    ["push", "e"],
  ]),
  {
    contents: ["c", "d", "e"],
    journal: ["stored", "stored", "stored", "evicted a", "evicted b"],
    lost: 2,
  },
  "contents run oldest to newest after the ring wraps",
);
assert.deepEqual(
  replayRingLog(2, "refuse", [
    ["push", "a"],
    ["push", "b"],
    ["push", "c"],
    ["pop"],
    ["push", "c"],
  ]),
  {
    contents: ["b", "c"],
    journal: ["stored", "stored", "refused", "took a", "stored"],
    lost: 1,
  },
  "a pop frees a seat that a later push may take",
);
assert.deepEqual(
  replayRingLog(2, "overwrite", [["push", "a"], ["peek"], ["peek"], ["pop"]]),
  { contents: [], journal: ["stored", "front a", "front a", "took a"], lost: 0 },
  "peeking never removes the label it reads",
);
assert.deepEqual(
  replayRingLog(1, "refuse", [["pop"], ["peek"]]),
  { contents: [], journal: ["bare", "bare"], lost: 0 },
  "reads against an empty ring cost nothing",
);
assert.deepEqual(
  replayRingLog(4, "overwrite", []),
  { contents: [], journal: [], lost: 0 },
  "no operations leave an empty journal",
);
assert.deepEqual(
  replayRingLog(2, "overwrite", [
    ["push", "a"],
    ["push", "a"],
    ["push", "a"],
  ]),
  { contents: ["a", "a"], journal: ["stored", "stored", "evicted a"], lost: 1 },
  "repeated labels occupy separate seats",
);

assert.throws(() => replayRingLog(0, "refuse", []), Error, "a zero capacity is rejected");
assert.throws(() => replayRingLog(2.5, "refuse", []), Error, "a fractional capacity is rejected");
assert.throws(() => replayRingLog(2, "drop", []), Error, "an unknown policy is rejected");
assert.throws(() => replayRingLog(2, "refuse", "pop"), Error, "a non-list replay is rejected");
assert.throws(() => replayRingLog(2, "refuse", [[]]), Error, "an empty operation is rejected");
assert.throws(() => replayRingLog(2, "refuse", [["shove", "a"]]), Error, "an unknown name is rejected");
assert.throws(() => replayRingLog(2, "refuse", [["push"]]), Error, "a push with no label is rejected");
assert.throws(() => replayRingLog(2, "refuse", [["push", ""]]), Error, "an empty label is rejected");
assert.throws(() => replayRingLog(2, "refuse", [["pop", "a"]]), Error, "a pop with a label is rejected");
console.log("ok");
