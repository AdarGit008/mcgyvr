import assert from "node:assert/strict";
import { firstDeadlineMiss } from "./solution.ts";

assert.equal(
  firstDeadlineMiss([
    { name: "A", work: 3, due: 5 },
    { name: "B", work: 2, due: 9 },
  ]),
  "",
  "a fitting plan misses nothing",
);
assert.equal(
  firstDeadlineMiss([
    { name: "B", work: 4, due: 10 },
    { name: "A", work: 2, due: 2 },
  ]),
  "",
  "the earliest due minute runs first, whatever the list order",
);
assert.equal(firstDeadlineMiss([{ name: "A", work: 3, due: 2 }]), "A", "one overloaded job misses");
assert.equal(
  firstDeadlineMiss([
    { name: "A", work: 5, due: 5 },
    { name: "B", work: 1, due: 5 },
    { name: "C", work: 1, due: 6 },
  ]),
  "B",
  "on a due tie the earlier-listed job runs first, and the miss is found in running order",
);
assert.equal(
  firstDeadlineMiss([
    { name: "A", work: 2, due: 4 },
    { name: "B", work: 5, due: 6 },
  ]),
  "B",
  "the miss need not be the first job run",
);
assert.equal(firstDeadlineMiss([]), "", "an empty list is on time");
assert.throws(() => firstDeadlineMiss([{ name: "A", work: 0, due: 3 }]), Error, "work 0 is rejected");
assert.throws(() => firstDeadlineMiss([{ name: "A", work: 2, due: 0 }]), Error, "due 0 is rejected");
assert.throws(() => firstDeadlineMiss([{ name: "A", work: 1.5, due: 3 }]), Error, "fractional work is rejected");
assert.throws(
  () =>
    firstDeadlineMiss([
      { name: "A", work: 1, due: 3 },
      { name: "A", work: 2, due: 4 },
    ]),
  Error,
  "a repeated name is rejected",
);
assert.throws(() => firstDeadlineMiss([{ name: 5, work: 1, due: 3 }]), Error, "a non-string name is rejected");
console.log("ok");
