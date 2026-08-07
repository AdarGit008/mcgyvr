import assert from "node:assert/strict";
import { reckonCoverEnd } from "./solution.ts";

assert.deepEqual(
  reckonCoverEnd({ bought: "2020-01-31", months: 12, extensions: [], repairs: [], claim: "2020-06-01" }),
  { ends: "2021-01-31", suspended: 0, verdict: "covered", left: 245 },
  "a plain year of cover lands on the same day number",
);
assert.deepEqual(
  reckonCoverEnd({ bought: "2020-01-31", months: 1, extensions: [], repairs: [], claim: "2020-02-29" }),
  { ends: "2020-02-29", suspended: 0, verdict: "covered", left: 1 },
  "a short leap month takes the landing to its last day",
);
assert.deepEqual(
  reckonCoverEnd({ bought: "2021-01-31", months: 1, extensions: [], repairs: [], claim: "2021-03-01" }),
  { ends: "2021-02-28", suspended: 0, verdict: "lapsed", left: 0 },
  "the same month outside a leap year is a day shorter",
);
assert.deepEqual(
  reckonCoverEnd({ bought: "2019-03-15", months: 24, extensions: [6, 6], repairs: [], claim: "2022-03-15" }),
  { ends: "2022-03-15", suspended: 0, verdict: "covered", left: 1 },
  "extension blocks pile on to the sold months",
);
assert.deepEqual(
  reckonCoverEnd({
    bought: "2022-01-01",
    months: 6,
    extensions: [],
    repairs: [{ in: "2022-02-10", out: "2022-02-19" }],
    claim: "2022-07-11",
  }),
  { ends: "2022-07-11", suspended: 10, verdict: "covered", left: 1 },
  "a workshop visit counts both its ends and pushes the ending out",
);
assert.deepEqual(
  reckonCoverEnd({
    bought: "2022-01-01",
    months: 6,
    extensions: [3],
    repairs: [
      { in: "2022-02-10", out: "2022-02-19" },
      { in: "2022-05-01", out: "2022-05-31" },
    ],
    claim: "2021-12-31",
  }),
  { ends: "2022-11-11", suspended: 41, verdict: "early", left: 0 },
  "two visits add up and a claim before the purchase is early",
);
assert.deepEqual(
  reckonCoverEnd({ bought: "1999-12-01", months: 3, extensions: [], repairs: [], claim: "2000-03-02" }),
  { ends: "2000-03-01", suspended: 0, verdict: "lapsed", left: 0 },
  "cover reaching over a century boundary still lands correctly",
);
assert.deepEqual(
  reckonCoverEnd({ bought: "2020-08-31", months: 6, extensions: [], repairs: [], claim: "2021-01-01" }),
  { ends: "2021-02-28", suspended: 0, verdict: "covered", left: 59 },
  "the days still in front of the claim are counted inclusively",
);

const sound = {
  bought: "2020-01-01",
  months: 12,
  extensions: [],
  repairs: [],
  claim: "2020-06-01",
};
assert.throws(() => reckonCoverEnd([]), Error, "a list is not a policy");
assert.throws(() => reckonCoverEnd({ ...sound, bought: "2020-2-01" }), Error, "an unpadded month");
assert.throws(() => reckonCoverEnd({ ...sound, bought: "2021-02-29" }), Error, "a day that never was");
assert.throws(() => reckonCoverEnd({ ...sound, bought: "1899-01-01" }), Error, "a year before 1900");
assert.throws(() => reckonCoverEnd({ ...sound, months: 0 }), Error, "no months of cover");
assert.throws(() => reckonCoverEnd({ ...sound, extensions: [61] }), Error, "an oversized block");
assert.throws(() => reckonCoverEnd({ ...sound, repairs: {} }), Error, "the repairs must be a list");
assert.throws(
  () => reckonCoverEnd({ ...sound, repairs: [{ in: "2020-03-05", out: "2020-03-01" }] }),
  Error,
  "a visit may not come back before it went",
);
assert.throws(
  () => reckonCoverEnd({ ...sound, repairs: [{ in: "2019-12-31", out: "2020-01-05" }] }),
  Error,
  "a visit may not open before the purchase",
);
assert.throws(
  () =>
    reckonCoverEnd({
      ...sound,
      repairs: [
        { in: "2020-03-01", out: "2020-03-10" },
        { in: "2020-03-10", out: "2020-03-12" },
      ],
    }),
  Error,
  "two visits may not touch or overlap",
);
assert.throws(() => reckonCoverEnd({ ...sound, claim: "nope" }), Error, "a claim must be a date");
console.log("ok");
