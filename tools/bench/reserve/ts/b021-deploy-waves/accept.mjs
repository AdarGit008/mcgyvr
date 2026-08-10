import assert from "node:assert/strict";
import { deployWaves } from "./solution.ts";

assert.deepEqual(deployWaves([]), [], "empty input yields no waves");
assert.deepEqual(deployWaves([["api", []]]), [["api"]], "single service");
assert.deepEqual(
  deployWaves([["c", ["b"]], ["b", ["a"]], ["a", []]]),
  [["a"], ["b"], ["c"]],
  "a chain is one service per wave",
);
assert.deepEqual(
  deployWaves([["zeta", []], ["alpha", []], ["mid", []]]),
  [["alpha", "mid", "zeta"]],
  "independent services share a wave, sorted",
);
assert.deepEqual(
  deployWaves([["d", ["b", "c"]], ["b", ["a"]], ["c", ["a"]], ["a", []]]),
  [["a"], ["b", "c"], ["d"]],
  "a diamond fans out and rejoins",
);
assert.deepEqual(
  deployWaves([["a", []], ["b", ["a"]], ["c", ["a", "b"]]]),
  [["a"], ["b"], ["c"]],
  "a service waits for its latest dependency",
);
assert.deepEqual(
  deployWaves([["a", []], ["c", ["a"]], ["d", ["b", "c"]], ["b", ["a"]]]),
  [["a"], ["b", "c"], ["d"]],
  "input order never affects the result",
);
assert.deepEqual(
  deployWaves([
    ["web", ["db", "cache"]],
    ["db", []],
    ["cache", []],
    ["worker", ["db"]],
    ["mail", ["worker", "web"]],
  ]),
  [["cache", "db"], ["web", "worker"], ["mail"]],
  "a wider graph settles into three waves",
);
assert.throws(
  () => deployWaves([["a", []], ["a", []]]),
  Error,
  "duplicate service name is rejected",
);
assert.throws(() => deployWaves([["", []]]), Error, "empty name is rejected");
assert.throws(() => deployWaves([[7, []]]), Error, "non-string name is rejected");
assert.throws(
  () => deployWaves([["a", [7]]]),
  Error,
  "non-string dependency is rejected",
);
assert.throws(
  () => deployWaves([["a", ["ghost"]]]),
  Error,
  "unknown dependency is rejected",
);
assert.throws(
  () => deployWaves([["a", ["a"]]]),
  Error,
  "self-dependency is rejected",
);
assert.throws(
  () => deployWaves([["a", []], ["b", ["a", "a"]]]),
  Error,
  "dependency listed twice is rejected",
);
assert.throws(
  () => deployWaves([["a", ["b"]], ["b", ["a"]]]),
  Error,
  "a two-cycle is rejected",
);
assert.throws(
  () => deployWaves([["a", ["b"]], ["b", ["c"]], ["c", ["a"]]]),
  Error,
  "a three-cycle is rejected",
);
console.log("ok");
