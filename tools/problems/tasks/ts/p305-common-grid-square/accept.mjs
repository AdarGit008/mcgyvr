import assert from "node:assert/strict";
import { commonGridSquare } from "./solution.ts";

assert.equal(
  commonGridSquare(["KM1234"]),
  "KM1234",
  "a lone reference already is its own tightest box",
);
assert.equal(
  commonGridSquare(["KM1234", "KM1234"]),
  "KM1234",
  "the same box twice does not loosen anything",
);
assert.equal(
  commonGridSquare(["KM1234", "KM1235"]),
  "KM13",
  "neighbours to the north slacken by one figure",
);
assert.equal(
  commonGridSquare(["KM1234", "KM1256"]),
  "KM",
  "boxes far apart inside the square fall back to the bare capitals",
);
assert.equal(
  commonGridSquare(["KM12", "KM1234"]),
  "KM",
  "a coarse entry caps how tight the answer may be",
);
assert.equal(
  commonGridSquare(["KM", "KM1234"]),
  "KM",
  "the coarsest entry is a whole square",
);
assert.equal(
  commonGridSquare(["KM123456", "KM123457"]),
  "KM1245",
  "a three-figure pair slackens to two",
);
assert.equal(
  commonGridSquare(["AB012345", "AB012346"]),
  "AB0134",
  "the answer keeps its leading nought",
);
assert.equal(
  commonGridSquare(["AA0000", "AA0001"]),
  "AA00",
  "the origin corner slackens to a tenth of the square",
);
assert.equal(
  commonGridSquare(["AA", "BA"]),
  "",
  "capitals that disagree leave nothing to hand back",
);
assert.equal(
  commonGridSquare(["AA9999999999", "BB0000000000"]),
  "",
  "diagonal neighbours in different squares share no box",
);
assert.throws(
  () => commonGridSquare("KM1234"),
  Error,
  "a bare string is not a list",
);
assert.throws(() => commonGridSquare([]), Error, "an empty list is rejected");
assert.throws(
  () => commonGridSquare(["KM1234", 12]),
  Error,
  "a number among the references is rejected",
);
assert.throws(
  () => commonGridSquare(["KM1234", "IA12"]),
  Error,
  "a struck-out capital is rejected",
);
assert.throws(
  () => commonGridSquare(["KM1234", "KM123"]),
  Error,
  "an odd tally of figures is rejected",
);
assert.throws(
  () => commonGridSquare(["KM123456789012"]),
  Error,
  "twelve figures overshoot the projection",
);
console.log("ok");
