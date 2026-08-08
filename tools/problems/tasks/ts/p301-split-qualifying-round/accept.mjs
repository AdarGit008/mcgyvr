import assert from "node:assert/strict";
import { splitQualifyingRound } from "./solution.ts";

const field = (count) => {
  const names = [];
  for (let n = 1; n <= count; n++) {
    names.push("s" + String(n).padStart(2, "0"));
  }
  return names;
};

assert.deepEqual(
  splitQualifyingRound(["a", "b"]),
  { direct: ["a", "b"], qualifying: [] },
  "two entrants are already a power of two",
);
assert.deepEqual(
  splitQualifyingRound(["a", "b", "c"]),
  { direct: ["a"], qualifying: [["b", "c"]] },
  "a surplus of one sends the two weakest to qualifying",
);
assert.deepEqual(
  splitQualifyingRound(["a", "b", "c", "d"]),
  { direct: ["a", "b", "c", "d"], qualifying: [] },
  "four walk in untroubled",
);
assert.deepEqual(
  splitQualifyingRound(["a", "b", "c", "d", "e"]),
  { direct: ["a", "b", "c"], qualifying: [["d", "e"]] },
  "five leaves a surplus of one over a draw of four",
);
assert.deepEqual(
  splitQualifyingRound(["a", "b", "c", "d", "e", "f"]),
  { direct: ["a", "b"], qualifying: [["c", "f"], ["d", "e"]] },
  "six draws two qualifying matches from the weakest four",
);
assert.deepEqual(
  splitQualifyingRound(["a", "b", "c", "d", "e", "f", "g"]),
  { direct: ["a"], qualifying: [["b", "g"], ["c", "f"], ["d", "e"]] },
  "seven leaves only the top seed walking in",
);
assert.deepEqual(
  splitQualifyingRound(field(8)),
  { direct: field(8), qualifying: [] },
  "eight is a power of two and plays nothing",
);
assert.deepEqual(
  splitQualifyingRound(field(9)),
  { direct: field(7), qualifying: [["s08", "s09"]] },
  "nine sends only the last two down",
);
assert.deepEqual(
  splitQualifyingRound(field(12)),
  {
    direct: field(4),
    qualifying: [
      ["s05", "s12"],
      ["s06", "s11"],
      ["s07", "s10"],
      ["s08", "s09"],
    ],
  },
  "twelve draws four matches inward from the weakest eight",
);

assert.throws(() => splitQualifyingRound("ab"), Error, "the field is a list");
assert.throws(() => splitQualifyingRound(["a"]), Error, "one entrant is no field");
assert.throws(() => splitQualifyingRound([]), Error, "an empty field is no field");
assert.throws(() => splitQualifyingRound(["a", 2]), Error, "a name is a string");
assert.throws(() => splitQualifyingRound(["a", "a"]), Error, "a name is listed once");
console.log("ok");
