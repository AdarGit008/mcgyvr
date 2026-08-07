import assert from "node:assert/strict";
import { countSentences } from "./solution.ts";

assert.equal(countSentences("It rained. It stopped.", []), 2, "two endings");
assert.equal(
  countSentences("Dr. Vance paid. Nobody argued.", ["Dr"]),
  2,
  "a supplied title makes the stop inert",
);
assert.equal(
  countSentences("Dr. Vance paid. Nobody argued.", []),
  3,
  "with no titles the same stop ends a sentence",
);
assert.equal(
  countSentences("Dr. Vance paid. Nobody argued.", ["dr"]),
  3,
  "titles are compared with case respected",
);
assert.equal(
  countSentences("The dial read 12.5 today.", []),
  1,
  "a stop between digits is inert",
);
assert.equal(
  countSentences("Ask J. Vance first.", []),
  1,
  "a single capital before the stop marks an initial",
);
assert.equal(
  countSentences("Check [the note. it helps] now. Go.", []),
  2,
  "square brackets shelter their stops",
);
assert.equal(
  countSentences("She said 'Wait. Stop.' then left.", []),
  1,
  "an aside shelters its stops",
);
assert.equal(countSentences("Really?! Truly.", []), 2, "a run ends one sentence");
assert.equal(
  countSentences("Bang! No stop at the end", []),
  2,
  "a trailing fragment counts as one more",
);
assert.equal(countSentences("Trailing words", []), 1, "no marks at all");
assert.equal(countSentences("", []), 0, "empty prose");
assert.equal(countSentences("     ", []), 0, "only spaces");
assert.throws(() => countSentences(7, []), Error, "prose must be a string");
assert.throws(() => countSentences("Hi.", "Dr"), Error, "titles must be a list");
assert.throws(() => countSentences("Hi.", [""]), Error, "an empty title");
assert.throws(() => countSentences("Hi.", ["Dr."]), Error, "a title with a stop");
assert.throws(() => countSentences("Hi] there.", []), Error, "closed with no opener");
assert.throws(() => countSentences("Hi [there.", []), Error, "left open");
assert.throws(() => countSentences("Hi 'there.", []), Error, "aside left open");
console.log("ok");
