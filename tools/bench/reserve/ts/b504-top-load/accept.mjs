import assert from "node:assert/strict";
import { topLoad } from "./solution.ts";

assert.equal(topLoad(["wood", "wood", "steel"]), "steel", "one heavy item outweighs two lighter");
assert.equal(topLoad(["wood", "wood", "wood", "steel"]), "wood", "three lighter items outweigh one heavy");
assert.equal(topLoad(["wood", "steel", "wood"]), "steel", "items of a kind counted together");
assert.equal(topLoad(["a", "b"]), "a", "kinds of a weight name the earliest");
assert.equal(topLoad(["steel"]), "steel", "a load of one item");
assert.equal(topLoad([]), "", "a load of nothing");
console.log("ok");
