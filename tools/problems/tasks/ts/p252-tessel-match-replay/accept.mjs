import assert from "node:assert/strict";
import { replayTesselMatch } from "./solution.ts";

const repeat = (side, times) => Array.from({ length: times }, () => side);

assert.deepEqual(
  replayTesselMatch([]),
  { winner: "", bands: [0, 0], points: [0, 0], serve: "A" },
  "no rallies: A holds the opening serve",
);
assert.deepEqual(
  replayTesselMatch(["B"]),
  { winner: "", bands: [0, 0], points: [0, 0], serve: "B" },
  "the receiver wins the rally but not a point",
);
assert.deepEqual(
  replayTesselMatch(["B", "B"]),
  { winner: "", bands: [0, 0], points: [0, 1], serve: "B" },
  "the new server scores on the next rally",
);
assert.deepEqual(
  replayTesselMatch(repeat("A", 4)),
  { winner: "", bands: [0, 0], points: [4, 0], serve: "A" },
  "a server holding serve stacks points",
);
assert.deepEqual(
  replayTesselMatch(repeat("A", 7)),
  { winner: "", bands: [1, 0], points: [0, 0], serve: "B" },
  "7-0 closes the band and hands the serve to the loser",
);

const evened = [...repeat("A", 6), ...repeat("B", 7)];
assert.deepEqual(
  replayTesselMatch(evened),
  { winner: "", bands: [0, 0], points: [6, 6], serve: "B" },
  "six all is not a band",
);

const capped = [
  ...evened,
  "B",
  "A", "A",
  "B", "B",
  "A", "A",
  "B", "B",
  "A", "A",
  "B", "B",
];
assert.deepEqual(
  replayTesselMatch(capped),
  { winner: "", bands: [0, 1], points: [0, 0], serve: "A" },
  "arriving at 10 takes the band on a one-point lead",
);

const swept = [...repeat("A", 7), ...repeat("A", 8), ...repeat("A", 8)];
assert.deepEqual(
  replayTesselMatch(swept),
  { winner: "A", bands: [3, 0], points: [7, 0], serve: "" },
  "three bands decide the match and freeze the closing points",
);

assert.throws(() => replayTesselMatch([...swept, "B"]), Error, "play past the decision is rejected");
assert.throws(() => replayTesselMatch(["A", "C"]), Error, "an unknown side is rejected");
assert.throws(() => replayTesselMatch("AB"), Error, "a string argument is rejected");
assert.throws(() => replayTesselMatch(null), Error, "a null argument is rejected");
console.log("ok");
