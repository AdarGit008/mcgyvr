import assert from "node:assert/strict";
import { expandTemplate } from "./solution.ts";

assert.equal(
  expandTemplate("hi ${name}!", { name: "Ada" }, "error"),
  "hi Ada!",
  "simple substitution"
);

assert.equal(
  expandTemplate("${user.home.city}", { user: { home: { city: "Oslo" } } }, "error"),
  "Oslo",
  "dotted path descends the nested context"
);

assert.equal(
  expandTemplate("${n} items", { n: 7 }, "error"),
  "7 items",
  "integer printed in decimal"
);

assert.equal(
  expandTemplate("cost: $$${n}", { n: 3 }, "error"),
  "cost: $3",
  "double dollar is one literal dollar"
);

assert.equal(
  expandTemplate("${a}", { a: "${b}" }, "error"),
  "${b}",
  "inserted text is never rescanned"
);

assert.equal(
  expandTemplate("<${gone}>", {}, "keep"),
  "<${gone}>",
  "keep policy preserves the delimiters"
);

assert.equal(
  expandTemplate("<${gone}>", {}, "blank"),
  "<>",
  "blank policy inserts nothing"
);

assert.throws(
  () => expandTemplate("${gone}", {}, "error"),
  Error,
  "error policy raises on a missing path"
);

assert.throws(
  () => expandTemplate("${a.b}", { a: "leaf" }, "error"),
  Error,
  "descending through a non-mapping is a missing path"
);

assert.equal(
  expandTemplate("${a.b}", { a: "leaf" }, "blank"),
  "",
  "a failed mid-path lookup obeys the policy"
);

assert.throws(
  () => expandTemplate("price $9", {}, "error"),
  Error,
  "a stray dollar is rejected"
);

assert.throws(
  () => expandTemplate("${open", {}, "error"),
  Error,
  "an unclosed placeholder is rejected"
);

assert.throws(
  () => expandTemplate("${a..b}", { a: { b: 1 } }, "error"),
  Error,
  "an empty segment is rejected"
);

assert.throws(
  () => expandTemplate("${}", { "": 1 }, "error"),
  Error,
  "an empty path is rejected"
);

assert.throws(
  () => expandTemplate("${flag}", { flag: true }, "error"),
  Error,
  "a boolean value is not printable"
);

assert.throws(
  () => expandTemplate("${user}", { user: { name: "x" } }, "error"),
  Error,
  "a mapping value is not printable"
);

assert.throws(
  () => expandTemplate("x", {}, "silent"),
  Error,
  "an unknown policy word is rejected"
);

console.log("ok");
