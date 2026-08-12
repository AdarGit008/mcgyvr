import assert from "node:assert/strict";
import { decodeStatusWord } from "./solution.ts";

assert.deepEqual(
  decodeStatusWord(0),
  { channel: 0, reading: 0, stale: false },
  "the all-zero word decodes to zeros",
);
assert.deepEqual(
  decodeStatusWord(0x3191),
  { channel: 3, reading: 100, stale: false },
  "a plain positive reading",
);
assert.deepEqual(
  decodeStatusWord(0xf7fe),
  { channel: 15, reading: 511, stale: true },
  "the largest channel and reading, stale",
);
assert.deepEqual(
  decodeStatusWord(0x7ffd),
  { channel: 7, reading: -1, stale: false },
  "all reading bits set decodes to minus one",
);
assert.deepEqual(
  decodeStatusWord(0x1803),
  { channel: 1, reading: -512, stale: true },
  "the most negative reading",
);
assert.deepEqual(
  decodeStatusWord(0x9401),
  { channel: 9, reading: 256, stale: false },
  "the sign bit alone is still positive at 256",
);
assert.deepEqual(
  decodeStatusWord(0x5b52),
  { channel: 5, reading: -300, stale: true },
  "a negative mid-range reading, stale",
);
assert.deepEqual(
  decodeStatusWord(0x2007),
  { channel: 2, reading: 1, stale: true },
  "a one-count reading with parity set",
);
assert.throws(() => decodeStatusWord(0x3190), Error, "odd parity is rejected");
assert.throws(() => decodeStatusWord(0xf7ff), Error, "odd parity near the top");
assert.throws(() => decodeStatusWord(-1), Error, "a negative word is rejected");
assert.throws(() => decodeStatusWord(65536), Error, "a 17-bit word is rejected");
assert.throws(() => decodeStatusWord(2.5), Error, "a fractional word is rejected");
assert.throws(() => decodeStatusWord(true), Error, "a boolean word is rejected");
assert.throws(() => decodeStatusWord("0x3191"), Error, "a string word is rejected");
console.log("ok");
