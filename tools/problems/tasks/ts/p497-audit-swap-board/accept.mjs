import assert from "node:assert/strict";
import { auditSwapBoard } from "./solution.ts";

const shift = (code, day, holder) => ({ code, day, holder });
const claim = (code, bidder) => ({ code, bidder });

const opening = () => [
  shift("m1", 1, "ada"),
  shift("m2", 2, "ada"),
  shift("m3", 1, "ben"),
  shift("m4", 3, "ben"),
  shift("m5", 2, "cleo"),
];

assert.deepEqual(
  auditSwapBoard(
    {
      shifts: opening(),
      claims: [
        claim("m1", "cleo"),
        claim("m3", "cleo"),
        claim("m4", "cleo"),
        claim("m3", "ada"),
        claim("m1", "ben"),
        claim("m5", "ada"),
        claim("m9", "ada"),
        claim("m2", "ada"),
      ],
    },
    2,
  ),
  {
    verdicts: ["taken", "busy", "full", "taken", "gone", "busy", "unknown", "self"],
    loads: ["ada 2", "ben 1", "cleo 2"],
  },
  "every refusal reason over one walk of the board",
);

assert.deepEqual(
  auditSwapBoard({ shifts: opening(), claims: [] }, 3),
  { verdicts: [], loads: ["ada 2", "ben 2", "cleo 1"] },
  "no claims leaves the opening loads",
);

assert.deepEqual(
  auditSwapBoard(
    { shifts: [shift("a", 1, "kim"), shift("b", 2, "lou")], claims: [claim("a", "lou")] },
    1,
  ),
  { verdicts: ["full"], loads: ["kim 1", "lou 1"] },
  "a ceiling of one refuses anybody already holding one",
);

assert.deepEqual(
  auditSwapBoard(
    { shifts: [shift("a", 1, "kim"), shift("b", 2, "lou")], claims: [claim("a", "lou")] },
    2,
  ),
  { verdicts: ["taken"], loads: ["lou 2"] },
  "somebody stripped of every shift drops off the loads",
);

assert.deepEqual(
  auditSwapBoard(
    {
      shifts: [shift("a", 4, "kim"), shift("b", 4, "lou"), shift("c", 6, "kim")],
      claims: [claim("a", "lou"), claim("c", "lou")],
    },
    5,
  ),
  { verdicts: ["busy", "taken"], loads: ["kim 1", "lou 2"] },
  "two shifts on one day cannot land on one person",
);

assert.deepEqual(
  auditSwapBoard(
    {
      shifts: [shift("a", 1, "kim")],
      claims: [claim("a", "lou"), claim("a", "kim")],
    },
    4,
  ),
  { verdicts: ["taken", "gone"], loads: ["lou 1"] },
  "a shift that has moved once will not move again",
);

assert.throws(() => auditSwapBoard("no", 1), Error, "the board must be a record");
assert.throws(
  () => auditSwapBoard({ shifts: [] }, 1),
  Error,
  "a missing board key is refused",
);
assert.throws(
  () => auditSwapBoard({ shifts: "no", claims: [] }, 1),
  Error,
  "shifts must be a list",
);
assert.throws(
  () => auditSwapBoard({ shifts: [{ code: "a", day: 1 }], claims: [] }, 1),
  Error,
  "a shift missing a key is refused",
);
assert.throws(
  () => auditSwapBoard({ shifts: [shift("a", 1, "kim"), shift("a", 2, "lou")], claims: [] }, 1),
  Error,
  "a repeated code is refused",
);
assert.throws(
  () => auditSwapBoard({ shifts: [shift("a", 8, "kim")], claims: [] }, 1),
  Error,
  "a day of eight is refused",
);
assert.throws(
  () => auditSwapBoard({ shifts: [shift("a", 1, "")], claims: [] }, 1),
  Error,
  "an empty holder is refused",
);
assert.throws(
  () => auditSwapBoard({ shifts: [], claims: [claim("a", "")] }, 1),
  Error,
  "an empty bidder is refused",
);
assert.throws(
  () => auditSwapBoard({ shifts: [], claims: [] }, 0),
  Error,
  "a ceiling of nought is refused",
);
console.log("ok");
