import assert from "node:assert/strict";
import { pickFlagVariant } from "./solution.ts";

const flag = {
  rules: [
    { match: [["plan", "is", "gold"]], split: [["full", 100]] },
    {
      match: [
        ["region", "in", ["eu", "uk"]],
        ["plan", "not", "free"],
      ],
      split: [
        ["full", 25],
        ["lite", 75],
      ],
    },
    {
      match: [],
      split: [
        ["full", 10],
        ["off", 0],
        ["lite", 90],
      ],
    },
  ],
  fallback: "off",
};

assert.deepEqual(
  pickFlagVariant(flag, { traits: { plan: "gold" }, bucket: 99 }),
  { variant: "full", rule: 0 },
  "the first rule takes a gold plan whatever its bucket",
);
assert.deepEqual(
  pickFlagVariant(flag, { traits: { region: "eu", plan: "pro" }, bucket: 24 }),
  { variant: "full", rule: 1 },
  "the last bucket inside the first share",
);
assert.deepEqual(
  pickFlagVariant(flag, { traits: { region: "eu", plan: "pro" }, bucket: 25 }),
  { variant: "lite", rule: 1 },
  "one past the running total crosses to the next entry",
);
assert.deepEqual(
  pickFlagVariant(flag, { traits: { region: "eu" }, bucket: 0 }),
  { variant: "full", rule: 1 },
  "a missing trait satisfies a not test",
);
assert.deepEqual(
  pickFlagVariant(flag, { traits: { region: "eu", plan: "free" }, bucket: 0 }),
  { variant: "full", rule: 2 },
  "a free plan falls past the second rule",
);
assert.deepEqual(
  pickFlagVariant(flag, { traits: { region: "us" }, bucket: 10 }),
  { variant: "lite", rule: 2 },
  "the zero share is stepped over",
);
assert.deepEqual(
  pickFlagVariant(flag, { traits: {}, bucket: 99 }),
  { variant: "lite", rule: 2 },
  "the catch-all rule takes a subject with no traits at all",
);
assert.deepEqual(
  pickFlagVariant({ rules: [], fallback: "held" }, { traits: {}, bucket: 0 }),
  { variant: "held", rule: -1 },
  "a flag with no rules answers with its fallback",
);
assert.deepEqual(
  pickFlagVariant(
    {
      rules: [{ match: [["plan", "is", "gold"]], split: [["full", 100]] }],
      fallback: "held",
    },
    { traits: { plan: "pro" }, bucket: 0 },
  ),
  { variant: "held", rule: -1 },
  "no rule taking the subject falls to the fallback",
);

const bad = { traits: {}, bucket: 0 };
assert.throws(() => pickFlagVariant({ rules: [] }, bad), Error, "a flag without a fallback is rejected");
assert.throws(
  () => pickFlagVariant({ rules: {}, fallback: "off" }, bad),
  Error,
  "rules that are not a list are rejected",
);
assert.throws(
  () =>
    pickFlagVariant(
      { rules: [{ match: [], split: [["a", 60], ["b", 30]] }], fallback: "off" },
      bad,
    ),
  Error,
  "shares adding to 90 are rejected",
);
assert.throws(
  () =>
    pickFlagVariant(
      { rules: [{ match: [], split: [["a", 110], ["b", -10]] }], fallback: "off" },
      bad,
    ),
  Error,
  "a negative share is rejected",
);
assert.throws(
  () =>
    pickFlagVariant(
      { rules: [{ match: [], split: [["a", 50], ["a", 50]] }], fallback: "off" },
      bad,
    ),
  Error,
  "a variant named twice in one split is rejected",
);
assert.throws(
  () => pickFlagVariant({ rules: [{ match: [], split: [] }], fallback: "off" }, bad),
  Error,
  "an empty split is rejected",
);
assert.throws(
  () =>
    pickFlagVariant(
      { rules: [{ match: [["plan", "over", "gold"]], split: [["a", 100]] }], fallback: "off" },
      bad,
    ),
  Error,
  "an unknown test word is rejected",
);
assert.throws(
  () =>
    pickFlagVariant(
      { rules: [{ match: [["plan", "in", []]], split: [["a", 100]] }], fallback: "off" },
      bad,
    ),
  Error,
  "an in test with nothing listed is rejected",
);
assert.throws(
  () =>
    pickFlagVariant(
      { rules: [{ match: [["plan", "is"]], split: [["a", 100]] }], fallback: "off" },
      bad,
    ),
  Error,
  "a two-element test is rejected",
);
assert.throws(
  () => pickFlagVariant(flag, { traits: {}, bucket: 100 }),
  Error,
  "a bucket of 100 is rejected",
);
assert.throws(
  () => pickFlagVariant(flag, { traits: {}, bucket: -1 }),
  Error,
  "a negative bucket is rejected",
);
assert.throws(
  () => pickFlagVariant(flag, { traits: { plan: 7 }, bucket: 0 }),
  Error,
  "a trait holding a number is rejected",
);
assert.throws(
  () => pickFlagVariant(flag, { bucket: 0 }),
  Error,
  "a subject without traits is rejected",
);
console.log("ok");
