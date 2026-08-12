import assert from "node:assert/strict";
import { slugTitles } from "./solution.ts";

assert.deepEqual(slugTitles([]), [], "no titles yields no slugs");
assert.deepEqual(slugTitles(["Bridge Repairs Begin"]), ["bridge-repairs-begin"], "spaces become single hyphens");
assert.deepEqual(slugTitles(["  ...Ferry Times, Revised!  "]), ["ferry-times-revised"], "runs of punctuation collapse and the ends stay clean");
assert.deepEqual(slugTitles(["Pier 9 Reopens"]), ["pier-9-reopens"], "digits survive the fold");
assert.deepEqual(slugTitles(["Tide Table", "Tide table", "TIDE  TABLE"]), ["tide-table", "tide-table-2", "tide-table-3"], "later claimants take their ordinal");
assert.throws(() => slugTitles(["fine", 7]), Error, "a title that is not a string is rejected");
assert.throws(() => slugTitles(["!!!"]), Error, "a title with no letter or digit is rejected");
console.log("ok");
