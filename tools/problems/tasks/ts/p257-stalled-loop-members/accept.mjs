import assert from "node:assert/strict";
import { stalledLoopMembers } from "./solution.ts";

assert.deepEqual(stalledLoopMembers({}), [], "an empty stall table has no loop");
assert.deepEqual(
  stalledLoopMembers({ a: "b" }),
  [],
  "waiting on a running job ends nowhere",
);
assert.deepEqual(
  stalledLoopMembers({ a: "b", b: "a" }),
  ["a", "b"],
  "two jobs waiting on each other are a loop",
);
assert.deepEqual(
  stalledLoopMembers({ tail: "a", a: "b", b: "c", c: "a" }),
  ["a", "b", "c"],
  "the job queued behind the loop is not a member",
);
assert.deepEqual(
  stalledLoopMembers({ z: "p", p: "q", q: "p" }),
  ["p", "q"],
  "the walk's starting job need not be on the loop",
);
assert.deepEqual(
  stalledLoopMembers({ x: "y", y: "x", m: "n", n: "m" }),
  ["m", "n"],
  "with two loops the smallest name decides, not the table order",
);
assert.deepEqual(
  stalledLoopMembers({ n2: "n1", n1: "n2" }),
  ["n1", "n2"],
  "members come back ascending, not in walk order",
);
assert.deepEqual(
  stalledLoopMembers({ one: "two", two: "three", three: "four" }),
  [],
  "a chain that runs out is no loop",
);

assert.throws(() => stalledLoopMembers({ a: "a" }), Error, "a job waiting on itself is rejected");
assert.throws(() => stalledLoopMembers({ "": "a" }), Error, "an empty job name is rejected");
assert.throws(() => stalledLoopMembers({ a: 5 }), Error, "a non-string wait target is rejected");
assert.throws(() => stalledLoopMembers({ a: "" }), Error, "an empty wait target is rejected");
assert.throws(() => stalledLoopMembers([["a", "b"]]), Error, "a list argument is rejected");
console.log("ok");
