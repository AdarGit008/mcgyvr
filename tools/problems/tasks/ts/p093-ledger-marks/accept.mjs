import assert from "node:assert/strict";
import { linkLedgerMarks } from "./solution.ts";

assert.deepEqual(
  linkLedgerMarks(["av-0042q", "AV/42Q", "vw 42q", "kx/26a"], { VW: "AV" }),
  [
    ["AV-42-Q", ["av-0042q", "AV/42Q", "vw 42q"]],
    ["KX-26-A", ["kx/26a"]],
  ],
  "case, zeros, separators and an alias all link",
);
assert.deepEqual(
  linkLedgerMarks(["KX/1b", "av-42q", "kx 001B"], {}),
  [
    ["KX-1-B", ["KX/1b", "kx 001B"]],
    ["AV-42-Q", ["av-42q"]],
  ],
  "groups keep first-appearance order and raw spellings",
);
assert.deepEqual(linkLedgerMarks([], {}), [], "no marks, no groups");
assert.deepEqual(
  linkLedgerMarks(["abc-7h"], {}),
  [["ABC-7-H", ["abc-7h"]]],
  "three-letter house code, serial 7 checks as H",
);

assert.throws(() => linkLedgerMarks(["av-42q"], { VW: "AV", AV: "KX" }), Error, "chained alias is rejected");
assert.throws(() => linkLedgerMarks([], { AV: "AV" }), Error, "self alias is rejected");
assert.throws(() => linkLedgerMarks(["av-42r"], {}), Error, "wrong check letter is rejected");
assert.throws(() => linkLedgerMarks(["av-0a"], {}), Error, "serial 0 is rejected");
assert.throws(() => linkLedgerMarks(["a-42q"], {}), Error, "one-letter house is rejected");
assert.throws(() => linkLedgerMarks(["av--42q"], {}), Error, "double separator is rejected");
assert.throws(() => linkLedgerMarks(["av-42"], {}), Error, "missing check letter is rejected");
assert.throws(() => linkLedgerMarks([7], {}), Error, "non-string mark is rejected");
console.log("ok");
