import assert from "node:assert/strict";
import { gradeReruns } from "./solution.ts";

assert.deepEqual(gradeReruns([], 2), [], "an empty log grades nothing");
assert.deepEqual(gradeReruns(["a green"], 2), ["a:solid"], "green first go is solid");
assert.deepEqual(
  gradeReruns(["a red", "a green"], 2),
  ["a:shaky"],
  "red then green is shaky",
);
assert.deepEqual(
  gradeReruns(["a red", "a red", "a green"], 2),
  ["a:shaky"],
  "two reds then green is still shaky",
);
assert.deepEqual(
  gradeReruns(["a red", "a red", "a red"], 2),
  ["a:broken"],
  "all reds using every go is broken",
);
assert.deepEqual(
  gradeReruns(["a red"], 2),
  ["a:dropped"],
  "all reds with goes to spare is dropped",
);
assert.deepEqual(
  gradeReruns(["a red", "a red"], 2),
  ["a:dropped"],
  "one go short of the budget is still dropped",
);
assert.deepEqual(
  gradeReruns(["a red"], 0),
  ["a:broken"],
  "with no reruns allowed one red is broken",
);
assert.deepEqual(
  gradeReruns(["b red", "a green", "b green"], 2),
  ["a:solid", "b:shaky"],
  "jobs interleave and come out ordered by name",
);
assert.deepEqual(
  gradeReruns(["z green", "a red", "a red", "a red"], 2),
  ["a:broken", "z:solid"],
  "name order beats arrival order",
);
assert.deepEqual(
  gradeReruns(["a red", "b red", "a red", "b green"], 1),
  ["a:broken", "b:shaky"],
  "a budget of one",
);

const rejects = (log, budget = 2) => {
  try {
    gradeReruns(log, budget);
  } catch {
    return true;
  }
  return false;
};

assert.ok(rejects(["a green", "a red"]), "a go after a green is rejected");
assert.ok(rejects(["a red", "a red", "a red", "a red"]), "overspending is rejected");
assert.ok(rejects(["a red", "a red"], 0), "overspending a zero budget is rejected");
assert.ok(rejects(["a blue"]), "an unknown mark is rejected");
assert.ok(rejects(["a"]), "one piece is rejected");
assert.ok(rejects(["a red x"]), "three pieces are rejected");
assert.ok(rejects([" red"]), "an empty name is rejected");
assert.ok(rejects(["a red"], -1), "a negative budget is rejected");
assert.ok(rejects(["a red"], "2"), "a non-numeric budget is rejected");
assert.ok(rejects("a red"), "a bare string log is rejected");
assert.ok(rejects([4]), "a non-string entry is rejected");
console.log("ok");
