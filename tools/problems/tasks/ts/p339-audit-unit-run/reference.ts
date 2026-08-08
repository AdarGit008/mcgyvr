const RUNNING_CEILING = 1000000000;

function greatestCommon(a: number, b: number): number {
  let left = Math.abs(a);
  let right = Math.abs(b);
  while (right !== 0) {
    const rest = left % right;
    left = right;
    right = rest;
  }
  return left;
}

export function auditUnitRun(
  top: number,
  bottom: number,
  parts: number[],
): { verdict: string; gap: number[] } {
  if (!Number.isInteger(top) || top < 0 || top > 100000) {
    throw new Error("the top must be a whole number from 0 through 100000");
  }
  if (!Number.isInteger(bottom) || bottom < 1 || bottom > 100000) {
    throw new Error("the bottom must be a whole number from 1 through 100000");
  }
  if (!Array.isArray(parts)) {
    throw new Error("the run must be a list");
  }
  if (parts.length > 10) {
    throw new Error("a run may hold at most ten pieces");
  }
  let earlier = 1;
  for (const piece of parts) {
    if (!Number.isInteger(piece) || piece < 2 || piece > 100000) {
      throw new Error("a piece must be a whole number from 2 through 100000");
    }
    if (piece <= earlier) {
      throw new Error("the pieces must strictly rise");
    }
    earlier = piece;
  }

  let sumTop = 0;
  let sumBottom = 1;
  for (const piece of parts) {
    const nextTop = sumTop * piece + sumBottom;
    const nextBottom = sumBottom * piece;
    const common = greatestCommon(nextTop, nextBottom);
    sumTop = nextTop / common;
    sumBottom = nextBottom / common;
    if (sumBottom > RUNNING_CEILING) {
      throw new Error("the running total's bottom has passed the ceiling");
    }
  }

  const gapTop = top * sumBottom - sumTop * bottom;
  if (gapTop === 0) {
    return { verdict: "exact", gap: [0, 1] };
  }
  const gapBottom = bottom * sumBottom;
  const common = greatestCommon(gapTop, gapBottom);
  return {
    verdict: gapTop > 0 ? "short" : "over",
    gap: [gapTop / common, gapBottom / common],
  };
}
