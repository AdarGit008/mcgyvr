import assert from "node:assert/strict";
import { flipChannels } from "./solution.ts";

assert.equal(flipChannels(0, 0, 0), 1, "flipping channel zero of a dark board lights it");
assert.equal(flipChannels(0, 0, 15), 65535, "flipping every channel of a dark board lights the board");
assert.equal(flipChannels(65535, 0, 15), 0, "flipping every channel of a lit board darkens it");
assert.equal(flipChannels(10, 1, 2), 12, "a two-channel span flips only its own bits");
assert.equal(flipChannels(1, 4, 7), 241, "channels outside the span keep their state");
assert.equal(flipChannels(flipChannels(37, 3, 9), 3, 9), 37, "flipping a span twice restores the word");
assert.throws(() => flipChannels(3.5, 0, 1), Error, "a fractional word is rejected");
assert.throws(() => flipChannels(65536, 0, 1), Error, "a word beyond 16 bits is rejected");
assert.throws(() => flipChannels(7, -1, 3), Error, "a negative bound is rejected");
assert.throws(() => flipChannels(7, 3, 16), Error, "a bound past channel 15 is rejected");
assert.throws(() => flipChannels(7, 9, 3), Error, "a lo greater than hi is rejected");
console.log("ok");
