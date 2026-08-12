import assert from "node:assert/strict";
import { doseTotals } from "./solution.ts";

assert.deepEqual(doseTotals([["saline", "1.25"], ["saline", "2.75"]]), { saline: "4.00" }, "matching places are kept");
assert.deepEqual(doseTotals([["dye", "0.5"], ["dye", "0.25"]]), { dye: "0.75" }, "the finest pour sets the printed places");
assert.deepEqual(doseTotals([["agar", "3"], ["agar", "4"]]), { agar: "7" }, "whole pours print without a point");
assert.deepEqual(doseTotals([["stock", "-1.5"], ["stock", "0.25"]]), { stock: "-1.25" }, "a drawdown may leave the total negative");
assert.deepEqual(doseTotals([["buffer", "0.1"], ["buffer", "0.2"]]), { buffer: "0.3" }, "tenths add without drift");
assert.deepEqual(doseTotals([]), {}, "an empty log totals nothing");
assert.throws(() => doseTotals([["dye", "1.2345"]]), Error, "an amount finer than a thousandth is rejected");
console.log("ok");
