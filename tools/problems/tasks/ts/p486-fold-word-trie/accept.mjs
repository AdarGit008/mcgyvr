import assert from "node:assert/strict";
import { foldWordTrie } from "./solution.ts";

assert.equal(
  foldWordTrie(["ant", "ante", "anvil", "bee"]),
  "an(t(-|e)|vil)|bee",
  "the worked example squeezes as stated",
);
assert.equal(
  foldWordTrie(["car", "card", "care", "cat"]),
  "ca(r(-|d|e)|t)",
  "the second worked example squeezes as stated",
);
assert.equal(foldWordTrie(["a"]), "a", "one word squeezes to itself");
assert.equal(foldWordTrie(["quill"]), "quill", "a long lone word keeps its letters");
assert.equal(
  foldWordTrie(["z", "b", "a"]),
  "a|b|z",
  "runs come out in rising order whatever order they arrived in",
);
assert.equal(foldWordTrie(["a", "ab"]), "a(-|b)", "a word that is the whole opening becomes a dash");
assert.equal(foldWordTrie(["ac", "ab"]), "a(b|c)", "two tails need no dash");
assert.equal(
  foldWordTrie(["dust", "dog", "do", "doze", "dot"]),
  "d(o(-|g|t|ze)|ust)",
  "the recipe applies again inside a bracket",
);
assert.equal(
  foldWordTrie(["ox", "oxen", "oxide", "pea", "peat", "pear"]),
  "ox(-|en|ide)|pea(-|r|t)",
  "two runs each carry their own dash",
);
assert.equal(
  foldWordTrie(["mist", "mister", "mistle", "misty"]),
  "mist(-|er|le|y)",
  "a shared opening may run the whole length of a word",
);

assert.throws(() => foldWordTrie("ant"), Error, "words must be a list");
assert.throws(() => foldWordTrie([]), Error, "an empty list is rejected");
assert.throws(() => foldWordTrie(["ant", 5]), Error, "a word must be a string");
assert.throws(() => foldWordTrie(["ant", ""]), Error, "an empty word is rejected");
assert.throws(() => foldWordTrie(["Ant"]), Error, "a capital letter is rejected");
assert.throws(() => foldWordTrie(["an-t"]), Error, "a dash inside a word is rejected");
assert.throws(() => foldWordTrie(["ant", "ant"]), Error, "a repeated word is rejected");
console.log("ok");
