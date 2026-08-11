import assert from "node:assert/strict";
import { moneyText } from "./solution.ts";

assert.equal(moneyText(1234), "12.34", "pounds and pence");
assert.equal(moneyText(5), "0.05", "under a pound keeps its nought");
assert.equal(moneyText(100), "1.00", "a whole pound shows two noughts");
assert.equal(moneyText(0), "0.00", "nothing at all");
assert.equal(moneyText(99), "0.99", "just under a pound");
assert.equal(moneyText(1000), "10.00", "ten pounds");
console.log("ok");
