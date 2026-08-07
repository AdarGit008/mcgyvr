import assert from "node:assert/strict";
import { fillDeskMap } from "./solution.ts";

assert.deepEqual(
  fillDeskMap(["aa.bb", "#a.b#", "..c.."], { a: ["Ada", "Bo"], b: ["Cyd"], c: [] }),
  {
    floor: ["AB.Cb", "#a.b#", "..c.."],
    sat: ["Ada r0 c0", "Bo r0 c1", "Cyd r0 c3"],
    spare: 4,
  },
  "banks fill in reading order and leftovers stay small",
);
assert.deepEqual(
  fillDeskMap(["dd", "dd"], { d: ["Wu", "Xi", "Yo", "Ze"] }),
  {
    floor: ["WX", "YZ"],
    sat: ["Wu r0 c0", "Xi r0 c1", "Yo r1 c0", "Ze r1 c1"],
    spare: 0,
  },
  "a bank can be filled to the last desk",
);
assert.deepEqual(
  fillDeskMap(["ab", "#."], {}),
  { floor: ["ab", "#."], sat: [], spare: 2 },
  "an empty legend leaves the floor as drawn",
);
assert.deepEqual(
  fillDeskMap(["zaz"], { z: ["Mo"], a: ["Nia"] }),
  { floor: ["MNz"], sat: ["Nia r0 c1", "Mo r0 c0"], spare: 1 },
  "banks are reported in rising letter order",
);
assert.deepEqual(
  fillDeskMap(["p", "p"], { p: ["ann"] }),
  { floor: ["A", "p"], sat: ["ann r0 c0"], spare: 1 },
  "the opening letter is written as a capital",
);
assert.equal(fillDeskMap(["...", "###"], {}).spare, 0, "a floor with no desks has no spare desks");
assert.throws(() => fillDeskMap("aa", {}), Error, "a floor that is not a list is rejected");
assert.throws(() => fillDeskMap([], {}), Error, "an empty floor is rejected");
assert.throws(() => fillDeskMap([7], {}), Error, "a row that is not a string is rejected");
assert.throws(() => fillDeskMap([""], {}), Error, "an empty row is rejected");
assert.throws(() => fillDeskMap(["aa", "a"], {}), Error, "ragged rows are rejected");
assert.throws(() => fillDeskMap(["aA"], {}), Error, "a stray character is rejected");
assert.throws(() => fillDeskMap(["aa"], []), Error, "a legend that is not a mapping is rejected");
assert.throws(() => fillDeskMap(["aa"], { ab: [] }), Error, "a two letter bank key is rejected");
assert.throws(() => fillDeskMap(["aa"], { b: [] }), Error, "a bank the floor never draws is rejected");
assert.throws(() => fillDeskMap(["aa"], { a: "Ada" }), Error, "a legend value that is not a list is rejected");
assert.throws(() => fillDeskMap(["aa"], { a: ["A1"] }), Error, "a name with a digit is rejected");
assert.throws(() => fillDeskMap(["aa"], { a: [""] }), Error, "an empty name is rejected");
assert.throws(() => fillDeskMap(["ab"], { a: ["Ada"], b: ["Ada"] }), Error, "one name at two desks is rejected");
assert.throws(() => fillDeskMap(["a"], { a: ["Ada", "Bo"] }), Error, "more people than desks is rejected");
console.log("ok");
