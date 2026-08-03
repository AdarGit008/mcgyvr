import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { celsiusToFahrenheit, celsiusToKelvin } from "./solution.ts";

assert.equal(celsiusToFahrenheit(0), 32, "freezing in fahrenheit");
assert.equal(celsiusToFahrenheit(100), 212, "boiling in fahrenheit");
assert.equal(celsiusToFahrenheit(-40), -40, "the crossover point");
assert.equal(celsiusToKelvin(0), 273.15, "freezing in kelvin");
assert.equal(celsiusToKelvin(-273.15), 0, "absolute zero is allowed");

for (const bad of [NaN, Infinity, -Infinity, "0"]) {
  assert.throws(() => celsiusToFahrenheit(bad), Error, `fahrenheit rejects ${String(bad)}`);
  assert.throws(() => celsiusToKelvin(bad), Error, `kelvin rejects ${String(bad)}`);
}
assert.throws(() => celsiusToFahrenheit(-300), Error, "below absolute zero, fahrenheit");
assert.throws(() => celsiusToKelvin(-300), Error, "below absolute zero, kelvin");

// Written once, not twice — the whole point of the change.
const source = readFileSync(new URL("./solution.ts", import.meta.url), "utf8");
const occurrences = source.split("must be a finite number").length - 1;
assert.equal(occurrences, 1, "the shared validation must be written exactly once");
