import assert from "node:assert/strict";
import { collectHeapCycles } from "./solution.ts";

const cell = (id, refs, finalizer) => ({ id, refs, finalizer });

assert.deepEqual(collectHeapCycles([], []), [], "no collections, no reports");
assert.deepEqual(
  collectHeapCycles([cell("a", [], false)], [["a"]]),
  [{ finalized: [], collected: [] }],
  "a held cell is painted and nothing is doomed",
);
assert.deepEqual(
  collectHeapCycles(
    [
      cell("a", ["b"], false),
      cell("b", [], false),
      cell("x", ["y"], false),
      cell("y", ["x"], false),
    ],
    [["a"]],
  ),
  [{ finalized: [], collected: ["x", "y"] }],
  "a ring nobody holds is swept whole",
);
assert.deepEqual(
  collectHeapCycles(
    [cell("a", ["f"], false), cell("f", [], true)],
    [["a"]],
  ),
  [{ finalized: [], collected: [] }],
  "a painted cell never has its finalizer run",
);
assert.deepEqual(
  collectHeapCycles(
    [cell("a", [], false), cell("m", ["n"], true), cell("n", [], true)],
    [["a", "m"], ["a"], ["a"]],
  ),
  [
    { finalized: [], collected: [] },
    { finalized: ["m", "n"], collected: [] },
    { finalized: [], collected: ["m", "n"] },
  ],
  "the collection that runs a finalizer sweeps nothing it touched",
);
assert.deepEqual(
  collectHeapCycles(
    [cell("a", [], false), cell("m", ["n"], true), cell("n", [], true)],
    [["a", "m"], ["a", "n"], ["a"], ["a"]],
  ),
  [
    { finalized: [], collected: [] },
    { finalized: ["m"], collected: [] },
    { finalized: ["n"], collected: ["m"] },
    { finalized: [], collected: ["n"] },
  ],
  "sparing n one round delays its own finalizer to the next",
);
assert.deepEqual(
  collectHeapCycles(
    [cell("r", [], false), cell("f", ["g"], true), cell("g", ["f"], true)],
    [["r"], ["r"]],
  ),
  [
    { finalized: ["f", "g"], collected: [] },
    { finalized: [], collected: ["f", "g"] },
  ],
  "two cells pointing at each other are finalized then swept",
);
assert.deepEqual(
  collectHeapCycles(
    [cell("a", [], false), cell("b", [], false), cell("c", [], false)],
    [["a", "a", "a"]],
  ),
  [{ finalized: [], collected: ["b", "c"] }],
  "holding one id three times holds it once",
);

assert.throws(() => collectHeapCycles("heap", []), Error, "a heap is a list");
assert.throws(
  () => collectHeapCycles([cell("a", [], false)], "roots"),
  Error,
  "the held-id lists are a list",
);
assert.throws(
  () => collectHeapCycles([{ refs: [], finalizer: false }], []),
  Error,
  "a cell needs an id",
);
assert.throws(
  () => collectHeapCycles([cell("a", [], false), cell("a", [], true)], []),
  Error,
  "two cells may not share an id",
);
assert.throws(
  () => collectHeapCycles([cell("a", ["ghost"], false)], []),
  Error,
  "a ref must name a cell",
);
assert.throws(
  () => collectHeapCycles([cell("a", [], "yes")], []),
  Error,
  "the finalizer flag is a boolean",
);
assert.throws(
  () => collectHeapCycles([cell("a", [], false)], [["b"]]),
  Error,
  "a held id must name a cell",
);
assert.throws(
  () => collectHeapCycles([cell("a", [], false), cell("z", [], false)], [["a"], ["z"]]),
  Error,
  "a swept cell can no longer be held",
);
console.log("ok");
