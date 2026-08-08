import assert from "node:assert/strict";
import { foldTapePrints } from "./solution.ts";

const ticket = (ref, way, limit, lots) => ({ ref, way, limit, lots });

assert.deepEqual(
  foldTapePrints(
    [ticket("s1", "sell", 12, 3), ticket("s2", "sell", 10, 2)],
    [ticket("f1", "buy", 12, 4)],
  ),
  {
    prints: [
      { limit: 10, lots: 2 },
      { limit: 12, lots: 2 },
    ],
    left: 1,
  },
  "the keenest limit goes first and each print carries the ladder's limit",
);

assert.deepEqual(
  foldTapePrints([], [ticket("f1", "buy", 50, 5), ticket("f2", "sell", 45, 3)]),
  { prints: [{ limit: 50, lots: 3 }], left: 2 },
  "what an arriving ticket leaves behind is reachable by later flow",
);

assert.deepEqual(
  foldTapePrints([ticket("s1", "sell", 20, 3)], []),
  { prints: [], left: 3 },
  "an empty flow prints nothing and leaves the ladder alone",
);

assert.deepEqual(
  foldTapePrints([ticket("s1", "sell", 20, 1)], [ticket("f1", "buy", 15, 1)]),
  { prints: [], left: 2 },
  "a limit that cannot be reached simply adds to the ladder",
);

assert.deepEqual(
  foldTapePrints(
    [ticket("b1", "buy", 30, 1), ticket("b2", "buy", 30, 1)],
    [ticket("f1", "sell", 30, 2)],
  ),
  { prints: [{ limit: 30, lots: 2 }], left: 0 },
  "two tickets at one limit are worked oldest first",
);

assert.deepEqual(
  foldTapePrints(
    [
      ticket("b1", "buy", 8, 2),
      ticket("b2", "buy", 9, 2),
      ticket("b3", "buy", 9, 1),
    ],
    [ticket("f1", "sell", 8, 4), ticket("f2", "sell", 8, 2)],
  ),
  {
    prints: [
      { limit: 8, lots: 2 },
      { limit: 9, lots: 3 },
    ],
    left: 1,
  },
  "prints from several arrivals gather under one limit and rise in order",
);

assert.deepEqual(
  foldTapePrints(
    [ticket("s1", "sell", 7, 5)],
    [ticket("f1", "buy", 7, 2), ticket("f2", "buy", 7, 2)],
  ),
  { prints: [{ limit: 7, lots: 4 }], left: 1 },
  "a resting ticket serves arrival after arrival until it is spent",
);

function rejects(opening, flow) {
  try {
    foldTapePrints(opening, flow);
  } catch (error) {
    return error instanceof Error;
  }
  return false;
}

assert.ok(
  rejects([], [ticket("f1", "bid", 5, 1)]),
  "a way outside buy and sell is rejected",
);
assert.ok(rejects([], [ticket("f1", "buy", 5, 0)]), "zero lots are rejected");
assert.ok(
  rejects([], [ticket("f1", "buy", 0, 1)]),
  "a limit of zero is rejected",
);
assert.ok(
  rejects([], [ticket("f1", "buy", 5.25, 1)]),
  "a fractional limit is rejected",
);
assert.ok(rejects([], [ticket("", "buy", 5, 1)]), "an empty ref is rejected");
assert.ok(
  rejects([ticket("same", "sell", 9, 1)], [ticket("same", "buy", 9, 1)]),
  "a ref carried twice in one session is rejected",
);
assert.ok(rejects([], ["not a ticket"]), "a ticket that is not a mapping is rejected");
assert.ok(rejects([], "flow"), "an argument that is not a list is rejected");
console.log("ok");
