import assert from "node:assert/strict";
import { serialize, deserialize } from "./solution.ts";

const leaf = (value) => ({ value, left: null, right: null });

assert.equal(serialize(null), "#", "empty tree");
assert.equal(serialize(leaf(7)), "7,#,#", "single node");
const full = { value: 1, left: leaf(2), right: leaf(3) };
assert.equal(serialize(full), "1,2,#,#,3,#,#", "one full level");
const leftOnly = { value: 1, left: leaf(2), right: null };
const rightOnly = { value: 1, left: null, right: leaf(2) };
assert.equal(serialize(leftOnly), "1,2,#,#,#", "lone left child");
assert.equal(serialize(rightOnly), "1,#,2,#,#", "lone right child");
assert.equal(
  serialize({ value: -5, left: leaf(-1), right: null }),
  "-5,-1,#,#,#",
  "negative values",
);

assert.deepEqual(deserialize("#"), null, "deserialize the empty tree");
assert.deepEqual(deserialize("1,2,#,#,#"), leftOnly, "left-only shape survives");
assert.deepEqual(deserialize("1,#,2,#,#"), rightOnly, "right-only shape survives");
assert.deepEqual(deserialize("1,2,#,#,3,#,#"), full, "full level round shape");

const bushy = "5,3,1,#,#,4,#,#,8,#,9,#,#";
assert.equal(serialize(deserialize(bushy)), bushy, "round trip, bushy tree");
const chain = "1,2,3,#,#,#,#";
assert.equal(serialize(deserialize(chain)), chain, "round trip, left chain");
assert.deepEqual(deserialize(serialize(full)), full, "round trip, object side");

assert.throws(() => deserialize("1,#"), Error, "truncated input throws");
assert.throws(() => deserialize("1,2,#,#"), Error, "incomplete right subtree throws");
assert.throws(() => deserialize("1,#,#,#"), Error, "leftover tokens throw");
assert.throws(() => deserialize("x,#,#"), Error, "non-integer token throws");
assert.throws(() => deserialize(""), Error, "empty string is not a tree");
