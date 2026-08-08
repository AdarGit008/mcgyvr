import assert from "node:assert/strict";
import { sweepLogGenerations } from "./solution.ts";

assert.deepEqual(
  sweepLogGenerations(
    "app.log",
    [
      { name: "app.log", bytes: 1200, days: 2 },
      { name: "app.log.1", bytes: 900, days: 5 },
      { name: "app.log.2", bytes: 800, days: 9 },
      { name: "app.log.3", bytes: 700, days: 20 },
    ],
    { rotateAt: 1000, keep: 3, maxDays: 14 },
  ),
  {
    kept: ["app.log", "app.log.1", "app.log.2", "app.log.3"],
    rotated: [
      ["app.log", "app.log.1"],
      ["app.log.1", "app.log.2"],
      ["app.log.2", "app.log.3"],
      ["app.log.3", "app.log.4"],
    ],
    deleted: ["app.log.4"],
  },
  "a full rotation with the oldest copy pushed past keep",
);

assert.deepEqual(
  sweepLogGenerations(
    "app.log",
    [
      { name: "app.log", bytes: 500, days: 1 },
      { name: "app.log.1", bytes: 900, days: 30 },
      { name: "app.log.2", bytes: 800, days: 3 },
    ],
    { rotateAt: 1000, keep: 5, maxDays: 14 },
  ),
  {
    kept: ["app.log", "app.log.2"],
    rotated: [],
    deleted: ["app.log.1"],
  },
  "too small to rotate, and age leaves a gap behind",
);

assert.deepEqual(
  sweepLogGenerations("j", [{ name: "j", bytes: 5, days: 10 }], {
    rotateAt: 1,
    keep: 2,
    maxDays: 3,
  }),
  { kept: ["j"], rotated: [["j", "j.1"]], deleted: ["j.1"] },
  "a stale live file is rotated and then thrown out at once",
);

assert.deepEqual(
  sweepLogGenerations(
    "x",
    [
      { name: "x", bytes: 100, days: 0 },
      { name: "x.1", bytes: 40, days: 1 },
      { name: "x.2", bytes: 40, days: 9 },
      { name: "x.3", bytes: 40, days: 2 },
    ],
    { rotateAt: 100, keep: 2, maxDays: 5 },
  ),
  {
    kept: ["x", "x.1", "x.2"],
    rotated: [
      ["x", "x.1"],
      ["x.1", "x.2"],
      ["x.2", "x.3"],
      ["x.3", "x.4"],
    ],
    deleted: ["x.3", "x.4"],
  },
  "reaching rotateAt exactly still rotates, and keep sheds two",
);

assert.deepEqual(
  sweepLogGenerations("s", [{ name: "s", bytes: 3, days: 0 }], {
    rotateAt: 10,
    keep: 1,
    maxDays: 1,
  }),
  { kept: ["s"], rotated: [], deleted: [] },
  "a lone live file below the trigger",
);

assert.deepEqual(
  sweepLogGenerations("s", [{ name: "s", bytes: 30, days: 0 }], {
    rotateAt: 10,
    keep: 1,
    maxDays: 1,
  }),
  { kept: ["s", "s.1"], rotated: [["s", "s.1"]], deleted: [] },
  "a lone live file over the trigger gains a copy",
);

const sound = [{ name: "q", bytes: 1, days: 1 }];
const plain = { rotateAt: 10, keep: 2, maxDays: 7 };
assert.throws(() => sweepLogGenerations("", sound, plain), Error, "an empty live name");
assert.throws(() => sweepLogGenerations(5, sound, plain), Error, "a live name that is no string");
assert.throws(() => sweepLogGenerations("q", 5, plain), Error, "files that are not a list");
assert.throws(() => sweepLogGenerations("q", [], plain), Error, "no live file at all");
assert.throws(() => sweepLogGenerations("q", [7], plain), Error, "a file that is not a record");
assert.throws(
  () => sweepLogGenerations("q", [{ name: 3, bytes: 1, days: 1 }], plain),
  Error,
  "a name that is not a string",
);
assert.throws(
  () =>
    sweepLogGenerations(
      "q",
      [
        { name: "q", bytes: 1, days: 1 },
        { name: "other", bytes: 1, days: 1 },
      ],
      plain,
    ),
  Error,
  "a stray name",
);
assert.throws(
  () =>
    sweepLogGenerations(
      "q",
      [
        { name: "q", bytes: 1, days: 1 },
        { name: "q.0", bytes: 1, days: 1 },
      ],
      plain,
    ),
  Error,
  "a copy numbered nothing",
);
assert.throws(
  () =>
    sweepLogGenerations(
      "q",
      [
        { name: "q", bytes: 1, days: 1 },
        { name: "q.01", bytes: 1, days: 1 },
      ],
      plain,
    ),
  Error,
  "a copy number with a leading zero",
);
assert.throws(
  () =>
    sweepLogGenerations(
      "q",
      [
        { name: "q", bytes: 1, days: 1 },
        { name: "q.2", bytes: 1, days: 1 },
      ],
      plain,
    ),
  Error,
  "a gap in the copy numbers",
);
assert.throws(
  () =>
    sweepLogGenerations(
      "q",
      [
        { name: "q", bytes: 1, days: 1 },
        { name: "q", bytes: 2, days: 2 },
      ],
      plain,
    ),
  Error,
  "one name twice",
);
assert.throws(
  () => sweepLogGenerations("q", [{ name: "q", bytes: -1, days: 1 }], plain),
  Error,
  "negative bytes",
);
assert.throws(
  () => sweepLogGenerations("q", [{ name: "q", bytes: 1, days: 1.5 }], plain),
  Error,
  "fractional days",
);
assert.throws(() => sweepLogGenerations("q", sound, 4), Error, "rules that are not a record");
assert.throws(
  () => sweepLogGenerations("q", sound, { rotateAt: 0, keep: 2, maxDays: 7 }),
  Error,
  "a trigger of nothing",
);
assert.throws(
  () => sweepLogGenerations("q", sound, { rotateAt: 10, keep: 0, maxDays: 7 }),
  Error,
  "keeping nothing",
);
assert.throws(
  () => sweepLogGenerations("q", sound, { rotateAt: 10, keep: 2, maxDays: 0 }),
  Error,
  "an age limit of nothing",
);
console.log("ok");
