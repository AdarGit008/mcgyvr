import assert from "node:assert/strict";
import { fillReleasedSeats } from "./solution.ts";

const seat = (id, holder, band) => ({ seat: id, holder, band });
const wait = (name, band, years, rank, roving) => ({
  name,
  band,
  years,
  rank,
  roving,
});

assert.deepEqual(fillReleasedSeats([], [], []), [], "no releases, no offers");
assert.deepEqual(
  fillReleasedSeats([seat("s1", "ada", "gold")], [], ["s1"]),
  [{ seat: "s1", taken: null }],
  "an empty waitlist leaves the seat standing empty",
);
assert.deepEqual(
  fillReleasedSeats(
    [seat("s1", "ada", "gold")],
    [wait("kip", "gold", 5, 3, false), wait("lou", "gold", 5, 2, false)],
    ["s1"],
  ),
  [{ seat: "s1", taken: "lou" }],
  "equal years hands the offer to the smaller rank",
);
assert.deepEqual(
  fillReleasedSeats(
    [seat("s1", "ada", "gold")],
    [wait("hal", "silver", 4, 1, false), wait("jon", "silver", 8, 3, true), wait("ivy", "bronze", 2, 2, true)],
    ["s1"],
  ),
  [{ seat: "s1", taken: "jon" }],
  "with no gold runner the offer widens to the roving entries",
);
assert.deepEqual(
  fillReleasedSeats(
    [seat("s1", "ada", "gold")],
    [wait("meg", "gold", 1, 4, false), wait("nol", "silver", 50, 1, true)],
    ["s1"],
  ),
  [{ seat: "s1", taken: "meg" }],
  "a band match beats fifty years of roving standing",
);
assert.deepEqual(
  fillReleasedSeats(
    [seat("s1", "ada", "gold"), seat("s2", "ben", "silver"), seat("s3", "cyd", "gold")],
    [
      wait("dot", "gold", 5, 1, false),
      wait("eli", "gold", 9, 2, false),
      wait("fay", "silver", 3, 3, true),
      wait("ben", "gold", 12, 4, false),
      wait("gus", "bronze", 1, 5, true),
    ],
    ["s1", "s2", "s3"],
  ),
  [
    { seat: "s1", taken: "eli" },
    { seat: "s2", taken: "fay" },
    { seat: "s3", taken: "ben" },
  ],
  "ben cannot run while seated, and wins the gold seat once he steps out",
);
assert.deepEqual(
  fillReleasedSeats(
    [seat("s1", "ada", "gold"), seat("s2", "bea", "silver")],
    [
      wait("mia", "gold", 1, 1, false),
      wait("mia", "silver", 9, 2, false),
      wait("ned", "silver", 3, 3, false),
    ],
    ["s1", "s2"],
  ),
  [
    { seat: "s1", taken: "mia" },
    { seat: "s2", taken: "ned" },
  ],
  "taking a seat strikes every entry in that name, band by band",
);
assert.deepEqual(
  fillReleasedSeats(
    [seat("s1", "ada", "gold")],
    [wait("pip", "gold", 2, 1, false), wait("quo", "gold", 1, 2, false)],
    ["s1", "s1"],
  ),
  [
    { seat: "s1", taken: "pip" },
    { seat: "s1", taken: "quo" },
  ],
  "a refilled seat may be released again",
);

assert.throws(() => fillReleasedSeats("s", [], []), Error, "the seats are a list");
assert.throws(
  () => fillReleasedSeats([seat("s1", "ada", "gold")], [], "s1"),
  Error,
  "the releases are a list",
);
assert.throws(
  () => fillReleasedSeats([seat("s1", "ada", "gold"), seat("s1", "bea", "gold")], [], []),
  Error,
  "two seats may not share an id",
);
assert.throws(
  () => fillReleasedSeats([seat("s1", "ada", "gold"), seat("s2", "ada", "gold")], [], []),
  Error,
  "one name may not hold two seats",
);
assert.throws(
  () => fillReleasedSeats([], [wait("kit", "gold", -1, 1, false)], []),
  Error,
  "years is never negative",
);
assert.throws(
  () => fillReleasedSeats([], [wait("kit", "gold", 2, 1.5, false)], []),
  Error,
  "rank is a whole number",
);
assert.throws(
  () => fillReleasedSeats([], [wait("kit", "gold", 2, 1, "no")], []),
  Error,
  "roving is a boolean",
);
assert.throws(
  () => fillReleasedSeats([], [wait("kit", "gold", 2, 1, false), wait("lyn", "silver", 3, 1, false)], []),
  Error,
  "two entries may not share a rank",
);
assert.throws(
  () => fillReleasedSeats([], [wait("kit", "gold", 2, 1, false), wait("kit", "gold", 3, 2, false)], []),
  Error,
  "one name waits on a band only once",
);
assert.throws(
  () => fillReleasedSeats([seat("s1", "ada", "gold")], [], ["s9"]),
  Error,
  "a release must name a seat",
);
assert.throws(
  () => fillReleasedSeats([seat("s1", "ada", "gold")], [], ["s1", "s1"]),
  Error,
  "an empty seat cannot be released twice",
);
console.log("ok");
