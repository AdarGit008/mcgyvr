import assert from "node:assert/strict";
import { zonePickWalk } from "./solution.ts";

const at = (code, zone, row, slot) => ({ code, zone, row, slot });
const plan = (zoneOrder, picks) => ({ zoneOrder, picks });

assert.deepEqual(zonePickWalk(plan(["a"], [])), [], "no picks, no lines");
assert.deepEqual(
  zonePickWalk(plan(["a"], [at("p1", "a", 3, 2)])),
  ["a/3:p1"],
  "one pick makes one line"
);
assert.deepEqual(
  zonePickWalk(
    plan(["z"], [at("a", "z", 5, 9), at("b", "z", 5, 2), at("c", "z", 5, 6)])
  ),
  ["z/5:b|c|a"],
  "the first row entered is taken facing up"
);
assert.deepEqual(
  zonePickWalk(
    plan(
      ["z"],
      [
        at("a", "z", 2, 1),
        at("b", "z", 2, 4),
        at("c", "z", 3, 1),
        at("d", "z", 3, 4),
      ]
    )
  ),
  ["z/2:a|b", "z/3:d|c"],
  "the trolley turns about on the second row entered"
);
assert.deepEqual(
  zonePickWalk(
    plan(["back", "front"], [at("f", "front", 1, 1), at("k", "back", 1, 1)])
  ),
  ["back/1:k", "front/1:f"],
  "zoneOrder decides the sequence, not the pick list"
);
assert.deepEqual(
  zonePickWalk(
    plan(["a", "b", "c"], [at("x", "c", 1, 1), at("y", "a", 1, 1)])
  ),
  ["a/1:y", "c/1:x"],
  "a zone with no picks is passed over"
);
assert.deepEqual(
  zonePickWalk(plan(["z"], [at("late", "z", 1, 3), at("early", "z", 1, 3)])),
  ["z/1:late|early"],
  "a shared slot keeps the listed order"
);
assert.deepEqual(
  zonePickWalk(
    plan(
      ["z", "y"],
      [
        at("a", "z", 1, 5),
        at("b", "z", 1, 2),
        at("c", "z", 2, 5),
        at("d", "z", 2, 2),
        at("e", "z", 3, 5),
        at("f", "z", 3, 2),
        at("g", "y", 4, 5),
        at("h", "y", 4, 2),
        at("i", "y", 7, 5),
        at("j", "y", 7, 2),
      ]
    )
  ),
  ["z/1:b|a", "z/2:c|d", "z/3:f|e", "y/4:h|g", "y/7:i|j"],
  "the facing resets when a new zone is entered"
);

assert.throws(() => zonePickWalk([1, 2]), Error, "a plan that is not a mapping is rejected");
assert.throws(
  () => zonePickWalk(plan([], [])),
  Error,
  "an empty zoneOrder is rejected"
);
assert.throws(
  () => zonePickWalk(plan(["a", "a"], [])),
  Error,
  "a repeated zone is rejected"
);
assert.throws(
  () => zonePickWalk(plan([7], [])),
  Error,
  "a zone that is not a string is rejected"
);
assert.throws(
  () => zonePickWalk({ zoneOrder: ["a"], picks: "none" }),
  Error,
  "picks that are not a list is rejected"
);
assert.throws(
  () => zonePickWalk(plan(["a"], [["a", 1]])),
  Error,
  "a pick that is not a mapping is rejected"
);
assert.throws(
  () => zonePickWalk(plan(["a"], [{ zone: "a", row: 1, slot: 1 }])),
  Error,
  "a missing code is rejected"
);
assert.throws(
  () => zonePickWalk(plan(["a"], [at("k", "a", 1, 1), at("k", "a", 2, 1)])),
  Error,
  "a repeated code is rejected"
);
assert.throws(
  () => zonePickWalk(plan(["a"], [at("k", "b", 1, 1)])),
  Error,
  "a pick in an unlisted zone is rejected"
);
assert.throws(
  () => zonePickWalk(plan(["a"], [at("k", "a", 0, 1)])),
  Error,
  "row zero is rejected"
);
assert.throws(
  () => zonePickWalk(plan(["a"], [at("k", "a", 1, "3")])),
  Error,
  "a slot that is not a number is rejected"
);

console.log("ok");
