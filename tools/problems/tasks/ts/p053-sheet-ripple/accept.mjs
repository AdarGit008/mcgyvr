import assert from "node:assert/strict";
import { changedCells } from "./solution.ts";

assert.deepEqual(
  changedCells({ A1: "1", B1: "=A1", C1: "=B1" }, "A1", "2"),
  ["A1", "B1", "C1"],
  "a change must ripple through intermediate formulas",
);
assert.deepEqual(
  changedCells(
    { A1: "1", B1: "=A1", C1: "=A1", D1: "=B1+C1" },
    "A1",
    "3",
  ),
  ["A1", "B1", "C1", "D1"],
  "diamond dependencies report each cell once",
);
assert.deepEqual(
  changedCells({ A1: "1", B1: "=A1" }, "A1", "1"),
  [],
  "an identical rewrite changes nothing",
);
assert.deepEqual(
  changedCells({ A1: "1", B1: "=A1" }, "A1", "+1"),
  [],
  "an equivalent respelling of the same integer changes nothing",
);
assert.deepEqual(
  changedCells({ A1: "1", B1: "2", C1: "=B1" }, "A1", "9"),
  ["A1"],
  "cells not depending on the edit stay out of the report",
);
assert.deepEqual(
  changedCells({ A1: "2", B1: "=A1", C1: "=B1+A1" }, "B1", "7"),
  ["B1", "C1"],
  "editing a formula cell to a literal reports its dependents",
);
assert.deepEqual(
  changedCells({ A1: "1", B1: "5", C1: "=B1" }, "B1", "=A1"),
  ["B1", "C1"],
  "the replacement text may itself be a formula",
);
assert.throws(
  () => changedCells({ A1: "1" }, "Q9", "2"),
  Error,
  "editing an absent cell is rejected",
);
console.log("ok");
