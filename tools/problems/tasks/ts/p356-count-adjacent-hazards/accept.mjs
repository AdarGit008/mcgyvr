import assert from "node:assert/strict";
import { countAdjacentHazards } from "./solution.ts";

assert.deepEqual(
  countAdjacentHazards(["#..", "...", "..#"]),
  { chart: ["#10", "121", "01#"], hazards: 2, clear: 7 },
  "the stated three-row field",
);
assert.deepEqual(
  countAdjacentHazards(["...", "..."]),
  { chart: ["000", "000"], hazards: 0, clear: 6 },
  "a field with nothing in it",
);
assert.deepEqual(
  countAdjacentHazards(["##", "##"]),
  { chart: ["##", "##"], hazards: 4, clear: 0 },
  "a field of nothing but hazards",
);
assert.deepEqual(
  countAdjacentHazards(["#"]),
  { chart: ["#"], hazards: 1, clear: 0 },
  "one square holding a hazard",
);
assert.deepEqual(
  countAdjacentHazards(["."]),
  { chart: ["0"], hazards: 0, clear: 1 },
  "one square holding nothing",
);
assert.deepEqual(
  countAdjacentHazards(["#.#.#"]),
  { chart: ["#2#2#"], hazards: 3, clear: 2 },
  "a single row counts on both hands",
);
assert.deepEqual(
  countAdjacentHazards([".#.", "#.#", ".#."]),
  { chart: ["2#2", "#4#", "2#2"], hazards: 4, clear: 5 },
  "the middle square touches four hazards",
);
assert.throws(
  () => countAdjacentHazards("#.."),
  Error,
  "a field that is not a list is thrown out",
);
assert.throws(
  () => countAdjacentHazards([]),
  Error,
  "a field with no rows is thrown out",
);
assert.throws(
  () => countAdjacentHazards([["#", "."]]),
  Error,
  "a row that is not a string is thrown out",
);
assert.throws(
  () => countAdjacentHazards(["#.", ""]),
  Error,
  "an empty row is thrown out",
);
assert.throws(
  () => countAdjacentHazards(["#..", ".."]),
  Error,
  "rows of unequal length are thrown out",
);
assert.throws(
  () => countAdjacentHazards(["#.x"]),
  Error,
  "a symbol outside hash and dot is thrown out",
);
console.log("ok");
