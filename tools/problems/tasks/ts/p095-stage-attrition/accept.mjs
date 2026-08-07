import assert from "node:assert/strict";
import { stageAttrition } from "./solution.ts";

const stages = [
  { stage: "mass-floor", field: "mass", low: 10, high: null },
  { stage: "span-band", field: "span", low: 5, high: 9 },
  { stage: "purity-cap", field: "purity", low: null, high: 80 },
];
assert.deepEqual(
  stageAttrition(
    [
      { mass: 12, span: 7, purity: 50 },
      { mass: 5, span: 1, purity: 99 },
      { mass: 20, span: 4, purity: 99 },
      { mass: 15, span: 9, purity: 81 },
      { mass: 15, purity: 10 },
    ],
    stages,
  ),
  [["mass-floor", 1], ["span-band", 2], ["purity-cap", 1], ["through", 1]],
  "each specimen counts once, at its first failing stage",
);
assert.deepEqual(
  stageAttrition([{ mass: 10, span: 5, purity: 80 }], stages),
  [["mass-floor", 0], ["span-band", 0], ["purity-cap", 0], ["through", 1]],
  "bounds are inclusive at both ends",
);
assert.deepEqual(
  stageAttrition([], stages),
  [["mass-floor", 0], ["span-band", 0], ["purity-cap", 0], ["through", 0]],
  "an empty line counts nothing",
);
assert.deepEqual(
  stageAttrition([{ mass: 1 }, { mass: 2 }], []),
  [["through", 2]],
  "no stages, everything is through",
);
assert.deepEqual(
  stageAttrition([{ mass: "heavy" }], [{ stage: "mass-floor", field: "mass", low: null, high: null }]),
  [["mass-floor", 1], ["through", 0]],
  "a non-number field fails its stage",
);
assert.throws(
  () => stageAttrition([], [{ stage: "", field: "a", low: null, high: null }]),
  Error,
  "empty stage name is rejected",
);
assert.throws(
  () =>
    stageAttrition([], [
      { stage: "x", field: "a", low: null, high: null },
      { stage: "x", field: "b", low: null, high: null },
    ]),
  Error,
  "repeated stage name is rejected",
);
assert.throws(
  () => stageAttrition([], [{ stage: "through", field: "a", low: null, high: null }]),
  Error,
  "a stage named through is rejected",
);
assert.throws(
  () => stageAttrition([], [{ stage: "x", field: "a", low: 9, high: 2 }]),
  Error,
  "reversed bounds are rejected",
);
console.log("ok");
