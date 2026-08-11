import assert from "node:assert/strict";
import { lineNumber } from "./solution.ts";

assert.equal(lineNumber("a\nb"), "1: a\n2: b", "two lines numbered");
assert.equal(lineNumber("only"), "1: only", "one line");
assert.equal(lineNumber(""), "", "nothing to number");
assert.equal(lineNumber("a\n\nc"), "1: a\n2: \n3: c", "an empty line still counts");
assert.equal(lineNumber("x\ny\nz"), "1: x\n2: y\n3: z", "three lines");
assert.equal(lineNumber("\n"), "1: \n2: ", "a lone break makes two lines");
console.log("ok");
