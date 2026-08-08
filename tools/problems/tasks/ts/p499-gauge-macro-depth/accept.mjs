import assert from "node:assert/strict";
import { gaugeMacroDepth } from "./solution.ts";

const sheet = [
  { name: "leaf", arity: 0, calls: [] },
  { name: "wrap", arity: 1, calls: [["leaf", 0]] },
  { name: "outer", arity: 0, calls: [["wrap", 1], ["leaf", 0]] },
  { name: "ping", arity: 0, calls: [["pong", 0]] },
  { name: "pong", arity: 0, calls: [["ping", 0]] },
  { name: "lead", arity: 0, calls: [["ping", 0]] },
];

assert.deepEqual(
  gaugeMacroDepth(sheet, 5),
  ["lead cyclic", "leaf 0", "outer 2", "ping cyclic", "pong cyclic", "wrap 1"],
  "depths, a two-macro loop, and a macro that reaches it",
);

assert.deepEqual(
  gaugeMacroDepth(sheet, 1),
  ["lead cyclic", "leaf 0", "outer over", "ping cyclic", "pong cyclic", "wrap 1"],
  "a bound of one puts only the deepest over",
);

assert.deepEqual(
  gaugeMacroDepth(sheet, 0),
  ["lead cyclic", "leaf 0", "outer over", "ping cyclic", "pong cyclic", "wrap over"],
  "a bound of nought leaves only the leaf inside it",
);

assert.deepEqual(
  gaugeMacroDepth([{ name: "solo", arity: 0, calls: [["solo", 0]] }], 9),
  ["solo cyclic"],
  "a macro calling itself never settles",
);

assert.deepEqual(
  gaugeMacroDepth(
    [
      { name: "leaf", arity: 0, calls: [] },
      { name: "twin", arity: 0, calls: [["leaf", 0], ["leaf", 0]] },
    ],
    4,
  ),
  ["leaf 0", "twin 1"],
  "calling one name twice is still one step",
);

assert.deepEqual(gaugeMacroDepth([], 3), [], "no macros gives no lines");

assert.deepEqual(
  gaugeMacroDepth(
    [
      { name: "a1", arity: 2, calls: [["b2", 1]] },
      { name: "b2", arity: 1, calls: [["c3", 0]] },
      { name: "c3", arity: 0, calls: [] },
    ],
    2,
  ),
  ["a1 2", "b2 1", "c3 0"],
  "a chain of three settles at rising depths",
);

assert.throws(() => gaugeMacroDepth("no", 1), Error, "the macros must be a list");
assert.throws(() => gaugeMacroDepth([3], 1), Error, "a macro must be a record");
assert.throws(
  () => gaugeMacroDepth([{ name: "a", arity: 0 }], 1),
  Error,
  "a macro missing a key is refused",
);
assert.throws(
  () => gaugeMacroDepth([{ name: "9a", arity: 0, calls: [] }], 1),
  Error,
  "a name opening with a digit is refused",
);
assert.throws(
  () =>
    gaugeMacroDepth(
      [
        { name: "a", arity: 0, calls: [] },
        { name: "a", arity: 1, calls: [] },
      ],
      1,
    ),
  Error,
  "a repeated name is refused",
);
assert.throws(
  () => gaugeMacroDepth([{ name: "a", arity: 10, calls: [] }], 1),
  Error,
  "an arity of ten is refused",
);
assert.throws(
  () => gaugeMacroDepth([{ name: "a", arity: 0, calls: "no" }], 1),
  Error,
  "calls that are not a list are refused",
);
assert.throws(
  () => gaugeMacroDepth([{ name: "a", arity: 0, calls: [["b"]] }], 1),
  Error,
  "a one-entry call is refused",
);
assert.throws(
  () => gaugeMacroDepth([{ name: "a", arity: 0, calls: [["ghost", 0]] }], 1),
  Error,
  "an undeclared callee is refused",
);
assert.throws(
  () =>
    gaugeMacroDepth(
      [
        { name: "a", arity: 0, calls: [["b", 2]] },
        { name: "b", arity: 1, calls: [] },
      ],
      1,
    ),
  Error,
  "a mismatched argument count is refused",
);
assert.throws(
  () => gaugeMacroDepth([{ name: "a", arity: 0, calls: [["a", -1]] }], 1),
  Error,
  "a negative argument count is refused",
);
assert.throws(
  () => gaugeMacroDepth([{ name: "a", arity: 0, calls: [] }], -2),
  Error,
  "a negative bound is refused",
);
console.log("ok");
