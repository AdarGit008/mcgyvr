import assert from "node:assert/strict";
import { netRequirements } from "./solution.ts";

const bench = [
  {
    item: "desk",
    needs: [
      { item: "top", per: 1 },
      { item: "leg", per: 4 },
    ],
  },
  {
    item: "leg",
    needs: [
      { item: "dowel", per: 2 },
      { item: "cap", per: 1 },
    ],
  },
];

assert.deepEqual(
  netRequirements(bench, [], "desk", 1),
  [
    { item: "cap", buy: 4 },
    { item: "dowel", buy: 8 },
    { item: "top", buy: 1 },
  ],
  "an empty store buys the whole tree in",
);
assert.deepEqual(
  netRequirements(
    bench,
    [
      { item: "leg", held: 2 },
      { item: "dowel", held: 3 },
    ],
    "desk",
    1,
  ),
  [
    { item: "cap", buy: 2 },
    { item: "dowel", buy: 1 },
    { item: "top", buy: 1 },
  ],
  "held sub-assemblies shrink what is made beneath them",
);
assert.deepEqual(
  netRequirements(
    bench,
    [
      { item: "leg", held: 4 },
      { item: "top", held: 1 },
    ],
    "desk",
    1,
  ),
  [],
  "a store that covers every call buys nothing",
);
assert.deepEqual(
  netRequirements(bench, [{ item: "desk", held: 99 }], "desk", 1),
  [
    { item: "cap", buy: 4 },
    { item: "dowel", buy: 8 },
    { item: "top", buy: 1 },
  ],
  "stock of the target itself is passed over",
);
assert.deepEqual(
  netRequirements(
    [
      {
        item: "kit",
        needs: [
          { item: "boxA", per: 1 },
          { item: "boxB", per: 1 },
        ],
      },
      { item: "boxA", needs: [{ item: "nail", per: 5 }] },
      { item: "boxB", needs: [{ item: "nail", per: 5 }] },
    ],
    [{ item: "nail", held: 6 }],
    "kit",
    1,
  ),
  [{ item: "nail", buy: 4 }],
  "the first branch reached draws the store down before the second",
);
assert.deepEqual(
  netRequirements(bench, [{ item: "cap", held: 1 }], "leg", 3),
  [
    { item: "cap", buy: 2 },
    { item: "dowel", buy: 6 },
  ],
  "any made item may be the target",
);
assert.deepEqual(
  netRequirements(bench, [{ item: "screw", held: 40 }], "screw", 7),
  [{ item: "screw", buy: 7 }],
  "a bought-in target stands for its whole batch",
);
assert.deepEqual(
  netRequirements(bench, [], "desk", 2),
  [
    { item: "cap", buy: 8 },
    { item: "dowel", buy: 16 },
    { item: "top", buy: 2 },
  ],
  "the batch carries down every branch",
);

assert.throws(
  () =>
    netRequirements(
      [
        { item: "a", needs: [{ item: "b", per: 1 }] },
        { item: "b", needs: [{ item: "a", per: 1 }] },
      ],
      [],
      "a",
      1,
    ),
  Error,
  "a two-item loop",
);
assert.throws(
  () => netRequirements([{ item: "a", needs: [{ item: "a", per: 1 }] }], [], "a", 1),
  Error,
  "an item made of itself",
);
assert.throws(() => netRequirements("no", [], "a", 1), Error, "recipes is not a list");
assert.throws(() => netRequirements(bench, "no", "desk", 1), Error, "stock is not a list");
assert.throws(
  () =>
    netRequirements(
      [
        { item: "a", needs: [{ item: "b", per: 1 }] },
        { item: "a", needs: [{ item: "c", per: 1 }] },
      ],
      [],
      "a",
      1,
    ),
  Error,
  "the same recipe twice",
);
assert.throws(
  () =>
    netRequirements(
      bench,
      [
        { item: "cap", held: 1 },
        { item: "cap", held: 2 },
      ],
      "desk",
      1,
    ),
  Error,
  "the same shelf twice",
);
assert.throws(
  () => netRequirements(bench, [{ item: "cap", held: -1 }], "desk", 1),
  Error,
  "a store holding less than nothing",
);
assert.throws(
  () => netRequirements([{ item: "a", needs: [] }], [], "a", 1),
  Error,
  "a recipe that needs nothing",
);
assert.throws(
  () =>
    netRequirements(
      [
        {
          item: "a",
          needs: [
            { item: "b", per: 1 },
            { item: "b", per: 2 },
          ],
        },
      ],
      [],
      "a",
      1,
    ),
  Error,
  "one need written twice",
);
assert.throws(
  () => netRequirements([{ item: "a", needs: [{ item: "b", per: 0 }] }], [], "a", 1),
  Error,
  "a per of nothing",
);
assert.throws(() => netRequirements(bench, [], "", 1), Error, "an empty target");
assert.throws(() => netRequirements(bench, [], "desk", 0), Error, "a batch of none");
console.log("ok");
