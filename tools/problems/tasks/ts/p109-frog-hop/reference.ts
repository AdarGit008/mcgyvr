export function canHop(pond: string[], from: number[], to: number[]): boolean {
  if (
    !Array.isArray(pond) ||
    pond.length !== 5 ||
    pond.some((row) => typeof row !== "string" || row.length !== 5)
  ) {
    throw new Error("malformed pond");
  }
  for (const square of [from, to]) {
    if (
      !Array.isArray(square) ||
      square.length !== 2 ||
      !square.every((n) => Number.isInteger(n) && n >= 0 && n <= 4)
    ) {
      throw new Error("a square must be a pair of integers between 0 and 4");
    }
  }
  if (pond[from[0]][from[1]] === ".") return false;
  if (pond[to[0]][to[1]] !== ".") return false;
  const dr = to[0] - from[0];
  const dc = to[1] - from[1];
  if (Math.abs(dr) + Math.abs(dc) === 1) return true;
  const vaultShape =
    (Math.abs(dr) === 2 && dc === 0) ||
    (dr === 0 && Math.abs(dc) === 2) ||
    (Math.abs(dr) === 2 && Math.abs(dc) === 2);
  if (!vaultShape) return false;
  return pond[from[0] + dr / 2][from[1] + dc / 2] !== ".";
}
