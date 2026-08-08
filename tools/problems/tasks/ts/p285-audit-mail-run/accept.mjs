import assert from "node:assert/strict";
import { auditMailRun } from "./solution.ts";

const plan = [
  { bin: "alpha", grades: "PL", offices: ["AB"] },
  { bin: "beta", grades: "P", offices: ["AB", "CD"] },
  { bin: "gamma", grades: "E", offices: ["MN"] },
];

assert.deepEqual(
  auditMailRun([], plan),
  { misrouted: [], tally: [] },
  "an empty night audits to nothing",
);
assert.deepEqual(
  auditMailRun([{ code: "PAB126", stamped: "alpha" }], plan),
  { misrouted: [], tally: [{ bin: "alpha", count: 1 }] },
  "a sound code stamped as planned",
);
assert.deepEqual(
  auditMailRun([{ code: "PCD007", stamped: "beta" }], plan),
  { misrouted: [], tally: [{ bin: "beta", count: 1 }] },
  "the first entry is skipped when its offices do not hold the code's",
);
assert.deepEqual(
  auditMailRun([{ code: "PAB123", stamped: "alpha" }], plan),
  {
    misrouted: [{ code: "PAB123", stamped: "alpha", correct: "QUERY" }],
    tally: [{ bin: "QUERY", count: 1 }],
  },
  "an unsound check digit outranks the plan",
);
assert.deepEqual(
  auditMailRun([{ code: "LZZ406", stamped: "gamma" }], plan),
  {
    misrouted: [{ code: "LZZ406", stamped: "gamma", correct: "SPARE" }],
    tally: [{ bin: "SPARE", count: 1 }],
  },
  "a sound code no entry claims falls to SPARE",
);
assert.deepEqual(
  auditMailRun(
    [
      { code: "PAB126", stamped: "alpha" },
      { code: "LAB991", stamped: "beta" },
      { code: "PCD007", stamped: "beta" },
      { code: "EMN074", stamped: "gamma" },
      { code: "LZZ406", stamped: "gamma" },
      { code: "PAB123", stamped: "alpha" },
    ],
    plan,
  ),
  {
    misrouted: [
      { code: "LAB991", stamped: "beta", correct: "alpha" },
      { code: "LZZ406", stamped: "gamma", correct: "SPARE" },
      { code: "PAB123", stamped: "alpha", correct: "QUERY" },
    ],
    tally: [
      { bin: "QUERY", count: 1 },
      { bin: "SPARE", count: 1 },
      { bin: "alpha", count: 2 },
      { bin: "beta", count: 1 },
      { bin: "gamma", count: 1 },
    ],
  },
  "a whole night, tallied by true bin with capitals sorting first",
);
assert.deepEqual(
  auditMailRun([{ code: "EMN074", stamped: "gamma" }], [
    { bin: "wide", grades: "PLE", offices: ["MN", "AB"] },
  ]),
  {
    misrouted: [{ code: "EMN074", stamped: "gamma", correct: "wide" }],
    tally: [{ bin: "wide", count: 1 }],
  },
  "one entry may hold every grade",
);

assert.throws(() => auditMailRun([], []), Error, "an empty plan");
assert.throws(
  () =>
    auditMailRun([], [
      { bin: "x", grades: "P", offices: ["AB"] },
      { bin: "x", grades: "L", offices: ["CD"] },
    ]),
  Error,
  "repeated bin",
);
assert.throws(
  () => auditMailRun([], [{ bin: "SPARE", grades: "P", offices: ["AB"] }]),
  Error,
  "a plan bin named for a mark",
);
assert.throws(
  () => auditMailRun([], [{ bin: "x", grades: "PP", offices: ["AB"] }]),
  Error,
  "a repeated grade letter",
);
assert.throws(
  () => auditMailRun([], [{ bin: "x", grades: "PX", offices: ["AB"] }]),
  Error,
  "an unknown grade letter",
);
assert.throws(
  () => auditMailRun([], [{ bin: "x", grades: "P", offices: ["Ab"] }]),
  Error,
  "an office that is not two capitals",
);
assert.throws(
  () => auditMailRun([], [{ bin: "x", grades: "P", offices: ["AB", "AB"] }]),
  Error,
  "a repeated office",
);
assert.throws(
  () => auditMailRun([{ code: "PAB12", stamped: "alpha" }], plan),
  Error,
  "a code of the wrong length",
);
assert.throws(
  () => auditMailRun([{ code: "XAB126", stamped: "alpha" }], plan),
  Error,
  "an unknown grade letter in a code",
);
assert.throws(
  () => auditMailRun([{ code: "PAB126", stamped: "" }], plan),
  Error,
  "an empty stamped bin",
);
console.log("ok");
