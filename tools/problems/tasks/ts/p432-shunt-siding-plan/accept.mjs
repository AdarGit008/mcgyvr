import assert from "node:assert/strict";
import { planShunting } from "./solution.ts";

assert.deepEqual(
  planShunting(["a", "b", "c"], ["a", "b", "c"], 3),
  {
    moves: [
      "hold a",
      "place a",
      "hold b",
      "place b",
      "hold c",
      "place c",
    ],
    blocked: "",
  },
  "an order already standing right is held and placed one car at a time",
);

assert.deepEqual(
  planShunting(["a", "b", "c"], ["c", "b", "a"], 3),
  {
    moves: [
      "hold a",
      "hold b",
      "hold c",
      "place c",
      "place b",
      "place a",
    ],
    blocked: "",
  },
  "a full reversal fills the siding and empties it",
);

assert.deepEqual(
  planShunting(["a", "b", "c"], ["b", "a", "c"], 2),
  {
    moves: [
      "hold a",
      "hold b",
      "place b",
      "place a",
      "hold c",
      "place c",
    ],
    blocked: "",
  },
  "a depth of two is enough when the siding drains between cars",
);

assert.deepEqual(
  planShunting(["a", "b", "c"], ["c", "b", "a"], 2),
  { moves: ["hold a", "hold b"], blocked: "full" },
  "the reversal needs a third place on the siding",
);

assert.deepEqual(
  planShunting(["a", "b", "c"], ["c", "a", "b"], 3),
  { moves: ["hold a", "hold b", "hold c", "place c"], blocked: "buried:a" },
  "a runs out of arrival cars while sitting under b",
);

assert.deepEqual(
  planShunting(["x"], ["x"], 1),
  { moves: ["hold x", "place x"], blocked: "" },
  "one car needs one place on the siding",
);

assert.deepEqual(
  planShunting(["r1", "r2", "r3", "r4"], ["r2", "r4", "r3", "r1"], 4),
  {
    moves: [
      "hold r1",
      "hold r2",
      "place r2",
      "hold r3",
      "hold r4",
      "place r4",
      "place r3",
      "place r1",
    ],
    blocked: "",
  },
  "longer codes ride the same drill",
);

assert.throws(() => planShunting("ab", ["a", "b"], 2), Error, "arrival must be a list");
assert.throws(() => planShunting(["a"], "a", 2), Error, "target must be a list");
assert.throws(() => planShunting([], [], 2), Error, "an empty arrival road is rejected");
assert.throws(() => planShunting(["a", ""], ["a", ""], 2), Error, "an empty code is rejected");
assert.throws(() => planShunting(["a", 7], ["a", 7], 2), Error, "a non-string code is rejected");
assert.throws(() => planShunting(["a", "a"], ["a", "a"], 2), Error, "a repeated arrival code is rejected");
assert.throws(() => planShunting(["a", "b"], ["a", "c"], 2), Error, "different cars are rejected");
assert.throws(() => planShunting(["a", "b"], ["a"], 2), Error, "a short target is rejected");
assert.throws(() => planShunting(["a", "b"], ["a", "b"], 0), Error, "a depth below one is rejected");
assert.throws(() => planShunting(["a", "b"], ["a", "b"], 1.5), Error, "a fractional depth is rejected");
console.log("ok");
