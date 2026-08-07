import assert from "node:assert/strict";
import { mergeThreeWay } from "./solution.ts";

const base = { host: "a", port: "80", mode: "dev" };

assert.deepEqual(
  mergeThreeWay(base, { host: "a", port: "81", mode: "dev" }, { host: "a", port: "80", mode: "prod" }),
  { merged: { host: "a", mode: "prod", port: "81" }, conflicts: [] },
  "disjoint edits both carry",
);
assert.deepEqual(
  mergeThreeWay(base, { host: "a", port: "81", mode: "dev" }, { host: "a", port: "82", mode: "dev" }),
  { merged: { host: "a", mode: "dev", port: "80" }, conflicts: ["port"] },
  "rival values conflict and the ancestor value stays",
);
assert.deepEqual(
  mergeThreeWay(base, { host: "a", port: "90", mode: "dev" }, { host: "a", port: "90", mode: "dev" }),
  { merged: { host: "a", mode: "dev", port: "90" }, conflicts: [] },
  "the identical edit on both sides is clean",
);
assert.deepEqual(
  mergeThreeWay(base, { port: "80", mode: "dev" }, base),
  { merged: { mode: "dev", port: "80" }, conflicts: [] },
  "a one-sided removal carries",
);
assert.deepEqual(
  mergeThreeWay(base, { port: "80", mode: "dev" }, { host: "b", port: "80", mode: "dev" }),
  { merged: { host: "a", mode: "dev", port: "80" }, conflicts: ["host"] },
  "removal against alteration conflicts and the ancestor entry stays",
);
assert.deepEqual(
  mergeThreeWay(base, { port: "80", mode: "dev" }, { port: "80", mode: "dev" }),
  { merged: { mode: "dev", port: "80" }, conflicts: [] },
  "both sides removing is clean",
);
assert.deepEqual(
  mergeThreeWay({}, { fresh: "x" }, {}),
  { merged: { fresh: "x" }, conflicts: [] },
  "a one-sided addition carries",
);
assert.deepEqual(
  mergeThreeWay({}, { fresh: "x" }, { fresh: "y" }),
  { merged: {}, conflicts: ["fresh"] },
  "rival additions conflict and stay absent",
);
assert.deepEqual(
  mergeThreeWay(
    { z: "1", a: "1" },
    { z: "2", a: "2" },
    { z: "3", a: "3" },
  ),
  { merged: { a: "1", z: "1" }, conflicts: ["a", "z"] },
  "conflicts come out in ascending key order",
);
assert.deepEqual(
  mergeThreeWay(base, base, base),
  { merged: { host: "a", mode: "dev", port: "80" }, conflicts: [] },
  "no edits, no conflicts",
);
assert.throws(() => mergeThreeWay(base, "nope", base), Error, "a non-mapping side is rejected");
assert.throws(() => mergeThreeWay(base, { port: 80 }, base), Error, "a non-string value is rejected");
console.log("ok");
