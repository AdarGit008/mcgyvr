import assert from "node:assert/strict";
import { pickImpactedTests } from "./solution.ts";

const table = {
  "api-smoke": ["src/api.ts", "src/util.ts"],
  "cli-args": ["src/cli.ts"],
  "lint-all": ["*"],
  "util-unit": ["src/util.ts"],
};

assert.deepEqual(
  pickImpactedTests(table, ["src/util.ts"]),
  ["api-smoke", "lint-all", "util-unit"],
  "one edited path reaches two touchers and the blanket test",
);
assert.deepEqual(
  pickImpactedTests(table, []),
  [],
  "an empty edit list impacts nothing, blanket test included",
);
assert.deepEqual(
  pickImpactedTests(table, ["docs/readme.md"]),
  ["lint-all"],
  "an untouched path still wakes the blanket test",
);
assert.deepEqual(
  pickImpactedTests(table, ["src/cli.ts", "src/api.ts"]),
  ["api-smoke", "cli-args", "lint-all"],
  "results are ascending, not input order",
);
assert.deepEqual(
  pickImpactedTests(table, ["src/util.ts", "src/util.ts", "src/api.ts"]),
  ["api-smoke", "lint-all", "util-unit"],
  "a repeated edit does not repeat a test",
);
assert.deepEqual(pickImpactedTests({}, ["src/api.ts"]), [], "an empty table picks nothing");

const starred = { blanket: ["*"], mixed: ["*", "src/a.ts"] };
assert.deepEqual(
  pickImpactedTests(starred, ["src/z.ts"]),
  ["blanket"],
  "a two-entry list is not a blanket even when it holds a star",
);
assert.deepEqual(
  pickImpactedTests(starred, ["*"]),
  ["blanket", "mixed"],
  "inside a longer list the star is compared as a path",
);

assert.throws(() => pickImpactedTests({ t: [] }, ["a"]), Error, "empty coverage is rejected");
assert.throws(() => pickImpactedTests({ t: ["a", "a"] }, ["a"]), Error, "a repeated path is rejected");
assert.throws(() => pickImpactedTests({ "": ["a"] }, ["a"]), Error, "an empty test name is rejected");
assert.throws(() => pickImpactedTests({ t: "a" }, ["a"]), Error, "a non-list coverage value is rejected");
assert.throws(() => pickImpactedTests(table, [7]), Error, "a non-string edited path is rejected");
assert.throws(() => pickImpactedTests([["t", ["a"]]], ["a"]), Error, "a list table is rejected");
assert.throws(() => pickImpactedTests(table, "src/api.ts"), Error, "a string edit list is rejected");
console.log("ok");
