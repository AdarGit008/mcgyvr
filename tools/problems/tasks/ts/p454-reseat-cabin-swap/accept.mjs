import assert from "node:assert/strict";
import { reseatCabin } from "./solution.ts";

const h = (name, seat, want) => ({ name, seat, want });
const wide = { rows: 3, left: "AB", right: "CD", blocked: [] };

assert.deepEqual(
  reseatCabin([h("ann", "1A", "window"), h("bob", "2C", "aisle")], wide),
  { seated: ["ann 1A kept", "bob 2C kept"], bumped: [] },
  "a seat the swap leaves standing is kept",
);
assert.deepEqual(
  reseatCabin([h("ann", "4A", "window"), h("bob", "4B", "any")], { rows: 1, left: "AB", right: "CD", blocked: [] }),
  { seated: ["ann 1A moved", "bob 1B moved"], bumped: [] },
  "rows the smaller cabin does not have send their holders forward",
);
assert.deepEqual(
  reseatCabin([h("ann", "1A", "window")], { rows: 2, left: "AB", right: "CD", blocked: ["1A"] }),
  { seated: ["ann 1D moved"], bumped: [] },
  "a barred old seat is not kept and the search stays in the row it can",
);
assert.deepEqual(
  reseatCabin([h("ann", "1A", "any"), h("bob", "1B", "any"), h("cid", "1C", "any")], {
    rows: 1,
    left: "A",
    right: "B",
    blocked: [],
  }),
  { seated: ["ann 1A kept", "bob 1B kept"], bumped: ["cid"] },
  "a holder left with no seat at all is bumped",
);
assert.deepEqual(
  reseatCabin([h("zed", "2D", "window"), h("ann", "1D", "window")], {
    rows: 2,
    left: "AB",
    right: "CD",
    blocked: ["1A", "1D", "2A", "2D"],
  }),
  { seated: ["ann 1B shifted", "zed 1C shifted"], bumped: [] },
  "service runs by old seat, not by the order the holders were listed",
);
assert.deepEqual(
  reseatCabin([h("ann", "9A", "aisle")], { rows: 1, left: "AB", right: "CD", blocked: ["1B", "1C"] }),
  { seated: ["ann 1A shifted"], bumped: [] },
  "a wish that cannot be met anywhere still gets a seat, marked shifted",
);
assert.deepEqual(
  reseatCabin([h("xan", "9Y", "window"), h("yin", "9Z", "aisle")], { rows: 1, left: "A", right: "BC", blocked: [] }),
  { seated: ["xan 1A moved", "yin 1B moved"], bumped: [] },
  "a lone letter on one side counts as both a window and an aisle",
);
assert.deepEqual(
  reseatCabin([h("ann", "1B", "window")], wide),
  { seated: ["ann 1B kept"], bumped: [] },
  "keeping the old seat outranks the wish",
);
assert.deepEqual(
  reseatCabin([h("ann", "9X", "window"), h("bob", "9Y", "window")], {
    rows: 3,
    left: "AB",
    right: "CD",
    blocked: ["1A", "1D", "2A", "2D"],
  }),
  { seated: ["ann 3A moved", "bob 3D moved"], bumped: [] },
  "the search spills into later rows when the early ones are barred",
);
assert.deepEqual(reseatCabin([], wide), { seated: [], bumped: [] }, "nobody aboard seats nobody");
assert.deepEqual(
  reseatCabin(
    [h("ann", "1A", "window"), h("bob", "1B", "aisle"), h("cid", "1C", "aisle"), h("dot", "1D", "window"), h("eve", "2A", "any")],
    { rows: 2, left: "AB", right: "CD", blocked: ["1A", "2A"] },
  ),
  { seated: ["ann 1D moved", "bob 1B kept", "cid 1C kept", "dot 2D moved", "eve 2B moved"], bumped: [] },
  "a displaced holder can take the seat a later holder was counting on",
);

assert.throws(() => reseatCabin("no", wide), Error, "holders that are not a list are refused");
assert.throws(() => reseatCabin([], null), Error, "a cabin that is not a record is refused");
assert.throws(() => reseatCabin([], { rows: 0, left: "A", right: "B", blocked: [] }), Error, "nought rows is refused");
assert.throws(() => reseatCabin([], { rows: 1, left: "a", right: "B", blocked: [] }), Error, "a small letter is refused");
assert.throws(() => reseatCabin([], { rows: 1, left: "", right: "B", blocked: [] }), Error, "an empty side is refused");
assert.throws(() => reseatCabin([], { rows: 1, left: "AB", right: "BC", blocked: [] }), Error, "a repeated letter is refused");
assert.throws(() => reseatCabin([], { rows: 1, left: "A", right: "B", blocked: "1A" }), Error, "blocked that is not a list is refused");
assert.throws(() => reseatCabin([], { rows: 1, left: "A", right: "B", blocked: ["A1"] }), Error, "a malformed barred seat is refused");
assert.throws(() => reseatCabin([], { rows: 1, left: "A", right: "B", blocked: ["9A"] }), Error, "a barred seat outside the cabin is refused");
assert.throws(() => reseatCabin([[1]], wide), Error, "a holder that is not a record is refused");
assert.throws(() => reseatCabin([h("", "1A", "any")], wide), Error, "an empty name is refused");
assert.throws(() => reseatCabin([h("a", "1A", "any"), h("a", "1B", "any")], wide), Error, "one name twice is refused");
assert.throws(() => reseatCabin([h("a", "0A", "any")], wide), Error, "a row of nought in an old seat is refused");
assert.throws(() => reseatCabin([h("a", "1AB", "any")], wide), Error, "two letters in an old seat are refused");
assert.throws(() => reseatCabin([h("a", "1A", "any"), h("b", "1A", "any")], wide), Error, "one old seat twice is refused");
assert.throws(() => reseatCabin([h("a", "1A", "middle")], wide), Error, "an unknown wish is refused");
console.log("ok");
