import assert from "node:assert/strict";
import { recodeAnswerSheet } from "./solution.ts";

const STEPS = [
  { label: "GOOD", wanted: ["good", "great", "lovely"], barred: ["not "], least: 2 },
  { label: "SLOW", wanted: ["slow", "late", "wait"], barred: [], least: 1 },
];

const SOUND = {
  steps: [{ label: "A", wanted: ["ok"], barred: [], least: 1 }],
  entries: [{ id: "e1", text: "ok" }],
};

function bent(patch) {
  return { ...SOUND, ...patch };
}

assert.deepEqual(
  recodeAnswerSheet({
    steps: STEPS,
    entries: [
      { id: "e1", text: "Good and great service" },
      { id: "e2", text: "good but not great" },
      { id: "e3", text: "very slow" },
      { id: "e4", text: "Good only" },
      { id: "e5", text: "  LATE\n\n  again  " },
    ],
  }),
  {
    coded: [
      { id: "e1", label: "GOOD" },
      { id: "e3", label: "SLOW" },
      { id: "e5", label: "SLOW" },
    ],
    loose: ["e2", "e4"],
    unused: [],
  },
  "the whole sheet, thresholds and bars and folding together",
);

assert.deepEqual(
  recodeAnswerSheet({
    steps: [{ label: "GOOD", wanted: ["good", "great"], barred: [], least: 2 }],
    entries: [{ id: "a", text: "good" }, { id: "b", text: "good and great" }],
  }),
  {
    coded: [{ id: "b", label: "GOOD" }],
    loose: ["a"],
    unused: [],
  },
  "one fragment short of least is not enough",
);

assert.deepEqual(
  recodeAnswerSheet({
    steps: [
      { label: "X", wanted: ["cost"], barred: ["free"], least: 1 },
      { label: "Y", wanted: ["cost"], barred: [], least: 1 },
    ],
    entries: [{ id: "a", text: "cost free" }],
  }),
  { coded: [{ id: "a", label: "Y" }], loose: [], unused: ["X"] },
  "a barred fragment sends the entry on to the next step",
);

assert.deepEqual(
  recodeAnswerSheet({
    steps: [{ label: "BUS", wanted: ["slow bus"], barred: [], least: 1 }],
    entries: [{ id: "a", text: "the slow\n   bus" }],
  }),
  { coded: [{ id: "a", label: "BUS" }], loose: [], unused: [] },
  "whitespace inside the text squeezes down before the fragment is sought",
);

assert.deepEqual(
  recodeAnswerSheet({
    steps: [
      { label: "FIRST", wanted: ["rain"], barred: [], least: 1 },
      { label: "SECOND", wanted: ["rain"], barred: [], least: 1 },
    ],
    entries: [{ id: "a", text: "rain" }],
  }),
  { coded: [{ id: "a", label: "FIRST" }], loose: [], unused: ["SECOND"] },
  "the earlier step takes it when both would",
);

assert.deepEqual(
  recodeAnswerSheet({ steps: STEPS, entries: [] }),
  { coded: [], loose: [], unused: ["GOOD", "SLOW"] },
  "no entries leaves every step unused",
);

assert.deepEqual(
  recodeAnswerSheet({
    steps: [{ label: "A", wanted: ["x"], barred: [], least: 1 }],
    entries: [{ id: "a", text: "   " }, { id: "b", text: "" }],
  }),
  { coded: [], loose: ["a", "b"], unused: ["A"] },
  "text that folds away to nothing is loose",
);

assert.deepEqual(
  recodeAnswerSheet({
    steps: [{ label: "A", wanted: ["late"], barred: ["not late"], least: 1 }],
    entries: [{ id: "a", text: "NOT   LATE" }],
  }),
  { coded: [], loose: ["a"], unused: ["A"] },
  "a bar is sought in the folded text just as a wanted fragment is",
);

assert.throws(() => recodeAnswerSheet(["steps"]), Error, "a sheet that is not a mapping is rejected");
assert.throws(() => recodeAnswerSheet(bent({ steps: [] })), Error, "an empty step list is rejected");
assert.throws(() => recodeAnswerSheet(bent({ steps: "A" })), Error, "steps that are not a list are rejected");
assert.throws(() => recodeAnswerSheet(bent({ entries: "e" })), Error, "entries that are not a list are rejected");
assert.throws(
  () => recodeAnswerSheet(bent({ steps: [{ label: "", wanted: ["ok"], barred: [], least: 1 }] })),
  Error,
  "an empty label is rejected",
);
assert.throws(
  () =>
    recodeAnswerSheet(
      bent({
        steps: [
          { label: "A", wanted: ["ok"], barred: [], least: 1 },
          { label: "A", wanted: ["no"], barred: [], least: 1 },
        ],
      }),
    ),
  Error,
  "two steps sharing a label are rejected",
);
assert.throws(
  () => recodeAnswerSheet(bent({ steps: [{ label: "A", wanted: [], barred: [], least: 1 }] })),
  Error,
  "a step wanting nothing is rejected",
);
assert.throws(
  () => recodeAnswerSheet(bent({ steps: [{ label: "A", wanted: ["Ok"], barred: [], least: 1 }] })),
  Error,
  "a fragment carrying a capital is rejected",
);
assert.throws(
  () => recodeAnswerSheet(bent({ steps: [{ label: "A", wanted: ["ok", "ok"], barred: [], least: 1 }] })),
  Error,
  "a repeated fragment is rejected",
);
assert.throws(
  () => recodeAnswerSheet(bent({ steps: [{ label: "A", wanted: ["ok"], barred: "no", least: 1 }] })),
  Error,
  "barred that is not a list is rejected",
);
assert.throws(
  () => recodeAnswerSheet(bent({ steps: [{ label: "A", wanted: ["ok"], barred: [], least: 2 }] })),
  Error,
  "least beyond the wanted list is rejected",
);
assert.throws(
  () => recodeAnswerSheet(bent({ steps: [{ label: "A", wanted: ["ok"], barred: [], least: 0 }] })),
  Error,
  "least below one is rejected",
);
assert.throws(
  () => recodeAnswerSheet(bent({ entries: [{ id: "", text: "ok" }] })),
  Error,
  "an empty id is rejected",
);
assert.throws(
  () => recodeAnswerSheet(bent({ entries: [{ id: "a", text: "ok" }, { id: "a", text: "ok" }] })),
  Error,
  "two entries sharing an id are rejected",
);
assert.throws(
  () => recodeAnswerSheet(bent({ entries: [{ id: "a", text: 5 }] })),
  Error,
  "text that is not a string is rejected",
);
console.log("ok");
