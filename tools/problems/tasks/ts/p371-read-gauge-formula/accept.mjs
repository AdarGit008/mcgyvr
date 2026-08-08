import assert from "node:assert/strict";
import { readGaugeFormula } from "./solution.ts";

const BOOK = {
  span: "12 flit",
  tick: "3 mor",
  pace: "4 flit*mor^-1",
  drift: "5",
  odd: "7 flit",
  back: "-6 flit",
  nil: "0",
  mix: "2 zed*ark^2",
};

assert.equal(readGaugeFormula(BOOK, "span"), "12 flit", "a lone label reads back");
assert.equal(
  readGaugeFormula(BOOK, "span/tick"),
  "4 flit*mor^-1",
  "dividing turns the divisor's exponent negative",
);
assert.equal(
  readGaugeFormula(BOOK, "pace*tick"),
  "12 flit",
  "a name whose exponent reaches zero disappears",
);
assert.equal(
  readGaugeFormula(BOOK, "span+odd"),
  "19 flit",
  "like quantities add",
);
assert.equal(
  readGaugeFormula(BOOK, "drift*drift"),
  "25",
  "a quantity with no units is written bare",
);
assert.equal(
  readGaugeFormula(BOOK, "mix"),
  "2 ark^2*zed",
  "names come out in rising alphabetical order, exponent one written bare",
);
assert.equal(
  readGaugeFormula(BOOK, "span/tick+pace"),
  "8 flit*mor^-1",
  "products are worked out before the plus signs join them",
);
assert.equal(
  readGaugeFormula(BOOK, "span+back"),
  "6 flit",
  "a negative number in the table subtracts",
);
assert.equal(
  readGaugeFormula(BOOK, "span+back+back"),
  "0 flit",
  "a result of nothing still carries its units",
);
assert.equal(
  readGaugeFormula(BOOK, "pace*pace"),
  "16 flit^2*mor^-2",
  "squaring doubles every exponent",
);

function rejects(table, formula) {
  try {
    readGaugeFormula(table, formula);
  } catch (error) {
    return error instanceof Error;
  }
  return false;
}

assert.ok(
  rejects(BOOK, "span/drift"),
  "a division that does not come out whole is rejected",
);
assert.ok(rejects(BOOK, "span/nil"), "dividing by nothing is rejected");
assert.ok(rejects(BOOK, "span+tick"), "adding unlike quantities is rejected");
assert.ok(rejects(BOOK, "span*"), "a trailing operator is rejected");
assert.ok(rejects(BOOK, "*span"), "a leading operator is rejected");
assert.ok(rejects(BOOK, "span**tick"), "a doubled operator is rejected");
assert.ok(rejects(BOOK, "span+"), "a trailing plus is rejected");
assert.ok(rejects(BOOK, ""), "an empty formula is rejected");
assert.ok(rejects(BOOK, "ghost"), "an unknown label is rejected");
assert.ok(rejects(BOOK, "Span"), "a label outside the small letters is rejected");
assert.ok(rejects(BOOK, 7), "a formula that is not a string is rejected");
assert.ok(
  rejects({ ...BOOK, bad: "12 flit^0" }, "span"),
  "a zero exponent anywhere in the table is rejected",
);
assert.ok(
  rejects({ ...BOOK, bad: "12 flit*flit" }, "span"),
  "a unit name written twice in one quantity is rejected",
);
assert.ok(
  rejects({ ...BOOK, bad: "1.5 flit" }, "span"),
  "a quantity that is not a whole number is rejected",
);
assert.ok(
  rejects({ ...BOOK, bad: "12 flit^+2" }, "span"),
  "an exponent carrying a plus sign is rejected",
);
assert.ok(
  rejects({ Bad: "12 flit" }, "span"),
  "a table label outside the small letters is rejected",
);
assert.ok(rejects("book", "span"), "a table that is not a mapping is rejected");
console.log("ok");
