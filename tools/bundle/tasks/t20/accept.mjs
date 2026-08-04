import assert from "node:assert/strict";
import { parseConfig } from "./solution.ts";

const config = parseConfig("a=1\nb=2");
assert.equal(config.a, "1", "first pair");
assert.equal(config.b, "2", "second pair");

assert.deepEqual({ ...parseConfig("") }, {}, "empty text");
assert.deepEqual({ ...parseConfig("\n\n") }, {}, "blank lines are ignored");
assert.deepEqual({ ...parseConfig("# a comment\nx=1") }, { x: "1" }, "comments are ignored");
assert.deepEqual({ ...parseConfig("   # indented comment\nx=1") }, { x: "1" }, "indented comment");
assert.deepEqual({ ...parseConfig("  key  =  value  ") }, { key: "value" }, "whitespace trimmed");
assert.deepEqual({ ...parseConfig("url=http://h/?a=1") }, { url: "http://h/?a=1" }, "= in the value");
assert.deepEqual({ ...parseConfig("empty=") }, { empty: "" }, "an empty value is allowed");
assert.deepEqual({ ...parseConfig("a=1\na=2") }, { a: "2" }, "a repeated key: last wins");

assert.throws(() => parseConfig("nosign"), Error, "a line with no = throws");
assert.throws(() => parseConfig("=value"), Error, "an empty key throws");

// "__proto__" must land as data. An ordinary object literal would silently
// drop it, or worse, walk the prototype chain.
const polluted = parseConfig("__proto__=x\nsafe=y");
assert.equal(polluted.safe, "y", "the ordinary key still parses");
assert.equal(
  Object.getOwnPropertyDescriptor(polluted, "__proto__")?.value,
  "x",
  "__proto__ must be stored as an own data property",
);
assert.equal({}.polluted, undefined, "Object.prototype must be untouched");
