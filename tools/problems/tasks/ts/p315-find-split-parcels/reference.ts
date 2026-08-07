export function findSplitParcels(plan: string[]): string[] {
  if (!Array.isArray(plan) || plan.length === 0) {
    throw new Error("the map must carry at least one row");
  }
  const height = plan.length;
  if (typeof plan[0] !== "string") {
    throw new Error("every row must be a string");
  }
  const width = plan[0].length;
  if (width === 0) {
    throw new Error("the map must carry at least one square");
  }
  for (const row of plan) {
    if (typeof row !== "string") {
      throw new Error("every row must be a string");
    }
    if (row.length !== width) {
      throw new Error("every row must share the width of the first");
    }
    for (const square of row) {
      if (square !== "." && (square < "A" || square > "Z")) {
        throw new Error(`unusable square marking: ${square}`);
      }
    }
  }

  let claimed = 0;
  for (const row of plan) {
    for (const square of row) {
      if (square !== ".") {
        claimed += 1;
      }
    }
  }
  if (claimed === 0) {
    throw new Error("the map claims not one square");
  }

  const walked: boolean[][] = plan.map(() => new Array(width).fill(false));
  const pieces = new Map<string, number>();
  for (let row = 0; row < height; row++) {
    for (let column = 0; column < width; column++) {
      const letter = plan[row][column];
      if (letter === "." || walked[row][column]) {
        continue;
      }
      pieces.set(letter, (pieces.get(letter) ?? 0) + 1);
      const stack: number[][] = [[row, column]];
      walked[row][column] = true;
      while (stack.length > 0) {
        const [r, c] = stack.pop()!;
        const steps = [
          [r - 1, c],
          [r + 1, c],
          [r, c - 1],
          [r, c + 1],
        ];
        for (const [nr, nc] of steps) {
          if (nr < 0 || nr >= height || nc < 0 || nc >= width) {
            continue;
          }
          if (walked[nr][nc] || plan[nr][nc] !== letter) {
            continue;
          }
          walked[nr][nc] = true;
          stack.push([nr, nc]);
        }
      }
    }
  }

  const split: string[] = [];
  for (const letter of [...pieces.keys()].sort()) {
    const count = pieces.get(letter)!;
    if (count > 1) {
      split.push(`${letter}:${count}`);
    }
  }
  return split;
}
