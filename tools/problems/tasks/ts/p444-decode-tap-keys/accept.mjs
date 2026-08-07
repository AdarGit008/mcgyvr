import assert from "node:assert/strict";
import { decodeTapKeys } from "./solution.ts";

assert.equal(decodeTapKeys("4433555-555666"), "HELLO", "a hyphen parts two letters on key 5");
assert.equal(decodeTapKeys("96667773"), "WORD", "runs on different keys need no hyphen");
assert.equal(decodeTapKeys("6-666-666-66"), "MOON", "three parted runs on key 6");
assert.equal(decodeTapKeys("84433"), "THE", "one tap then two then two");
assert.equal(decodeTapKeys("44-0-44"), "H H", "key 0 is a space");
assert.equal(decodeTapKeys("0"), " ", "a lone space");
assert.equal(decodeTapKeys("9999"), "Z", "the fourth letter of a four-letter key");
assert.equal(decodeTapKeys("7777"), "S", "four taps of 7 reach S");
assert.equal(decodeTapKeys("2"), "A", "a single tap");

assert.throws(() => decodeTapKeys(""), Error, "an empty sequence is refused");
assert.throws(() => decodeTapKeys(88), Error, "a non-string is refused");
assert.throws(() => decodeTapKeys("2222"), Error, "a run past the end of a key is refused");
assert.throws(() => decodeTapKeys("00"), Error, "two taps of 0 are refused");
assert.throws(() => decodeTapKeys("77777"), Error, "five taps of 7 are refused");
assert.throws(() => decodeTapKeys("144"), Error, "key 1 is refused");
assert.throws(() => decodeTapKeys("4a4"), Error, "a stray character is refused");
assert.throws(() => decodeTapKeys("-44"), Error, "a leading hyphen is refused");
assert.throws(() => decodeTapKeys("44-"), Error, "a trailing hyphen is refused");
assert.throws(() => decodeTapKeys("44--33"), Error, "two hyphens in a row are refused");
console.log("ok");
