import assert from "node:assert/strict";
import { tallyByUnit } from "./solution.ts";

const mass = { t: 1000000, kg: 1000, g: 1 };

assert.deepEqual(tallyByUnit([["flour", 3, "kg"]], mass), { flour: [3, "kg"] }, "a lone entry keeps its own unit");
assert.deepEqual(tallyByUnit([["flour", 1, "kg"], ["flour", 500, "g"]], mass), { flour: [1500, "g"] }, "a total no larger unit divides drops to the base");
assert.deepEqual(tallyByUnit([["sand", 2000, "kg"]], mass), { sand: [2, "t"] }, "an exactly divisible total climbs to the largest unit");
assert.deepEqual(tallyByUnit([["salt", 0, "g"]], mass), { salt: [0, "t"] }, "a total of zero is reported in the largest unit");
assert.deepEqual(tallyByUnit([["oats", 2, "kg"], ["rice", 250, "g"]], mass), { oats: [2, "kg"], rice: [250, "g"] }, "items are totalled apart");
assert.deepEqual(tallyByUnit([], mass), {}, "no entries give an empty mapping");
assert.deepEqual(tallyByUnit([["nail", 3, "box"], ["nail", 6, "single"]], { box: 12, single: 1 }), { nail: [42, "single"] }, "the table given drives the report");
console.log("ok");
