import assert from "node:assert/strict";
import { scaleBatchLines } from "./solution.ts";

assert.deepEqual(
  scaleBatchLines(["200 g flour", "100 ml milk", "2 each egg"], 3, 2),
  ["300 g flour", "150 ml milk", "3 each egg"],
  "a clean ratio leaves every measure on its tick",
);
assert.deepEqual(
  scaleBatchLines(["10 ml oil"], 1, 4),
  ["5 ml oil"],
  "a value halfway between ticks goes up",
);
assert.deepEqual(
  scaleBatchLines(["1 g salt"], 1, 3),
  ["1 g salt"],
  "what settles to nothing becomes one tick",
);
assert.deepEqual(
  scaleBatchLines(["100 g sugar"], 2, 3),
  ["67 g sugar"],
  "two thirds of a hundred settles upward",
);
assert.deepEqual(
  scaleBatchLines(["7 ml vanilla extract"], 1, 1),
  ["5 ml vanilla extract"],
  "the ml tick binds even when the batch does not change",
);
assert.deepEqual(
  scaleBatchLines(["3 ml tonic"], 1, 1),
  ["5 ml tonic"],
  "a small ml quantity is lifted to one tick",
);
assert.deepEqual(
  scaleBatchLines([], 4, 1),
  [],
  "an empty sheet stays empty",
);
assert.deepEqual(
  scaleBatchLines(["3 each bay leaf", "40 g brown sugar"], 7, 3),
  ["7 each bay leaf", "93 g brown sugar"],
  "names of several words survive the rewrite",
);
assert.throws(() => scaleBatchLines("200 g flour", 1, 1), Error, "a sheet that is not a list is rejected");
assert.throws(() => scaleBatchLines([7], 1, 1), Error, "a line that is not a string is rejected");
assert.throws(() => scaleBatchLines(["200 flour"], 1, 1), Error, "a two part line is rejected");
assert.throws(() => scaleBatchLines(["0 g flour"], 1, 1), Error, "a quantity of zero is rejected");
assert.throws(() => scaleBatchLines(["01 g flour"], 1, 1), Error, "a padded quantity is rejected");
assert.throws(() => scaleBatchLines(["200 kg flour"], 1, 1), Error, "an unknown measure is rejected");
assert.throws(() => scaleBatchLines(["200 g flour2"], 1, 1), Error, "a digit in the name is rejected");
assert.throws(() => scaleBatchLines(["200 g  flour"], 1, 1), Error, "a doubled space is rejected");
assert.throws(() => scaleBatchLines(["1 g salt", "2 g salt"], 1, 1), Error, "two lines naming the same stuff are rejected");
assert.throws(() => scaleBatchLines(["1 g salt"], 0, 1), Error, "a wanted count of zero is rejected");
assert.throws(() => scaleBatchLines(["1 g salt"], 1, 0), Error, "a written count of zero is rejected");
assert.throws(() => scaleBatchLines(["1 g salt"], 1.5, 1), Error, "a fractional portion count is rejected");
assert.throws(() => scaleBatchLines(["1 g salt"], 1, "2"), Error, "a portion count that is not a number is rejected");
console.log("ok");
