const STEPS: number[][] = [
  [1, 0],
  [1, -1],
  [0, -1],
  [-1, 0],
  [-1, 1],
  [0, 1],
];

const SOUTHWEST = 4;

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function hexRingWalk(center: number[], radius: number): number[][] {
  if (!Array.isArray(center) || center.length !== 2) {
    throw new Error("the centre must be a two-element axial address");
  }
  if (!whole(center[0]) || !whole(center[1])) {
    throw new Error("axial coordinates must be whole numbers");
  }
  if (!whole(radius)) {
    throw new Error("the radius must be a whole number");
  }
  if (radius < 0) {
    throw new Error("the radius must not be negative");
  }
  if (radius === 0) {
    return [[center[0], center[1]]];
  }
  let q = center[0] + STEPS[SOUTHWEST][0] * radius;
  let r = center[1] + STEPS[SOUTHWEST][1] * radius;
  const ring: number[][] = [];
  for (const step of STEPS) {
    for (let taken = 0; taken < radius; taken++) {
      ring.push([q, r]);
      q += step[0];
      r += step[1];
    }
  }
  return ring;
}
