import assert from "node:assert/strict";
import { advanceWorkingDays } from "./solution.ts";

assert.equal(advanceWorkingDays("2024-03-04", 1, []), "2024-03-05", "one day on from a Monday");
assert.equal(advanceWorkingDays("2024-03-08", 1, []), "2024-03-11", "one day on from a Friday clears the weekend");
assert.equal(advanceWorkingDays("2024-03-04", 5, []), "2024-03-11", "five working days on is a week");
assert.equal(advanceWorkingDays("2024-03-04", 20, []), "2024-04-01", "twenty working days on is four weeks");
assert.equal(advanceWorkingDays("2024-03-04", 0, []), "2024-03-04", "nought on a working day stays put");
assert.equal(advanceWorkingDays("2024-03-08", 0, []), "2024-03-08", "nought on a Friday stays put");
assert.equal(advanceWorkingDays("2024-03-09", 0, []), "2024-03-11", "nought on a Saturday rolls to the Monday");
assert.equal(
  advanceWorkingDays("2024-03-04", 0, ["2024-03-04", "2024-03-05"]),
  "2024-03-06",
  "nought rolls over a run of shut days",
);
assert.equal(
  advanceWorkingDays("2024-03-10", 0, ["2024-03-11", "2024-03-12"]),
  "2024-03-13",
  "nought on a Sunday rolls past the shut days behind it",
);
assert.equal(advanceWorkingDays("2024-03-11", -1, []), "2024-03-08", "one day back from a Monday");
assert.equal(advanceWorkingDays("2024-03-11", -3, []), "2024-03-06", "three days back");
assert.equal(advanceWorkingDays("2024-03-04", -1, []), "2024-03-01", "one day back over a weekend");
assert.equal(advanceWorkingDays("2024-03-04", 3, ["2024-03-06"]), "2024-03-08", "a shut day in the middle is stepped over");
assert.equal(advanceWorkingDays("2024-03-09", 1, []), "2024-03-11", "setting off from a Saturday still moves one working day");
assert.equal(advanceWorkingDays("2024-03-09", -1, []), "2024-03-08", "and one working day back from a Saturday");
assert.equal(advanceWorkingDays("2024-02-28", 1, []), "2024-02-29", "the leap day is a working day");
assert.equal(advanceWorkingDays("2023-02-28", 1, []), "2023-03-01", "a plain February has no 29th to land on");
assert.equal(advanceWorkingDays("2024-12-31", 1, []), "2025-01-01", "a step across the turn of the year");
assert.equal(advanceWorkingDays("2024-01-01", 250, []), "2024-12-16", "a long walk through a leap year");

const rejects = (start, count, closures) => {
  try {
    advanceWorkingDays(start, count, closures);
  } catch {
    return true;
  }
  return false;
};

assert.ok(rejects("2024-03-04", 5001, []), "a move past five thousand is refused");
assert.ok(rejects("2024-03-04", -5001, []), "and past minus five thousand");
assert.ok(rejects("2024-03-04", 1.5, []), "a fractional move is refused");
assert.ok(rejects("2024-3-04", 1, []), "a date that is not zero-padded is refused");
assert.ok(rejects("2023-02-29", 1, []), "the 29th of a plain February is refused");
assert.ok(rejects("2024-03-04", 1, ["2024-03-06", "2024-03-06"]), "a shut day named twice is refused");
assert.ok(rejects("2024-03-04", 1, ["nope"]), "a malformed shut day is refused");
assert.ok(rejects("2999-12-31", 5000, []), "a walk off the far end is refused");
assert.ok(rejects("1900-01-01", -5000, []), "a walk off the near end is refused");
console.log("ok");
