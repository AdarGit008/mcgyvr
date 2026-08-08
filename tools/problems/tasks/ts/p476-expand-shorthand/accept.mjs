import assert from "node:assert/strict";
import { expandShorthand } from "./solution.ts";

const book = {
  asap: "as soon as possible",
  bldg: "building",
  n: "north",
  rd: "road",
};

assert.equal(
  expandShorthand("asap", book),
  "as soon as possible",
  "a lowercase word takes the value as written",
);
assert.equal(
  expandShorthand("ASAP", book),
  "AS SOON AS POSSIBLE",
  "an uppercase word raises every letter of the value",
);
assert.equal(
  expandShorthand("Asap", book),
  "As soon as possible",
  "a capitalised word raises only the opening character",
);
assert.equal(
  expandShorthand("AsAp", book),
  "AsAp",
  "a word cased any other way is left alone",
);
assert.equal(
  expandShorthand("Meet at bldg 4 ASAP.", book),
  "Meet at building 4 AS SOON AS POSSIBLE.",
  "a whole line is rewritten word by word",
);
assert.equal(
  expandShorthand("re-asap", book),
  "re-as soon as possible",
  "a hyphen breaks a word so the tail is looked up",
);
assert.equal(
  expandShorthand("asaply", book),
  "asaply",
  "a longer word holding the shorthand is not touched",
);
assert.equal(
  expandShorthand("bldg9", book),
  "bldg9",
  "trailing digits make a different word",
);
assert.equal(
  expandShorthand("N and n and Rd", book),
  "NORTH and north and Road",
  "a lone capital follows the uppercase rule",
);
assert.equal(
  expandShorthand("a b", { a: "b", b: "c" }),
  "b c",
  "what a value writes into the text is never looked up again",
);
assert.equal(expandShorthand("", book), "", "empty text stays empty");
assert.equal(
  expandShorthand("Bldg 7, off the RD.", book),
  "Building 7, off the ROAD.",
  "punctuation around a word survives the rewrite",
);
assert.equal(
  expandShorthand("constructor toString", { asap: "x" }),
  "constructor toString",
  "a word the table never held is not fetched from anywhere else",
);

assert.throws(
  () => expandShorthand(42, book),
  Error,
  "a text that is not a string is rejected",
);
assert.throws(
  () => expandShorthand("asap", ["asap"]),
  Error,
  "a table that is not a mapping is rejected",
);
assert.throws(
  () => expandShorthand("asap", { AS: "alongside" }),
  Error,
  "an uppercase key is rejected",
);
assert.throws(
  () => expandShorthand("asap", { "1st": "first" }),
  Error,
  "a key beginning with a digit is rejected",
);
assert.throws(
  () => expandShorthand("asap", { "as ap": "x" }),
  Error,
  "a key holding a space is rejected",
);
assert.throws(
  () => expandShorthand("asap", { asap: "" }),
  Error,
  "an empty value is rejected",
);
assert.throws(
  () => expandShorthand("asap", { asap: 7 }),
  Error,
  "a value that is not a string is rejected",
);
console.log("ok");
