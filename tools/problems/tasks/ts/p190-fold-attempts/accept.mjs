import assert from "node:assert/strict";
import { foldAttempts } from "./solution.ts";

assert.deepEqual(foldAttempts([]), [], "no records, no cases");
assert.deepEqual(foldAttempts(["alpha 1 pass"]), ["alpha=pass"], "one try that passed");
assert.deepEqual(foldAttempts(["alpha 1 fail"]), ["alpha=fail"], "one try that failed");
assert.deepEqual(
  foldAttempts(["alpha 1 fail", "alpha 2 pass"]),
  ["alpha=flake"],
  "failed then passed is a flake",
);
assert.deepEqual(
  foldAttempts(["alpha 2 pass", "alpha 1 fail"]),
  ["alpha=flake"],
  "records may arrive out of order",
);
assert.deepEqual(
  foldAttempts(["alpha 1 fail", "alpha 2 fail", "alpha 3 fail"]),
  ["alpha=fail"],
  "three failures settle to fail",
);
assert.deepEqual(
  foldAttempts(["alpha 1 pass", "alpha 2 fail", "alpha 3 pass"]),
  ["alpha=flake"],
  "one failure among passes is a flake",
);
assert.deepEqual(
  foldAttempts(["beta 1 pass", "alpha 1 fail"]),
  ["alpha=fail", "beta=pass"],
  "cases come out ordered by name",
);
assert.deepEqual(
  foldAttempts(["beta 1 fail", "alpha 1 pass", "beta 2 pass", "alpha 2 pass"]),
  ["alpha=pass", "beta=flake"],
  "two cases interleaved",
);

assert.throws(() => foldAttempts(["alpha 1"]), Error, "two pieces are rejected");
assert.throws(
  () => foldAttempts(["alpha 1 pass extra"]),
  Error,
  "four pieces are rejected",
);
assert.throws(() => foldAttempts(["alpha 1 skip"]), Error, "a third word is rejected");
assert.throws(() => foldAttempts(["alpha 0 pass"]), Error, "try zero is rejected");
assert.throws(() => foldAttempts(["alpha 01 pass"]), Error, "a padded try is rejected");
assert.throws(() => foldAttempts(["alpha x pass"]), Error, "a lettered try is rejected");
assert.throws(() => foldAttempts([" 1 pass"]), Error, "an empty name is rejected");
assert.throws(
  () => foldAttempts(["alpha 1 pass", "alpha 3 pass"]),
  Error,
  "a skipped try number is rejected",
);
assert.throws(
  () => foldAttempts(["alpha 1 pass", "alpha 1 fail"]),
  Error,
  "a repeated try number is rejected",
);
assert.throws(() => foldAttempts("alpha 1 pass"), Error, "a bare string is rejected");
assert.throws(() => foldAttempts([12]), Error, "a non-string record is rejected");
console.log("ok");
