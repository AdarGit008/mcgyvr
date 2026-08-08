import assert from "node:assert/strict";
import { processStockMoves } from "./solution.ts";

assert.deepEqual(
  processStockMoves([]),
  { levels: {}, refused: [] },
  "empty input",
);
assert.deepEqual(
  processStockMoves([
    { op: "receive", item: "bolt", qty: 5 },
    { op: "issue", item: "bolt", qty: 2 },
  ]),
  { levels: { bolt: 3 }, refused: [] },
  "receive then issue",
);
assert.deepEqual(
  processStockMoves([{ op: "issue", item: "nut", qty: 1 }]),
  { levels: {}, refused: [[0, "unknown_item"]] },
  "issuing an unseen item is refused and creates nothing",
);
assert.deepEqual(
  processStockMoves([
    { op: "receive", item: "cog", qty: 2 },
    { op: "issue", item: "cog", qty: 5 },
    { op: "issue", item: "cog", qty: 2 },
  ]),
  { levels: { cog: 0 }, refused: [[1, "short"]] },
  "a short issue is skipped, later moves still apply",
);
assert.deepEqual(
  processStockMoves([
    { op: "recount", item: "pin", qty: 0 },
    { op: "receive", item: "pin", qty: 4 },
    { op: "recount", item: "pin", qty: 1 },
  ]),
  { levels: { pin: 1 }, refused: [] },
  "recount creates and overwrites",
);
assert.deepEqual(
  processStockMoves([
    { op: "receive", item: "rod", qty: 1 },
    { op: "issue", item: "wire", qty: 1 },
    { op: "issue", item: "rod", qty: 3 },
    { op: "issue", item: "rod", qty: 1 },
  ]),
  { levels: { rod: 0 }, refused: [[1, "unknown_item"], [2, "short"]] },
  "refusal indices and order, zero level still listed",
);
assert.throws(
  () => processStockMoves([{ op: "ship", item: "a", qty: 1 }]),
  Error,
  "unknown op is rejected",
);
assert.throws(
  () => processStockMoves([{ op: "receive", item: "", qty: 1 }]),
  Error,
  "empty item is rejected",
);
assert.throws(
  () => processStockMoves([{ op: "receive", item: "a", qty: "3" }]),
  Error,
  "non-integer qty is rejected",
);
assert.throws(
  () => processStockMoves([{ op: "issue", item: "a", qty: 0 }]),
  Error,
  "issue qty below 1 is rejected",
);
assert.throws(
  () => processStockMoves([{ op: "recount", item: "a", qty: -1 }]),
  Error,
  "recount below 0 is rejected",
);
assert.throws(
  () => processStockMoves([{ op: "receive", item: "a", qty: 1.5 }]),
  Error,
  "fractional qty is rejected",
);
console.log("ok");
