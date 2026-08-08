const BOTTOM_CEILING = 10000000;

function floorDiv(a: number, b: number): number {
  let quotient = Math.trunc(a / b);
  let rest = a - quotient * b;
  while (rest < 0) {
    quotient -= 1;
    rest += b;
  }
  while (rest >= b) {
    quotient += 1;
    rest -= b;
  }
  return quotient;
}

function ceilDiv(a: number, b: number): number {
  const quotient = floorDiv(a, b);
  return quotient * b === a ? quotient : quotient + 1;
}

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

export function greedyUnitParts(top: number, bottom: number): number[] {
  if (!Number.isInteger(top) || !Number.isInteger(bottom)) {
    throw new Error("top and bottom must be whole numbers");
  }
  if (bottom < 1 || bottom > 10000) {
    throw new Error("the bottom must lie in 1 through 10000");
  }
  if (top < 1) {
    throw new Error("the top must be above nothing");
  }
  if (top >= bottom) {
    throw new Error("the quotient must be below one");
  }

  const parts: number[] = [];
  let restTop = top;
  let restBottom = bottom;
  const shrink = greatestCommon(restTop, restBottom);
  restTop /= shrink;
  restBottom /= shrink;

  while (restTop !== 0) {
    if (restBottom > BOTTOM_CEILING) {
      throw new Error("the remainder's bottom has exploded past the ceiling");
    }
    const piece = ceilDiv(restBottom, restTop);
    parts.push(piece);
    const nextTop = restTop * piece - restBottom;
    const nextBottom = restBottom * piece;
    if (nextTop === 0) {
      restTop = 0;
      restBottom = 1;
      break;
    }
    const common = greatestCommon(nextTop, nextBottom);
    restTop = nextTop / common;
    restBottom = nextBottom / common;
  }
  return parts;
}
