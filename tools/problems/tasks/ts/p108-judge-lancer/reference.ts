export function judgeLancer(
  board: string[],
  side: string,
  from: number[],
  to: number[],
): string {
  if (
    !Array.isArray(board) ||
    board.length !== 7 ||
    board.some(
      (row) => typeof row !== "string" || row.length !== 7 || /[^WB.]/.test(row),
    )
  ) {
    throw new Error("malformed board");
  }
  if (side !== "W" && side !== "B") {
    throw new Error("bad side");
  }
  for (const square of [from, to]) {
    if (
      !Array.isArray(square) ||
      square.length !== 2 ||
      !square.every((n) => Number.isInteger(n))
    ) {
      throw new Error("a square must be a pair of integers");
    }
  }
  const inside = (sq: number[]) =>
    sq[0] >= 0 && sq[0] < 7 && sq[1] >= 0 && sq[1] < 7;
  if (!inside(from) || !inside(to)) return "off_board";
  if (board[from[0]][from[1]] !== side) return "no_piece";
  const dr = to[0] - from[0];
  const dc = to[1] - from[1];
  const span = Math.abs(dr) + Math.abs(dc);
  if ((dr !== 0 && dc !== 0) || span < 1 || span > 3) return "bad_line";
  const sr = Math.sign(dr);
  const sc = Math.sign(dc);
  for (let k = 1; k < span; k++) {
    if (board[from[0] + sr * k][from[1] + sc * k] !== ".") return "blocked";
  }
  const landing = board[to[0]][to[1]];
  if (landing === side) return "own_piece";
  if (landing !== "." && span < 2) return "too_close";
  return "ok";
}
