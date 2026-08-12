/** Steer a forklift across a warehouse floor of aisles by bays. */

const STEPS: Record<string, number[]> = {
  north: [0, -1],
  south: [0, 1],
  east: [1, 0],
  west: [-1, 0],
};

export function steerForklift(aisles: number, bays: number, moves: string[]): number[] {
  for (const size of [aisles, bays]) {
    if (!Number.isInteger(size) || size <= 0) {
      throw new Error("floor sizes must be positive integers");
    }
  }
  let x = 0;
  let y = 0;
  for (const move of moves) {
    const step = STEPS[move];
    if (step === undefined) {
      throw new Error("unknown move: " + move);
    }
    x += step[0];
    y += step[1];
    if (x < 0 || x >= aisles || y < 0 || y >= bays) {
      throw new Error("the forklift would leave the floor");
    }
  }
  return [x, y];
}
