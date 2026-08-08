import assert from "node:assert/strict";
import { stackAddressPanel } from "./solution.ts";

const parts = {
  name: "Dela Voss",
  unit: "  Flat 3 ",
  road: "Ember Lane",
  city: "brack",
  pin: "tt-90",
  care: "   ",
};

const plan = [
  { slots: ["name"], fold: "keep", must: true },
  { slots: ["care"], fold: "keep", must: false },
  { slots: ["unit", "road"], fold: "keep", must: true },
  { slots: ["city"], fold: "up", must: true },
  { slots: ["pin"], fold: "up", must: true },
];

assert.deepEqual(
  stackAddressPanel(parts, plan),
  ["Dela Voss", "Flat 3 Ember Lane", "BRACK", "TT-90"],
  "a step with nothing to write and must false is dropped",
);

assert.deepEqual(
  stackAddressPanel(parts, [{ slots: ["care", "road"], fold: "down", must: true }]),
  ["ember lane"],
  "a blank slot is passed over and the rest still writes the line",
);

assert.deepEqual(
  stackAddressPanel(parts, [{ slots: ["unit"], fold: "keep", must: true }]),
  ["Flat 3"],
  "outer blanks go and inner ones stay",
);

assert.deepEqual(
  stackAddressPanel(parts, [
    { slots: ["name", "pin"], fold: "up", must: true },
    { slots: ["name", "pin"], fold: "down", must: true },
  ]),
  ["DELA VOSS TT-90", "dela voss tt-90"],
  "up and down fold the whole joined line",
);

assert.deepEqual(
  stackAddressPanel({ road: 41, city: "Ort" }, [
    { slots: ["road"], fold: "keep", must: false },
    { slots: ["city"], fold: "keep", must: true },
  ]),
  ["Ort"],
  "a slot holding something other than text is passed over",
);

assert.deepEqual(
  stackAddressPanel(parts, [{ slots: ["gone", "care"], fold: "keep", must: false }]),
  [],
  "a panel may end up with no lines at all",
);

assert.throws(
  () => stackAddressPanel(parts, [{ slots: ["care"], fold: "keep", must: true }]),
  Error,
  "a must step that finds nothing is fatal",
);
assert.throws(() => stackAddressPanel("bag", plan), Error, "parts must be a record");
assert.throws(() => stackAddressPanel(parts, []), Error, "an empty plan is rejected");
assert.throws(() => stackAddressPanel(parts, "plan"), Error, "plan must be a list");
assert.throws(() => stackAddressPanel(parts, ["name"]), Error, "a step must be a record");
assert.throws(
  () => stackAddressPanel(parts, [{ slots: [], fold: "keep", must: true }]),
  Error,
  "a step naming no slot is rejected",
);
assert.throws(
  () => stackAddressPanel(parts, [{ slots: ["name", ""], fold: "keep", must: true }]),
  Error,
  "an empty slot name is rejected",
);
assert.throws(
  () => stackAddressPanel(parts, [{ slots: ["name"], fold: "sideways", must: true }]),
  Error,
  "an unknown fold is rejected",
);
assert.throws(
  () => stackAddressPanel(parts, [{ slots: ["name"], fold: "keep", must: "yes" }]),
  Error,
  "must must be a boolean",
);
console.log("ok");
