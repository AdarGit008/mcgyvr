import assert from "node:assert/strict";
import { replayRecentPanel } from "./solution.ts";

const open = (name) => ["open", name];
const pin = (name) => ["pin", name];
const unpin = (name) => ["unpin", name];
const forget = (name) => ["forget", name];

assert.deepEqual(replayRecentPanel(3, []), [], "no events leaves the panel empty");
assert.deepEqual(
  replayRecentPanel(3, [open("a"), open("b"), open("c")]),
  ["c", "b", "a"],
  "the recent region reads newest first",
);
assert.deepEqual(
  replayRecentPanel(3, [open("a"), open("b"), open("c"), open("d")]),
  ["d", "c", "b"],
  "the oldest name is let go at the limit",
);
assert.deepEqual(
  replayRecentPanel(3, [open("a"), open("b"), open("c"), open("a")]),
  ["a", "c", "b"],
  "opening a held name lifts it to the head",
);
assert.deepEqual(
  replayRecentPanel(3, [open("a"), open("b"), pin("a")]),
  ["a", "b"],
  "a pinned name leads the panel",
);
assert.deepEqual(
  replayRecentPanel(2, [open("a"), open("b"), pin("a"), open("c"), open("d")]),
  ["a", "d", "c"],
  "pinned names are held outside the limit",
);
assert.deepEqual(
  replayRecentPanel(3, [pin("a"), open("b"), open("a"), open("c")]),
  ["a", "c", "b"],
  "opening a pinned name stirs nothing",
);
assert.deepEqual(replayRecentPanel(2, [pin("z")]), ["z"], "a name never seen may be pinned");
assert.deepEqual(
  replayRecentPanel(2, [pin("a"), pin("b"), pin("c")]),
  ["a", "b", "c"],
  "the pinned region reads in pin order",
);
assert.deepEqual(
  replayRecentPanel(2, [open("x"), open("y"), pin("x"), unpin("x")]),
  ["x", "y"],
  "an unpinned name returns at the head of the recent region",
);
assert.deepEqual(
  replayRecentPanel(1, [open("p"), open("q"), pin("p"), unpin("p")]),
  ["p"],
  "an unpin trims the recent region the way an open does",
);
assert.deepEqual(
  replayRecentPanel(3, [open("a"), open("b"), forget("a")]),
  ["b"],
  "forgetting drops a held name",
);
assert.deepEqual(replayRecentPanel(3, [pin("a"), forget("a")]), ["a"], "a pinned name cannot be forgotten");
assert.deepEqual(replayRecentPanel(3, [open("a"), forget("z")]), ["a"], "forgetting an unknown name stirs nothing");
assert.deepEqual(replayRecentPanel(3, [open("a"), unpin("a")]), ["a"], "unpinning a name that is not pinned stirs nothing");
assert.deepEqual(
  replayRecentPanel(3, [pin("a"), pin("b"), unpin("a"), pin("a")]),
  ["b", "a"],
  "a repinned name joins the tail of the pinned region",
);
assert.deepEqual(
  replayRecentPanel(2, [open("a"), pin("a"), pin("a"), open("b"), open("c"), open("d"), forget("c")]),
  ["a", "d"],
  "a long replay over pins, drops and a forget",
);

assert.throws(() => replayRecentPanel(0, []), Error, "a limit under 1 is refused");
assert.throws(() => replayRecentPanel(1.5, []), Error, "a fractional limit is refused");
assert.throws(() => replayRecentPanel("3", []), Error, "a limit that is not a number is refused");
assert.throws(() => replayRecentPanel(3, [["open"]]), Error, "an event that is not a pair is refused");
assert.throws(() => replayRecentPanel(3, [["close", "a"]]), Error, "an unknown verb is refused");
assert.throws(() => replayRecentPanel(3, [["open", ""]]), Error, "an empty name is refused");
assert.throws(() => replayRecentPanel(3, [["open", 7]]), Error, "a name that is not a string is refused");
console.log("ok");
