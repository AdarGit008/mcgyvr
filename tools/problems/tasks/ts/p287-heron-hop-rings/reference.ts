const HOPS: number[][] = [
  [-1, 0],
  [1, 0],
  [0, -1],
  [0, 1],
  [-3, 0],
  [3, 0],
  [0, -3],
  [0, 3],
];

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function reachByHops(
  across: number,
  down: number,
  start: number[],
  marsh: number[][],
  hops: number,
): number[] {
  if (!whole(across) || across < 1) {
    throw new Error("across must be an integer of at least 1");
  }
  if (!whole(down) || down < 1) {
    throw new Error("down must be an integer of at least 1");
  }
  if (!whole(hops) || hops < 0) {
    throw new Error("hops must be an integer of at least 0");
  }
  const onFen = (square: unknown): boolean =>
    Array.isArray(square) &&
    square.length === 2 &&
    whole(square[0]) &&
    whole(square[1]) &&
    square[0] >= 0 &&
    square[0] < down &&
    square[1] >= 0 &&
    square[1] < across;

  if (!Array.isArray(marsh)) {
    throw new Error("marsh must be a list");
  }
  const wet = new Set<number>();
  for (const square of marsh) {
    if (!onFen(square)) {
      throw new Error("a marsh square must be a pair naming a fen square");
    }
    const key = square[0] * across + square[1];
    if (wet.has(key)) {
      throw new Error("marsh names the same square twice");
    }
    wet.add(key);
  }
  if (!onFen(start)) {
    throw new Error("start must be a pair naming a fen square");
  }
  const first = start[0] * across + start[1];
  if (wet.has(first)) {
    throw new Error("start names a marsh square");
  }

  const rings: number[] = [];
  for (let i = 0; i <= hops; i++) {
    rings.push(0);
  }
  const seen = new Set<number>([first]);
  let edge: number[][] = [[start[0], start[1]]];
  rings[0] = 1;
  for (let ring = 1; ring <= hops; ring++) {
    const next: number[][] = [];
    for (const square of edge) {
      for (const hop of HOPS) {
        const r = square[0] + hop[0];
        const c = square[1] + hop[1];
        if (r < 0 || r >= down || c < 0 || c >= across) {
          continue;
        }
        const key = r * across + c;
        if (wet.has(key) || seen.has(key)) {
          continue;
        }
        seen.add(key);
        next.push([r, c]);
      }
    }
    rings[ring] = next.length;
    edge = next;
  }
  return rings;
}
