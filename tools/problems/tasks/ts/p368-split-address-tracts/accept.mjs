import assert from "node:assert/strict";
import { splitAddressTracts } from "./solution.ts";

assert.deepEqual(
  splitAddressTracts("aaaaa/0", [30, 3, 100]),
  {
    refused: false,
    tracts: ["baaaa/2", "bbaaa/4", "aaaaa/1"],
    spare: 700,
  },
  "the roomiest want is served first and the rest fall in behind it",
);

assert.deepEqual(
  splitAddressTracts("aaaaa/3", [1, 4]),
  { refused: false, tracts: ["aaaba/5", "aaaaa/4"], spare: 11 },
  "a single address is pinned all five letters deep",
);

assert.deepEqual(
  splitAddressTracts("aaaaa/3", [4, 4, 4, 4]),
  {
    refused: false,
    tracts: ["aaaaa/4", "aaaba/4", "aaaca/4", "aaada/4"],
    spare: 0,
  },
  "wants of one length are laid down in the order they were listed",
);

assert.deepEqual(
  splitAddressTracts("baaaa/1", [200]),
  { refused: false, tracts: ["baaaa/1"], spare: 0 },
  "a want rounding up to the root's own span takes the root whole",
);

assert.deepEqual(
  splitAddressTracts("caaaa/1", [64, 64]),
  { refused: false, tracts: ["caaaa/2", "cbaaa/2"], spare: 128 },
  "a root away from the start still hands out runs in rising order",
);

assert.deepEqual(
  splitAddressTracts("baaaa/1", [300]),
  { refused: true, tracts: [], spare: 256 },
  "a want past the root's span is refused outright",
);

assert.deepEqual(
  splitAddressTracts("aaaaa/3", [1, 6]),
  { refused: true, tracts: [], spare: 16 },
  "a want that fills the root leaves nowhere for the small one",
);

assert.deepEqual(
  splitAddressTracts("aaaaa/2", [17, 17, 17, 17, 17]),
  { refused: true, tracts: [], spare: 64 },
  "five wants rounded to sixty-four cannot share a root of sixty-four",
);

assert.throws(
  () => splitAddressTracts("aaaaa", [4]),
  Error,
  "a root with no slash is rejected",
);
assert.throws(
  () => splitAddressTracts("aaaaa/6", [4]),
  Error,
  "a pinned count past five is rejected",
);
assert.throws(
  () => splitAddressTracts("aaaab/0", [4]),
  Error,
  "a letter past the pinned ones that is not a is rejected",
);
assert.throws(
  () => splitAddressTracts("aaeaa/2", [4]),
  Error,
  "a letter outside a to d is rejected",
);
assert.throws(
  () => splitAddressTracts("aaaa/2", [4]),
  Error,
  "an address of the wrong length is rejected",
);
assert.throws(
  () => splitAddressTracts(9, [4]),
  Error,
  "a root that is not a string is rejected",
);
assert.throws(
  () => splitAddressTracts("aaaaa/0", []),
  Error,
  "an empty want list is rejected",
);
assert.throws(
  () => splitAddressTracts("aaaaa/0", [0]),
  Error,
  "a want of zero is rejected",
);
assert.throws(
  () => splitAddressTracts("aaaaa/0", [2.5]),
  Error,
  "a fractional want is rejected",
);
assert.throws(
  () => splitAddressTracts("aaaaa/0", "four"),
  Error,
  "wants that are not a list are rejected",
);
console.log("ok");
