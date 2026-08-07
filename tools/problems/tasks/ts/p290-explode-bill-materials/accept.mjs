import assert from "node:assert/strict";
import { explodeBillOfMaterials } from "./solution.ts";

const works = [
  {
    part: "bike",
    uses: [
      { part: "wheel", per: 2 },
      { part: "frame", per: 1 },
    ],
  },
  {
    part: "wheel",
    uses: [
      { part: "spoke", per: 8 },
      { part: "rim", per: 1 },
    ],
  },
  { part: "frame", uses: [{ part: "tube", per: 4 }] },
];

assert.deepEqual(
  explodeBillOfMaterials(works, "bike", 1),
  [
    { part: "rim", count: 2 },
    { part: "spoke", count: 16 },
    { part: "tube", count: 4 },
  ],
  "one whole assembly down to raw stock",
);
assert.deepEqual(
  explodeBillOfMaterials(works, "bike", 3),
  [
    { part: "rim", count: 6 },
    { part: "spoke", count: 48 },
    { part: "tube", count: 12 },
  ],
  "the batch multiplies every leaf",
);
assert.deepEqual(
  explodeBillOfMaterials(works, "wheel", 1),
  [
    { part: "rim", count: 1 },
    { part: "spoke", count: 8 },
  ],
  "a sub-assembly may be the root",
);
assert.deepEqual(
  explodeBillOfMaterials(works, "spoke", 5),
  [{ part: "spoke", count: 5 }],
  "raw stock as the root is its own answer",
);
assert.deepEqual(
  explodeBillOfMaterials(
    [
      {
        part: "cart",
        uses: [
          { part: "axle", per: 2 },
          { part: "bed", per: 1 },
        ],
      },
      { part: "axle", uses: [{ part: "pin", per: 3 }] },
      {
        part: "bed",
        uses: [
          { part: "pin", per: 5 },
          { part: "plank", per: 6 },
        ],
      },
    ],
    "cart",
    1,
  ),
  [
    { part: "pin", count: 11 },
    { part: "plank", count: 6 },
  ],
  "stock wanted by two branches is summed once",
);
assert.deepEqual(
  explodeBillOfMaterials(
    [
      { part: "a", uses: [{ part: "b", per: 2 }] },
      { part: "b", uses: [{ part: "c", per: 3 }] },
      { part: "c", uses: [{ part: "d", per: 5 }] },
    ],
    "a",
    2,
  ),
  [{ part: "d", count: 60 }],
  "the per counts multiply the whole way down",
);
assert.deepEqual(
  explodeBillOfMaterials(
    [
      { part: "lamp", uses: [{ part: "glass", per: 1 }] },
      { part: "x", uses: [{ part: "y", per: 1 }] },
      { part: "y", uses: [{ part: "x", per: 1 }] },
    ],
    "lamp",
    1,
  ),
  [{ part: "glass", count: 1 }],
  "a loop the root never reaches is no concern",
);

assert.throws(
  () =>
    explodeBillOfMaterials(
      [
        { part: "x", uses: [{ part: "y", per: 1 }] },
        { part: "y", uses: [{ part: "x", per: 1 }] },
      ],
      "x",
      1,
    ),
  Error,
  "a two-part loop",
);
assert.throws(
  () => explodeBillOfMaterials([{ part: "a", uses: [{ part: "a", per: 1 }] }], "a", 1),
  Error,
  "a part that swallows itself",
);
assert.throws(() => explodeBillOfMaterials("works", "a", 1), Error, "parts is not a list");
assert.throws(
  () =>
    explodeBillOfMaterials(
      [
        { part: "a", uses: [{ part: "b", per: 1 }] },
        { part: "a", uses: [{ part: "c", per: 1 }] },
      ],
      "a",
      1,
    ),
  Error,
  "the same part named twice",
);
assert.throws(
  () => explodeBillOfMaterials([{ part: "", uses: [{ part: "b", per: 1 }] }], "a", 1),
  Error,
  "an empty part name",
);
assert.throws(
  () => explodeBillOfMaterials([{ part: "a", uses: [] }], "a", 1),
  Error,
  "an assembly that swallows nothing",
);
assert.throws(
  () =>
    explodeBillOfMaterials(
      [
        {
          part: "a",
          uses: [
            { part: "b", per: 1 },
            { part: "b", per: 2 },
          ],
        },
      ],
      "a",
      1,
    ),
  Error,
  "the same sub-part named twice in one entry",
);
assert.throws(
  () => explodeBillOfMaterials([{ part: "a", uses: [{ part: "b", per: 0 }] }], "a", 1),
  Error,
  "a per of nothing",
);
assert.throws(
  () => explodeBillOfMaterials([{ part: "a", uses: [{ part: "b", per: 1.5 }] }], "a", 1),
  Error,
  "a fractional per",
);
assert.throws(() => explodeBillOfMaterials(works, "", 1), Error, "an empty root");
assert.throws(() => explodeBillOfMaterials(works, "bike", 0), Error, "a batch of none");
console.log("ok");
