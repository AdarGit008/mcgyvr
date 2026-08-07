import assert from "node:assert/strict";
import { kinshipDegree } from "./solution.ts";

const REGISTER = {
  amos: [],
  olive: ["amos"],
  pearl: ["amos"],
  rex: ["olive", "pearl"],
  sara: ["olive", "pearl"],
  tom: ["rex"],
  una: ["sara"],
  vic: ["tom"],
  wren: ["una"],
  yuri: [],
  zoe: ["yuri"],
};

assert.deepEqual(
  kinshipDegree(REGISTER, "rex", "rex"),
  { steps: 0, line: "direct", meet: "rex" },
  "a person against themselves stands nought steps away",
);

assert.deepEqual(
  kinshipDegree(REGISTER, "rex", "olive"),
  { steps: 1, line: "direct", meet: "olive" },
  "one step up the direct line",
);

assert.deepEqual(
  kinshipDegree(REGISTER, "olive", "rex"),
  { steps: 1, line: "direct", meet: "olive" },
  "the elder is the meeting point whichever way round the two are given",
);

assert.deepEqual(
  kinshipDegree(REGISTER, "vic", "amos"),
  { steps: 4, line: "direct", meet: "amos" },
  "four steps up the direct line",
);

assert.deepEqual(
  kinshipDegree(REGISTER, "amos", "vic"),
  { steps: 4, line: "direct", meet: "amos" },
  "and the same four counted downward",
);

assert.deepEqual(
  kinshipDegree(REGISTER, "rex", "sara"),
  { steps: 2, line: "collateral", meet: "olive" },
  "two shared forebears at the same sum, and the name that sorts first takes it",
);

assert.deepEqual(
  kinshipDegree(REGISTER, "tom", "una"),
  { steps: 4, line: "collateral", meet: "olive" },
  "the nearer shared forebear beats the one further up",
);

assert.deepEqual(
  kinshipDegree(REGISTER, "tom", "sara"),
  { steps: 3, line: "collateral", meet: "olive" },
  "an uneven pair of climbs still adds to the least sum",
);

assert.deepEqual(
  kinshipDegree(REGISTER, "wren", "vic"),
  { steps: 6, line: "collateral", meet: "olive" },
  "the longest collateral reach in the register",
);

assert.deepEqual(
  kinshipDegree(REGISTER, "rex", "zoe"),
  { steps: 0, line: "apart", meet: "" },
  "two people out of each other's reach entirely",
);

assert.deepEqual(
  kinshipDegree(REGISTER, "zoe", "yuri"),
  { steps: 1, line: "direct", meet: "yuri" },
  "the far branch has a direct line of its own",
);

assert.throws(() => kinshipDegree([], "a", "b"), Error, "a register that is not a mapping is rejected");
assert.throws(() => kinshipDegree({ "": [] }, "", ""), Error, "an empty key is rejected");
assert.throws(() => kinshipDegree({ a: "b", b: [] }, "a", "b"), Error, "a forebear list that is not a list is rejected");
assert.throws(
  () => kinshipDegree({ a: ["b", "c", "d"], b: [], c: [], d: [] }, "a", "b"),
  Error,
  "a third forebear is rejected",
);
assert.throws(() => kinshipDegree({ a: ["b", "b"], b: [] }, "a", "b"), Error, "a forebear named twice is rejected");
assert.throws(() => kinshipDegree({ a: ["a"] }, "a", "a"), Error, "someone made their own forebear is rejected");
assert.throws(() => kinshipDegree({ a: ["b"] }, "a", "a"), Error, "a forebear who is not a key is rejected");
assert.throws(() => kinshipDegree({ a: [5], b: [] }, "a", "b"), Error, "a forebear that is not a string is rejected");
assert.throws(() => kinshipDegree({ a: ["b"], b: ["a"] }, "a", "b"), Error, "a register that closes a loop is rejected");
assert.throws(() => kinshipDegree(REGISTER, "nobody", "rex"), Error, "a second person who is not a key is rejected");
assert.throws(() => kinshipDegree(REGISTER, "rex", "nobody"), Error, "a third person who is not a key is rejected");
assert.throws(() => kinshipDegree(REGISTER, 4, "rex"), Error, "a person who is not a string is rejected");
console.log("ok");
