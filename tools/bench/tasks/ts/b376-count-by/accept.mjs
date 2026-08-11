import assert from "node:assert/strict";
import { countBy } from "./solution.ts";

assert.deepEqual(
  countBy([{ city: "rome" }, { city: "rome" }, { city: "oslo" }], "city"),
  { rome: 2, oslo: 1 },
  "counted by value",
);
assert.deepEqual(countBy([{ city: "rome" }], "town"), {}, "no record holds the field");
assert.deepEqual(countBy([], "city"), {}, "no records at all");
assert.deepEqual(
  countBy([{ city: "rome" }, { town: "oslo" }], "city"),
  { rome: 1 },
  "a record lacking the field is passed over",
);
assert.deepEqual(countBy([{ city: "" }], "city"), { "": 1 }, "an empty value counts");
assert.throws(() => countBy([], ""), Error, "an unnamed field is rejected");
console.log("ok");
