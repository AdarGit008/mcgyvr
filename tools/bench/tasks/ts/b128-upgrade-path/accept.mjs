import assert from "node:assert/strict";
import { vetUpgradePath } from "./solution.ts";

assert.equal(vetUpgradePath("1.4", []), "1.4", "an empty path keeps the installed tag");
assert.equal(
  vetUpgradePath("1.4", [{ tag: "1.5", requires: "1.0" }]),
  "1.5",
  "a single lawful step lands on its tag",
);
assert.equal(
  vetUpgradePath("1.4", [
    { tag: "2.0", requires: "1.4" },
    { tag: "2.1", requires: "2.0" },
  ]),
  "2.1",
  "a chain carries the tag step by step",
);
assert.equal(
  vetUpgradePath("2.9", [{ tag: "2.10", requires: "2.0" }]),
  "2.10",
  "a point release past 9 still climbs",
);
assert.equal(
  vetUpgradePath("9.3", [{ tag: "10.0", requires: "9.0" }]),
  "10.0",
  "a line jump past 9 still climbs",
);
assert.equal(
  vetUpgradePath("3.0", [{ tag: "3.1", requires: "3.0" }]),
  "3.1",
  "a floor met exactly is lawful",
);
assert.equal(
  vetUpgradePath("0.9", [{ tag: "1.0", requires: "0.1" }]),
  "1.0",
  "zero parts read as plain numbers",
);
assert.throws(
  () => vetUpgradePath("10.2", [{ tag: "9.9", requires: "1.0" }]),
  Error,
  "a numeric downgrade is refused",
);
assert.throws(
  () => vetUpgradePath("3.1", [{ tag: "3.1", requires: "3.0" }]),
  Error,
  "a step repeating the carried tag is refused",
);
assert.throws(
  () => vetUpgradePath("1.2", [{ tag: "2.0", requires: "1.5" }]),
  Error,
  "an unmet floor is refused",
);
assert.throws(() => vetUpgradePath(7, []), Error, "a non-string installed tag is rejected");
assert.throws(() => vetUpgradePath("1.0", "nope"), Error, "a non-list path is rejected");
assert.throws(() => vetUpgradePath("1.0", ["2.0"]), Error, "a bare-string step is rejected");
assert.throws(
  () => vetUpgradePath("1.0", [{ tag: "2.0" }]),
  Error,
  "a step without requires is rejected",
);
assert.throws(
  () => vetUpgradePath("1.0", [{ tag: "2.0.1", requires: "1.0" }]),
  Error,
  "three parts are rejected",
);
assert.throws(
  () => vetUpgradePath("1.0", [{ tag: "2.", requires: "1.0" }]),
  Error,
  "an empty part is rejected",
);
assert.throws(
  () => vetUpgradePath("1.0", [{ tag: "2.x", requires: "1.0" }]),
  Error,
  "stray characters are rejected",
);
assert.throws(
  () => vetUpgradePath("1.0", [{ tag: "2.05", requires: "1.0" }]),
  Error,
  "a leading zero is rejected",
);
console.log("ok");
