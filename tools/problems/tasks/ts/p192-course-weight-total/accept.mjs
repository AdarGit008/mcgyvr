import assert from "node:assert/strict";
import { courseWeightTotal } from "./solution.ts";

const only = (items, weight = 10000) => [{ label: "all", weight, items }];

assert.equal(courseWeightTotal(only([[45, 50]])), 9000, "one category, one item");
assert.equal(
  courseWeightTotal(only([[50, 50], [20, 20]])),
  10000,
  "a flawless syllabus reads 10000"
);
assert.equal(courseWeightTotal(only([[1, 3]])), 3333, "the remainder is dropped");
assert.equal(
  courseWeightTotal(only([[0, 5], [0, 5]])),
  0,
  "nothing earned scores nothing"
);
assert.equal(
  courseWeightTotal(only([[1, 1], [0, 9]])),
  1000,
  "points pool across items rather than averaging item by item"
);

assert.equal(
  courseWeightTotal([
    { label: "quizzes", weight: 6000, items: [[7, 10]] },
    { label: "final", weight: 4000, items: [[1, 3]] },
  ]),
  5533,
  "two categories, each truncated on its own"
);

assert.equal(
  courseWeightTotal([
    { label: "labs", weight: 5000, items: [[3, 4]] },
    { label: "essays", weight: 3000, items: [[2, 7], [5, 7]] },
    { label: "oral", weight: 2000, items: [[9, 10]] },
  ]),
  7050,
  "three categories"
);

assert.equal(
  courseWeightTotal([
    { label: "graded", weight: 10000, items: [[1, 2]] },
    { label: "practice", weight: 0, items: [[0, 1]] },
  ]),
  5000,
  "a zero weight contributes nothing but is still counted in the sum"
);

assert.throws(() => courseWeightTotal([]), Error, "an empty syllabus is rejected");
assert.throws(
  () =>
    courseWeightTotal([
      { label: "same", weight: 5000, items: [[1, 1]] },
      { label: "same", weight: 5000, items: [[1, 1]] },
    ]),
  Error,
  "a repeated label is rejected"
);
assert.throws(
  () => courseWeightTotal(only([[1, 1]], 9000)),
  Error,
  "weights short of 10000 are rejected"
);
assert.throws(
  () =>
    courseWeightTotal([
      { label: "a", weight: 11000, items: [[1, 1]] },
      { label: "b", weight: -1000, items: [[1, 1]] },
    ]),
  Error,
  "a negative weight is rejected"
);
assert.throws(
  () => courseWeightTotal([{ label: "empty", weight: 10000, items: [] }]),
  Error,
  "a category with no items is rejected"
);
assert.throws(
  () => courseWeightTotal(only([[0, 0]])),
  Error,
  "an item worth nothing is rejected"
);
assert.throws(
  () => courseWeightTotal(only([[6, 5]])),
  Error,
  "earning more than the item is worth is rejected"
);
assert.throws(
  () => courseWeightTotal(only([[-1, 5]])),
  Error,
  "negative earned points are rejected"
);

console.log("ok");
