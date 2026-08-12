import assert from "node:assert/strict";
import { drawStock } from "./solution.ts";

assert.deepEqual(drawStock({ bolt: 4 }, [["bolt", 3]]), { bolt: 1 }, "one line pulls its count");
assert.deepEqual(drawStock({ bolt: 4 }, [["bolt", 2], ["bolt", 2]]), { bolt: 0 }, "repeat lines drain to zero, item kept");
assert.deepEqual(drawStock({ bolt: 4, nut: 2 }, [["bolt", 1]]), { bolt: 3, nut: 2 }, "untouched items keep their counts");
assert.deepEqual(drawStock({ nut: 0 }, []), { nut: 0 }, "an empty order changes nothing");
const pantry = { bolt: 5 };
drawStock(pantry, [["bolt", 5]]);
assert.deepEqual(pantry, { bolt: 5 }, "the shelf passed in is never modified");
assert.throws(() => drawStock({ bolt: -1 }, []), Error, "a negative shelf count is rejected");
assert.throws(() => drawStock({ bolt: 1.5 }, []), Error, "a fractional shelf count is rejected");
assert.throws(() => drawStock({ bolt: 4 }, "bolt"), Error, "a non-list order is rejected");
assert.throws(() => drawStock({ bolt: 4 }, [["washer", 1]]), Error, "an item the shelf lacks is rejected");
assert.throws(() => drawStock({ bolt: 4 }, [["bolt", 0]]), Error, "a zero line count is rejected");
assert.throws(() => drawStock({ bolt: 4 }, [["bolt", 3], ["bolt", 2]]), Error, "pulling past the remainder is rejected");
console.log("ok");
