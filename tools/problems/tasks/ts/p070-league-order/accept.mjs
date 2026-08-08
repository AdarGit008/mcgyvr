import assert from "node:assert/strict";
import { leagueOrder } from "./solution.ts";

assert.deepEqual(
  leagueOrder([["A", "B", 1, 0], ["B", "C", 5, 0], ["C", "D", 0, 0], ["A", "D", 0, 3]]),
  ["D", "A", "B", "C"],
  "the level-group recount beats a fatter goal difference",
);
assert.deepEqual(
  leagueOrder([["E", "F", 1, 1], ["E", "G", 3, 0], ["F", "G", 2, 0]]),
  ["E", "F", "G"],
  "after a drawn meeting, season goal difference decides",
);
assert.deepEqual(
  leagueOrder([["H", "I", 2, 2], ["H", "J", 3, 1], ["I", "J", 4, 2]]),
  ["I", "H", "J"],
  "with equal goal difference, goals scored decide",
);
assert.deepEqual(
  leagueOrder([["gamma", "beta", 1, 0], ["beta", "alpha", 1, 0], ["alpha", "gamma", 1, 0]]),
  ["alpha", "beta", "gamma"],
  "a perfect cycle falls back to names",
);
assert.deepEqual(leagueOrder([["X", "Y", 2, 0]]), ["X", "Y"], "one match, two places");
assert.deepEqual(
  leagueOrder([["m", "k", 0, 0]]),
  ["k", "m"],
  "a bare draw is ranked alphabetically",
);
assert.throws(() => leagueOrder([["A", "A", 1, 0]]), Error, "self-match rejected");
assert.throws(() => leagueOrder([["A", "B", -1, 0]]), Error, "negative goals rejected");
assert.throws(() => leagueOrder([["A", "B", 1.5, 0]]), Error, "fractional goals rejected");
assert.throws(() => leagueOrder([["A", "B", 1]]), Error, "3-item entry rejected");
assert.throws(() => leagueOrder([[7, "B", 1, 0]]), Error, "non-string name rejected");
console.log("ok");
