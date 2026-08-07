import assert from "node:assert/strict";
import { rollupTotals } from "./solution.ts";

assert.deepEqual(
  rollupTotals({
    r: { value: 1, parent: "" },
    a: { value: 2, parent: "r" },
    b: { value: 4, parent: "a" },
  }),
  { r: 7, a: 6, b: 4 },
  "a grandchild counts into the root",
);
assert.deepEqual(
  rollupTotals({
    r: { value: 1, parent: "" },
    a: { value: 2, parent: "r" },
    b: { value: 3, parent: "r" },
    c: { value: 5, parent: "a" },
  }),
  { r: 11, a: 7, b: 3, c: 5 },
  "branches roll up separately",
);
assert.deepEqual(
  rollupTotals({ solo: { value: 9, parent: "" } }),
  { solo: 9 },
  "a lone root keeps its own value",
);
assert.deepEqual(
  rollupTotals({
    r: { value: 1, parent: "" },
    a: { value: 1, parent: "r" },
    b: { value: 1, parent: "a" },
    c: { value: 1, parent: "b" },
  }),
  { r: 4, a: 3, b: 2, c: 1 },
  "four levels accumulate",
);
assert.throws(
  () => rollupTotals({ r: { value: 1, parent: "ghost" } }),
  Error,
  "unknown parent rejected",
);
assert.throws(
  () =>
    rollupTotals({
      r: { value: 1, parent: "" },
      s: { value: 1, parent: "" },
    }),
  Error,
  "two roots rejected",
);
assert.throws(
  () =>
    rollupTotals({
      a: { value: 1, parent: "b" },
      b: { value: 1, parent: "a" },
    }),
  Error,
  "no root rejected",
);
assert.throws(
  () =>
    rollupTotals({
      r: { value: 1, parent: "" },
      a: { value: 1, parent: "b" },
      b: { value: 1, parent: "a" },
    }),
  Error,
  "nodes off the root rejected",
);
console.log("ok");
