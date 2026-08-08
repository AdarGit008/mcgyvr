import assert from "node:assert/strict";
import { reassembleStream } from "./solution.ts";

assert.equal(
  reassembleStream(5, [
    [0, "he"],
    [2, "llo"],
  ]),
  "hello",
  "contiguous fragments in order",
);
assert.equal(
  reassembleStream(5, [
    [2, "llo"],
    [0, "he"],
  ]),
  "hello",
  "arrival order must not matter",
);
assert.equal(
  reassembleStream(5, [
    [0, "abc"],
    [2, "cde"],
  ]),
  "abcde",
  "agreeing overlap merges into one message",
);
assert.equal(
  reassembleStream(2, [
    [0, "hi"],
    [0, "hi"],
  ]),
  "hi",
  "an exact duplicate fragment is harmless",
);
assert.equal(
  reassembleStream(4, [
    [0, "abcd"],
    [1, "bc"],
  ]),
  "abcd",
  "a fragment wholly inside another is harmless",
);
assert.equal(reassembleStream(0, []), "", "an empty message needs no fragments");
assert.equal(
  reassembleStream(2, [
    [1, ""],
    [0, "ab"],
  ]),
  "ab",
  "zero-length fragments contribute nothing",
);
assert.throws(
  () =>
    reassembleStream(3, [
      [0, "ab"],
      [1, "xz"],
    ]),
  Error,
  "a disagreeing overlap is rejected",
);
assert.throws(
  () =>
    reassembleStream(3, [
      [0, "a"],
      [2, "c"],
    ]),
  Error,
  "an uncovered position is rejected",
);
assert.throws(
  () => reassembleStream(3, [[1, "abc"]]),
  Error,
  "a fragment running past the end is rejected",
);
assert.throws(
  () => reassembleStream(2, [[-1, "ab"]]),
  Error,
  "a negative offset is rejected",
);
console.log("ok");
