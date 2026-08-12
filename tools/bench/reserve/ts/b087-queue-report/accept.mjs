import assert from "node:assert/strict";
import { queueReport } from "./solution.ts";

assert.deepEqual(queueReport([]), { waited: 0, longest: 0, idle: 0 }, "empty list is all zeroes");
assert.deepEqual(queueReport([[5, 3]]), { waited: 0, longest: 0, idle: 5 }, "opening gap counts as idle");
assert.deepEqual(
  queueReport([[0, 2], [2, 2]]),
  { waited: 0, longest: 0, idle: 0 },
  "back-to-back orders never idle",
);
assert.deepEqual(
  queueReport([[0, 4], [1, 2], [2, 1]]),
  { waited: 7, longest: 4, idle: 0 },
  "a backlog accumulates waits",
);
assert.deepEqual(
  queueReport([[0, 2], [5, 1]]),
  { waited: 0, longest: 0, idle: 3 },
  "a lull between orders is idle",
);
assert.deepEqual(
  queueReport([[3, 2], [3, 2]]),
  { waited: 2, longest: 2, idle: 3 },
  "same-minute orders queue up",
);
assert.deepEqual(
  queueReport([[1, 3], [2, 1], [9, 2]]),
  { waited: 2, longest: 2, idle: 5 },
  "waits and idle in one run",
);
assert.throws(() => queueReport(42), Error, "non-list is rejected");
assert.throws(() => queueReport([[1]]), Error, "a lone minute is rejected");
assert.throws(() => queueReport([[-1, 2]]), Error, "negative placement is rejected");
assert.throws(() => queueReport([[0, 0]]), Error, "zero hand-over is rejected");
assert.throws(() => queueReport([[4, 1], [2, 1]]), Error, "decreasing placement is rejected");
console.log("ok");
