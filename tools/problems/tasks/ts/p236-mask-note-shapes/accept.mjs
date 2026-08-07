import assert from "node:assert/strict";
import { maskSensitive } from "./solution.ts";

assert.deepEqual(
  maskSensitive(""),
  { text: "", badges: 0, vaults: 0 },
  "an empty note carries nothing",
);
assert.deepEqual(
  maskSensitive("ticket AB-1234 filed"),
  { text: "ticket AB-#### filed", badges: 1, vaults: 0 },
  "a badge keeps its letters, its hyphen and its length",
);
assert.deepEqual(
  maskSensitive("WXYZ-12345678."),
  { text: "WXYZ-########.", badges: 1, vaults: 0 },
  "four letters and eight digits are still a badge",
);
assert.deepEqual(
  maskSensitive("ABCDE-1234 and A-1234 and AB-123 and AB-123456789"),
  {
    text: "ABCDE-1234 and A-1234 and AB-123 and AB-123456789",
    badges: 0,
    vaults: 0,
  },
  "one letter or digit outside the range makes it no badge at all",
);
assert.deepEqual(
  maskSensitive("XY-1234AB-5678"),
  { text: "XY-####AB-####", badges: 2, vaults: 0 },
  "a badge may begin right where the one before it ended",
);
assert.deepEqual(
  maskSensitive("see vk=abc123 now"),
  { text: "see [vault] now", badges: 0, vaults: 1 },
  "a vault key goes entirely, token and all",
);
assert.deepEqual(
  maskSensitive("vk=abcde vk=abcdefghijk myvk=abc123"),
  { text: "vk=abcde vk=abcdefghijk myvk=abc123", badges: 0, vaults: 0 },
  "too short, too long, and glued to a word: none of them is a vault key",
);
assert.deepEqual(
  maskSensitive("vk=abc123X"),
  { text: "[vault]X", badges: 0, vaults: 1 },
  "a capital ends the stretch, so the six before it stand",
);
assert.deepEqual(
  maskSensitive("QQ-4444/ZZZ-55555 vk=zz99aa!"),
  { text: "QQ-####/ZZZ-##### [vault]!", badges: 2, vaults: 1 },
  "both shapes in one note are counted apart",
);
assert.deepEqual(
  maskSensitive("hash # and vault already"),
  { text: "hash # and vault already", badges: 0, vaults: 0 },
  "a note with neither shape comes back untouched",
);
assert.throws(() => maskSensitive(1234), Error, "a number is not a note");
assert.throws(() => maskSensitive(null), Error, "nothing is not a note");
console.log("ok");
