function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function shifted(row: number): boolean {
  return ((row % 2) + 2) % 2 === 1;
}

function advance(col: number, row: number, move: string): number[] {
  const odd = shifted(row);
  if (move === "e") return [col + 1, row];
  if (move === "w") return [col - 1, row];
  if (move === "ne") return [odd ? col + 1 : col, row - 1];
  if (move === "nw") return [odd ? col : col - 1, row - 1];
  if (move === "se") return [odd ? col + 1 : col, row + 1];
  if (move === "sw") return [odd ? col : col - 1, row + 1];
  throw new Error("unrecognised move name");
}

export function hopOffsetGrid(
  start: number[],
  moves: string[],
): { cell: number[]; distance: number } {
  if (!Array.isArray(start) || start.length !== 2) {
    throw new Error("the start must be a two-element address");
  }
  if (!whole(start[0]) || !whole(start[1])) {
    throw new Error("an address must hold whole numbers");
  }
  if (!Array.isArray(moves)) {
    throw new Error("the moves must be a list");
  }
  let col = start[0];
  let row = start[1];
  for (const move of moves) {
    const next = advance(col, row, move);
    col = next[0];
    row = next[1];
  }
  const fromQ = start[0] - Math.floor(start[1] / 2);
  const toQ = col - Math.floor(row / 2);
  const dq = toQ - fromQ;
  const dr = row - start[1];
  const distance = (Math.abs(dq) + Math.abs(dr) + Math.abs(dq + dr)) / 2;
  return { cell: [col, row], distance };
}
