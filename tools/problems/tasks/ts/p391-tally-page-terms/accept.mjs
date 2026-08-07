import assert from "node:assert/strict";
import { tallyPageTerms } from "./solution.ts";

assert.deepEqual(
  tallyPageTerms(["Carts", "cart", "CART", "dogs", "Dog"], ["cart"]),
  { dogs: 1, dog: 1 },
  "the skip list is weighed against the headword, capitals and all",
);
assert.deepEqual(
  tallyPageTerms(["Books", "books", "BOOKS"], []),
  { book: 3 },
  "entries parting only over capitals share one tally",
);
assert.deepEqual(
  tallyPageTerms(["bus", "gas", "its"], []),
  { bus: 1, gas: 1, its: 1 },
  "a short entry holds on to its s",
);
assert.deepEqual(
  tallyPageTerms(["Trees", "trees"], ["tree"]),
  {},
  "every entry may be skipped",
);
assert.deepEqual(tallyPageTerms([], ["a"]), {}, "no entries make no tallies");
assert.deepEqual(
  tallyPageTerms(["Alpha", "alpha"], []),
  { alpha: 2 },
  "an entry that ends in no s is only folded",
);
assert.deepEqual(tallyPageTerms(["press"], []), { pres: 1 }, "exactly four letters may survive");
assert.deepEqual(
  tallyPageTerms(["Mice", "mice", "MICE"], ["mice"]),
  {},
  "a folded entry the skip list names is passed over",
);
assert.deepEqual(
  tallyPageTerms(["Nodes", "node", "NODES"], []),
  { node: 3 },
  "folding and the lost s meet on the same headword",
);

assert.throws(() => tallyPageTerms("cat", []), Error, "a non-list of entries is rejected");
assert.throws(() => tallyPageTerms([], "cat"), Error, "a non-list skip list is rejected");
assert.throws(() => tallyPageTerms([5], []), Error, "an entry that is not a string is rejected");
assert.throws(() => tallyPageTerms([""], []), Error, "an empty entry is rejected");
console.log("ok");
