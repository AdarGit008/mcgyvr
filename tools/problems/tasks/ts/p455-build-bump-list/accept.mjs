import assert from "node:assert/strict";
import { buildBumpList } from "./solution.ts";

const t = (code, fare, miles, checked) => ({ code, fare, miles, checked });
const roll = [t("ann", "saver", 500, 3), t("bob", "flex", 10, 5), t("cid", "award", 900, 1), t("dot", "saver", 500, 2)];

assert.deepEqual(
  buildBumpList(roll, 9, []),
  { boarding: ["bob", "dot", "ann", "cid"], bumped: [] },
  "a roomier aeroplane bumps nobody and still ranks the roll",
);
assert.deepEqual(
  buildBumpList(roll, 4, []),
  { boarding: ["bob", "dot", "ann", "cid"], bumped: [] },
  "seats exactly matching the roll bump nobody",
);
assert.deepEqual(
  buildBumpList(roll, 3, []),
  { boarding: ["bob", "dot", "ann"], bumped: ["cid"] },
  "one seat short drops the least protected",
);
assert.deepEqual(
  buildBumpList(roll, 2, []),
  { boarding: ["bob", "dot"], bumped: ["cid", "ann"] },
  "two seats short works up from the bottom",
);
assert.deepEqual(
  buildBumpList(roll, 3, ["bob"]),
  { boarding: ["dot", "ann", "cid"], bumped: ["bob"] },
  "a volunteer goes ahead of the least protected",
);
assert.deepEqual(
  buildBumpList(roll, 3, ["bob", "cid"]),
  { boarding: ["dot", "ann", "cid"], bumped: ["bob"] },
  "only as many volunteers are taken as seats are missing",
);
assert.deepEqual(
  buildBumpList(roll, 4, ["bob"]),
  { boarding: ["bob", "dot", "ann", "cid"], bumped: [] },
  "with seats for everyone the offer is not taken up",
);
assert.deepEqual(
  buildBumpList(roll, 2, ["bob"]),
  { boarding: ["dot", "ann"], bumped: ["bob", "cid"] },
  "a volunteer covers part of the shortfall and ranking covers the rest",
);
assert.deepEqual(
  buildBumpList(roll, 3, ["cid"]),
  { boarding: ["bob", "dot", "ann"], bumped: ["cid"] },
  "a volunteer who was going anyway is not counted twice",
);
assert.deepEqual(
  buildBumpList(roll, 0, []),
  { boarding: [], bumped: ["cid", "ann", "dot", "bob"] },
  "an aeroplane with no seats leaves the whole roll behind, worst first",
);
assert.deepEqual(buildBumpList([], 3, []), { boarding: [], bumped: [] }, "an empty roll boards nobody");
assert.deepEqual(
  buildBumpList([t("p", "saver", 700, 9), t("q", "saver", 700, 4)], 1, []),
  { boarding: ["q"], bumped: ["p"] },
  "equal miles are broken by the earlier check-in",
);
assert.deepEqual(
  buildBumpList([t("p", "flex", 0, 9), t("q", "award", 9999, 1)], 1, []),
  { boarding: ["p"], bumped: ["q"] },
  "the fare outranks any pile of miles",
);

assert.throws(() => buildBumpList("no", 1, []), Error, "a roll that is not a list is refused");
assert.throws(() => buildBumpList([], -1, []), Error, "a negative seat count is refused");
assert.throws(() => buildBumpList([], 1.5, []), Error, "a fractional seat count is refused");
assert.throws(() => buildBumpList([], 1, "ann"), Error, "volunteers that are not a list are refused");
assert.throws(() => buildBumpList([[1]], 1, []), Error, "a traveller that is not a record is refused");
assert.throws(() => buildBumpList([t("", "flex", 1, 1)], 1, []), Error, "an empty code is refused");
assert.throws(
  () => buildBumpList([t("a", "flex", 1, 1), t("a", "flex", 1, 2)], 1, []),
  Error,
  "one code carried twice is refused",
);
assert.throws(() => buildBumpList([t("a", "gold", 1, 1)], 1, []), Error, "an unknown fare is refused");
assert.throws(() => buildBumpList([t("a", "flex", -1, 1)], 1, []), Error, "negative miles are refused");
assert.throws(() => buildBumpList([t("a", "flex", 1, 0)], 1, []), Error, "a check-in of nought is refused");
assert.throws(
  () => buildBumpList([t("a", "flex", 1, 2), t("b", "flex", 1, 2)], 1, []),
  Error,
  "two travellers at one check-in are refused",
);
assert.throws(() => buildBumpList([t("a", "flex", 1, 1)], 1, ["zz"]), Error, "a volunteer nobody answers to is refused");
assert.throws(
  () => buildBumpList([t("a", "flex", 1, 1), t("b", "flex", 1, 2)], 1, ["a", "a"]),
  Error,
  "a volunteer named twice is refused",
);
console.log("ok");
