import assert from "node:assert/strict";
import { computeSheet } from "./solution.ts";

assert.deepEqual(
  computeSheet({ A1: "4", B2: "-7" }),
  { A1: 4, B2: -7 },
  "literal cells evaluate to their integers",
);
assert.deepEqual(
  computeSheet({ A1: "2", B1: "=A1 + 3", C1: "=B1+B1" }),
  { A1: 2, B1: 5, C1: 10 },
  "chained references resolve through intermediates",
);
assert.deepEqual(computeSheet({}), {}, "empty sheet yields empty mapping");
assert.deepEqual(
  computeSheet({ Z9: "=5+-2" }),
  { Z9: 3 },
  "a formula may hold only literals, including negatives",
);
assert.deepEqual(
  computeSheet({ A1: "=B1+C1", B1: "=C1+1", C1: "10" }),
  { A1: 21, B1: 11, C1: 10 },
  "key order must not matter to resolution",
);
assert.deepEqual(
  computeSheet({ AB12: "3", C1: "=AB12+AB12+AB12" }),
  { AB12: 3, C1: 9 },
  "multi-letter columns and repeated terms",
);
assert.throws(() => computeSheet({ A1: "=B1" }), Error, "unknown reference");
assert.throws(() => computeSheet({ A1: "=A1" }), Error, "self reference");
assert.throws(
  () => computeSheet({ A1: "=B1", B1: "=A1" }),
  Error,
  "two-cell cycle",
);
assert.throws(() => computeSheet({ A1: "=1*2" }), Error, "unsupported operator");
assert.throws(() => computeSheet({ A1: "hello" }), Error, "malformed literal");
assert.throws(() => computeSheet({ A1: "=" }), Error, "empty formula");
console.log("ok");
