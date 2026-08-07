import assert from "node:assert/strict";
import { examSlotClasses } from "./solution.ts";

assert.deepEqual(
  examSlotClasses([[1, 2, 3], [0], [0], [0]]),
  [[0], [1, 2, 3]],
  "one busy exam and three quiet ones",
);
assert.deepEqual(
  examSlotClasses([[1], [0, 2], [1, 3], [2]]),
  [
    [1, 3],
    [0, 2],
  ],
  "a chain of four",
);
assert.deepEqual(
  examSlotClasses([
    [1, 2],
    [0, 2],
    [0, 1],
  ]),
  [[0], [1], [2]],
  "three exams all sharing",
);
assert.deepEqual(examSlotClasses([[], [], []]), [[0, 1, 2]], "nothing shared");
assert.deepEqual(examSlotClasses([[]]), [[0]], "a single exam");
assert.deepEqual(
  examSlotClasses([
    [1, 4],
    [0, 2],
    [1, 3],
    [2, 4],
    [0, 3],
  ]),
  [[0, 2], [1, 3], [4]],
  "an odd ring opens a third sitting",
);
assert.deepEqual(
  examSlotClasses([[1, 2, 3], [0, 2], [0, 1], [0]]),
  [[0], [1, 3], [2]],
  "busiest first",
);
assert.deepEqual(
  examSlotClasses([[1], [0], [3], [2]]),
  [
    [0, 2],
    [1, 3],
  ],
  "two independent pairs",
);

assert.throws(() => examSlotClasses([]), Error, "no exams rejected");
assert.throws(() => examSlotClasses("e"), Error, "non-list rejected");
assert.throws(() => examSlotClasses([[0]]), Error, "self sharing rejected");
assert.throws(
  () => examSlotClasses([[1, 1], [0]]),
  Error,
  "the same exam named twice rejected",
);
assert.throws(() => examSlotClasses([[1], []]), Error, "one-sided pair rejected");
assert.throws(
  () => examSlotClasses([[1], [0], [9]]),
  Error,
  "an exam that does not exist rejected",
);
console.log("ok");
