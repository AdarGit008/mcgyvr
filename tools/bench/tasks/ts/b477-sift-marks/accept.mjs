import assert from "node:assert/strict";
import { siftMarks } from "./solution.ts";

assert.deepEqual(siftMarks(["ax", "b", "ay"], "a"), [["ax", "ay"], ["b"]], "both runs keep their order");
assert.deepEqual(siftMarks(["b", "c"], "a"), [[], ["b", "c"]], "nothing carries the mark");
assert.deepEqual(siftMarks(["ab", "ac"], "a"), [["ab", "ac"], []], "everything carries the mark");
assert.deepEqual(siftMarks(["ba", "ab"], "ab"), [["ab"], ["ba"]], "a mark of more than one character");
assert.deepEqual(siftMarks(["a"], "a"), [["a"], []], "an entry that is the mark itself");
assert.deepEqual(siftMarks(["a", "abc"], "ab"), [["abc"], ["a"]], "an entry shorter than the mark");
assert.deepEqual(siftMarks([], "a"), [[], []], "no entries at all");
console.log("ok");
