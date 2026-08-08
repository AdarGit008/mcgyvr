import assert from "node:assert/strict";
import { chooseUpgrades } from "./solution.ts";

const req = (installed, offers, rules) => ({ installed, offers, rules });
const rule = (name, min, max) => ({ package: name, min, max });
const move = (name, to, action) => ({ package: name, to, action });
const snag = (name, why) => ({ package: name, why });

assert.deepEqual(
  chooseUpgrades(req({ a: "1.4" }, { a: ["1.4", "1.6", "2.0"] }, [rule("a", "1.0", "1.9")])),
  { moves: [move("a", "1.4", "hold")], snags: [] },
  "a permitted release running today stays put"
);
assert.deepEqual(
  chooseUpgrades(req({ a: "1.4" }, { a: ["1.4", "1.6", "2.0"] }, [rule("a", "1.5", "2.5")])),
  { moves: [move("a", "1.6", "lift")], snags: [] },
  "a lift takes the lowest permitted release above today"
);
assert.deepEqual(
  chooseUpgrades(req({}, { b: ["2.0", "2.4"] }, [rule("b", "2.0", "3.0")])),
  { moves: [move("b", "2.0", "fetch")], snags: [] },
  "a library running nothing takes the lowest permitted release"
);
assert.deepEqual(
  chooseUpgrades(req({ c: "5.0" }, { c: ["1.0", "2.0", "5.0"] }, [rule("c", "1.0", "2.0")])),
  { moves: [], snags: [snag("c", "drop")] },
  "permitted releases all below today are a drop"
);
assert.deepEqual(
  chooseUpgrades(req({ d: "1.0" }, { d: ["1.0"] }, [rule("d", "3.0", "4.0")])),
  { moves: [], snags: [snag("d", "none")] },
  "no permitted release at all is none"
);
assert.deepEqual(
  chooseUpgrades(
    req({ e: "1.0" }, { e: ["1.0", "1.5", "2.0"] }, [
      rule("e", "1.0", "2.0"),
      rule("e", "1.5", "3.0"),
    ])
  ),
  { moves: [move("e", "1.5", "lift")], snags: [] },
  "every rule on a library must be cleared"
);
assert.deepEqual(
  chooseUpgrades(req({ f: "9.0" }, { f: ["9.0", "10.0"] }, [rule("f", "9.0", "10.0")])),
  { moves: [move("f", "9.0", "hold")], snags: [] },
  "the first group orders as a number"
);
assert.deepEqual(
  chooseUpgrades(req({}, { g: ["1.2", "1.10"] }, [rule("g", "1.0", "1.20")])),
  { moves: [move("g", "1.2", "fetch")], snags: [] },
  "the second group orders as a number too"
);
assert.deepEqual(
  chooseUpgrades(
    req({ h: "1.0", z: "9.9" }, { h: ["1.0", "1.1"], z: ["9.9"] }, [
      rule("h", "1.0", "1.5"),
    ])
  ),
  { moves: [move("h", "1.0", "hold")], snags: [] },
  "an unruled library is reported nowhere"
);
assert.deepEqual(
  chooseUpgrades(
    req({}, { b: ["1.0"], a: ["1.0"], y: ["1.0"], x: ["5.0"] }, [
      rule("b", "1.0", "2.0"),
      rule("y", "9.0", "9.9"),
      rule("a", "1.0", "2.0"),
      rule("x", "9.0", "9.9"),
    ])
  ),
  {
    moves: [move("a", "1.0", "fetch"), move("b", "1.0", "fetch")],
    snags: [snag("x", "none"), snag("y", "none")],
  },
  "both reports run in ascending library order"
);
assert.deepEqual(
  chooseUpgrades(req({ a: "1.0" }, { a: ["1.0"] }, [])),
  { moves: [], snags: [] },
  "no rules, nothing to report"
);

assert.throws(() => chooseUpgrades([1, 2]), Error, "a request that is not a mapping is rejected");
assert.throws(
  () => chooseUpgrades({ installed: [], offers: {}, rules: [] }),
  Error,
  "installed that is not a mapping is rejected"
);
assert.throws(
  () => chooseUpgrades({ installed: {}, offers: [], rules: [] }),
  Error,
  "offers that is not a mapping is rejected"
);
assert.throws(
  () => chooseUpgrades({ installed: {}, offers: {}, rules: {} }),
  Error,
  "rules that is not a list is rejected"
);
assert.throws(
  () => chooseUpgrades(req({}, { a: ["1.0"] }, ["a"])),
  Error,
  "a rule that is not a mapping is rejected"
);
assert.throws(
  () => chooseUpgrades(req({}, { a: ["1.0"] }, [rule("q", "1.0", "2.0")])),
  Error,
  "a rule on an uncarried library is rejected"
);
assert.throws(
  () => chooseUpgrades(req({}, { a: ["1.0"] }, [rule("a", "2.0", "1.0")])),
  Error,
  "a min above its max is rejected"
);
assert.throws(
  () => chooseUpgrades(req({ q: "1.0" }, { a: ["1.0"] }, [])),
  Error,
  "a library running today that is not carried is rejected"
);
assert.throws(
  () => chooseUpgrades(req({}, { a: [] }, [])),
  Error,
  "an empty offers entry is rejected"
);
assert.throws(
  () => chooseUpgrades(req({}, { a: ["1.0", "1.0"] }, [])),
  Error,
  "a repeated release is rejected"
);
assert.throws(
  () => chooseUpgrades(req({}, { a: ["1"] }, [])),
  Error,
  "a release of one group is rejected"
);
assert.throws(
  () => chooseUpgrades(req({}, { a: ["1.0.0"] }, [])),
  Error,
  "a release of three groups is rejected"
);
assert.throws(
  () => chooseUpgrades(req({}, { a: ["01.2"] }, [])),
  Error,
  "a leading zero is rejected"
);

console.log("ok");
