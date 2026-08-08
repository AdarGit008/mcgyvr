import assert from "node:assert/strict";
import { runCrane } from "./solution.ts";

assert.deepEqual(
  runCrane([["load", "a"], ["load", "b"], ["ship"], ["ship"]]),
  ["b", "a"],
  "the pile ships last-in first-out",
);
assert.deepEqual(
  runCrane([["load", "a"], ["load", "b"], ["load", "c"], ["bury"], ["ship"]]),
  ["b"],
  "bury sends the top crate to the bottom",
);
assert.deepEqual(
  runCrane([["load", "a"], ["load", "b"], ["scrap"], ["ship"]]),
  ["a"],
  "a scrapped crate never reaches the manifest",
);
assert.deepEqual(
  runCrane([["load", "x"], ["bury"], ["ship"]]),
  ["x"],
  "burying the only crate leaves it on top",
);
assert.deepEqual(runCrane([]), [], "an empty script ships nothing");
assert.deepEqual(runCrane([["load", "q"]]), [], "loading alone ships nothing");
assert.deepEqual(
  runCrane([["load", "a"], ["load", "b"], ["bury"], ["bury"], ["ship"], ["ship"]]),
  ["b", "a"],
  "two buries on two crates cycle the pile back",
);
assert.throws(() => runCrane([["ship"]]), Error, "shipping from an empty pile is a fault");
assert.throws(() => runCrane([["load", "a"], ["hoist"]]), Error, "an unknown move is a fault");
assert.throws(() => runCrane([["bury"]]), Error, "burying with an empty pile is a fault");
assert.throws(() => runCrane([["scrap"]]), Error, "scrapping with an empty pile is a fault");
console.log("ok");
