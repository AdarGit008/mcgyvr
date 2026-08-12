import assert from "node:assert/strict";
import { sortKey } from "./solution.ts";

assert.equal(sortKey("Ada Lovelace"), "lovelace ada", "surname leads");
assert.equal(sortKey("Grace Hopper"), "hopper grace", "another pair");
assert.equal(sortKey("prince"), "prince", "one word stands alone");
assert.equal(sortKey("Prince"), "prince", "and is lowered");
assert.equal(sortKey(""), "", "an empty name");
assert.equal(sortKey("Ann Van Dyke"), "van dyke ann", "only the first space cuts");
console.log("ok");
