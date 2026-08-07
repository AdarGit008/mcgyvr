import assert from "node:assert/strict";
import { checkGuaranteeClaim } from "./solution.ts";

assert.deepEqual(
  checkGuaranteeClaim("2023-05-10", 24, 30, "2025-05-10"),
  { plain: "2025-05-10", last: "2025-06-09", verdict: "inside", over: 0 },
  "a complaint on the very day the backing runs out is still inside it",
);
assert.deepEqual(
  checkGuaranteeClaim("2023-05-10", 24, 30, "2025-05-11"),
  { plain: "2025-05-10", last: "2025-06-09", verdict: "grace", over: 0 },
  "the day after the backing runs out falls in the allowance",
);
assert.deepEqual(
  checkGuaranteeClaim("2023-05-10", 24, 30, "2025-06-09"),
  { plain: "2025-05-10", last: "2025-06-09", verdict: "grace", over: 0 },
  "the last day of the allowance is still heard",
);
assert.deepEqual(
  checkGuaranteeClaim("2023-05-10", 24, 30, "2025-06-10"),
  { plain: "2025-05-10", last: "2025-06-09", verdict: "lapsed", over: 1 },
  "one day past the allowance is a day over",
);
assert.deepEqual(
  checkGuaranteeClaim("2024-02-29", 12, 0, "2025-03-01"),
  { plain: "2025-02-28", last: "2025-02-28", verdict: "lapsed", over: 1 },
  "a leap day sale runs out on the 28th the year after",
);
assert.deepEqual(
  checkGuaranteeClaim("2023-05-10", 24, 30, "2023-05-09"),
  { plain: "2025-05-10", last: "2025-06-09", verdict: "early", over: 0 },
  "a complaint before the sale is early",
);
assert.deepEqual(
  checkGuaranteeClaim("2020-12-31", 2, 5, "2021-03-05"),
  { plain: "2021-02-28", last: "2021-03-05", verdict: "grace", over: 0 },
  "a short month pulls the run-out back to its final day",
);
assert.deepEqual(
  checkGuaranteeClaim("2023-01-01", 240, 365, "2043-01-01"),
  { plain: "2043-01-01", last: "2044-01-01", verdict: "inside", over: 0 },
  "twenty years of backing reach across five leap years",
);

assert.throws(() => checkGuaranteeClaim("2023-5-10", 12, 0, "2024-01-01"), Error, "an unpadded month");
assert.throws(() => checkGuaranteeClaim("2023-02-30", 12, 0, "2024-01-01"), Error, "a day that never was");
assert.throws(() => checkGuaranteeClaim("3000-01-01", 12, 0, "3000-06-01"), Error, "a year past 2999");
assert.throws(() => checkGuaranteeClaim("2023-01-01", 0, 0, "2024-01-01"), Error, "no months backed");
assert.throws(() => checkGuaranteeClaim("2023-01-01", 241, 0, "2024-01-01"), Error, "too many months");
assert.throws(() => checkGuaranteeClaim("2023-01-01", 12, -1, "2024-01-01"), Error, "a negative allowance");
assert.throws(() => checkGuaranteeClaim("2023-01-01", 12, 366, "2024-01-01"), Error, "an allowance past a year");
assert.throws(() => checkGuaranteeClaim("2023-01-01", 12.5, 0, "2024-01-01"), Error, "months must be whole");
assert.throws(() => checkGuaranteeClaim("2023-01-01", 12, 0, 20240101), Error, "the complaint day must be a string");
console.log("ok");
