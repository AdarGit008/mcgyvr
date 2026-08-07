import assert from "node:assert/strict";
import { auditArtistGaps } from "./solution.ts";

assert.deepEqual(
  auditArtistGaps(["Vela", "Kesh", "Vela", "Orn", "Pell", "Kesh"], 2),
  [{ artist: "Vela", at: 2, between: 1 }],
  "one track between two plays is short of two",
);
assert.deepEqual(
  auditArtistGaps(["Vela", "Kesh", "Vela", "Orn", "Pell", "Kesh"], 1),
  [],
  "one track between is enough for a spacing of one",
);
assert.deepEqual(
  auditArtistGaps(["Vela", "Vela"], 0),
  [],
  "a spacing of zero can never be broken",
);
assert.deepEqual(
  auditArtistGaps(["Vela", "Vela"], 1),
  [{ artist: "Vela", at: 1, between: 0 }],
  "back to back plays sit no tracks apart",
);
assert.deepEqual(
  auditArtistGaps(["Orn", "Orn", "Orn"], 1),
  [
    { artist: "Orn", at: 1, between: 0 },
    { artist: "Orn", at: 2, between: 0 },
  ],
  "three in a row give two broken pairs",
);
assert.deepEqual(
  auditArtistGaps(["Vela", "x", "Vela", "y", "Vela"], 4),
  [
    { artist: "Vela", at: 2, between: 1 },
    { artist: "Vela", at: 4, between: 1 },
  ],
  "the first and last plays are not compared across the middle one",
);
assert.deepEqual(
  auditArtistGaps(["Vela", "Kesh", "Orn"], 5),
  [],
  "an artist played once is never crowded",
);
assert.deepEqual(
  auditArtistGaps(["Vela", "Kesh", "Kesh", "Vela"], 3),
  [
    { artist: "Kesh", at: 2, between: 0 },
    { artist: "Vela", at: 3, between: 2 },
  ],
  "the report is ordered by position, not by artist",
);

assert.throws(() => auditArtistGaps([], 1), Error, "an empty playlist is refused");
assert.throws(() => auditArtistGaps("Vela", 1), Error, "a playlist that is not a list is refused");
assert.throws(() => auditArtistGaps(["Vela", ""], 1), Error, "an empty artist name is refused");
assert.throws(() => auditArtistGaps(["Vela", 7], 1), Error, "an entry that is not a string is refused");
assert.throws(() => auditArtistGaps(["Vela"], -1), Error, "a negative spacing is refused");
assert.throws(() => auditArtistGaps(["Vela"], 1.5), Error, "a spacing that is not whole is refused");
assert.throws(() => auditArtistGaps(["Vela"], "two"), Error, "a spacing that is not a number is refused");
console.log("ok");
