import assert from "node:assert/strict";
import { parseInvocation } from "./solution.ts";

const CAT = [
  { name: "verbose", kind: "toggle", alias: "v" },
  { name: "out", kind: "single", alias: "o" },
  { name: "tag", kind: "repeat" },
];

assert.deepEqual(
  parseInvocation(CAT, []),
  { options: { verbose: false, out: null, tag: [] }, operands: [] },
  "defaults when nothing is mentioned",
);
assert.deepEqual(
  parseInvocation(CAT, ["-v", "build", "--out=dist"]),
  { options: { verbose: true, out: "dist", tag: [] }, operands: ["build"] },
  "alias toggle, operand, inline single",
);
assert.deepEqual(
  parseInvocation(CAT, ["--tag", "a", "--tag=b", "c"]),
  { options: { verbose: false, out: null, tag: ["a", "b"] }, operands: ["c"] },
  "repeat collects both forms in order",
);
assert.deepEqual(
  parseInvocation(CAT, ["-o", "-v", "x"]),
  { options: { verbose: false, out: "-v", tag: [] }, operands: ["x"] },
  "the next token is consumed as the value no matter what",
);
assert.deepEqual(
  parseInvocation(CAT, ["--", "--out", "late"]),
  { options: { verbose: false, out: null, tag: [] }, operands: ["--out", "late"] },
  "everything after bare -- is an operand",
);
assert.deepEqual(
  parseInvocation(CAT, ["-v", "--verbose"]),
  { options: { verbose: true, out: null, tag: [] }, operands: [] },
  "a toggle mentioned twice stays true",
);
assert.deepEqual(
  parseInvocation(CAT, ["--out="]),
  { options: { verbose: false, out: "", tag: [] }, operands: [] },
  "inline empty value is a value",
);
assert.deepEqual(
  parseInvocation(CAT, ["-", "-xy"]),
  { options: { verbose: false, out: null, tag: [] }, operands: ["-", "-xy"] },
  "lone dash and multi-letter clusters are operands",
);
assert.throws(() => parseInvocation(CAT, ["--depth", "2"]), Error, "unknown long name");
assert.throws(() => parseInvocation(CAT, ["-z"]), Error, "unknown alias");
assert.throws(() => parseInvocation(CAT, ["--verbose=yes"]), Error, "inline on toggle");
assert.throws(
  () => parseInvocation(CAT, ["--out", "a", "-o", "b"]),
  Error,
  "single mentioned twice",
);
assert.throws(() => parseInvocation(CAT, ["--out"]), Error, "missing value at the end");
console.log("ok");
