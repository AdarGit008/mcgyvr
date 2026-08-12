import assert from "node:assert/strict";
import { pathToll } from "./solution.ts";

assert.equal(pathToll(["flat", "flat", "flat"]), 4, "the third step is free");
assert.equal(pathToll(["hill", "hill"]), 10, "no step reaches the third");
assert.equal(pathToll(["flat", "flat", "flat", "flat"]), 6, "counting carries on past the third");
assert.equal(pathToll(["hill", "flat", "hill", "flat"]), 9, "kinds mixed along the path");
assert.equal(pathToll(["odd"]), 3, "an unnamed kind takes the middle cost");
assert.equal(pathToll([]), 0, "a path of no steps");
console.log("ok");
