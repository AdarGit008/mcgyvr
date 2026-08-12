import assert from "node:assert/strict";
import { crustSlice } from "./solution.ts";

assert.equal(crustSlice("notes.txt"), "notes", "the extension comes off");
assert.equal(crustSlice("archive.tar.gz"), "archive.tar", "only the final dot cuts");
assert.equal(crustSlice("README"), "README", "no dot, no cut");
assert.equal(crustSlice(".gitignore"), ".gitignore", "a hidden name is untouched");
assert.equal(crustSlice("trailing."), "trailing", "a final dot still cuts");
assert.equal(crustSlice(""), "", "empty stays empty");
console.log("ok");
