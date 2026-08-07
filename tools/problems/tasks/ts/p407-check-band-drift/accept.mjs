import assert from "node:assert/strict";
import { checkBandDrift } from "./solution.ts";

assert.deepEqual(
  checkBandDrift(
    [
      { code: "L1", hits: 500, was: "A" },
      { code: "L2", hits: 300, was: "C" },
      { code: "L3", hits: 150, was: "A" },
      { code: "L4", hits: 50, was: "C" },
    ],
    [700, 950],
  ),
  { up: ["L2"], down: ["L3"], steady: 2 },
  "one code nearer, one further, two unmoved",
);

assert.deepEqual(
  checkBandDrift(
    [
      { code: "P", hits: 60, was: "B" },
      { code: "Q", hits: 30, was: "B" },
      { code: "R", hits: 10, was: "A" },
      { code: "Z", hits: 0, was: "C" },
    ],
    [600, 900],
  ),
  { up: ["P"], down: ["R"], steady: 2 },
  "a code with no hits at all rides on the last class",
);

assert.deepEqual(
  checkBandDrift(
    [
      { code: "B", hits: 100, was: "B" },
      { code: "A", hits: 100, was: "A" },
    ],
    [500, 900],
  ),
  { up: [], down: ["B"], steady: 1 },
  "a tie of hits is swept by code, and the pile is weighed after the entry",
);

assert.deepEqual(
  checkBandDrift([{ code: "S", hits: 10, was: "A" }], [1, 999]),
  { up: [], down: ["S"], steady: 0 },
  "a lone code can outrun both marks",
);

assert.deepEqual(
  checkBandDrift(
    [
      { code: "M", hits: 6, was: "A" },
      { code: "N", hits: 3, was: "C" },
      { code: "O", hits: 1, was: "B" },
    ],
    [600, 900],
  ),
  { up: ["N"], down: ["O"], steady: 1 },
  "landing exactly on a mark keeps the nearer class",
);

const sound = [
  { code: "G", hits: 4, was: "A" },
  { code: "H", hits: 1, was: "C" },
];
assert.throws(() => checkBandDrift("x", [500, 900]), Error, "entries that are not a list");
assert.throws(() => checkBandDrift([], [500, 900]), Error, "no entries at all");
assert.throws(() => checkBandDrift([3], [500, 900]), Error, "an entry that is not a record");
assert.throws(
  () => checkBandDrift([{ code: "", hits: 1, was: "A" }], [500, 900]),
  Error,
  "an empty code",
);
assert.throws(
  () =>
    checkBandDrift(
      [
        { code: "G", hits: 1, was: "A" },
        { code: "G", hits: 2, was: "B" },
      ],
      [500, 900],
    ),
  Error,
  "one code twice",
);
assert.throws(
  () => checkBandDrift([{ code: "G", hits: -1, was: "A" }], [500, 900]),
  Error,
  "hits below nothing",
);
assert.throws(
  () => checkBandDrift([{ code: "G", hits: 1.5, was: "A" }], [500, 900]),
  Error,
  "fractional hits",
);
assert.throws(
  () => checkBandDrift([{ code: "G", hits: 1, was: "D" }], [500, 900]),
  Error,
  "a former class outside the three letters",
);
assert.throws(
  () => checkBandDrift([{ code: "G", hits: 0, was: "A" }], [500, 900]),
  Error,
  "a season with no hits at all",
);
assert.throws(() => checkBandDrift(sound, [500]), Error, "only one mark");
assert.throws(() => checkBandDrift(sound, [0, 900]), Error, "a mark below one");
assert.throws(() => checkBandDrift(sound, [500, 1000]), Error, "a mark above nine hundred and ninety-nine");
assert.throws(() => checkBandDrift(sound, [900, 500]), Error, "marks the wrong way round");
console.log("ok");
