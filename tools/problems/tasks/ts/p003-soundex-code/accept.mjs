import assert from "node:assert/strict";
import { soundexCode } from "./solution.ts";

assert.equal(soundexCode("Robert"), "R163", "Robert");
assert.equal(soundexCode("Rupert"), "R163", "Rupert matches Robert");
assert.equal(soundexCode("Ashcraft"), "A261", "h between same digits collapses");
assert.equal(soundexCode("Tymczak"), "T522", "adjacent same digits collapse");
assert.equal(soundexCode("Pfister"), "P236", "first letter joins collapsing");
assert.equal(soundexCode("Jackson"), "J250", "vowel after first letter keeps next");
assert.equal(soundexCode("Honeyman"), "H555", "vowel between same digits keeps both");
assert.equal(soundexCode("washington"), "W252", "lowercase input, truncation");
assert.equal(soundexCode("Euler"), "E460", "padding to three digits");
assert.equal(soundexCode("a"), "A000", "single letter pads with zeros");
assert.throws(() => soundexCode(""), Error, "empty word is rejected");
assert.throws(() => soundexCode("van Dyk"), Error, "space is rejected");
assert.throws(() => soundexCode("O'Brien"), Error, "apostrophe is rejected");
assert.throws(() => soundexCode(42), Error, "non-string is rejected");
console.log("ok");
