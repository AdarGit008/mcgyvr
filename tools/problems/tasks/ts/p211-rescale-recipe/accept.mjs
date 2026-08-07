import assert from "node:assert/strict";
import { rescaleRecipe } from "./solution.ts";

assert.deepEqual(
  rescaleRecipe(["1 tsp salt"], 3, 2),
  ["1 1/2 tsp salt"],
  "a whole count can grow into a whole count and a part",
);
assert.deepEqual(
  rescaleRecipe(["1/3 cup oats"], 1, 1),
  ["3/8 cup oats"],
  "a third of a cup lands on the nearest eighth",
);
assert.deepEqual(
  rescaleRecipe(["2 egg white"], 1, 2),
  ["1 egg white"],
  "eggs round on a whole",
);
assert.deepEqual(
  rescaleRecipe(["1 tsp salt"], 1, 100),
  ["1/4 tsp salt"],
  "nothing at all becomes one grain",
);
assert.deepEqual(
  rescaleRecipe(["1 tsp salt"], 1, 8),
  ["1/4 tsp salt"],
  "exactly half a grain rounds upward",
);
assert.deepEqual(
  rescaleRecipe(["3 g yeast"], 1, 2),
  ["2 g yeast"],
  "one and a half grams rounds up to two",
);
assert.deepEqual(
  rescaleRecipe(["1 1/2 cup flour"], 2, 1),
  ["3 cup flour"],
  "a mixed amount can double into a bare count",
);
assert.deepEqual(
  rescaleRecipe(["2 tbsp oil"], 1, 3),
  ["1/2 tbsp oil"],
  "two thirds of a tablespoon falls to a half",
);
assert.deepEqual(
  rescaleRecipe(["3/4 cup sugar"], 3, 1),
  ["2 1/4 cup sugar"],
  "a part can grow past one and be respelled",
);
assert.deepEqual(
  rescaleRecipe(["1/4 cup cocoa"], 4, 1),
  ["1 cup cocoa"],
  "a part can land exactly on a whole",
);
assert.deepEqual(
  rescaleRecipe(["1 tsp salt", "2 egg white", "1/2 cup milk"], 3, 2),
  ["1 1/2 tsp salt", "3 egg white", "3/4 cup milk"],
  "every row is pulled by the same ratio",
);
assert.deepEqual(rescaleRecipe([], 2, 1), [], "an empty recipe stays empty");
assert.throws(() => rescaleRecipe("1 tsp salt", 1, 1), Error, "a recipe that is not a list is rejected");
assert.throws(() => rescaleRecipe([7], 1, 1), Error, "a row that is not a string is rejected");
assert.throws(() => rescaleRecipe(["2 cups salt"], 1, 1), Error, "an unknown unit is rejected");
assert.throws(() => rescaleRecipe(["0 tsp salt"], 1, 1), Error, "a whole count of zero is rejected");
assert.throws(() => rescaleRecipe(["01 tsp salt"], 1, 1), Error, "a padded count is rejected");
assert.throws(() => rescaleRecipe(["2/4 tsp salt"], 1, 1), Error, "a part that is not reduced is rejected");
assert.throws(() => rescaleRecipe(["5/4 tsp salt"], 1, 1), Error, "a part that is not below one is rejected");
assert.throws(() => rescaleRecipe(["1 2 tsp salt"], 1, 1), Error, "a whole count followed by another is rejected");
assert.throws(() => rescaleRecipe(["2 tsp salt2"], 1, 1), Error, "a digit in the ingredient is rejected");
assert.throws(() => rescaleRecipe(["2 tsp  salt"], 1, 1), Error, "a doubled space is rejected");
assert.throws(() => rescaleRecipe(["1 tsp salt", "2 tsp salt"], 1, 1), Error, "two rows carrying one ingredient are rejected");
assert.throws(() => rescaleRecipe(["1 tsp salt"], 0, 1), Error, "a numerator of zero is rejected");
assert.throws(() => rescaleRecipe(["1 tsp salt"], 1, 0), Error, "a denominator of zero is rejected");
assert.throws(() => rescaleRecipe(["1 tsp salt"], 1.5, 1), Error, "a fractional ratio side is rejected");
assert.throws(() => rescaleRecipe(["1 tsp salt"], 1, "2"), Error, "a ratio side that is not a number is rejected");
console.log("ok");
