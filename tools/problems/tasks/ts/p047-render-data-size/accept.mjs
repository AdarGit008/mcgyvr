import assert from "node:assert/strict";
import { renderDataSize } from "./solution.ts";

assert.equal(renderDataSize(0), "0B", "zero renders as 0B alone");
assert.equal(renderDataSize(5), "5B", "a few bytes stay bytes");
assert.equal(renderDataSize(1024), "1KiB", "exactly one binary kilobyte");
assert.equal(renderDataSize(1023), "1023B", "one under the ladder stays in bytes");
assert.equal(
  renderDataSize(1048576 + 1024 + 1),
  "1MiB 1KiB 1B",
  "each nonzero rung appears once",
);
assert.equal(
  renderDataSize(3 * 1073741824 + 2 * 1024),
  "3GiB 2KiB",
  "a zero rung between nonzero rungs is absent",
);
assert.equal(
  renderDataSize(2047),
  "1KiB 1023B",
  "the remainder after a rung stays below that rung",
);
assert.equal(
  renderDataSize(5 * 1073741824),
  "5GiB",
  "a round count is a single component",
);
assert.throws(() => renderDataSize(-1), Error, "a negative count is rejected");
assert.throws(() => renderDataSize(1.5), Error, "a fractional count is rejected");
assert.throws(() => renderDataSize("1024"), Error, "a string count is rejected");
console.log("ok");
