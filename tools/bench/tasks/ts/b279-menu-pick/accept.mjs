import assert from "node:assert/strict";
import { menuPick } from "./solution.ts";

const soup = { name: "soup", price: 200 };
const pie = { name: "pie", price: 350 };

assert.deepEqual(menuPick([soup, pie], 300), ["soup"], "the dear one is dropped");
assert.deepEqual(menuPick([pie, soup], 400), ["soup", "pie"], "cheapest leads");
assert.deepEqual(
  menuPick([{ name: "tea", price: 100 }, { name: "ale", price: 100 }], 100),
  ["ale", "tea"],
  "a tie is broken by name",
);
assert.deepEqual(menuPick([], 500), [], "an empty menu");
assert.deepEqual(menuPick([pie], 100), [], "nothing is affordable");
assert.deepEqual(
  menuPick(
    [{ name: "a", price: 100 }, { name: "b", price: 100 }, { name: "c", price: 50 }],
    100,
  ),
  ["c", "a", "b"],
  "price first, then name",
);
console.log("ok");
