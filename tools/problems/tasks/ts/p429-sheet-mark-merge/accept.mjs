import assert from "node:assert/strict";
import { mergeSheetMarks } from "./solution.ts";

assert.deepEqual(mergeSheetMarks(["3-7"]), { spec: "3-7", sheets: 5 }, "one span, already canonical");
assert.deepEqual(mergeSheetMarks(["1 2 3"]), { spec: "1-3", sheets: 3 }, "lone sheets draw together into a run");
assert.deepEqual(mergeSheetMarks([]), { spec: "", sheets: 0 }, "no readers hold nothing");
assert.deepEqual(mergeSheetMarks(["!5"]), { spec: "", sheets: 0 }, "striking what was never gathered holds nothing");
assert.deepEqual(mergeSheetMarks(["1-9 !1-9"]), { spec: "", sheets: 0 }, "a strike may empty the holding");
assert.deepEqual(
  mergeSheetMarks(["1-5 !3"]),
  { spec: "1-2 4-5", sheets: 4 },
  "a strike through the middle leaves two runs",
);
assert.deepEqual(
  mergeSheetMarks(["1-5", "!2-4"]),
  { spec: "1 5", sheets: 2 },
  "a later reader strikes what an earlier one gathered",
);
assert.deepEqual(
  mergeSheetMarks(["1-3 5-7", "4"]),
  { spec: "1-7", sheets: 7 },
  "a gather between two runs welds them into one",
);
assert.deepEqual(
  mergeSheetMarks(["10-12 !11 11"]),
  { spec: "10-12", sheets: 3 },
  "a gather may put back what a strike took away",
);
assert.deepEqual(mergeSheetMarks(["9999", "1"]), { spec: "1 9999", sheets: 2 }, "the ends of the run of sheets");
assert.deepEqual(mergeSheetMarks(["5", "5"]), { spec: "5", sheets: 1 }, "gathering one sheet twice holds it once");
assert.deepEqual(
  mergeSheetMarks(["2-4 6", "!3 8-9", "!9"]),
  { spec: "2 4 6 8", sheets: 4 },
  "three readers over one holding",
);
assert.deepEqual(mergeSheetMarks(["4-4"]), { spec: "4", sheets: 1 }, "a span of one renders as a lone figure");

assert.throws(() => mergeSheetMarks("1-2"), Error, "an argument that is not a list is refused");
assert.throws(() => mergeSheetMarks([5]), Error, "a mark that is not a string is refused");
assert.throws(() => mergeSheetMarks([""]), Error, "an empty mark is refused");
assert.throws(() => mergeSheetMarks([" 1"]), Error, "a leading blank is refused");
assert.throws(() => mergeSheetMarks(["1 "]), Error, "a trailing blank is refused");
assert.throws(() => mergeSheetMarks(["1  2"]), Error, "two blanks running together are refused");
assert.throws(() => mergeSheetMarks(["1--2"]), Error, "a doubled hyphen is refused");
assert.throws(() => mergeSheetMarks(["!"]), Error, "a bare exclamation mark is refused");
assert.throws(() => mergeSheetMarks(["!!1"]), Error, "a doubled exclamation mark is refused");
assert.throws(() => mergeSheetMarks(["1!2"]), Error, "an exclamation mark inside a segment is refused");
assert.throws(() => mergeSheetMarks(["01"]), Error, "a leading nought is refused");
assert.throws(() => mergeSheetMarks(["0"]), Error, "a sheet of nought is refused");
assert.throws(() => mergeSheetMarks(["10000"]), Error, "a sheet past the last is refused");
assert.throws(() => mergeSheetMarks(["7-3"]), Error, "a backwards span is refused");
assert.throws(() => mergeSheetMarks(["!7-3"]), Error, "a backwards strike is refused");
console.log("ok");
