import assert from "node:assert/strict";
import { splitProseSentences } from "./solution.ts";

assert.deepEqual(
  splitProseSentences("The rain fell. The road flooded.", []),
  ["The rain fell.", "The road flooded."],
  "two plain sentences",
);
assert.deepEqual(
  splitProseSentences("Dr. Vance signed the form. She left.", ["Dr."]),
  ["Dr. Vance signed the form.", "She left."],
  "a listed abbreviation cancels the candidate",
);
assert.deepEqual(
  splitProseSentences("Dr. Vance signed the form. She left.", []),
  ["Dr.", "Vance signed the form.", "She left."],
  "an unlisted abbreviation breaks",
);
assert.deepEqual(
  splitProseSentences("The gauge read 3.5 bar. Nothing moved.", []),
  ["The gauge read 3.5 bar.", "Nothing moved."],
  "a point with no space after it never breaks",
);
assert.deepEqual(
  splitProseSentences('He yelled "Stop! Now!" and sat down.', []),
  ['He yelled "Stop! Now!" and sat down.'],
  "an open quotation shields its stop marks",
);
assert.deepEqual(
  splitProseSentences("Bring water (it may rain. bring more) now. Done.", []),
  ["Bring water (it may rain. bring more) now.", "Done."],
  "brackets shield their stop marks",
);
assert.deepEqual(
  splitProseSentences("Really?! I doubt it.", []),
  ["Really?!", "I doubt it."],
  "a run of stop marks is one candidate",
);
assert.deepEqual(
  splitProseSentences("Hold on... Then go.", []),
  ["Hold on...", "Then go."],
  "three points end one sentence",
);
assert.deepEqual(
  splitProseSentences("We met e.g. on Tuesday. Fine.", ["e.g."]),
  ["We met e.g. on Tuesday.", "Fine."],
  "an abbreviation carrying inner periods",
);
assert.deepEqual(splitProseSentences("", []), [], "an empty passage");
assert.deepEqual(splitProseSentences("    ", []), [], "a passage of spaces");
assert.deepEqual(
  splitProseSentences("Almost done", []),
  ["Almost done"],
  "a remainder with no stop mark",
);
assert.throws(() => splitProseSentences(42, []), Error, "passage must be a string");
assert.throws(
  () => splitProseSentences("A tale.", "Dr."),
  Error,
  "abbreviations must be a list",
);
assert.throws(
  () => splitProseSentences("A tale.", ["Dr"]),
  Error,
  "an abbreviation must end in a period",
);
assert.throws(
  () => splitProseSentences("A tale.", ["a b."]),
  Error,
  "an abbreviation may not hold a space",
);
assert.throws(
  () => splitProseSentences("Go) home.", []),
  Error,
  "closing bracket with no opener",
);
assert.throws(
  () => splitProseSentences("Go (home.", []),
  Error,
  "bracket left open",
);
assert.throws(
  () => splitProseSentences('He said "hi', []),
  Error,
  "quotation left open",
);
console.log("ok");
