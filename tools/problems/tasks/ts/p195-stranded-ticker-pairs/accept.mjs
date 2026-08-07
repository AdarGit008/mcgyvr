import assert from "node:assert/strict";
import { strandedTickerPairs } from "./solution.ts";

assert.deepEqual(
  strandedTickerPairs([["AAA", "BBB"]]),
  ["BBB>AAA"],
  "one leg leaves the return trip stranded"
);

assert.deepEqual(
  strandedTickerPairs([
    ["AAA", "BBB"],
    ["BBB", "AAA"],
  ]),
  [],
  "a two-leg loop strands nothing"
);

assert.deepEqual(
  strandedTickerPairs([
    ["AAA", "BBB"],
    ["BBB", "CCC"],
    ["CCC", "AAA"],
  ]),
  [],
  "a three-leg loop reaches everything"
);

assert.deepEqual(
  strandedTickerPairs([
    ["AAA", "BBB"],
    ["BBB", "CCC"],
  ]),
  ["BBB>AAA", "CCC>AAA", "CCC>BBB"],
  "a chain routes downstream only"
);

assert.deepEqual(
  strandedTickerPairs([
    ["CCC", "DDD"],
    ["AAA", "BBB"],
  ]),
  [
    "AAA>CCC",
    "AAA>DDD",
    "BBB>AAA",
    "BBB>CCC",
    "BBB>DDD",
    "CCC>AAA",
    "CCC>BBB",
    "DDD>AAA",
    "DDD>BBB",
    "DDD>CCC",
  ],
  "two islands strand every couple that crosses between them"
);

assert.deepEqual(
  strandedTickerPairs([
    ["AAA", "HUB"],
    ["HUB", "AAA"],
    ["BBB", "HUB"],
    ["HUB", "BBB"],
  ]),
  [],
  "a hub with legs both ways joins its spokes"
);

assert.deepEqual(
  strandedTickerPairs([
    ["AAA", "SSS"],
    ["BBB", "SSS"],
  ]),
  ["AAA>BBB", "BBB>AAA", "SSS>AAA", "SSS>BBB"],
  "a ticker everyone buys into reaches nobody"
);

assert.throws(() => strandedTickerPairs([]), Error, "no legs at all is rejected");
assert.throws(
  () => strandedTickerPairs([["AAA", "BBB", "CCC"]]),
  Error,
  "a three-element leg is rejected"
);
assert.throws(
  () => strandedTickerPairs([["AAA", ""]]),
  Error,
  "an empty ticker is rejected"
);
assert.throws(
  () => strandedTickerPairs([["AAA", 7]]),
  Error,
  "a ticker that is not a string is rejected"
);
assert.throws(
  () => strandedTickerPairs([["AAA", "AAA"]]),
  Error,
  "a leg on one ticker is rejected"
);
assert.throws(
  () =>
    strandedTickerPairs([
      ["AAA", "BBB"],
      ["AAA", "BBB"],
    ]),
  Error,
  "a leg published twice is rejected"
);

console.log("ok");
