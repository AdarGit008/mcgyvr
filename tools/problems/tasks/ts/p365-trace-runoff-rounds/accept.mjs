import assert from "node:assert/strict";
import { traceRunoffRounds } from "./solution.ts";

const repeat = (paper, times) => Array.from({ length: times }, () => [...paper]);

assert.deepEqual(
  traceRunoffRounds([["kite"], ["kite"], ["drum"]]),
  ["1|kite=2,drum=1|won:kite"],
  "one round is enough when a runner already passes half",
);

assert.deepEqual(
  traceRunoffRounds([["one"], ["one"]]),
  ["1|one=2|won:one"],
  "a race of one closes immediately",
);

assert.deepEqual(
  traceRunoffRounds([
    ["a", "b"],
    ["b", "a"],
    ["c", "a"],
  ]),
  ["1|a=1,b=1,c=1|out:c", "2|a=2,b=1|won:a"],
  "an opening-round tie falls to the runner met last",
);

assert.deepEqual(
  traceRunoffRounds([["a"], ["b"], ["c"]]),
  ["1|a=1,b=1,c=1|out:c", "2|a=1,b=1|out:b", "3|a=1|won:a"],
  "papers set aside shrink the half the tally must pass",
);

assert.deepEqual(
  traceRunoffRounds([
    ...repeat(["a"], 8),
    ...repeat(["b", "a"], 3),
    ...repeat(["c"], 4),
    ["d", "b"],
    ["d"],
  ]),
  [
    "1|a=8,c=4,b=3,d=2|out:d",
    "2|a=8,b=4,c=4|out:b",
    "3|a=11,c=4|won:a",
  ],
  "a bottom tie is settled by the round before, not by the names",
);

assert.deepEqual(
  traceRunoffRounds([
    ...repeat(["red", "blue"], 3),
    ...repeat(["blue", "red"], 2),
    ...repeat(["gold", "blue"], 2),
  ]),
  ["1|red=3,blue=2,gold=2|out:gold", "2|blue=4,red=3|won:blue"],
  "the runner ahead in the opening round can be overtaken",
);

assert.deepEqual(
  traceRunoffRounds([
    ["p", "q", "r"],
    ["p", "q", "r"],
    ["q", "r", "p"],
    ["r", "q", "p"],
    ["r", "p", "q"],
  ]),
  ["1|p=2,r=2,q=1|out:q", "2|r=3,p=2|won:r"],
  "falling tally leads the line and first-met order settles the rest",
);

assert.throws(
  () => traceRunoffRounds([]),
  Error,
  "a race with no papers is rejected",
);
assert.throws(
  () => traceRunoffRounds([[]]),
  Error,
  "an empty paper is rejected",
);
assert.throws(
  () => traceRunoffRounds([["a", "a"]]),
  Error,
  "a runner named twice on one paper is rejected",
);
assert.throws(
  () => traceRunoffRounds([["a"], [""]]),
  Error,
  "an empty runner name is rejected",
);
assert.throws(
  () => traceRunoffRounds([["a=b"]]),
  Error,
  "a name holding an equals sign is rejected",
);
assert.throws(
  () => traceRunoffRounds([["a|b"]]),
  Error,
  "a name holding a bar is rejected",
);
assert.throws(
  () => traceRunoffRounds([["a,b"]]),
  Error,
  "a name holding a comma is rejected",
);
assert.throws(
  () => traceRunoffRounds([["a"], 5]),
  Error,
  "a paper that is not a list is rejected",
);
assert.throws(
  () => traceRunoffRounds("papers"),
  Error,
  "an argument that is not a list is rejected",
);
console.log("ok");
