import assert from "node:assert/strict";
import { fifoCacheTrace } from "./solution.ts";

assert.deepEqual(
  fifoCacheTrace(2, ["a", "b", "a", "c", "a"]),
  ["miss", "miss", "hit", "miss", "miss"],
  "a hit must not save `a` from FIFO eviction",
);
assert.deepEqual(
  fifoCacheTrace(2, ["a", "b", "c", "b", "d", "c"]),
  ["miss", "miss", "miss", "hit", "miss", "hit"],
  "insertion order alone picks the victims",
);
assert.deepEqual(
  fifoCacheTrace(1, ["a", "a", "b", "a"]),
  ["miss", "hit", "miss", "miss"],
  "capacity one keeps only the newest insertion",
);
assert.deepEqual(
  fifoCacheTrace(3, ["a", "b", "c", "a", "b", "c"]),
  ["miss", "miss", "miss", "hit", "hit", "hit"],
  "no eviction below capacity",
);
assert.deepEqual(fifoCacheTrace(2, []), [], "empty log gives an empty trace");
assert.throws(() => fifoCacheTrace(0, ["a"]), Error, "zero capacity is rejected");
assert.throws(() => fifoCacheTrace(2.5, ["a"]), Error, "fractional capacity is rejected");
console.log("ok");
