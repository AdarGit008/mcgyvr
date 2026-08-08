import assert from "node:assert/strict";
import { codeOpenAnswers } from "./solution.ts";

const RULES = [
  { code: "PRICE", phrase: "too dear" },
  { code: "PRICE", phrase: "costs a lot" },
  { code: "WAIT", phrase: "queue" },
  { code: "STAFF", phrase: "rude staff" },
];

assert.deepEqual(
  codeOpenAnswers([{ code: "A", phrase: "bus" }], ["The bus was late"]),
  { tally: [{ code: "A", count: 1 }], loose: [] },
  "one rule taking one answer",
);

assert.deepEqual(
  codeOpenAnswers(RULES, ["Far too dear!", "Costs a lot, honestly"]),
  {
    tally: [
      { code: "PRICE", count: 2 },
      { code: "WAIT", count: 0 },
      { code: "STAFF", count: 0 },
    ],
    loose: [],
  },
  "two phrases feeding one code, and the untouched codes still listed",
);

assert.deepEqual(
  codeOpenAnswers(RULES, ["Nothing at all to report"]),
  {
    tally: [
      { code: "PRICE", count: 0 },
      { code: "WAIT", count: 0 },
      { code: "STAFF", count: 0 },
    ],
    loose: ["nothing at all to report"],
  },
  "an answer nothing takes is reported tidied",
);

assert.deepEqual(
  codeOpenAnswers(
    [
      { code: "FIRST", phrase: "long queue" },
      { code: "SECOND", phrase: "queue" },
    ],
    ["a long queue outside"],
  ),
  {
    tally: [
      { code: "FIRST", count: 1 },
      { code: "SECOND", count: 0 },
    ],
    loose: [],
  },
  "the earlier rule wins when both would take the answer",
);

assert.deepEqual(
  codeOpenAnswers([{ code: "Q", phrase: "queue" }], ["QUEUEING for ages"]),
  { tally: [{ code: "Q", count: 0 }], loose: ["queueing for ages"] },
  "a phrase matches whole words, never a word's opening",
);

assert.deepEqual(
  codeOpenAnswers([{ code: "Q", phrase: "rude staff" }], ["  rude,,,STAFF  "]),
  { tally: [{ code: "Q", count: 1 }], loose: [] },
  "punctuation between the words collapses to the one space",
);

assert.deepEqual(
  codeOpenAnswers([{ code: "Q", phrase: "bus" }], ["!!!", "bus"]),
  { tally: [{ code: "Q", count: 1 }], loose: [""] },
  "an answer that tidies away to nothing is loose and empty",
);

assert.deepEqual(
  codeOpenAnswers([{ code: "Q", phrase: "bus" }], []),
  { tally: [{ code: "Q", count: 0 }], loose: [] },
  "no answers leaves every count at zero",
);

assert.deepEqual(
  codeOpenAnswers([{ code: "N9", phrase: "route 9" }], ["Route 9 again"]),
  { tally: [{ code: "N9", count: 1 }], loose: [] },
  "digits count as ordinary phrase characters",
);

assert.deepEqual(
  codeOpenAnswers([{ code: "R", phrase: "no lift" }], ["lift no good", "no lift"]),
  { tally: [{ code: "R", count: 1 }], loose: ["lift no good"] },
  "the phrase words must run consecutively and in order",
);

assert.throws(() => codeOpenAnswers([], ["x"]), Error, "an empty rule list is rejected");
assert.throws(() => codeOpenAnswers("rules", ["x"]), Error, "rules that are not a list are rejected");
assert.throws(() => codeOpenAnswers([["A", "bus"]], ["x"]), Error, "a rule that is not a mapping is rejected");
assert.throws(() => codeOpenAnswers([{ code: "", phrase: "bus" }], ["x"]), Error, "an empty code is rejected");
assert.throws(() => codeOpenAnswers([{ code: "A", phrase: "Bus" }], ["x"]), Error, "an uppercase phrase is rejected");
assert.throws(() => codeOpenAnswers([{ code: "A", phrase: "a  b" }], ["x"]), Error, "a doubled space in a phrase is rejected");
assert.throws(() => codeOpenAnswers([{ code: "A", phrase: "" }], ["x"]), Error, "an empty phrase is rejected");
assert.throws(
  () => codeOpenAnswers([{ code: "A", phrase: "bus" }, { code: "B", phrase: "bus" }], ["x"]),
  Error,
  "two rules sharing a phrase are rejected",
);
assert.throws(() => codeOpenAnswers([{ code: "A", phrase: "bus" }], "x"), Error, "answers that are not a list are rejected");
assert.throws(() => codeOpenAnswers([{ code: "A", phrase: "bus" }], [7]), Error, "an answer that is not a string is rejected");
console.log("ok");
