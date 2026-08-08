import assert from "node:assert/strict";
import { holdShelfReplay } from "./solution.ts";

assert.deepEqual(
  holdShelfReplay([
    "join ana",
    "join bob",
    "join ana",
    "serve",
    "serve",
    "serve",
    "leave bob",
    "join cal",
    "leave bob",
    "join bob",
    "serve",
  ]),
  [
    "at:1",
    "at:2",
    "no:again",
    "take:ana",
    "take:bob",
    "idle",
    "no:absent",
    "at:1",
    "no:absent",
    "at:2",
    "take:cal",
  ],
  "join, duplicate join, serving down to empty, rejoining",
);
assert.deepEqual(
  holdShelfReplay([
    "join a",
    "join b",
    "join c",
    "leave b",
    "join d",
    "serve",
    "serve",
  ]),
  ["at:1", "at:2", "at:3", "out", "at:3", "take:a", "take:c"],
  "leaving from the middle closes the gap",
);
assert.deepEqual(holdShelfReplay([]), [], "no slips, no answers");
assert.deepEqual(holdShelfReplay(["serve"]), ["idle"], "serving an empty queue");
assert.throws(() => holdShelfReplay(["dance ana"]), Error, "unknown verb throws");
assert.throws(() => holdShelfReplay(["join "]), Error, "empty name throws");
assert.throws(() => holdShelfReplay(["leave"]), Error, "nameless leave throws");
assert.throws(
  () => holdShelfReplay(["serve now"]),
  Error,
  "serve with a payload throws",
);
assert.throws(() => holdShelfReplay([42]), Error, "non-string slip throws");
console.log("ok");
