import assert from "node:assert/strict";
import { preemptFirstOverrun } from "./solution.ts";

assert.equal(
  preemptFirstOverrun([
    { name: "A", at: 0, work: 10, due: 20 },
    { name: "B", at: 2, work: 3, due: 6 },
  ]),
  "",
  "an urgent arrival takes the machine over and both jobs make it",
);
assert.equal(
  preemptFirstOverrun([
    { name: "A", at: 0, work: 9, due: 30 },
    { name: "B", at: 1, work: 4, due: 10 },
    { name: "C", at: 2, work: 2, due: 5 },
  ]),
  "",
  "a chain of takeovers still lands every job in time",
);
assert.equal(
  preemptFirstOverrun([{ name: "A", at: 0, work: 5, due: 3 }]),
  "A",
  "a genuinely overloaded job overruns",
);
assert.equal(
  preemptFirstOverrun([{ name: "A", at: 5, work: 2, due: 7 }]),
  "",
  "the machine idles until the first arrival, finishing exactly on time",
);
assert.equal(
  preemptFirstOverrun([{ name: "A", at: 5, work: 2, due: 6 }]),
  "A",
  "idle minutes are not free work",
);
assert.equal(
  preemptFirstOverrun([
    { name: "A", at: 0, work: 6, due: 5 },
    { name: "B", at: 0, work: 6, due: 11 },
  ]),
  "A",
  "with several overruns the earliest due minute is blamed",
);
assert.equal(
  preemptFirstOverrun([
    { name: "B", at: 0, work: 2, due: 3 },
    { name: "A", at: 0, work: 2, due: 3 },
  ]),
  "B",
  "on a due tie the alphabetically smaller name runs first",
);
assert.equal(preemptFirstOverrun([]), "", "no jobs, no overrun");
assert.throws(
  () =>
    preemptFirstOverrun([
      { name: "A", at: 0, work: 1, due: 2 },
      { name: "A", at: 1, work: 1, due: 3 },
    ]),
  Error,
  "a repeated name is rejected",
);
assert.throws(() => preemptFirstOverrun([{ name: "A", at: -1, work: 1, due: 2 }]), Error, "a negative at is rejected");
assert.throws(() => preemptFirstOverrun([{ name: "A", at: 0, work: 0, due: 2 }]), Error, "work 0 is rejected");
assert.throws(() => preemptFirstOverrun([{ name: "A", at: 0, work: 1, due: 0 }]), Error, "due 0 is rejected");
assert.throws(() => preemptFirstOverrun([{ name: "", at: 0, work: 1, due: 2 }]), Error, "an empty name is rejected");
console.log("ok");
