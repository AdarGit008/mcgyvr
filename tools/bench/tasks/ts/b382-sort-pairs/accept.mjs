import assert from "node:assert/strict";
import { fieldOf, sortPairs } from "./solution.ts";

assert.equal(fieldOf({ age: 3 }, "age"), 3, "the field is read");
assert.deepEqual(
  sortPairs([{ age: 3 }, { age: 1 }], "age"),
  [{ age: 1 }, { age: 3 }],
  "ordered by the field",
);
assert.deepEqual(sortPairs([], "age"), [], "no records at all");
assert.deepEqual(sortPairs([{ age: 2 }], "age"), [{ age: 2 }], "a single record");
assert.deepEqual(
  sortPairs([{ age: 1, id: 1 }, { age: 1, id: 2 }], "age"),
  [{ age: 1, id: 1 }, { age: 1, id: 2 }],
  "a tie keeps the earlier record earlier",
);
assert.throws(() => fieldOf({ age: 3 }, "name"), Error, "a missing field is rejected");
console.log("ok");
