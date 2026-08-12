import assert from "node:assert/strict";
import { shiftRoster } from "./solution.ts";

assert.deepEqual(shiftRoster([]), {}, "no entries yields an empty roster");
assert.deepEqual(shiftRoster([["mira", "day"]]), { day: ["mira"] }, "one entry fills one shift");
assert.deepEqual(shiftRoster([["zoe", "day"], ["abe", "day"]]), { day: ["abe", "zoe"] }, "names within a shift come out alphabetical");
assert.deepEqual(shiftRoster([["kai", "night"], ["ana", "day"], ["ben", "night"]]), { night: ["ben", "kai"], day: ["ana"] }, "entries group under their own shifts");
assert.deepEqual(shiftRoster([["cyd", "late"], ["ada", "early"], ["bo", "late"], ["eli", "early"]]), { late: ["bo", "cyd"], early: ["ada", "eli"] }, "several shifts fill independently");
assert.throws(() => shiftRoster("crew"), Error, "an entries argument that is not a list is rejected");
assert.throws(() => shiftRoster([["solo"]]), Error, "a one-item entry is rejected");
assert.throws(() => shiftRoster([["ana", "day", "extra"]]), Error, "a three-item entry is rejected");
assert.throws(() => shiftRoster([["", "day"]]), Error, "an empty name is rejected");
assert.throws(() => shiftRoster([["ana", 7]]), Error, "a shift that is not a string is rejected");
assert.throws(() => shiftRoster([["ana", "day"], ["ana", "night"]]), Error, "a name signed up twice is rejected");
console.log("ok");
