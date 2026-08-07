import assert from "node:assert/strict";
import { crossRestingOrders } from "./solution.ts";

const order = (tag, side, price, size) => ({ tag, side, price, size });

assert.deepEqual(
  crossRestingOrders([order("r1", "ask", 105, 5)], order("n1", "bid", 100, 3)),
  {
    trades: [],
    book: [order("n1", "bid", 100, 3), order("r1", "ask", 105, 5)],
  },
  "an order that cannot reach the far side simply rests",
);

assert.deepEqual(
  crossRestingOrders([], order("solo", "ask", 7, 2)),
  { trades: [], book: [order("solo", "ask", 7, 2)] },
  "an empty book takes the arriving order whole",
);

assert.deepEqual(
  crossRestingOrders(
    [
      order("a1", "ask", 103, 2),
      order("a2", "ask", 101, 4),
      order("a3", "ask", 101, 1),
    ],
    order("n1", "bid", 103, 6),
  ),
  {
    trades: [
      { maker: "a2", price: 101, size: 4 },
      { maker: "a3", price: 101, size: 1 },
      { maker: "a1", price: 103, size: 1 },
    ],
    book: [order("a1", "ask", 103, 1)],
  },
  "cheapest ask first, then the older of the two at one price",
);

assert.deepEqual(
  crossRestingOrders([order("a1", "ask", 50, 2)], order("n1", "bid", 60, 5)),
  {
    trades: [{ maker: "a1", price: 50, size: 2 }],
    book: [order("n1", "bid", 60, 3)],
  },
  "the trade happens at the maker's price and the rest rests",
);

assert.deepEqual(
  crossRestingOrders(
    [order("b1", "bid", 90, 3), order("b2", "bid", 95, 2)],
    order("n1", "ask", 90, 4),
  ),
  {
    trades: [
      { maker: "b2", price: 95, size: 2 },
      { maker: "b1", price: 90, size: 2 },
    ],
    book: [order("b1", "bid", 90, 1)],
  },
  "an arriving ask works the dearest bid down",
);

assert.deepEqual(
  crossRestingOrders(
    [order("b1", "bid", 40, 1), order("b2", "bid", 40, 1)],
    order("n1", "ask", 40, 1),
  ),
  {
    trades: [{ maker: "b1", price: 40, size: 1 }],
    book: [order("b2", "bid", 40, 1)],
  },
  "at one price the older resting order trades first",
);

assert.deepEqual(
  crossRestingOrders(
    [
      order("a1", "ask", 20, 1),
      order("b1", "bid", 11, 1),
      order("a2", "ask", 18, 1),
      order("b2", "bid", 12, 1),
    ],
    order("n1", "bid", 12, 1),
  ),
  {
    trades: [],
    book: [
      order("b2", "bid", 12, 1),
      order("n1", "bid", 12, 1),
      order("b1", "bid", 11, 1),
      order("a2", "ask", 18, 1),
      order("a1", "ask", 20, 1),
    ],
  },
  "the surviving book is sorted by side, then keenness, then age",
);

assert.throws(
  () => crossRestingOrders([], order("n1", "buy", 5, 1)),
  Error,
  "a side outside bid and ask is rejected",
);
assert.throws(
  () => crossRestingOrders([], order("n1", "bid", 5, 0)),
  Error,
  "a size of zero is rejected",
);
assert.throws(
  () => crossRestingOrders([], order("n1", "bid", 5.5, 1)),
  Error,
  "a fractional price is rejected",
);
assert.throws(
  () => crossRestingOrders([], order("", "bid", 5, 1)),
  Error,
  "an empty tag is rejected",
);
assert.throws(
  () =>
    crossRestingOrders(
      [order("dup", "bid", 5, 1), order("dup", "bid", 4, 1)],
      order("n1", "ask", 9, 1),
    ),
  Error,
  "two resting orders sharing a tag are rejected",
);
assert.throws(
  () => crossRestingOrders([order("n1", "bid", 5, 1)], order("n1", "ask", 9, 1)),
  Error,
  "an arriving tag that already rests is rejected",
);
assert.throws(
  () =>
    crossRestingOrders(
      [order("b1", "bid", 100, 1), order("a1", "ask", 99, 1)],
      order("n1", "bid", 50, 1),
    ),
  Error,
  "a book that already crosses is rejected",
);
assert.throws(
  () => crossRestingOrders("no", order("n1", "bid", 5, 1)),
  Error,
  "a book that is not a list is rejected",
);
console.log("ok");
