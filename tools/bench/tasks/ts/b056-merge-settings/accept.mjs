import assert from "node:assert/strict";
import { mergeSettings } from "./solution.ts";

assert.deepEqual(
  mergeSettings({ theme: "dark" }, { theme: "dark" }, { theme: "dark" }),
  { theme: "dark" },
  "identical sides come back unchanged",
);
assert.deepEqual(
  mergeSettings({ lang: "en" }, { lang: "fr" }, { lang: "en" }),
  { lang: "fr" },
  "our lone edit wins",
);
assert.deepEqual(
  mergeSettings({ tab: "4" }, { tab: "2" }, { tab: "2" }),
  { tab: "2" },
  "the same edit on both sides is kept once",
);
assert.deepEqual(
  mergeSettings({ a: "1", b: "2" }, { a: "1", b: "2", c: "3" }, { b: "2" }),
  { b: "2", c: "3" },
  "an addition by us and a deletion by them merge cleanly",
);
assert.deepEqual(mergeSettings({}, {}, {}), {}, "empty sides merge to empty");
assert.throws(
  () => mergeSettings({ x: "1" }, { x: "2" }, { x: "3" }),
  Error,
  "two different edits conflict",
);
assert.throws(
  () => mergeSettings({ x: "1" }, { x: "2" }, {}),
  Error,
  "an edit against a deletion conflicts",
);
assert.throws(() => mergeSettings([], {}, {}), Error, "an array side is rejected");
assert.throws(
  () => mergeSettings({}, { n: 7 }, {}),
  Error,
  "a non-string value is rejected",
);
console.log("ok");
