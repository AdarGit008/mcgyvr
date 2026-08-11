import assert from "node:assert/strict";
import { paceOf, paceList } from "./solution.ts";

assert.equal(paceOf(600, 2), 300, "ten minutes over two kilometres");
assert.equal(paceOf(601, 2), 300, "the remainder is discarded");
assert.deepEqual(
  paceList([{ seconds: 600, kilometres: 2 }, { seconds: 300, kilometres: 1 }]),
  [300, 300],
  "a pace for each leg",
);
assert.deepEqual(paceList([]), [], "a run with no legs");
assert.throws(() => paceOf(600, 0), Error, "no ground covered is rejected");
assert.throws(
  () => paceList([{ seconds: 600, kilometres: 0 }]),
  Error,
  "and the rejection carries up",
);
console.log("ok");
