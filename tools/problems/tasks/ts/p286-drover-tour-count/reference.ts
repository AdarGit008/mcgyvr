const STEPS: number[][] = [
  [-1, 0],
  [1, 0],
  [0, -1],
  [0, 1],
  [-2, -2],
  [-2, 2],
  [2, -2],
  [2, 2],
];

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function countPieceTours(
  width: number,
  height: number,
  start: number[],
  blocked: number[][],
): number {
  if (!whole(width) || width < 1) {
    throw new Error("width must be an integer of at least 1");
  }
  if (!whole(height) || height < 1) {
    throw new Error("height must be an integer of at least 1");
  }
  const onBoard = (square: unknown): boolean =>
    Array.isArray(square) &&
    square.length === 2 &&
    whole(square[0]) &&
    whole(square[1]) &&
    square[0] >= 0 &&
    square[0] < height &&
    square[1] >= 0 &&
    square[1] < width;

  if (!Array.isArray(blocked)) {
    throw new Error("blocked must be a list");
  }
  const shut = new Set<number>();
  for (const square of blocked) {
    if (!onBoard(square)) {
      throw new Error("a blocked square must be a pair naming a board square");
    }
    const key = square[0] * width + square[1];
    if (shut.has(key)) {
      throw new Error("blocked names the same square twice");
    }
    shut.add(key);
  }
  const open = width * height - shut.size;
  if (open > 12) {
    throw new Error("the board leaves more than 12 unblocked squares");
  }
  if (!onBoard(start)) {
    throw new Error("start must be a pair naming a board square");
  }
  const first = start[0] * width + start[1];
  if (shut.has(first)) {
    throw new Error("start names a blocked square");
  }

  const seen = new Set<number>([first]);
  let tours = 0;

  const walk = (row: number, col: number, stood: number): void => {
    if (stood === open) {
      tours += 1;
      return;
    }
    for (const step of STEPS) {
      const r = row + step[0];
      const c = col + step[1];
      if (r < 0 || r >= height || c < 0 || c >= width) {
        continue;
      }
      const key = r * width + c;
      if (shut.has(key) || seen.has(key)) {
        continue;
      }
      seen.add(key);
      walk(r, c, stood + 1);
      seen.delete(key);
    }
  };

  walk(start[0], start[1], 1);
  return tours;
}
