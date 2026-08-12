import assert from "node:assert/strict";
import { pickSnippet } from "./solution.ts";

const notes = [
  "The harbour closes at dusk.",
  "A ripe mango fell near the harbour wall.",
  "Mango season ends soon.",
];

assert.equal(
  pickSnippet("ripe mango", notes),
  notes[1],
  "the sentence covering more query words wins",
);
assert.equal(pickSnippet("RIPE", notes), notes[1], "matching ignores case");
assert.equal(pickSnippet("season", notes), notes[2], "one covered word can be enough");
assert.equal(
  pickSnippet("ripe mango", ["mango mango mango stand", "ripe mango juice"]),
  "ripe mango juice",
  "distinct coverage beats sheer repetition",
);
assert.equal(
  pickSnippet("cat", ["The cargo catalog is heavy.", "A cat naps."]),
  "A cat naps.",
  "only whole words match",
);
assert.equal(
  pickSnippet("spice", ["The spice market opens early today.", "Spice sells fast."]),
  "Spice sells fast.",
  "a tie goes to the sentence with fewer words",
);
assert.equal(
  pickSnippet("lamp", ["Old lamp glows.", "New lamp hums."]),
  "Old lamp glows.",
  "a full tie falls to the earlier sentence",
);
assert.throws(() => pickSnippet(42, notes), Error, "a non-string query is rejected");
assert.throws(() => pickSnippet("?!", notes), Error, "a wordless query is rejected");
assert.throws(() => pickSnippet("dusk", []), Error, "an empty sentence list is rejected");
assert.throws(
  () => pickSnippet("dusk", "not a list"),
  Error,
  "sentences must arrive as a list",
);
assert.throws(
  () => pickSnippet("ok", ["ok here", 7]),
  Error,
  "a non-string sentence is rejected",
);
assert.throws(
  () => pickSnippet("ok", ["ok here", ""]),
  Error,
  "an empty sentence is rejected",
);
assert.throws(() => pickSnippet("quartz", notes), Error, "a query nothing matches is rejected");
console.log("ok");
