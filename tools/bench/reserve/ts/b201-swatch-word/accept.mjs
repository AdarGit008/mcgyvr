import assert from "node:assert/strict";
import { swatchWord } from "./solution.ts";

assert.equal(swatchWord("#ffffff", [5, 6, 5]), "1111111111111111", "a white colour keeps every reduced bit set");
assert.equal(swatchWord("#000000", [5, 6, 5]), "0000000000000000", "a black colour pads out to the summed depth");
assert.equal(swatchWord("#3a7f2b", [5, 6, 5]), "0011101111100101", "channels are reduced then packed red first");
assert.equal(swatchWord("#804020", [3, 3, 2]), "10001000", "uneven depths keep only the top bits of each byte");
assert.equal(swatchWord("#f0a", [4, 4, 4]), "111100001010", "the short form doubles each digit into a byte");
assert.throws(() => swatchWord("3a7f2b", [5, 6, 5]), Error, "a colour without the leading hash is rejected");
assert.throws(() => swatchWord("#3a7f2b", [5, 6, 9]), Error, "a depth above eight is rejected");
console.log("ok");
