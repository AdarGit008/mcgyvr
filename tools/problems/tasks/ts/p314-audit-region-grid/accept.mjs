import assert from "node:assert/strict";
import { auditRegionGrid } from "./solution.ts";

const shapes = ["AAAB", "CABB", "CCDB", "CDDD"];

assert.equal(
  auditRegionGrid(["1234", "3412", "2143", "4321"], shapes),
  "ok",
  "a sound board under jagged territories",
);
assert.equal(auditRegionGrid(["1"], ["A"]), "ok", "a board of side one");
assert.equal(auditRegionGrid(["12", "21"], ["AB", "AB"]), "ok", "territories as files");
assert.equal(
  auditRegionGrid(["1234", "2143", "3412", "4321"], shapes),
  "territory A",
  "rows and files hold but the first territory does not",
);
assert.equal(
  auditRegionGrid(["1234", "3421", "4312", "2143"], shapes),
  "territory B",
  "the earliest broken territory by letter",
);
assert.equal(
  auditRegionGrid(["1234", "3421", "4311", "2143"], shapes),
  "row 3",
  "a repeated digit in a row outranks anything later",
);
assert.equal(
  auditRegionGrid(["1234", "1234", "3412", "4321"], shapes),
  "file 1",
  "files are tested once every row has held",
);
assert.throws(
  () => auditRegionGrid(["1234", "341", "2143", "4321"], shapes),
  Error,
  "a short row is rejected",
);
assert.throws(
  () => auditRegionGrid(["12", "21"], ["AB"]),
  Error,
  "unequal heights are rejected",
);
assert.throws(
  () => auditRegionGrid(["1235", "3412", "2143", "4321"], shapes),
  Error,
  "a digit above the side is rejected",
);
assert.throws(
  () => auditRegionGrid(["1234", "3412", "2143", "4321"], ["aaab", "CABB", "CCDB", "CDDD"]),
  Error,
  "a lowercase label is rejected",
);
assert.throws(
  () => auditRegionGrid(["1234", "3412", "2143", "4321"], ["AAAA", "BBBB", "CCCC", "CCCC"]),
  Error,
  "three territories on a board of four is rejected",
);
assert.throws(
  () => auditRegionGrid(["1234", "3412", "2143", "4321"], ["AAAA", "AABB", "BBCC", "CCDD"]),
  Error,
  "territories of unequal size are rejected",
);
console.log("ok");
