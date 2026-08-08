import assert from "node:assert/strict";
import { criticalChainName } from "./solution.ts";

assert.equal(
  criticalChainName([
    { label: "a", hours: 3, needs: [] },
    { label: "b", hours: 2, needs: ["a"] },
    { label: "c", hours: 4, needs: ["a"] },
    { label: "d", hours: 1, needs: ["b", "c"] },
  ]),
  "a>c>d",
  "the heavier arm of a diamond",
);
assert.equal(
  criticalChainName([{ label: "solo", hours: 5, needs: [] }]),
  "solo",
  "one step is its own run",
);
assert.equal(
  criticalChainName([
    { label: "x", hours: 2, needs: [] },
    { label: "y", hours: 5, needs: [] },
  ]),
  "y",
  "two steps with nothing linking them",
);
assert.equal(
  criticalChainName([
    { label: "zip", hours: 1, needs: [] },
    { label: "arc", hours: 2, needs: ["zip"] },
    { label: "mid", hours: 3, needs: ["arc"] },
  ]),
  "zip>arc>mid",
  "a run reported in link order, not list order",
);
assert.equal(
  criticalChainName([
    { label: "p", hours: 1, needs: [] },
    { label: "q", hours: 2, needs: ["p"] },
    { label: "r", hours: 2, needs: ["p"] },
  ]),
  "p>q",
  "equal weights settled by the labels",
);
assert.equal(
  criticalChainName([
    { label: "aa", hours: 4, needs: [] },
    { label: "ab", hours: 1, needs: [] },
    { label: "ac", hours: 3, needs: ["ab"] },
  ]),
  "aa",
  "a one-step run can beat a two-step run of the same weight",
);
assert.throws(() => criticalChainName("a"), Error, "not a list");
assert.throws(() => criticalChainName([]), Error, "an empty job");
assert.throws(() => criticalChainName(["a"]), Error, "a step that is not a mapping");
assert.throws(
  () => criticalChainName([{ label: "", hours: 1, needs: [] }]),
  Error,
  "an empty label",
);
assert.throws(
  () => criticalChainName([
    { label: "a", hours: 1, needs: [] },
    { label: "a", hours: 2, needs: [] },
  ]),
  Error,
  "two steps with the same label",
);
assert.throws(
  () => criticalChainName([{ label: "a", hours: 0, needs: [] }]),
  Error,
  "zero hours",
);
assert.throws(
  () => criticalChainName([{ label: "a", hours: 2.5, needs: [] }]),
  Error,
  "fractional hours",
);
assert.throws(
  () => criticalChainName([{ label: "a", hours: 1, needs: "b" }]),
  Error,
  "a needs list that is not a list",
);
assert.throws(
  () => criticalChainName([{ label: "a", hours: 1, needs: ["ghost"] }]),
  Error,
  "a needs entry matching nothing",
);
assert.throws(
  () => criticalChainName([{ label: "a", hours: 1, needs: ["a"] }]),
  Error,
  "a step needing itself",
);
assert.throws(
  () => criticalChainName([
    { label: "a", hours: 1, needs: ["b"] },
    { label: "b", hours: 1, needs: ["a"] },
  ]),
  Error,
  "a ring",
);
console.log("ok");
