import assert from "node:assert/strict";
import { teamHeadcount } from "./solution.ts";

const shift = { ada: ["bo", "cy"], bo: ["di"], cy: [], di: [] };
const bench = { lead: ["mix", "prove", "bake"], mix: [], prove: [], bake: [] };
const chain = { a1: ["a2"], a2: ["a3"], a3: ["a4"], a4: [] };

assert.equal(teamHeadcount(shift, "ada"), 4, "the top name covers the whole chart");
assert.equal(teamHeadcount(shift, "bo"), 2, "a middle name covers itself and its one report");
assert.equal(teamHeadcount(shift, "cy"), 1, "a worker who leads nobody covers only themselves");
assert.equal(teamHeadcount(shift, "di"), 1, "the deepest name covers only themselves");
assert.equal(teamHeadcount(bench, "lead"), 4, "three direct reports and no depth still count");
assert.equal(teamHeadcount(chain, "a1"), 4, "a chart four levels deep is counted to the bottom");
assert.equal(teamHeadcount(chain, "a3"), 2, "counting starts partway down the chain");
assert.throws(() => teamHeadcount("ada", "ada"), Error, "a chart that is not a mapping is rejected");
assert.throws(() => teamHeadcount(shift, "zoe"), Error, "a name outside the chart is rejected");
assert.throws(() => teamHeadcount({ solo: "nobody" }, "solo"), Error, "reports that are not a list are rejected");
assert.throws(() => teamHeadcount({ lead: [7] }, "lead"), Error, "a report that is not a name is rejected");
console.log("ok");
