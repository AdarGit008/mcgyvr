import assert from "node:assert/strict";
import { decodeBitRun } from "./solution.ts";

const book = { ash: "0", birch: "10", cedar: "110", dogwood: "111" };

assert.deepEqual(decodeBitRun(book, ""), [], "an empty strip puts nothing down");
assert.deepEqual(decodeBitRun(book, "0"), ["ash"], "one short mark");
assert.deepEqual(decodeBitRun(book, "010"), ["ash", "birch"], "a short mark then a longer one");
assert.deepEqual(decodeBitRun(book, "110111"), ["cedar", "dogwood"], "two long marks");
assert.deepEqual(
  decodeBitRun(book, "0011010"),
  ["ash", "ash", "cedar", "birch"],
  "a strip that uses every width",
);
assert.deepEqual(
  decodeBitRun({ solo: "1" }, "111"),
  ["solo", "solo", "solo"],
  "a single-word codebook repeats",
);
assert.throws(() => decodeBitRun(42, "0"), Error, "a non-mapping codebook is rejected");
assert.throws(() => decodeBitRun([], "0"), Error, "a list codebook is rejected");
assert.throws(() => decodeBitRun({}, "0"), Error, "a codebook naming no words is rejected");
assert.throws(() => decodeBitRun({ Ash: "0" }, "0"), Error, "a capital in a key is rejected");
assert.throws(() => decodeBitRun({ ash: "" }, "0"), Error, "an empty mark is rejected");
assert.throws(() => decodeBitRun({ ash: "02" }, "0"), Error, "a mark holding 2 is rejected");
assert.throws(
  () => decodeBitRun({ ash: "0", birch: "0" }, "0"),
  Error,
  "two words on one mark are rejected",
);
assert.throws(
  () => decodeBitRun({ ash: "0", birch: "01" }, "0"),
  Error,
  "a mark opening another mark is rejected",
);
assert.throws(() => decodeBitRun(book, 101), Error, "a non-string strip is rejected");
assert.throws(() => decodeBitRun(book, "02"), Error, "a strip holding 2 is rejected");
assert.throws(() => decodeBitRun(book, "011"), Error, "a strip with a ragged tail is rejected");
console.log("ok");
