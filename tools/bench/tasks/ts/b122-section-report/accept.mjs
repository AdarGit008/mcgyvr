import assert from "node:assert/strict";
import { sectionReport } from "./solution.ts";

const woven = [["fruit", "apple", 3], ["dairy", "milk", 2], ["fruit", "pear", 4]];
assert.deepEqual(
  sectionReport(woven),
  {
    lines: [
      ["item", "fruit", "apple", 3],
      ["item", "fruit", "pear", 4],
      ["section", "fruit", "", 7],
      ["item", "dairy", "milk", 2],
      ["section", "dairy", "", 2],
      ["grand", "", "", 9],
    ],
    sections: [["fruit", 2, 7], ["dairy", 1, 2]],
    grand: 9,
  },
  "an interrupted section regroups under its first appearance",
);
assert.deepEqual(
  sectionReport([["ads", "spot", 5], ["web", "banner", 2]]),
  {
    lines: [
      ["item", "ads", "spot", 5],
      ["section", "ads", "", 5],
      ["item", "web", "banner", 2],
      ["section", "web", "", 2],
      ["grand", "", "", 7],
    ],
    sections: [["ads", 1, 5], ["web", 1, 2]],
    grand: 7,
  },
  "each section carries its own subtotal",
);
assert.deepEqual(
  sectionReport([["ops", "toner", -4]]),
  {
    lines: [
      ["item", "ops", "toner", -4],
      ["section", "ops", "", -4],
      ["grand", "", "", -4],
    ],
    sections: [["ops", 1, -4]],
    grand: -4,
  },
  "a lone negative row flows through",
);
assert.deepEqual(
  sectionReport([]),
  { lines: [["grand", "", "", 0]], sections: [], grand: 0 },
  "no rows still yields the grand line",
);
const tied = [["beta", "x", 4], ["alpha", "y", 4]];
assert.deepEqual(
  sectionReport(tied).lines,
  [
    ["item", "beta", "x", 4],
    ["section", "beta", "", 4],
    ["item", "alpha", "y", 4],
    ["section", "alpha", "", 4],
    ["grand", "", "", 8],
  ],
  "lines keep first-appearance order",
);
assert.deepEqual(
  sectionReport(tied).sections,
  [["alpha", 1, 4], ["beta", 1, 4]],
  "tied subtotals rank by name",
);
assert.deepEqual(
  sectionReport([["s1", "a", 1], ["s2", "b", 9], ["s3", "c", 5]]).sections,
  [["s2", 1, 9], ["s3", 1, 5], ["s1", 1, 1]],
  "summary ranks by subtotal descending",
);
assert.deepEqual(
  sectionReport([["kit", "bolt", 0], ["kit", "bolt", 2]]),
  {
    lines: [
      ["item", "kit", "bolt", 0],
      ["item", "kit", "bolt", 2],
      ["section", "kit", "", 2],
      ["grand", "", "", 2],
    ],
    sections: [["kit", 2, 2]],
    grand: 2,
  },
  "repeated labels and a zero amount are fine",
);
assert.deepEqual(
  sectionReport([["a", "x", 1], ["b", "y", 1], ["a", "z", 1], ["b", "w", 1]]),
  {
    lines: [
      ["item", "a", "x", 1],
      ["item", "a", "z", 1],
      ["section", "a", "", 2],
      ["item", "b", "y", 1],
      ["item", "b", "w", 1],
      ["section", "b", "", 2],
      ["grand", "", "", 4],
    ],
    sections: [["a", 2, 2], ["b", 2, 2]],
    grand: 4,
  },
  "two sections woven twice regroup cleanly",
);
assert.throws(() => sectionReport("rows"), Error, "non-list rows");
assert.throws(() => sectionReport([["a", "b"]]), Error, "two-item row");
assert.throws(() => sectionReport([["a", "b", 1, 2]]), Error, "four-item row");
assert.throws(() => sectionReport([["", "b", 1]]), Error, "empty section name");
assert.throws(() => sectionReport([[7, "b", 1]]), Error, "non-string section");
assert.throws(() => sectionReport([["a", 42, 1]]), Error, "non-string label");
assert.throws(() => sectionReport([["a", "b", "9"]]), Error, "string amount");
console.log("ok");
