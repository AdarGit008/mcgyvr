export function segmentRelation(one: number[][], other: number[][]): string {
  const whole = (value: any) =>
    typeof value === "number" && Number.isInteger(value);
  const rod = (given: any): number[][] => {
    if (!Array.isArray(given) || given.length !== 2) {
      throw new Error("a rod must be a list of exactly two tips");
    }
    const tips: number[][] = [];
    for (const tip of given) {
      if (
        !Array.isArray(tip) ||
        tip.length !== 2 ||
        !whole(tip[0]) ||
        !whole(tip[1])
      ) {
        throw new Error("a tip must be a pair of two whole numbers");
      }
      if (Math.abs(tip[0]) > 500 || Math.abs(tip[1]) > 500) {
        throw new Error("a measure magnitude passes five hundred");
      }
      tips.push([tip[0] + 0, tip[1] + 0]);
    }
    if (tips[0][0] === tips[1][0] && tips[0][1] === tips[1][1]) {
      throw new Error("a rod's tips coincide");
    }
    return tips;
  };
  const [a, b] = rod(one);
  const [c, d] = rod(other);
  const rx = b[0] - a[0];
  const ry = b[1] - a[1];
  const sx = d[0] - c[0];
  const sy = d[1] - c[1];
  const qx = c[0] - a[0];
  const qy = c[1] - a[1];
  const twist = rx * sy - ry * sx;
  const rank = (p: number[], q: number[]) => p[0] - q[0] || p[1] - q[1];
  if (twist === 0) {
    if (qx * ry - qy * rx !== 0) {
      return "clear";
    }
    const mine = [a, b].sort(rank);
    const yours = [c, d].sort(rank);
    const low = rank(mine[0], yours[0]) >= 0 ? mine[0] : yours[0];
    const high = rank(mine[1], yours[1]) <= 0 ? mine[1] : yours[1];
    const span = rank(low, high);
    if (span > 0) {
      return "clear";
    }
    return span === 0 ? "pinned" : "shared";
  }
  let bottom = twist;
  let along = qx * sy - qy * sx;
  let across = qx * ry - qy * rx;
  if (bottom < 0) {
    bottom = -bottom;
    along = -along;
    across = -across;
  }
  if (along < 0 || along > bottom || across < 0 || across > bottom) {
    return "clear";
  }
  const wide = a[0] * bottom + along * rx;
  const tall = a[1] * bottom + along * ry;
  return wide % bottom === 0 && tall % bottom === 0 ? "pinned" : "adrift";
}
