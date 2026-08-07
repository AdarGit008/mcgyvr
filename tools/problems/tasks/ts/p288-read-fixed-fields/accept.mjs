import assert from "node:assert/strict";
import { readFixedFields } from "./solution.ts";

const layout = [
  { name: "code", start: 1, width: 4 },
  { name: "town", start: 5, width: 8 },
  { name: "note", start: 13, width: 6 },
];

assert.deepEqual(
  readFixedFields(["AB12Harwell early "], layout),
  [{ code: "AB12", town: "Harwell", note: "early" }],
  "three values packed out with spaces",
);
assert.deepEqual(
  readFixedFields([" X9 Ely     "], layout),
  [{ code: " X9", town: "Ely", note: "" }],
  "a leading space survives, a short line supplies spaces",
);
assert.deepEqual(
  readFixedFields([""], layout),
  [{ code: "", town: "", note: "" }],
  "an empty line yields empty values throughout",
);
assert.deepEqual(
  readFixedFields(["    Harwell       "], layout),
  [{ code: "", town: "Harwell", note: "" }],
  "a run of nothing but spaces is the empty value",
);
assert.deepEqual(
  readFixedFields(
    ["AB12Harwell early ", " X9 Ely     ", "ZZ99Rye     late  "],
    layout,
  ),
  [
    { code: "AB12", town: "Harwell", note: "early" },
    { code: " X9", town: "Ely", note: "" },
    { code: "ZZ99", town: "Rye", note: "late" },
  ],
  "one record per line, in line order",
);
assert.deepEqual(readFixedFields([], layout), [], "no lines, no records");
assert.deepEqual(
  readFixedFields(["one  two"], [{ name: "tail", start: 6, width: 3 }]),
  [{ tail: "two" }],
  "a layout may begin part way along the line",
);
assert.deepEqual(
  readFixedFields(["  a  "], [{ name: "only", start: 1, width: 5 }]),
  [{ only: "  a" }],
  "spaces inside and before a value are kept",
);

assert.throws(() => readFixedFields(["x"], []), Error, "an empty layout");
assert.throws(
  () =>
    readFixedFields(["x"], [
      { name: "a", start: 1, width: 2 },
      { name: "a", start: 3, width: 2 },
    ]),
  Error,
  "repeated field name",
);
assert.throws(
  () =>
    readFixedFields(["x"], [
      { name: "a", start: 1, width: 4 },
      { name: "b", start: 3, width: 2 },
    ]),
  Error,
  "two fields over one column",
);
assert.throws(
  () => readFixedFields(["x"], [{ name: "a", start: 0, width: 2 }]),
  Error,
  "a start left of the first column",
);
assert.throws(
  () => readFixedFields(["x"], [{ name: "a", start: 1, width: 0 }]),
  Error,
  "a width of no columns",
);
assert.throws(
  () => readFixedFields(["a\tb"], layout),
  Error,
  "a tab on the grid",
);
assert.throws(() => readFixedFields([5], layout), Error, "a line that is not a string");
assert.throws(() => readFixedFields("AB12", layout), Error, "lines is not a list");
console.log("ok");
