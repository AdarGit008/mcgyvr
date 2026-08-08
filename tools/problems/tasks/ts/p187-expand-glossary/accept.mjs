import assert from "node:assert/strict";
import { expandGlossary } from "./solution.ts";

assert.equal(expandGlossary(["1=red", "!1"]), "red", "one store, one send");
assert.equal(expandGlossary([]), "", "a script with no lines sends nothing");
assert.equal(
  expandGlossary(["1=red", "2=big {1} ball", "!2"]),
  "big red ball",
  "one splice inside a body",
);
assert.equal(
  expandGlossary(["1=red", "2=big {1}", "3={2} ball", "!3"]),
  "big red ball",
  "a body settled from a body that was itself settled",
);
assert.equal(
  expandGlossary(["1={{x}}", "!1"]),
  "{x}",
  "doubled braces are literal, not a splice",
);
assert.equal(expandGlossary(["1=ab", "!1", "!1"]), "abab", "the same slot sent twice");
assert.equal(
  expandGlossary(["1=a", "!1", "2=b", "!2"]),
  "ab",
  "sends join in the order they appear",
);
assert.equal(
  expandGlossary(["7=x", "12={7}{7}", "!12"]),
  "xx",
  "multi-digit slot numbers and back-to-back splices",
);
assert.equal(
  expandGlossary(["1=a", "2={1}}}", "!2"]),
  "a}",
  "a doubled closing brace right after a splice",
);
assert.equal(expandGlossary(["1=", "2=[{1}]", "!2"]), "[]", "an empty body splices");

const rejects = (script) => {
  try {
    expandGlossary(script);
  } catch {
    return true;
  }
  return false;
};

assert.ok(rejects(["1={2}", "2=x", "!1"]), "a splice naming a later slot");
assert.ok(rejects(["1=a", "1=b", "!1"]), "a slot stored twice");
assert.ok(rejects(["!1"]), "a send of a slot never stored");
assert.ok(rejects(["hello"]), "a line of neither kind");
assert.ok(rejects(["01=a", "!01"]), "a padded slot number");
assert.ok(rejects(["0=a", "!0"]), "a slot number of zero");
assert.ok(rejects(["1=a", "2={1", "!2"]), "a brace never closed");
assert.ok(rejects(["1=a}", "!1"]), "a closing brace with nothing open");
assert.ok(rejects("1=a"), "a script that is not a list");
console.log("ok");
