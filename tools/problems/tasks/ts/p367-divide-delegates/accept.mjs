import assert from "node:assert/strict";
import { divideDelegates } from "./solution.ts";

const slate = (name, votes, roster) => ({ name, votes, roster });

assert.deepEqual(
  divideDelegates(
    [slate("ash", 720, 10), slate("bay", 180, 10), slate("cob", 100, 10)],
    10,
  ),
  { ash: 7, bay: 2, cob: 1 },
  "the leftover delegate goes to the largest leftover",
);

assert.deepEqual(
  divideDelegates(
    [slate("zeta", 35, 10), slate("alpha", 25, 10), slate("mid", 40, 10)],
    10,
  ),
  { zeta: 4, alpha: 2, mid: 4 },
  "a level leftover is settled by the vote count, not the name",
);

assert.deepEqual(
  divideDelegates(
    [slate("yew", 45, 10), slate("ash", 45, 10), slate("elm", 10, 10)],
    10,
  ),
  { yew: 5, ash: 4, elm: 1 },
  "level leftovers and level votes fall to the earlier slate",
);

assert.deepEqual(
  divideDelegates(
    [slate("big", 800, 3), slate("wee", 100, 10), slate("tot", 100, 10)],
    10,
  ),
  { big: 3, wee: 4, tot: 3 },
  "delegates freed by a roster are reckoned again, not lost",
);

assert.deepEqual(
  divideDelegates(
    [slate("a", 600, 2), slate("b", 300, 3), slate("c", 100, 10)],
    10,
  ),
  { a: 2, b: 3, c: 5 },
  "pinning one slate can push the next above its own roster",
);

assert.deepEqual(
  divideDelegates([slate("north", 500, 10), slate("south", 500, 10)], 4),
  { north: 2, south: 2 },
  "an exact split leaves nothing over to pass around",
);

assert.deepEqual(
  divideDelegates([slate("lone", 7, 5)], 5),
  { lone: 5 },
  "one slate takes the whole convention",
);

assert.deepEqual(
  divideDelegates(
    [slate("cap", 900, 1), slate("rest", 100, 9)],
    9,
  ),
  { cap: 1, rest: 8 },
  "a slate held to one leaves the remainder to the others",
);

function rejects(slates, delegates) {
  try {
    divideDelegates(slates, delegates);
  } catch (error) {
    return error instanceof Error;
  }
  return false;
}

assert.ok(rejects([], 3), "no slates at all is rejected");
assert.ok(rejects([slate("a", 5, 5)], 0), "a delegate count of zero is rejected");
assert.ok(
  rejects([slate("a", 5, 5)], 1.5),
  "a fractional delegate count is rejected",
);
assert.ok(rejects([slate("", 5, 5)], 2), "an empty slate name is rejected");
assert.ok(
  rejects([slate("a", 5, 5), slate("a", 4, 5)], 2),
  "two slates sharing a name are rejected",
);
assert.ok(rejects([slate("a", 0, 5)], 2), "a slate with no votes is rejected");
assert.ok(rejects([slate("a", 5, 0)], 2), "a roster of zero is rejected");
assert.ok(
  rejects([slate("a", 5, 2), slate("b", 5, 2)], 5),
  "rosters too small for the convention are rejected",
);
assert.ok(rejects(["a slate"], 2), "a slate that is not a mapping is rejected");
assert.ok(rejects("slates", 2), "slates that are not a list are rejected");
console.log("ok");
