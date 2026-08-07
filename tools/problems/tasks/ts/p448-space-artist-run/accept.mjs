import assert from "node:assert/strict";
import { spaceArtistRun } from "./solution.ts";

const t = (title, artist) => ({ title, artist });

assert.deepEqual(spaceArtistRun([t("solo", "Vela")]), ["solo"], "one track is its own run");

assert.deepEqual(
  spaceArtistRun([t("a1", "Vela"), t("a2", "Vela"), t("b1", "Kesh")]),
  ["a1", "b1", "a2"],
  "the busier artist opens and closes",
);

assert.deepEqual(
  spaceArtistRun([t("t1", "Pell"), t("t2", "Quire")]),
  ["t1", "t2"],
  "level artists go by which appeared first",
);

assert.deepEqual(
  spaceArtistRun([
    t("x1", "Vela"),
    t("x2", "Vela"),
    t("x3", "Vela"),
    t("y1", "Kesh"),
    t("y2", "Kesh"),
    t("z1", "Orn"),
  ]),
  ["x1", "y1", "x2", "y2", "x3", "z1"],
  "six tracks over three artists",
);

assert.deepEqual(
  spaceArtistRun([t("x1", "Vela"), t("x2", "Vela"), t("y1", "Kesh"), t("z1", "Orn")]),
  ["x1", "y1", "x2", "z1"],
  "a level pair is settled by first appearance",
);

assert.deepEqual(
  spaceArtistRun([
    t("a1", "Pell"),
    t("a2", "Pell"),
    t("b1", "Quire"),
    t("b2", "Quire"),
    t("b3", "Quire"),
  ]),
  ["b1", "a1", "b2", "a2", "b3"],
  "the run need not open with the first track handed over",
);

assert.deepEqual(
  spaceArtistRun([t("m1", "Orn"), t("m2", "Vela"), t("m3", "Orn"), t("m4", "Vela")]),
  ["m1", "m2", "m3", "m4"],
  "two artists of equal weight alternate in order",
);

assert.throws(() => spaceArtistRun([]), Error, "an empty list is refused");
assert.throws(() => spaceArtistRun("tracks"), Error, "a non-list is refused");
assert.throws(
  () => spaceArtistRun([t("a1", "Vela"), t("a2", "Vela")]),
  Error,
  "two tracks by one artist cannot be parted",
);
assert.throws(
  () => spaceArtistRun([t("a1", "Vela"), t("a2", "Vela"), t("a3", "Vela"), t("b1", "Kesh")]),
  Error,
  "an artist holding more than half the run is refused",
);
assert.throws(
  () => spaceArtistRun([t("", "Vela"), t("b1", "Kesh")]),
  Error,
  "an empty title is refused",
);
assert.throws(
  () => spaceArtistRun([{ title: "a1" }, t("b1", "Kesh")]),
  Error,
  "a missing artist is refused",
);
assert.throws(
  () => spaceArtistRun([t("same", "Vela"), t("same", "Kesh")]),
  Error,
  "two tracks sharing a title are refused",
);
assert.throws(
  () => spaceArtistRun([t("a1", 7), t("b1", "Kesh")]),
  Error,
  "an artist that is not a string is refused",
);
console.log("ok");
