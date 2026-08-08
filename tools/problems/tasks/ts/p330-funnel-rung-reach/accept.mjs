import assert from "node:assert/strict";
import { funnelRungReach } from "./solution.ts";

const ladder = ["view", "cart", "pay"];
const marks = [
  ["u1", "view", 10],
  ["u1", "cart", 20],
  ["u1", "pay", 30],
  ["u2", "view", 10],
  ["u2", "pay", 20],
  ["u3", "cart", 5],
  ["u3", "view", 10],
  ["u3", "cart", 20],
  ["u4", "view", 10],
  ["u4", "cart", 10],
  ["u5", "browse", 1],
];

assert.deepEqual(
  funnelRungReach(marks, ladder, 100),
  [
    ["view", 4],
    ["cart", 2],
    ["pay", 1],
  ],
  "a cart before the view does not count and an equal at does not either",
);
assert.deepEqual(
  funnelRungReach(marks, ladder, 15),
  [
    ["view", 4],
    ["cart", 2],
    ["pay", 0],
  ],
  "the window cuts the last rung off",
);
assert.deepEqual(
  funnelRungReach(marks, ladder, 0),
  [
    ["view", 4],
    ["cart", 0],
    ["pay", 0],
  ],
  "a window of nothing leaves only the first rung reachable",
);
assert.deepEqual(
  funnelRungReach([], ladder, 100),
  [
    ["view", 0],
    ["cart", 0],
    ["pay", 0],
  ],
  "no marks credit nobody",
);
assert.deepEqual(
  funnelRungReach(marks, ["view"], 0),
  [["view", 4]],
  "a ladder of one rung counts everyone who was seen",
);
assert.deepEqual(
  funnelRungReach(
    [
      ["u5", "a", 0],
      ["u5", "b", 100],
      ["u5", "a", 99],
    ],
    ["a", "b"],
    5,
  ),
  [
    ["a", 1],
    ["b", 1],
  ],
  "a later start rescues an actor whose first attempt ran out of window",
);
assert.deepEqual(
  funnelRungReach(
    [
      ["u5", "a", 0],
      ["u5", "b", 100],
    ],
    ["a", "b"],
    5,
  ),
  [
    ["a", 1],
    ["b", 0],
  ],
  "with no later start the window bites",
);
assert.deepEqual(
  funnelRungReach([["u6", "elsewhere", 4]], ["a", "b"], 100),
  [
    ["a", 0],
    ["b", 0],
  ],
  "a mark outside the ladder is ignored outright",
);

assert.throws(
  () => funnelRungReach(marks, [], 10),
  Error,
  "an empty ladder is rejected",
);
assert.throws(
  () => funnelRungReach(marks, ["view", "view"], 10),
  Error,
  "a ladder naming one step twice is rejected",
);
assert.throws(
  () => funnelRungReach(marks, ["view", ""], 10),
  Error,
  "an empty ladder step is rejected",
);
assert.throws(
  () => funnelRungReach("marks", ladder, 10),
  Error,
  "marks that are not a list are rejected",
);
assert.throws(
  () => funnelRungReach([["u1", "view"]], ladder, 10),
  Error,
  "a mark of two items is rejected",
);
assert.throws(
  () => funnelRungReach([["u1", "view", 1.5]], ladder, 10),
  Error,
  "a fractional at is rejected",
);
assert.throws(
  () => funnelRungReach([["", "view", 1]], ladder, 10),
  Error,
  "an empty actor name is rejected",
);
assert.throws(
  () => funnelRungReach(marks, ladder, -1),
  Error,
  "a negative window is rejected",
);
console.log("ok");
