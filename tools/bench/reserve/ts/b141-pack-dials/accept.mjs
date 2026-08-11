import assert from "node:assert/strict";
import { packDials } from "./solution.ts";

assert.equal(packDials({}), "", "an empty preset renders as the empty string");
assert.equal(packDials({ gain: 3 }), "gain=3", "a single dial renders as one pair");
assert.equal(packDials({ tone: 2, bass: 10 }), "bass=10;tone=2", "pairs come out sorted by name");
assert.equal(packDials({ mix: 0 }), "mix=0", "a zero position is rendered");
assert.equal(packDials({ b: 1, a: 2, c: 3 }), "a=2;b=1;c=3", "insertion order does not matter");
assert.throws(() => packDials(42), Error, "a non-mapping is rejected");
assert.throws(() => packDials({ "": 4 }), Error, "an empty name is rejected");
assert.throws(() => packDials({ "lo=fi": 1 }), Error, "a name holding = is rejected");
assert.throws(() => packDials({ "a;b": 1 }), Error, "a name holding ; is rejected");
assert.throws(() => packDials({ hum: 2.5 }), Error, "a fractional position is rejected");
assert.throws(() => packDials({ vol: -1 }), Error, "a negative position is rejected");
console.log("ok");
