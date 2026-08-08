import assert from "node:assert/strict";
import { auditShieldContrast } from "./solution.ts";

const keep = {
  label: "keep",
  field: ["azure"],
  charges: [
    { figure: "lion", tincture: "or" },
    { figure: "bend", tincture: "gules" },
  ],
};
const gate = {
  label: "gate",
  field: ["argent"],
  charges: [{ figure: "rose", tincture: "gules" }],
};
const tower = {
  label: "tower",
  field: ["or", "gules"],
  charges: [
    { figure: "mullet", tincture: "argent" },
    { figure: "crescent", tincture: "or" },
  ],
};
const ward = {
  label: "ward",
  field: ["azure", "sable"],
  charges: [{ figure: "lion", tincture: "vert" }],
};
const vane = {
  label: "vane",
  field: ["or", "argent"],
  charges: [
    { figure: "bend", tincture: "purpure" },
    { figure: "rose", tincture: "argent" },
  ],
};

assert.deepEqual(
  auditShieldContrast([keep]),
  [{ label: "keep", unsound: ["bend"] }],
  "colour on a colour field is unsound",
);
assert.deepEqual(auditShieldContrast([gate]), [], "a wholly sound shield is left out");
assert.deepEqual(
  auditShieldContrast([tower]),
  [{ label: "tower", unsound: ["crescent"] }],
  "a tincture shared with a half is unsound even where the classes differ",
);
assert.deepEqual(
  auditShieldContrast([ward]),
  [{ label: "ward", unsound: ["lion"] }],
  "two colour halves contrast with no colour figure",
);
assert.deepEqual(
  auditShieldContrast([vane]),
  [{ label: "vane", unsound: ["rose"] }],
  "two metal halves still admit a colour figure",
);
assert.deepEqual(
  auditShieldContrast([gate, keep, tower]),
  [
    { label: "keep", unsound: ["bend"] },
    { label: "tower", unsound: ["crescent"] },
  ],
  "the surviving shields keep the order they arrived in",
);
assert.deepEqual(
  auditShieldContrast([{ label: "bare", field: ["vert"], charges: [] }]),
  [],
  "a shield bearing nothing reports nothing",
);
assert.deepEqual(auditShieldContrast([]), [], "an empty roll of shields is empty");

assert.throws(() => auditShieldContrast(5), Error, "a non-list is refused");
assert.throws(
  () => auditShieldContrast([{ label: "", field: ["vert"], charges: [] }]),
  Error,
  "an empty label is refused",
);
assert.throws(
  () => auditShieldContrast([keep, { ...keep }]),
  Error,
  "a repeated label is refused",
);
assert.throws(
  () => auditShieldContrast([{ label: "void", field: [], charges: [] }]),
  Error,
  "a field of no tinctures is refused",
);
assert.throws(
  () =>
    auditShieldContrast([
      { label: "third", field: ["or", "vert", "sable"], charges: [] },
    ]),
  Error,
  "a field of three tinctures is refused",
);
assert.throws(
  () => auditShieldContrast([{ label: "odd", field: ["beige"], charges: [] }]),
  Error,
  "an unknown field tincture is refused",
);
assert.throws(
  () =>
    auditShieldContrast([
      { label: "odd", field: ["vert"], charges: [{ figure: "lion", tincture: "puce" }] },
    ]),
  Error,
  "an unknown figure tincture is refused",
);
assert.throws(
  () =>
    auditShieldContrast([
      {
        label: "twice",
        field: ["vert"],
        charges: [
          { figure: "lion", tincture: "or" },
          { figure: "lion", tincture: "argent" },
        ],
      },
    ]),
  Error,
  "the same figure borne twice is refused",
);
console.log("ok");
