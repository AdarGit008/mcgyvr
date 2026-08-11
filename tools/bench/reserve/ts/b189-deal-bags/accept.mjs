import assert from "node:assert/strict";
import { dealBags } from "./solution.ts";

assert.deepEqual(dealBags([], [2, 2]), { loads: [[], []], spare: [] }, "no parcels leaves every bag empty");
assert.deepEqual(dealBags(["a", "b", "c", "d"], [2, 2]), { loads: [["a", "c"], ["b", "d"]], spare: [] }, "the round hands bags one parcel each in turn");
assert.deepEqual(dealBags(["a", "b", "c", "d", "e", "f", "g"], [2, 1, 3]), { loads: [["a", "d"], ["b"], ["c", "e", "f"]], spare: ["g"] }, "a filled bag drops out of the round and the rest goes spare");
assert.deepEqual(dealBags(["a", "b", "c"], [2]), { loads: [["a", "b"]], spare: ["c"] }, "one bag fills and the overflow is spare");
assert.throws(() => dealBags("abc", [2]), Error, "a parcels argument that is not a list is rejected");
assert.throws(() => dealBags(["a"], [2, 0]), Error, "a capacity that is not positive is rejected");
console.log("ok");
