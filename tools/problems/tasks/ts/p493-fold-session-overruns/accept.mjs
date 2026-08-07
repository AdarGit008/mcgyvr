import assert from "node:assert/strict";
import { foldSessionOverruns } from "./solution.ts";

const turn = (speaker, slot, ran, pause) => ({ speaker, slot, ran, pause });

assert.deepEqual(
  foldSessionOverruns(
    [turn("ines", 20, 35, 10), turn("omar", 15, 15, 5), turn("pia", 10, 20, 0)],
    60,
  ),
  {
    lines: ["ines 0 35 full", "omar 35 50 full", "pia 55 60 cut"],
    spill: [],
    finish: 60,
  },
  "a squeezed break stops at nought and the last turn is guillotined",
);

assert.deepEqual(
  foldSessionOverruns([turn("kai", 30, 30, 0), turn("lena", 10, 10, 0)], 30),
  { lines: ["kai 0 30 full"], spill: ["lena"], finish: 30 },
  "a turn beginning exactly on the wall never happens",
);

assert.deepEqual(
  foldSessionOverruns(
    [turn("a", 10, 25, 0), turn("b", 5, 5, 0), turn("c", 5, 5, 0)],
    20,
  ),
  { lines: ["a 0 20 cut"], spill: ["b", "c"], finish: 20 },
  "everything behind a guillotined turn spills",
);

assert.deepEqual(
  foldSessionOverruns([], 45),
  { lines: [], spill: [], finish: 0 },
  "an empty runsheet closes at nought",
);

assert.deepEqual(
  foldSessionOverruns([turn("x", 20, 12, 8), turn("y", 10, 10, 0)], 100),
  { lines: ["x 0 12 full", "y 20 30 full"], spill: [], finish: 30 },
  "a speaker inside the slot leaves the printed break whole",
);

assert.deepEqual(
  foldSessionOverruns([turn("p", 10, 13, 8), turn("q", 5, 5, 0)], 100),
  { lines: ["p 0 13 full", "q 18 23 full"], spill: [], finish: 23 },
  "a small overrun squeezes part of the break",
);

assert.deepEqual(
  foldSessionOverruns([turn("solo", 5, 0, 3)], 12),
  { lines: ["solo 0 0 full"], spill: [], finish: 0 },
  "a speaker who uses no minutes still holds the lectern",
);

assert.throws(() => foldSessionOverruns("nope", 10), Error, "runsheet must be a list");
assert.throws(() => foldSessionOverruns([7], 10), Error, "an entry must be a record");
assert.throws(
  () => foldSessionOverruns([{ speaker: "z", slot: 5, ran: 5 }], 10),
  Error,
  "a missing key is refused",
);
assert.throws(
  () => foldSessionOverruns([turn("", 5, 5, 0)], 10),
  Error,
  "an empty speaker is refused",
);
assert.throws(
  () => foldSessionOverruns([turn("z", 5, 5, 0), turn("z", 4, 4, 0)], 10),
  Error,
  "a repeated speaker is refused",
);
assert.throws(
  () => foldSessionOverruns([turn("z", 0, 5, 0)], 10),
  Error,
  "a slot of nought is refused",
);
assert.throws(
  () => foldSessionOverruns([turn("z", 5, -1, 0)], 10),
  Error,
  "a negative ran is refused",
);
assert.throws(
  () => foldSessionOverruns([turn("z", 5, 5, -3)], 10),
  Error,
  "a negative pause is refused",
);
assert.throws(
  () => foldSessionOverruns([turn("z", 5, 5, 0)], 0),
  Error,
  "a wall of nought is refused",
);
console.log("ok");
