import assert from "node:assert/strict";
import { cheapestTray } from "./solution.ts";

const items = [
  { code: "sup", price: 300 },
  { code: "mug", price: 250 },
  { code: "pie", price: 400 },
];
const bundles = [
  { code: "deal", price: 500, holds: ["sup", "mug"] },
  { code: "big", price: 900, holds: ["sup", "mug", "pie"] },
];

assert.deepEqual(
  cheapestTray(items, bundles, []),
  { total: 0, picks: [] },
  "requiring nothing costs nothing",
);
assert.deepEqual(
  cheapestTray(items, bundles, ["sup"]),
  { total: 300, picks: ["sup"] },
  "a single item beats every bundle holding it",
);
assert.deepEqual(
  cheapestTray(items, bundles, ["sup", "mug"]),
  { total: 500, picks: ["deal"] },
  "a bundle beats the two items it holds",
);
assert.deepEqual(
  cheapestTray(items, bundles, ["sup", "mug", "pie"]),
  { total: 900, picks: ["big"] },
  "an equal price is settled by the smaller number of purchases",
);
assert.deepEqual(
  cheapestTray(items, bundles, ["mug"]),
  { total: 250, picks: ["mug"] },
  "carrying more than was asked is allowed but never cheaper here",
);
assert.deepEqual(
  cheapestTray(
    [
      { code: "a", price: 100 },
      { code: "b", price: 100 },
      { code: "c", price: 100 },
      { code: "d", price: 100 },
    ],
    [{ code: "pack", price: 250, holds: ["a", "b", "c"] }],
    ["a", "b", "c", "d"],
  ),
  { total: 350, picks: ["d", "pack"] },
  "a bundle and a loose item together beat four loose items",
);
assert.deepEqual(
  cheapestTray(
    [{ code: "x", price: 100 }],
    [
      { code: "c2", price: 100, holds: ["x"] },
      { code: "c1", price: 100, holds: ["x"] },
    ],
    ["x"],
  ),
  { total: 100, picks: ["c1"] },
  "same price and same count is settled by the codes reading smaller",
);
assert.deepEqual(
  cheapestTray(items, bundles, ["pie", "sup"]),
  { total: 700, picks: ["pie", "sup"] },
  "picks come back sorted upward whatever order they were found in",
);
assert.throws(
  () => cheapestTray(items, bundles, ["soup"]),
  Error,
  "a required code no item sells is rejected",
);
assert.throws(
  () => cheapestTray(items, bundles, ["sup", "sup"]),
  Error,
  "a code required twice is rejected",
);
assert.throws(
  () => cheapestTray(items, [{ code: "z", price: 10, holds: ["ghost"] }], ["sup"]),
  Error,
  "a bundle holding an unknown code is rejected",
);
assert.throws(
  () => cheapestTray(items, [{ code: "z", price: 10, holds: [] }], ["sup"]),
  Error,
  "a bundle holding nothing is rejected",
);
assert.throws(
  () => cheapestTray(items, [{ code: "sup", price: 10, holds: ["sup"] }], ["sup"]),
  Error,
  "a bundle wearing an item's code is rejected",
);
assert.throws(
  () => cheapestTray([{ code: "sup", price: 0 }], [], ["sup"]),
  Error,
  "a price below one penny is rejected",
);
assert.throws(
  () =>
    cheapestTray(
      Array.from({ length: 15 }, (_unused, i) => ({ code: "i" + i, price: 5 })),
      [],
      ["i0"],
    ),
  Error,
  "fifteen things on sale is too many to search",
);
console.log("ok");
