import assert from "node:assert/strict";
import { readBlazonLine } from "./solution.ts";

assert.deepEqual(
  readBlazonLine("azure"),
  { field: { cut: "plain", tinctures: ["azure"] }, charges: [] },
  "a bare tincture is a plain field with no charges",
);

assert.deepEqual(
  readBlazonLine("or; a lion gules"),
  {
    field: { cut: "plain", tinctures: ["or"] },
    charges: [{ count: 1, charge: "lion", tincture: "gules" }],
  },
  "one charge on a plain field",
);

assert.deepEqual(
  readBlazonLine("parted pale argent and gules; three mullets sable"),
  {
    field: { cut: "pale", tinctures: ["argent", "gules"] },
    charges: [{ count: 3, charge: "mullet", tincture: "sable" }],
  },
  "a parted field keeps its tinctures in written order",
);

assert.deepEqual(
  readBlazonLine("parted fess sable and or; five crescents argent"),
  {
    field: { cut: "fess", tinctures: ["sable", "or"] },
    charges: [{ count: 5, charge: "crescent", tincture: "argent" }],
  },
  "fess division and the largest count",
);

assert.deepEqual(
  readBlazonLine("vert; two roses argent; a bend or"),
  {
    field: { cut: "plain", tinctures: ["vert"] },
    charges: [
      { count: 2, charge: "rose", tincture: "argent" },
      { count: 1, charge: "bend", tincture: "or" },
    ],
  },
  "two charge clauses keep their order",
);

assert.deepEqual(
  readBlazonLine("purpure; four bends or"),
  {
    field: { cut: "plain", tinctures: ["purpure"] },
    charges: [{ count: 4, charge: "bend", tincture: "or" }],
  },
  "the bare word is reported, not the plural",
);

assert.throws(() => readBlazonLine(""), Error, "an empty line is refused");
assert.throws(() => readBlazonLine(17), Error, "a non-string is refused");
assert.throws(() => readBlazonLine("beige"), Error, "an unknown tincture is refused");
assert.throws(
  () => readBlazonLine("parted pale or and or"),
  Error,
  "a parted field of one tincture is refused",
);
assert.throws(
  () => readBlazonLine("parted pale or"),
  Error,
  "a truncated field clause is refused",
);
assert.throws(
  () => readBlazonLine("parted bend or and gules"),
  Error,
  "an unknown division is refused",
);
assert.throws(
  () => readBlazonLine("azure; a lions gules"),
  Error,
  "a plural word with a count of one is refused",
);
assert.throws(
  () => readBlazonLine("azure; two rose gules"),
  Error,
  "a bare word with a count above one is refused",
);
assert.throws(
  () => readBlazonLine("azure; six lions or"),
  Error,
  "an unknown count is refused",
);
assert.throws(
  () => readBlazonLine("azure; a dragon gules"),
  Error,
  "an unknown charge word is refused",
);
assert.throws(
  () => readBlazonLine("azure; a lion"),
  Error,
  "a two-word charge clause is refused",
);
assert.throws(
  () => readBlazonLine("azure; a lion gules; two lions or"),
  Error,
  "a charge word named twice is refused",
);
assert.throws(
  () => readBlazonLine("azure; "),
  Error,
  "an empty clause is refused",
);
console.log("ok");
