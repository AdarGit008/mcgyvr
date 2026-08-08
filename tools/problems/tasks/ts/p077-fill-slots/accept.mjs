import assert from "node:assert/strict";
import { fillPlaceholders } from "./solution.ts";

assert.equal(
  fillPlaceholders("dear %who%,", { who: "Sam" }),
  "dear Sam,",
  "simple slot"
);

assert.equal(
  fillPlaceholders("%a% and %b%", { a: "salt", b: "pepper" }),
  "salt and pepper",
  "two slots"
);

assert.equal(
  fillPlaceholders("100%% sure", {}),
  "100% sure",
  "doubled percent is a literal"
);

assert.equal(
  fillPlaceholders("%%who%%", { who: "Sam" }),
  "%who%",
  "doubled percents around a word stay literal"
);

assert.equal(
  fillPlaceholders("%a%", { a: "see %b%", b: "nope" }),
  "see %b%",
  "replacement text is never scanned again"
);

assert.equal(
  fillPlaceholders("%a%%b%", { a: "x", b: "y" }),
  "xy",
  "adjacent slots both fill"
);

assert.throws(
  () => fillPlaceholders("hi %stranger%", {}),
  Error,
  "unknown slot raises"
);

assert.throws(
  () => fillPlaceholders("50% off", { off: "x" }),
  Error,
  "unpaired percent raises"
);

console.log("ok");
