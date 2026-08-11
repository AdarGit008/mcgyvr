import assert from "node:assert/strict";
import { pickFields } from "./solution.ts";

assert.deepEqual(
  pickFields(
    [{ name: "ada", role: "pilot" }, { name: "vi", role: "nav" }],
    ["name", "role"],
  ),
  [["ada", "pilot"], ["vi", "nav"]],
  "one row per record in field order",
);
assert.deepEqual(
  pickFields([{ a: 1, b: 2 }], ["b", "a"]),
  [[2, 1]],
  "the field list, not the record, orders the row",
);
assert.deepEqual(
  pickFields([{ name: "ada", nick: "ace" }], ["name", "nick?"]),
  [["ada", "ace"]],
  "a present optional field reads its value",
);
assert.deepEqual(
  pickFields([{ name: "vi" }], ["name", "nick?"]),
  [["vi", null]],
  "an absent optional field reads as null",
);
assert.deepEqual(pickFields([], ["name"]), [], "no records, no rows");
assert.deepEqual(
  pickFields([{ n: 0, s: "" }], ["n", "s"]),
  [[0, ""]],
  "falsy values pass through untouched",
);
assert.throws(() => pickFields("crew", ["name"]), Error, "records must be a list");
assert.throws(() => pickFields([7], ["name"]), Error, "a record must be a mapping");
assert.throws(() => pickFields([], []), Error, "an empty field list is rejected");
assert.throws(() => pickFields([], [7]), Error, "a field name must be a string");
assert.throws(() => pickFields([], ["?"]), Error, "a bare marker has no stem");
assert.throws(() => pickFields([], ["id", "id"]), Error, "a repeated field is rejected");
assert.throws(
  () => pickFields([], ["id", "id?"]),
  Error,
  "optional and required twins share a stem",
);
assert.throws(
  () => pickFields([{ a: 1 }], ["b"]),
  Error,
  "a missing required field is rejected",
);
console.log("ok");
