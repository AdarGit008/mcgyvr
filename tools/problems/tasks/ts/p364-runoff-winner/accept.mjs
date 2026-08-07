import assert from "node:assert/strict";
import { runoffWinner } from "./solution.ts";

assert.equal(
  runoffWinner([["a"], ["a"], ["b"]]),
  "a",
  "a first-round majority ends it at once",
);
assert.equal(
  runoffWinner([["solo"], ["solo"]]),
  "solo",
  "a lone option wins unopposed",
);
assert.equal(
  runoffWinner([
    ["x", "z"],
    ["x", "z"],
    ["y", "z"],
    ["y", "z"],
    ["z", "x"],
  ]),
  "x",
  "the dropped option's ballot moves to its next standing choice",
);
assert.equal(
  runoffWinner([
    ["p", "r"],
    ["q", "r"],
    ["r", "p"],
  ]),
  "p",
  "a three-way bottom tie drops the greatest name",
);
assert.equal(
  runoffWinner([["a"], ["b"], ["c", "a"], ["c", "a"]]),
  "c",
  "a spent ballot shrinks the count the majority is measured against",
);
assert.equal(
  runoffWinner([["a"], ["b"], ["c"]]),
  "a",
  "rounds keep going while every ballot spends itself",
);
assert.equal(
  runoffWinner([
    ["a", "b"],
    ["c", "b"],
    ["d", "b"],
    ["a", "b"],
  ]),
  "a",
  "an option nobody put first is at the bottom with zero",
);
assert.equal(
  runoffWinner([
    ["a"],
    ["a"],
    ["a"],
    ["a"],
    ["a"],
    ["b", "c"],
    ["b", "c"],
    ["b", "c"],
    ["c", "b"],
    ["c", "b"],
    ["c", "b"],
    ["c", "b"],
  ]),
  "c",
  "the option ahead after the first round can still lose",
);

assert.throws(() => runoffWinner([]), Error, "no ballots at all is rejected");
assert.throws(() => runoffWinner([[]]), Error, "an empty ballot is rejected");
assert.throws(
  () => runoffWinner([["a", "a"]]),
  Error,
  "an option named twice on one ballot is rejected",
);
assert.throws(
  () => runoffWinner([["a", ""]]),
  Error,
  "an empty option name is rejected",
);
assert.throws(
  () => runoffWinner([["a"], "b"]),
  Error,
  "a ballot that is not a list is rejected",
);
assert.throws(
  () => runoffWinner("nope"),
  Error,
  "an argument that is not a list is rejected",
);
console.log("ok");
