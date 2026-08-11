import assert from "node:assert/strict";
import { linkFind } from "./solution.ts";

assert.deepEqual(linkFind("a[one]b", "[", "]"), ["one"], "one piece between markers");
assert.deepEqual(linkFind("[a][b]", "[", "]"), ["a", "b"], "two pieces");
assert.deepEqual(linkFind("plain", "[", "]"), [], "no markers at all");
assert.deepEqual(linkFind("", "[", "]"), [], "an empty line");
assert.deepEqual(linkFind("[open", "[", "]"), [], "an opening never closed");
assert.deepEqual(linkFind("[]", "[", "]"), [""], "an empty piece still counts");
console.log("ok");
