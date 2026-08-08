import assert from "node:assert/strict";
import { runByeLadder } from "./solution.ts";

assert.deepEqual(
  runByeLadder(["x", "y"], []),
  { rounds: [{ bye: null, matches: [["x", "y"]] }], champion: "x" },
  "two entrants meet once and the stronger seed takes it",
);
assert.deepEqual(
  runByeLadder(["x", "y"], ["y"]),
  { rounds: [{ bye: null, matches: [["x", "y"]] }], champion: "y" },
  "a named upset turns the only match around",
);
assert.deepEqual(
  runByeLadder(["a", "b", "c", "d"], []),
  {
    rounds: [
      { bye: null, matches: [["a", "d"], ["b", "c"]] },
      { bye: null, matches: [["a", "b"]] },
    ],
    champion: "a",
  },
  "an even field meets head to tail and never sits anybody out",
);
assert.deepEqual(
  runByeLadder(["p", "q", "r"], []),
  {
    rounds: [
      { bye: "p", matches: [["q", "r"]] },
      { bye: null, matches: [["p", "q"]] },
    ],
    champion: "p",
  },
  "three entrants sit the strongest out of the opening round",
);
assert.deepEqual(
  runByeLadder(["ana", "bo", "cy", "dee", "eli"], []),
  {
    rounds: [
      { bye: "ana", matches: [["bo", "eli"], ["cy", "dee"]] },
      { bye: "bo", matches: [["ana", "cy"]] },
      { bye: null, matches: [["ana", "bo"]] },
    ],
    champion: "ana",
  },
  "the second sit-out passes over the one who already sat",
);
assert.deepEqual(
  runByeLadder(["ana", "bo", "cy", "dee", "eli"], ["eli", "cy"]),
  {
    rounds: [
      { bye: "ana", matches: [["bo", "eli"], ["cy", "dee"]] },
      { bye: "cy", matches: [["ana", "eli"]] },
      { bye: null, matches: [["cy", "eli"]] },
    ],
    champion: "eli",
  },
  "an upset carries the weakest seed all the way up",
);

const field = [];
for (let n = 1; n <= 17; n++) {
  field.push("t" + String(n).padStart(2, "0"));
}
const long = runByeLadder(field, []);
assert.equal(long.rounds.length, 5, "seventeen entrants take five rounds");
assert.deepEqual(long.rounds[0].bye, "t01", "the strongest sits the first round out");
assert.equal(long.rounds[0].matches.length, 8, "sixteen play eight matches");
assert.deepEqual(long.rounds[0].matches[0], ["t02", "t17"], "head meets tail");
assert.deepEqual(
  [long.rounds[1].bye, long.rounds[2].bye],
  ["t02", "t03"],
  "the sit-out walks down the seeds while fresh ones remain",
);
assert.deepEqual(
  long.rounds[3],
  { bye: "t01", matches: [["t02", "t03"]] },
  "with all three having sat before, the strongest sits again",
);
assert.deepEqual(
  long.rounds[4],
  { bye: null, matches: [["t01", "t02"]] },
  "the final is even and needs no sitter",
);
assert.equal(long.champion, "t01", "no upsets means the top seed wins");

assert.throws(() => runByeLadder("ab", []), Error, "the seeds are a list");
assert.throws(() => runByeLadder(["a", "b"], "a"), Error, "the upsets are a list");
assert.throws(() => runByeLadder(["a"], []), Error, "one entrant is no ladder");
assert.throws(() => runByeLadder(["a", 2], []), Error, "a name is a string");
assert.throws(() => runByeLadder(["a", "a"], []), Error, "a name is entered once");
assert.throws(() => runByeLadder(["a", "b"], ["z"]), Error, "z is no entrant");
assert.throws(
  () => runByeLadder(["a", "b"], ["b", "b"]),
  Error,
  "an upset is named once",
);
console.log("ok");
