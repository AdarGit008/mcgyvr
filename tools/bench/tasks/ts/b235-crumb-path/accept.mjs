import assert from "node:assert/strict";
import { crumbSplit, crumbJoin } from "./solution.ts";

assert.deepEqual(crumbSplit("/docs//api/"), ["docs", "api"], "empties dropped");
assert.deepEqual(crumbSplit("docs"), ["docs"], "a single segment");
assert.deepEqual(crumbSplit(""), [], "an empty trail");
assert.deepEqual(crumbSplit("///"), [], "slashes only");
assert.equal(crumbJoin(["docs", "api"]), "docs/api", "one slash between");
assert.equal(crumbJoin(["docs", "", "api"]), "docs/api", "an empty part is dropped");
assert.equal(crumbJoin([]), "", "nothing joins to nothing");
console.log("ok");
