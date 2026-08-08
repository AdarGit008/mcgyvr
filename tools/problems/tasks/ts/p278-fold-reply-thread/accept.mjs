import assert from "node:assert/strict";
import { foldReplyThread } from "./solution.ts";

assert.equal(
  foldReplyThread([["a", "", "hello"]]),
  "a hello",
  "a lone opening message",
);
assert.equal(
  foldReplyThread([
    ["a", "", "top"],
    ["b", "a", "re"],
    ["c", "", "other"],
  ]),
  "a top\n> b re\nc other",
  "one answer, then a second conversation",
);
assert.equal(
  foldReplyThread([
    ["a", "", "one"],
    ["b", "a", "two"],
    ["c", "b", "three"],
    ["d", "a", "four"],
  ]),
  "a one\n> b two\n> > c three\n> d four",
  "an answer to an answer, then back out",
);
assert.equal(
  foldReplyThread([
    ["b", "a", "child"],
    ["a", "", "root"],
  ]),
  "a root\n> b child",
  "an answer handed over before what it answers",
);
assert.equal(
  foldReplyThread([
    ["a", "", "r1"],
    ["x", "", "r2"],
    ["b", "a", "c1"],
    ["y", "x", "c2"],
    ["c", "a", "c3"],
  ]),
  "a r1\n> b c1\n> c c3\nx r2\n> y c2",
  "two conversations interleaved in the batch",
);
assert.equal(
  foldReplyThread([
    ["a", "", "1"],
    ["b", "a", "2"],
    ["c", "b", "3"],
    ["d", "c", "4"],
  ]),
  "a 1\n> b 2\n> > c 3\n> > > d 4",
  "a chain four deep",
);
assert.equal(
  foldReplyThread([
    ["a", "", "same"],
    ["c", "a", "later"],
    ["b", "a", "earlier"],
  ]),
  "a same\n> c later\n> b earlier",
  "answers keep the batch's own order, not the id's",
);
assert.throws(() => foldReplyThread([]), Error, "an empty batch is rejected");
assert.throws(() => foldReplyThread("a"), Error, "a batch that is not a list is rejected");
assert.throws(
  () => foldReplyThread([["a", ""]]),
  Error,
  "a message of two values is rejected",
);
assert.throws(
  () => foldReplyThread([["", "", "x"]]),
  Error,
  "an empty id is rejected",
);
assert.throws(
  () =>
    foldReplyThread([
      ["a", "", "x"],
      ["a", "", "y"],
    ]),
  Error,
  "a repeated id is rejected",
);
assert.throws(
  () => foldReplyThread([["a", "z", "x"]]),
  Error,
  "a parent naming nobody is rejected",
);
assert.throws(
  () => foldReplyThread([["a", "", "two\nlines"]]),
  Error,
  "a text carrying a newline is rejected",
);
assert.throws(
  () =>
    foldReplyThread([
      ["a", "b", "x"],
      ["b", "a", "y"],
    ]),
  Error,
  "parent links in a circle are rejected",
);
assert.throws(
  () =>
    foldReplyThread([
      ["a", "", "x"],
      ["b", "b", "y"],
    ]),
  Error,
  "a message answering itself is rejected",
);
console.log("ok");
