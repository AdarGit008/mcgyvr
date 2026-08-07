import assert from "node:assert/strict";
import { walkSkipForm } from "./solution.ts";

const form = [
  { code: "q1", options: ["yes", "no"], jumps: [{ on: "no", to: "close" }] },
  { code: "q2", options: ["car", "bus", "walk"], jumps: [{ on: "walk", to: "q4" }] },
  { code: "q3", options: ["a", "b"], jumps: [] },
  { code: "q4", options: ["ok", "bad"], jumps: [{ on: "bad", to: "close" }] },
  { code: "q5", options: ["1", "2"], jumps: [] },
];

assert.deepEqual(
  walkSkipForm(form, { q1: "yes", q2: "walk", q4: "ok", q5: "2" }),
  { asked: ["q1", "q2", "q4", "q5"], blank: [], wrong: [], stray: [], ending: "spent" },
  "a jump forward skips the step it steps over",
);
assert.deepEqual(
  walkSkipForm(form, { q1: "no", q3: "a" }),
  { asked: ["q1"], blank: [], wrong: [], stray: ["q3"], ending: "close" },
  "closing at once leaves an answer to an unreached step stray",
);
assert.deepEqual(
  walkSkipForm(form, { q1: "maybe", q2: "bus", q3: "b", q4: "bad" }),
  { asked: ["q1", "q2", "q3", "q4"], blank: [], wrong: ["q1"], stray: [], ending: "close" },
  "an answer off the option list falls through rather than jumping",
);
assert.deepEqual(
  walkSkipForm(form, { q2: "car" }),
  {
    asked: ["q1", "q2", "q3", "q4", "q5"],
    blank: ["q1", "q3", "q4", "q5"],
    wrong: [],
    stray: [],
    ending: "spent",
  },
  "an unheard step falls through to the next step",
);
assert.deepEqual(
  walkSkipForm(form, {}),
  {
    asked: ["q1", "q2", "q3", "q4", "q5"],
    blank: ["q1", "q2", "q3", "q4", "q5"],
    wrong: [],
    stray: [],
    ending: "spent",
  },
  "an empty answer set still walks the whole form",
);
assert.deepEqual(
  walkSkipForm(form, { q1: "yes", q2: "walk", q3: "a", q4: "bad", q5: "1" }),
  { asked: ["q1", "q2", "q4"], blank: [], wrong: [], stray: ["q3", "q5"], ending: "close" },
  "stray codes come out in the order the form declares them",
);
assert.deepEqual(
  walkSkipForm([{ code: "only", options: ["go"], jumps: [] }], { only: "go" }),
  { asked: ["only"], blank: [], wrong: [], stray: [], ending: "spent" },
  "a one-step form runs off the end",
);

assert.throws(() => walkSkipForm([], {}), Error, "an empty form is refused");
assert.throws(() => walkSkipForm(["q1"], {}), Error, "a step must be a mapping");
assert.throws(
  () => walkSkipForm([{ code: "a", options: ["x"], jumps: [] }, { code: "a", options: ["y"], jumps: [] }], {}),
  Error,
  "two steps may not share a code",
);
assert.throws(
  () => walkSkipForm([{ code: "a", options: [], jumps: [] }], {}),
  Error,
  "a step needs at least one option",
);
assert.throws(
  () => walkSkipForm([{ code: "a", options: ["x"], jumps: [{ on: "z", to: "close" }] }], {}),
  Error,
  "a jump may not fire on a foreign option",
);
assert.throws(
  () => walkSkipForm([{ code: "a", options: ["x"], jumps: [{ on: "x", to: "a" }] }], {}),
  Error,
  "a jump may not point at its own step",
);
assert.throws(
  () =>
    walkSkipForm(
      [
        { code: "a", options: ["x"], jumps: [{ on: "x", to: "close" }, { on: "x", to: "b" }] },
        { code: "b", options: ["y"], jumps: [] },
      ],
      {},
    ),
  Error,
  "two jumps of one step may not fire on the same option",
);
assert.throws(
  () => walkSkipForm(form, { nowhere: "yes" }),
  Error,
  "an answer to a step the form never declares is refused",
);
assert.throws(() => walkSkipForm(form, { q1: 3 }), Error, "an answer must be a string");
console.log("ok");
