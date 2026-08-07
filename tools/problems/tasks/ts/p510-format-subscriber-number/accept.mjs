import assert from "node:assert/strict";
import { formatSubscriberNumber } from "./solution.ts";

assert.equal(
  formatSubscriberNumber("kv", "123456789"),
  "0 123 456 789",
  "kv takes a single-figure stem and three blocks of three",
);
assert.equal(
  formatSubscriberNumber("mr", "12345678"),
  "07 1234 5678",
  "mr takes a two-figure stem and two blocks of four",
);
assert.equal(
  formatSubscriberNumber("ts", "1234567890"),
  "+31 12 3456 7890",
  "ts takes a stem with a plus and blocks of two, four and four",
);
assert.equal(
  formatSubscriberNumber("wd", "1234567"),
  "123 4567",
  "wd carries no stem, so the blocks stand alone",
);
assert.equal(
  formatSubscriberNumber("kv", "900000001"),
  "0 900 000 001",
  "noughts inside the run are printed like any other digit",
);
assert.equal(
  formatSubscriberNumber("wd", "9876543"),
  "987 6543",
  "the shortest region still splits three then four",
);

assert.throws(() => formatSubscriberNumber("zz", "1234567"), Error, "an unknown region");
assert.throws(() => formatSubscriberNumber("KV", "123456789"), Error, "a region in capitals");
assert.throws(() => formatSubscriberNumber(7, "1234567"), Error, "a region must be a string");
assert.throws(() => formatSubscriberNumber("wd", 1234567), Error, "the digits must be a string");
assert.throws(() => formatSubscriberNumber("wd", "123 4567"), Error, "a space inside the run");
assert.throws(() => formatSubscriberNumber("wd", "12-4567"), Error, "a dash inside the run");
assert.throws(() => formatSubscriberNumber("wd", "12345678"), Error, "one digit too many for wd");
assert.throws(() => formatSubscriberNumber("kv", "12345678"), Error, "one digit too few for kv");
assert.throws(() => formatSubscriberNumber("wd", ""), Error, "an empty run");
assert.throws(() => formatSubscriberNumber("wd", "0123456"), Error, "a run opening with a nought");
console.log("ok");
