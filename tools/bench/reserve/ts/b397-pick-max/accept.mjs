import assert from "node:assert/strict";
import { pickMax } from "./solution.ts";

assert.deepEqual(pickMax([{ a: 1 }, { a: 3 }], "a"), { a: 3 }, "the highest wins");
assert.deepEqual(
  pickMax([{ a: 3, id: 1 }, { a: 3, id: 2 }], "a"),
  { a: 3, id: 1 },
  "a tie goes to the earlier record",
);
assert.deepEqual(pickMax([], "a"), {}, "no records at all");
assert.deepEqual(pickMax([{ b: 1 }], "a"), {}, "no record carries the field");
assert.deepEqual(pickMax([{ a: 5 }], "a"), { a: 5 }, "one record wins by default");
assert.deepEqual(pickMax([{ a: 1 }, { a: 2 }, { a: 0 }], "a"), { a: 2 }, "the middle one");
console.log("ok");
