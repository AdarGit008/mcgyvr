import assert from "node:assert/strict";
import { readCrossingStates } from "./solution.ts";

const plaza = [
  { name: "quay", start: 0, walk: 6, clear: 3 },
  { name: "mall", start: 10, walk: 5, clear: 2 },
  { name: "pier", start: 17, walk: 4, clear: 1 },
];
const wrap = [{ name: "lane", start: 18, walk: 4, clear: 0 }];

assert.deepEqual(readCrossingStates(20, plaza, []), [], "no moments asked about");
assert.deepEqual(readCrossingStates(20, plaza, [0]), ["WSW"], "a crossing offset late is already walking at second zero");
assert.deepEqual(readCrossingStates(20, plaza, [1]), ["WSC"], "the offset crossing has slipped into its clearing stretch");
assert.deepEqual(readCrossingStates(20, plaza, [5, 6, 8, 9]), ["WSS", "CSS", "CSS", "SSS"], "the first crossing walks, clears and stops");
assert.deepEqual(readCrossingStates(20, plaza, [10, 14, 16]), ["SWS", "SWS", "SCS"], "the middle crossing takes its turn");
assert.deepEqual(readCrossingStates(20, plaza, [17, 19]), ["SSW", "SSW"], "the late crossing opens near the end of the period");
assert.deepEqual(readCrossingStates(20, plaza, [20, 21]), ["WSW", "WSC"], "a second period repeats the first");
assert.deepEqual(readCrossingStates(20, plaza, [1000000]), ["WSW"], "a far off moment folds back the same way");
assert.deepEqual(readCrossingStates(20, wrap, [17, 18, 19, 0, 1, 2]), ["S", "W", "W", "W", "W", "S"], "a stretch that runs off the end and resumes at zero");
assert.deepEqual(readCrossingStates(1, [{ name: "solo", start: 0, walk: 1, clear: 0 }], [0, 1, 7]), ["W", "W", "W"], "a one second period always walks");

assert.throws(() => readCrossingStates(0, plaza, [0]), Error, "a period of zero");
assert.throws(() => readCrossingStates(86401, plaza, [0]), Error, "a period past the ceiling");
assert.throws(() => readCrossingStates(1.5, plaza, [0]), Error, "a fractional period");
assert.throws(() => readCrossingStates(20, [], [0]), Error, "an empty crossing list");
assert.throws(() => readCrossingStates(20, "plaza", [0]), Error, "crossings given as text");
assert.throws(() => readCrossingStates(20, [{ name: "a", start: 0, walk: 3 }], [0]), Error, "a crossing missing clear");
assert.throws(() => readCrossingStates(20, [{ name: "", start: 0, walk: 3, clear: 1 }], [0]), Error, "an empty crossing name");
assert.throws(() => readCrossingStates(20, [{ name: "a", start: 20, walk: 3, clear: 1 }], [0]), Error, "a start equal to the period");
assert.throws(() => readCrossingStates(20, [{ name: "a", start: 0, walk: 0, clear: 1 }], [0]), Error, "a crossing that never walks");
assert.throws(() => readCrossingStates(20, [{ name: "a", start: 0, walk: 18, clear: 5 }], [0]), Error, "walk plus clear outrunning the period");
assert.throws(
  () => readCrossingStates(20, [{ name: "a", start: 0, walk: 3, clear: 1 }, { name: "a", start: 5, walk: 2, clear: 0 }], [0]),
  Error,
  "a repeated crossing name"
);
assert.throws(() => readCrossingStates(20, plaza, "0"), Error, "moments given as text");
assert.throws(() => readCrossingStates(20, plaza, [-1]), Error, "a moment below zero");
assert.throws(() => readCrossingStates(20, plaza, [1000001]), Error, "a moment past the ceiling");
assert.throws(() => readCrossingStates(20, plaza, [2.5]), Error, "a fractional moment");
console.log("ok");
