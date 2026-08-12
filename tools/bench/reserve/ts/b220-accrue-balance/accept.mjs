import assert from "node:assert/strict";
import { accrueBalance } from "./solution.ts";

assert.equal(accrueBalance(100000, 250, 1), 102500, "a period paying whole cents credits them all");
assert.equal(accrueBalance(1, 1, 1), 1, "interest far under a cent leaves the balance alone");
assert.equal(accrueBalance(100, 50, 1), 100, "exactly half a cent stays put on an even balance");
assert.equal(accrueBalance(25, 200, 1), 26, "exactly half a cent buys a cent on an odd balance");
assert.equal(accrueBalance(1000, 125, 3), 1038, "carried remainders compound and finally buy a cent");
assert.equal(accrueBalance(4321, 375, 0), 4321, "no periods leaves the opening balance untouched");
assert.throws(() => accrueBalance(1000, 250, -1), Error, "a negative period count is rejected");
assert.throws(() => accrueBalance(1000, -250, 2), Error, "a negative rate is rejected");
console.log("ok");
