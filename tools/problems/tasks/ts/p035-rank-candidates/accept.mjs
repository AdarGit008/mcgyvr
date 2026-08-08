import assert from "node:assert/strict";
import { rankCandidates } from "./solution.ts";

const pool = ["Prelude", "preload", "PRE", "espresso", "spread", "grep"];
assert.deepEqual(
  rankCandidates(pool, "pre", 10),
  ["PRE", "Prelude", "preload", "spread", "espresso"],
  "exact, then prefixes in original order, then infixes by length",
);
assert.deepEqual(
  rankCandidates(pool, "pre", 3),
  ["PRE", "Prelude", "preload"],
  "limit truncates the ranking",
);
assert.deepEqual(
  rankCandidates(pool, "PrE", 10),
  ["PRE", "Prelude", "preload", "spread", "espresso"],
  "query case never matters",
);
assert.deepEqual(
  rankCandidates(["alpha", "beta"], "zzz", 5),
  [],
  "no candidate contains the query",
);
assert.deepEqual(
  rankCandidates(["log", "dialog", "logger", "blog"], "log", 10),
  ["log", "logger", "blog", "dialog"],
  "shorter infix beats longer infix",
);
assert.deepEqual(
  rankCandidates(["ab", "xab", "AB"], "ab", 10),
  ["ab", "AB", "xab"],
  "equal-length exact matches keep list order and infix follows",
);
assert.throws(() => rankCandidates(pool, "", 3), Error, "empty query is rejected");
assert.throws(() => rankCandidates(pool, 7, 3), Error, "non-string query is rejected");
assert.throws(() => rankCandidates(pool, "pre", 0), Error, "zero limit is rejected");
assert.throws(() => rankCandidates(["ok", 5], "o", 3), Error, "non-string candidate is rejected");
console.log("ok");
