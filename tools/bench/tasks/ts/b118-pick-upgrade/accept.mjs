import assert from "node:assert/strict";
import { compareBuilds, pickUpgrade } from "./solution.ts";

assert.equal(pickUpgrade("2.1", ["2.4"]), "2.4", "a lone newer offer wins");
assert.equal(
  pickUpgrade("2.1", ["2.9", "2.3", "2.4"]),
  "2.9",
  "the newest qualifying offer wins, not the last",
);
assert.equal(pickUpgrade("2.4", ["2.4"]), null, "the installed build is no upgrade");
assert.equal(
  pickUpgrade("2.3", ["2.3.0"]),
  null,
  "the same build written deeper is no upgrade",
);
assert.equal(
  pickUpgrade("2.9.9", ["2.10"]),
  "2.10",
  "positions compare numerically, not by their characters",
);
assert.equal(
  pickUpgrade("2.1", ["3.5", "1.9"]),
  null,
  "other release lines never qualify",
);
assert.equal(pickUpgrade("2.5", ["2.4", "2.1"]), null, "older offers never qualify");
assert.equal(pickUpgrade("2.1", []), null, "no offers, no upgrade");
assert.equal(
  pickUpgrade("10.2", ["10.2.1", "11.0"]),
  "10.2.1",
  "a two-digit line matches itself only",
);
assert.equal(compareBuilds("1.10", "1.9"), 1, "ten beats nine");
assert.equal(compareBuilds("2.3", "2.3.0"), 0, "a trailing zero changes nothing");
assert.throws(() => pickUpgrade(7, ["1.2"]), Error, "a non-string install is rejected");
assert.throws(() => pickUpgrade("v2.1", ["2.2"]), Error, "a prefixed build is rejected");
assert.throws(() => pickUpgrade("1.4", ["01.2"]), Error, "a leading zero is rejected");
assert.throws(() => pickUpgrade("2.2", "2.3"), Error, "offers must arrive as a list");
console.log("ok");
