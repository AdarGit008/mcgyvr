import assert from "node:assert/strict";
import { meterCharges } from "./solution.ts";

assert.deepEqual(meterCharges({ alpha: 10 }, [["alpha", 4]]), { alpha: { used: 4, left: 6, refused: 0 } }, "a cost within the grant is spent");
assert.deepEqual(meterCharges({ alpha: 10 }, [["alpha", 10]]), { alpha: { used: 10, left: 0, refused: 0 } }, "a cost equal to the grant still fits");
assert.deepEqual(meterCharges({ alpha: 10 }, [["alpha", 4], ["alpha", 8]]), { alpha: { used: 4, left: 6, refused: 1 } }, "an oversized cost spends nothing");
assert.deepEqual(meterCharges({ alpha: 10 }, [["alpha", 4], ["alpha", 8], ["alpha", 6]]), { alpha: { used: 10, left: 0, refused: 1 } }, "a smaller cost after a refusal is accepted");
assert.deepEqual(meterCharges({ alpha: 10, beta: 4 }, [["alpha", 1]]), { alpha: { used: 1, left: 9, refused: 0 }, beta: { used: 0, left: 4, refused: 0 } }, "a caller with no activity is still reported");
assert.deepEqual(meterCharges({ alpha: 10 }, [["alpha", 3], ["alpha", -9]]), { alpha: { used: 0, left: 10, refused: 0 } }, "a credit returns no more than was used");
assert.throws(() => meterCharges({ alpha: 10 }, [["gamma", 1]]), Error, "a charge for an ungranted caller is rejected");
console.log("ok");
