import assert from "node:assert/strict";
import { foldCoercionChain } from "./solution.ts";

assert.deepEqual(
  foldCoercionChain("bit", [{ op: "join", type: "bit" }]),
  ["whole"],
  "a pair of bits joins to a whole",
);
assert.deepEqual(
  foldCoercionChain("whole", [{ op: "join", type: "ratio" }]),
  ["ratio"],
  "a ratio on either side wins the join",
);
assert.deepEqual(
  foldCoercionChain("ratio", [{ op: "join", type: "word" }]),
  ["word"],
  "a word swallows the join",
);
assert.deepEqual(
  foldCoercionChain("word", [{ op: "join", type: "bit" }]),
  ["word"],
  "the word may stand on the running side",
);
assert.deepEqual(
  foldCoercionChain("whole", [{ op: "weigh", type: "ratio" }]),
  ["bit"],
  "weighing two numbers gives a bit",
);
assert.deepEqual(
  foldCoercionChain("word", [{ op: "weigh", type: "word" }]),
  ["bit"],
  "weighing two words gives a bit",
);
assert.deepEqual(
  foldCoercionChain("bit", [
    { op: "join", type: "bit" },
    { op: "join", type: "ratio" },
    { op: "weigh", type: "whole" },
    { op: "join", type: "word" },
  ]),
  ["whole", "ratio", "bit", "word"],
  "the running type is reported after every term",
);
assert.deepEqual(foldCoercionChain("empty", []), [], "a chain of no terms reports nothing");
assert.deepEqual(
  foldCoercionChain("bit", [
    { op: "weigh", type: "bit" },
    { op: "join", type: "bit" },
  ]),
  ["bit", "whole"],
  "a weigh leaves a bit for the next term to join",
);

const rejects = (start, terms) => {
  try {
    foldCoercionChain(start, terms);
  } catch {
    return true;
  }
  return false;
};

assert.ok(rejects("empty", [{ op: "join", type: "bit" }]), "an empty cannot be joined");
assert.ok(rejects("bit", [{ op: "join", type: "empty" }]), "an empty cannot be joined from the term side");
assert.ok(rejects("word", [{ op: "weigh", type: "empty" }]), "an empty cannot be weighed");
assert.ok(rejects("word", [{ op: "weigh", type: "whole" }]), "a word cannot be weighed against a number");
assert.ok(rejects("ratio", [{ op: "weigh", type: "word" }]), "nor a number against a word");
assert.ok(rejects("rune", []), "an unknown starting type is refused");
assert.ok(rejects("bit", [{ op: "join", type: "rune" }]), "an unknown term type is refused");
assert.ok(rejects("bit", [{ op: "blend", type: "bit" }]), "an unknown op is refused");
assert.ok(rejects("bit", "terms"), "terms that are not a list are refused");
assert.ok(rejects("bit", [["join", "bit"]]), "a term that is not a mapping is refused");
console.log("ok");
