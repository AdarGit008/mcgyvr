import assert from "node:assert/strict";
import { crossingPoint } from "./solution.ts";

assert.deepEqual(
  crossingPoint(
    [
      [0, 0],
      [4, 4],
    ],
    [
      [0, 4],
      [4, 0],
    ],
  ),
  { kind: "point", x: [2, 1], y: [2, 1] },
  "a plain crossing lands on the grid",
);

assert.deepEqual(
  crossingPoint(
    [
      [0, 0],
      [2, 1],
    ],
    [
      [0, 1],
      [2, 0],
    ],
  ),
  { kind: "point", x: [1, 1], y: [1, 2] },
  "a meeting halfway up is reported as a top over a bottom",
);

assert.deepEqual(
  crossingPoint(
    [
      [-3, 0],
      [0, 1],
    ],
    [
      [-1, -2],
      [-1, 5],
    ],
  ),
  { kind: "point", x: [-1, 1], y: [2, 3] },
  "thirds and a negative coordinate stay exact",
);

assert.deepEqual(
  crossingPoint(
    [
      [-1, -1],
      [1, 1],
    ],
    [
      [-1, 0],
      [1, 0],
    ],
  ),
  { kind: "point", x: [0, 1], y: [0, 1] },
  "a meeting at the origin has bottom one and no minus zero",
);

assert.deepEqual(
  crossingPoint(
    [
      [0, 0],
      [2, 0],
    ],
    [
      [2, 0],
      [2, 3],
    ],
  ),
  { kind: "point", x: [2, 1], y: [0, 1] },
  "strokes meeting only at an end still meet",
);

assert.deepEqual(
  crossingPoint(
    [
      [0, 0],
      [2, 0],
    ],
    [
      [0, 1],
      [2, 1],
    ],
  ),
  { kind: "apart" },
  "parallel strokes never meet",
);

assert.deepEqual(
  crossingPoint(
    [
      [0, 0],
      [1, 0],
    ],
    [
      [2, -1],
      [2, 1],
    ],
  ),
  { kind: "apart" },
  "the lines would meet but the strokes stop short",
);

assert.deepEqual(
  crossingPoint(
    [
      [0, 0],
      [4, 0],
    ],
    [
      [6, 0],
      [2, 0],
    ],
  ),
  { kind: "stretch", from: [2, 0], to: [4, 0] },
  "an overlap is reported from the smaller end",
);

assert.deepEqual(
  crossingPoint(
    [
      [0, 0],
      [6, 3],
    ],
    [
      [4, 2],
      [2, 1],
    ],
  ),
  { kind: "stretch", from: [2, 1], to: [4, 2] },
  "one stroke swallowed by the other gives the swallowed stretch",
);

assert.deepEqual(
  crossingPoint(
    [
      [0, 0],
      [2, 2],
    ],
    [
      [2, 2],
      [5, 5],
    ],
  ),
  { kind: "point", x: [2, 1], y: [2, 1] },
  "collinear strokes touching at one end share a single spot",
);

assert.deepEqual(
  crossingPoint(
    [
      [0, 0],
      [1, 1],
    ],
    [
      [3, 3],
      [5, 5],
    ],
  ),
  { kind: "apart" },
  "collinear strokes with a gap between them",
);

assert.throws(
  () =>
    crossingPoint(
      [
        [0, 0],
        [1, 1],
        [2, 2],
      ],
      [
        [0, 1],
        [1, 0],
      ],
    ),
  Error,
  "three ends is not a stroke",
);
assert.throws(
  () =>
    crossingPoint(
      [
        [0, 0],
        [0, 0],
      ],
      [
        [0, 1],
        [1, 0],
      ],
    ),
  Error,
  "a stroke of no length is rejected",
);
assert.throws(
  () =>
    crossingPoint(
      [
        [0, 0],
        [1, 0.5],
      ],
      [
        [0, 1],
        [1, 0],
      ],
    ),
  Error,
  "a fractional coordinate is rejected",
);
assert.throws(
  () =>
    crossingPoint(
      [
        [0, 0],
        [1001, 0],
      ],
      [
        [0, 1],
        [1, 0],
      ],
    ),
  Error,
  "an oversized coordinate is rejected",
);
assert.throws(
  () => crossingPoint("line", [[0, 1], [1, 0]]),
  Error,
  "a non-list stroke is rejected",
);
console.log("ok");
