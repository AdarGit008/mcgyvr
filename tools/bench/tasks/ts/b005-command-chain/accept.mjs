import assert from "node:assert/strict";
import { chainOfCommand, headcount, widestTeam } from "./solution.ts";

const org = {
  name: "avery",
  reports: [
    {
      name: "birch",
      reports: [
        { name: "casey", reports: [] },
        { name: "dana", reports: [{ name: "elm", reports: [] }] },
      ],
    },
    { name: "fern", reports: [] },
  ],
};

assert.deepEqual(chainOfCommand(org, "avery"), ["avery"], "the head alone");
assert.deepEqual(
  chainOfCommand(org, "elm"),
  ["avery", "birch", "dana", "elm"],
  "a deep chain",
);
assert.deepEqual(chainOfCommand(org, "fern"), ["avery", "fern"], "a direct report");
assert.deepEqual(
  chainOfCommand(org, "casey"),
  ["avery", "birch", "casey"],
  "a leaf under the first branch",
);
assert.throws(() => chainOfCommand(org, "zoe"), Error, "absent person is rejected");
assert.throws(
  () =>
    chainOfCommand(
      { name: "dot", reports: [{ name: "dot", reports: [] }] },
      "dot",
    ),
  Error,
  "a duplicated person is rejected",
);
assert.throws(
  () => chainOfCommand({ name: "ok", reports: [{ name: "", reports: [] }] }, "ok"),
  Error,
  "an empty name anywhere is rejected",
);
assert.throws(() => chainOfCommand(org, ""), Error, "empty person is rejected");
assert.throws(() => chainOfCommand(org, 42), Error, "non-string person is rejected");
assert.equal(headcount(org), 6, "headcount of the whole chart");
assert.equal(widestTeam(org), 2, "widest team in the chart");
assert.equal(widestTeam({ name: "solo", reports: [] }), 0, "widest team of one");
console.log("ok");
