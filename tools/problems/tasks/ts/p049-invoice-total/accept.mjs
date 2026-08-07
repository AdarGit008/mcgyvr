import assert from "node:assert/strict";
import { invoiceTotal } from "./solution.ts";

assert.deepEqual(
  invoiceTotal([{ qty: 2, unit: 500, discount: 0 }], 0),
  { subtotal: 1000, tax: 0, total: 1000 },
  "no discount and no tax is plain multiplication",
);
assert.deepEqual(
  invoiceTotal([{ qty: 1, unit: 999, discount: 250 }], 0),
  { subtotal: 974, tax: 0, total: 974 },
  "24.975 cents of rebate round half up to 25",
);
assert.equal(
  invoiceTotal(
    [
      { qty: 1, unit: 5, discount: 1000 },
      { qty: 1, unit: 5, discount: 1000 },
    ],
    0,
  ).subtotal,
  8,
  "per-line rounding: two nets of 4, not a pooled 9",
);
assert.equal(
  invoiceTotal([{ qty: 1, unit: 2, discount: 2500 }], 0).subtotal,
  1,
  "an exact half cent of rebate rounds up",
);
assert.deepEqual(
  invoiceTotal([{ qty: 3, unit: 1, discount: 0 }], 1667),
  { subtotal: 3, tax: 1, total: 4 },
  "tax of 0.5001 cents rounds half up to 1",
);
assert.deepEqual(
  invoiceTotal([{ qty: 1, unit: 2, discount: 0 }], 2500),
  { subtotal: 2, tax: 1, total: 3 },
  "an exact half cent of tax rounds up",
);
assert.equal(
  invoiceTotal([{ qty: 4, unit: 250, discount: 10000 }], 5000).total,
  0,
  "a full discount leaves nothing to tax",
);
assert.deepEqual(
  invoiceTotal(
    [
      { qty: 2, unit: 1050, discount: 0 },
      { qty: 1, unit: 333, discount: 3333 },
    ],
    825,
  ),
  { subtotal: 2322, tax: 192, total: 2514 },
  "a mixed invoice totals correctly end to end",
);
assert.throws(() => invoiceTotal([], 0), Error, "an empty invoice is rejected");
assert.throws(
  () => invoiceTotal([{ qty: 0, unit: 100, discount: 0 }], 0),
  Error,
  "zero qty is rejected",
);
assert.throws(
  () => invoiceTotal([{ qty: 1, unit: -5, discount: 0 }], 0),
  Error,
  "negative unit price is rejected",
);
assert.throws(
  () => invoiceTotal([{ qty: 1, unit: 100, discount: 10001 }], 0),
  Error,
  "discount above 10000 basis points is rejected",
);
assert.throws(
  () => invoiceTotal([{ qty: 1, unit: 100, discount: 0 }], -1),
  Error,
  "negative tax rate is rejected",
);
assert.throws(
  () => invoiceTotal([{ qty: 1.5, unit: 100, discount: 0 }], 0),
  Error,
  "fractional qty is rejected",
);
console.log("ok");
