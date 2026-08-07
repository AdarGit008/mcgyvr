import assert from "node:assert/strict";
import { spreadNightDuty } from "./solution.ts";

assert.deepEqual(
  spreadNightDuty(["ivy", "hal", "gus"], [1, 1, 1, 1, 1, 1], [[], [], [], [], [], []]),
  ["gus", "hal", "ivy", "gus", "hal", "ivy"],
  "three quiet sleepers take turns in name order",
);
assert.deepEqual(
  spreadNightDuty(
    ["ann", "bea", "cal", "dot"],
    [2, 1, 1, 1, 2, 1, 1],
    [[], [], [], [], [], [], []],
  ),
  ["ann", "bea", "cal", "dot", "bea", "cal", "dot"],
  "the punishing nights steer who is lightest later",
);
assert.deepEqual(
  spreadNightDuty(["zoe", "amy"], [1, 1, 1, 1], [[], [], [], []]),
  ["amy", "zoe", "?", "amy"],
  "rest empties a night, and amy sorts before zoe",
);
assert.deepEqual(
  spreadNightDuty(["ann", "bea", "cal"], [1, 1, 1], [["ann"], [], ["bea"]]),
  ["bea", "ann", "cal"],
  "being away shifts the opening pick",
);
assert.deepEqual(
  spreadNightDuty(["ann", "bea", "cal"], [2, 2, 2], [[], [], []]),
  ["ann", "bea", "cal"],
  "three punishing nights, one each",
);
assert.deepEqual(
  spreadNightDuty(["sol"], [1, 1, 1, 1], [[], [], [], []]),
  ["sol", "?", "?", "sol"],
  "one person rests two nights between turns",
);
assert.deepEqual(
  spreadNightDuty(["ann", "bea"], [1, 1], [["ann", "bea"], []]),
  ["?", "ann"],
  "an unworked night rests nobody",
);
assert.throws(
  () => spreadNightDuty([], [1], [[]]),
  Error,
  "an empty crew is rejected",
);
assert.throws(
  () => spreadNightDuty(["ann", "ann"], [1], [[]]),
  Error,
  "a repeated crew name is rejected",
);
assert.throws(
  () => spreadNightDuty(["ann", "?"], [1], [[]]),
  Error,
  "the mark as a crew name is rejected",
);
assert.throws(
  () => spreadNightDuty(["ann", 4], [1], [[]]),
  Error,
  "a crew name that is not a string is rejected",
);
assert.throws(
  () => spreadNightDuty(["ann"], [], []),
  Error,
  "no nights at all is rejected",
);
assert.throws(
  () => spreadNightDuty(["ann"], [3], [[]]),
  Error,
  "a weight of three is rejected",
);
assert.throws(
  () => spreadNightDuty(["ann"], [1, 1], [[]]),
  Error,
  "away shorter than weights is rejected",
);
assert.throws(
  () => spreadNightDuty(["ann"], [1], ["ann"]),
  Error,
  "an away entry that is not a list is rejected",
);
assert.throws(
  () => spreadNightDuty(["ann"], [1], [["eve"]]),
  Error,
  "an away entry naming an outsider is rejected",
);
console.log("ok");
