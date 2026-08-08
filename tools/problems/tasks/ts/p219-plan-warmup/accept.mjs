import assert from "node:assert/strict";
import { planWarmup } from "./solution.ts";

const brief = (budget, slots, caps, items) => ({ budget, slots, caps, items });
const item = (name, bytes, weight, family) => ({ name, bytes, weight, family });
const away = (name, why) => ({ name, why });

assert.deepEqual(
  planWarmup(brief(10, 3, {}, [])),
  { loaded: [], spare: 10, turned: [] },
  "nothing offered, nothing loaded"
);
assert.deepEqual(
  planWarmup(brief(100, 5, { g: 5 }, [item("a", 10, 5, "g"), item("b", 20, 3, "g")])),
  { loaded: ["a", "b"], spare: 70, turned: [] },
  "everything fits and the heavier goes first"
);
assert.deepEqual(
  planWarmup(brief(100, 1, { g: 5 }, [item("a", 10, 5, "g"), item("b", 20, 3, "g")])),
  { loaded: ["a"], spare: 90, turned: [away("b", "slots")] },
  "the store runs out of places"
);
assert.deepEqual(
  planWarmup(
    brief(100, 5, { g: 1, h: 2 }, [
      item("a", 10, 5, "g"),
      item("b", 20, 3, "g"),
      item("c", 5, 1, "h"),
    ])
  ),
  { loaded: ["a", "c"], spare: 85, turned: [away("b", "family")] },
  "a family stops contributing once its cap is spent"
);
assert.deepEqual(
  planWarmup(
    brief(12, 5, { g: 5 }, [
      item("a", 10, 9, "g"),
      item("b", 5, 8, "g"),
      item("c", 2, 7, "g"),
    ])
  ),
  { loaded: ["a", "c"], spare: 0, turned: [away("b", "bytes")] },
  "the walk goes on past an item the budget cannot hold"
);
assert.deepEqual(
  planWarmup(brief(3, 1, { g: 5 }, [item("a", 3, 9, "g"), item("b", 50, 8, "g")])),
  { loaded: ["a"], spare: 0, turned: [away("b", "slots")] },
  "no place left is judged before the budget"
);
assert.deepEqual(
  planWarmup(brief(5, 5, { g: 1 }, [item("a", 5, 9, "g"), item("b", 50, 8, "g")])),
  { loaded: ["a"], spare: 0, turned: [away("b", "family")] },
  "a spent family is judged before the budget"
);
assert.deepEqual(
  planWarmup(
    brief(100, 5, { g: 9 }, [
      item("zed", 4, 2, "g"),
      item("abe", 4, 2, "g"),
      item("mid", 1, 2, "g"),
    ])
  ),
  { loaded: ["mid", "abe", "zed"], spare: 91, turned: [] },
  "equal weight settles on bytes then on the name"
);
assert.deepEqual(
  planWarmup(brief(100, 5, { g: 0 }, [item("a", 1, 1, "g")])),
  { loaded: [], spare: 100, turned: [away("a", "family")] },
  "a cap of nothing keeps the whole family out"
);
assert.deepEqual(
  planWarmup(
    brief(6, 2, { g: 2, h: 2 }, [
      item("w", 5, 4, "g"),
      item("x", 4, 3, "h"),
      item("y", 1, 2, "g"),
      item("z", 1, 1, "h"),
    ])
  ),
  {
    loaded: ["w", "y"],
    spare: 0,
    turned: [away("x", "bytes"), away("z", "slots")],
  },
  "three limits bite in one walk"
);

assert.throws(() => planWarmup([1, 2]), Error, "a brief that is not a mapping is rejected");
assert.throws(
  () => planWarmup(brief(-1, 1, {}, [])),
  Error,
  "a negative budget is rejected"
);
assert.throws(
  () => planWarmup(brief(10, 0, {}, [])),
  Error,
  "a store with no places is rejected"
);
assert.throws(
  () => planWarmup(brief(10, 1, [], [])),
  Error,
  "caps that is not a mapping is rejected"
);
assert.throws(
  () => planWarmup(brief(10, 1, {}, "none")),
  Error,
  "items that is not a list is rejected"
);
assert.throws(
  () => planWarmup(brief(10, 1, { g: -1 }, [])),
  Error,
  "a negative cap is rejected"
);
assert.throws(
  () => planWarmup(brief(10, 1, { g: 1 }, [["a"]])),
  Error,
  "an item that is not a mapping is rejected"
);
assert.throws(
  () => planWarmup(brief(10, 1, { g: 1 }, [{ bytes: 1, weight: 1, family: "g" }])),
  Error,
  "a missing name is rejected"
);
assert.throws(
  () =>
    planWarmup(
      brief(10, 1, { g: 1 }, [item("a", 1, 1, "g"), item("a", 2, 1, "g")])
    ),
  Error,
  "a repeated name is rejected"
);
assert.throws(
  () => planWarmup(brief(10, 1, { g: 1 }, [item("a", 0, 1, "g")])),
  Error,
  "bytes of zero is rejected"
);
assert.throws(
  () => planWarmup(brief(10, 1, { g: 1 }, [item("a", 1, -1, "g")])),
  Error,
  "a negative weight is rejected"
);
assert.throws(
  () => planWarmup(brief(10, 1, { g: 1 }, [item("a", 1, 1, "q")])),
  Error,
  "a family caps does not mention is rejected"
);

console.log("ok");
