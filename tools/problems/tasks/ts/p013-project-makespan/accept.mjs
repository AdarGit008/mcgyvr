import assert from "node:assert/strict";
import { projectMakespan } from "./solution.ts";

assert.equal(projectMakespan({ a: 3 }, []), 3, "single task");
assert.equal(projectMakespan({ a: 2, b: 3 }, []), 3, "independent tasks overlap");
assert.equal(
  projectMakespan({ a: 1, b: 2, c: 3 }, [["a", "b"], ["b", "c"]]),
  6,
  "a chain adds up",
);
assert.equal(
  projectMakespan(
    { a: 1, b: 5, c: 2, d: 1 },
    [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]],
  ),
  7,
  "diamond takes its slowest branch",
);
assert.equal(
  projectMakespan({ a: 4, b: 1, c: 1 }, [["b", "c"]]),
  4,
  "a lone slow task dominates a short chain",
);
assert.equal(
  projectMakespan({ a: 2, b: 2, c: 2 }, [["a", "c"], ["b", "c"]]),
  4,
  "join waits for both prerequisites",
);
assert.throws(() => projectMakespan({ a: 0 }, []), Error, "zero duration rejected");
assert.throws(() => projectMakespan({ a: 2.5 }, []), Error, "fractional duration rejected");
assert.throws(
  () => projectMakespan({ a: 1 }, [["a", "ghost"]]),
  Error,
  "unknown task in a pair rejected",
);
assert.throws(
  () => projectMakespan({ a: 1 }, [["a", "a"]]),
  Error,
  "self-dependency rejected",
);
assert.throws(
  () => projectMakespan({ a: 1, b: 1 }, [["a", "b"], ["b", "a"]]),
  Error,
  "cycle rejected",
);
console.log("ok");
