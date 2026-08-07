import assert from "node:assert/strict";
import { tallyReplyRemoves } from "./solution.ts";

assert.deepEqual(tallyReplyRemoves([["a", ""]]), [1], "one note starts and ends it");
assert.deepEqual(
  tallyReplyRemoves([
    ["a", ""],
    ["b", "a"],
    ["c", "a"],
  ]),
  [1, 2],
  "two notes answer the same note",
);
assert.deepEqual(
  tallyReplyRemoves([
    ["a", ""],
    ["b", "a"],
    ["c", "b"],
    ["d", ""],
  ]),
  [2, 1, 1],
  "two discussions, one of them two removes deep",
);
assert.deepEqual(
  tallyReplyRemoves([
    ["a", ""],
    ["b", "a"],
    ["c", "b"],
    ["d", "c"],
  ]),
  [1, 1, 1, 1],
  "a single file four removes long",
);
assert.deepEqual(
  tallyReplyRemoves([
    ["a", ""],
    ["b", ""],
    ["c", ""],
  ]),
  [3],
  "nobody answers anybody",
);
assert.deepEqual(
  tallyReplyRemoves([
    ["b", "a"],
    ["a", ""],
  ]),
  [1, 1],
  "the answer is listed before what it answers",
);
assert.deepEqual(
  tallyReplyRemoves([
    ["r", ""],
    ["x", "r"],
    ["y", "r"],
    ["z", "r"],
    ["q", "x"],
  ]),
  [1, 3, 1],
  "a wide remove and a narrow one below it",
);
assert.throws(() => tallyReplyRemoves([]), Error, "an empty batch is rejected");
assert.throws(
  () => tallyReplyRemoves("a"),
  Error,
  "a batch that is not a list is rejected",
);
assert.throws(
  () => tallyReplyRemoves([["a"]]),
  Error,
  "a link of one value is rejected",
);
assert.throws(() => tallyReplyRemoves([["", ""]]), Error, "an empty id is rejected");
assert.throws(
  () =>
    tallyReplyRemoves([
      ["a", ""],
      ["a", "a"],
    ]),
  Error,
  "an id used twice is rejected",
);
assert.throws(
  () => tallyReplyRemoves([["a", "z"]]),
  Error,
  "answering a note nobody sent is rejected",
);
assert.throws(
  () =>
    tallyReplyRemoves([
      ["a", "b"],
      ["b", "a"],
    ]),
  Error,
  "answering in a circle is rejected",
);
assert.throws(
  () =>
    tallyReplyRemoves([
      ["a", ""],
      ["b", "b"],
    ]),
  Error,
  "a note answering itself is rejected",
);
console.log("ok");
