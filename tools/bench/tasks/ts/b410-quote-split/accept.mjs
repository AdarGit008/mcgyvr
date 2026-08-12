import assert from "node:assert/strict";
import { inQuote, quoteSplit } from "./solution.ts";

assert.equal(inQuote('"'), true, "the quotation mark");
assert.equal(inQuote("a"), false, "an ordinary character");
assert.deepEqual(quoteSplit("a,b"), ["a", "b"], "a plain break");
assert.deepEqual(quoteSplit('"a,b"'), ['"a,b"'], "a quoted comma does not break");
assert.deepEqual(quoteSplit(""), [""], "an empty line is one empty piece");
assert.deepEqual(
  quoteSplit('a,"b,c",d'),
  ["a", '"b,c"', "d"],
  "a quoted piece among plain ones",
);
console.log("ok");
