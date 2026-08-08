import assert from "node:assert/strict";
import { expandMacroCalls } from "./solution.ts";

const book = [
  { name: "greet", arity: 1, body: "hello #1!" },
  { name: "pair", arity: 2, body: "[#1|#2]" },
  { name: "dash", arity: 0, body: "--" },
  { name: "twice", arity: 1, body: "#1#1" },
  { name: "loop", arity: 0, body: "@loop" },
  { name: "hash", arity: 0, body: "##" },
  { name: "bad", arity: 1, body: "#2" },
];

assert.equal(expandMacroCalls(book, "@greet{world}", 3), "hello world!", "one argument fills one place");
assert.equal(expandMacroCalls(book, "@dash", 3), "--", "a bare name calls a macro of no arity");
assert.equal(expandMacroCalls(book, "@pair{a|b}", 3), "[a|b]", "a bar parts two arguments");
assert.equal(expandMacroCalls(book, "@twice{@dash}", 3), "----", "the filled body is walked again");
assert.equal(expandMacroCalls(book, "@@ and @dash", 3), "@ and --", "doubled at signs stand for one");
assert.equal(expandMacroCalls(book, "@hash", 3), "#", "doubled hashes stand for one");
assert.equal(
  expandMacroCalls(book, "@greet{@greet{x}}", 3),
  "hello hello x!!",
  "a call may stand inside an argument",
);
assert.equal(
  expandMacroCalls(book, "@greet{a{b|c}d}", 3),
  "hello a{b|c}d!",
  "a bar buried in braces parts nothing",
);
assert.equal(expandMacroCalls(book, "@greet{}", 3), "hello !", "empty braces carry one empty argument");
assert.equal(
  expandMacroCalls(book, "plain text | with } odd # marks", 3),
  "plain text | with } odd # marks",
  "text outside a call is copied across",
);
assert.equal(expandMacroCalls(book, "", 3), "", "an empty source walks to nothing");
assert.equal(expandMacroCalls(book, "@twice{@twice{x}}", 3), "xxxx", "two nested doublings");
assert.equal(expandMacroCalls(book, "@dash", 1), "--", "a bound of one allows one step");

assert.throws(() => expandMacroCalls(book, "@nope", 3), Error, "an undeclared macro is refused");
assert.throws(
  () => expandMacroCalls(book, "@greet{a|b}", 3),
  Error,
  "two arguments for an arity of one are refused",
);
assert.throws(
  () => expandMacroCalls(book, "@dash{}", 3),
  Error,
  "one argument for an arity of nought is refused",
);
assert.throws(() => expandMacroCalls(book, "@greet{a", 3), Error, "an unclosed brace is refused");
assert.throws(() => expandMacroCalls(book, "@", 3), Error, "a trailing at sign is refused");
assert.throws(() => expandMacroCalls(book, "@1x", 3), Error, "a name opening with a digit is refused");
assert.throws(() => expandMacroCalls(book, "@bad{x}", 3), Error, "a body reaching past its arity is refused");
assert.throws(
  () => expandMacroCalls(book, "@twice{@dash}", 1),
  Error,
  "a nested call under a bound of one is refused",
);
assert.throws(() => expandMacroCalls(book, "@loop", 5), Error, "a macro calling itself is refused");
assert.throws(() => expandMacroCalls("no", "x", 3), Error, "the macros must be a list");
assert.throws(() => expandMacroCalls([7], "x", 3), Error, "a macro must be a record");
assert.throws(
  () => expandMacroCalls([{ name: "a", arity: 0 }], "x", 3),
  Error,
  "a macro missing a key is refused",
);
assert.throws(
  () => expandMacroCalls([{ name: "A", arity: 0, body: "" }], "x", 3),
  Error,
  "a capital in a name is refused",
);
assert.throws(
  () => expandMacroCalls(
    [{ name: "a", arity: 0, body: "" }, { name: "a", arity: 1, body: "#1" }],
    "x",
    3,
  ),
  Error,
  "a repeated name is refused",
);
assert.throws(
  () => expandMacroCalls([{ name: "a", arity: 10, body: "" }], "x", 3),
  Error,
  "an arity of ten is refused",
);
assert.throws(
  () => expandMacroCalls([{ name: "a", arity: 0, body: 5 }], "x", 3),
  Error,
  "a body that is not a string is refused",
);
assert.throws(() => expandMacroCalls(book, 5, 3), Error, "a source that is not a string is refused");
assert.throws(() => expandMacroCalls(book, "x", 0), Error, "a bound of nought is refused");
console.log("ok");
