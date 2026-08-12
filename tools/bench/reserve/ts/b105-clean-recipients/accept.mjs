import assert from "node:assert/strict";
import { cleanRecipients } from "./solution.ts";

assert.deepEqual(
  cleanRecipients(["  Ana.Lee@Mail.Example.com  "]),
  ["Ana.Lee@mail.example.com"],
  "trims and lowercases only the domain",
);
assert.deepEqual(
  cleanRecipients(["Kim@a.io", "jo@b.co", "kim@A.IO"]),
  ["Kim@a.io", "jo@b.co"],
  "a distant duplicate is dropped case-insensitively",
);
assert.deepEqual(
  cleanRecipients(["Dana Reyes <Dana@Ops.example>"]),
  ["Dana@ops.example"],
  "a display entry keeps only its bracketed address",
);
assert.deepEqual(
  cleanRecipients(["ed@hq.example", "Ed <ED@HQ.example>"]),
  ["ed@hq.example"],
  "a display duplicate is dropped too",
);
assert.deepEqual(cleanRecipients([]), [], "no entries, no addresses");
assert.deepEqual(
  cleanRecipients(["Team <  crew@list.example.org  >"]),
  ["crew@list.example.org"],
  "padding inside the brackets trims away",
);
assert.throws(() => cleanRecipients("solo@one.example"), Error, "a bare string");
assert.throws(() => cleanRecipients([7]), Error, "a numeric entry is rejected");
assert.throws(() => cleanRecipients(["plainname"]), Error, "no @ at all");
assert.throws(() => cleanRecipients(["pat@@dual.example"]), Error, "two @ signs");
assert.throws(() => cleanRecipients(["@lone.example"]), Error, "an empty local part");
assert.throws(() => cleanRecipients(["pat@host"]), Error, "a dotless domain");
assert.throws(() => cleanRecipients(["pat@host.example."]), Error, "a trailing dot");
assert.throws(() => cleanRecipients(["pa t@host.example"]), Error, "inner whitespace");
assert.throws(
  () => cleanRecipients(["Dana <pat@host.example> yes"]),
  Error,
  "text after the closing bracket",
);
console.log("ok");
