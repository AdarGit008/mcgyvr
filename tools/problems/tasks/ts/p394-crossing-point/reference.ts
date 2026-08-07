export function crossingPoint(first: number[][], second: number[][]): any {
  const whole = (value: any) =>
    typeof value === "number" && Number.isInteger(value);
  const read = (stroke: any): number[][] => {
    if (!Array.isArray(stroke) || stroke.length !== 2) {
      throw new Error("a stroke must be a list of exactly two ends");
    }
    const ends: number[][] = [];
    for (const end of stroke) {
      if (
        !Array.isArray(end) ||
        end.length !== 2 ||
        !whole(end[0]) ||
        !whole(end[1])
      ) {
        throw new Error("an end must be a pair of two whole numbers");
      }
      if (Math.abs(end[0]) > 1000 || Math.abs(end[1]) > 1000) {
        throw new Error("a coordinate magnitude passes one thousand");
      }
      ends.push([end[0] + 0, end[1] + 0]);
    }
    if (ends[0][0] === ends[1][0] && ends[0][1] === ends[1][1]) {
      throw new Error("a stroke's two ends sit on the same spot");
    }
    return ends;
  };
  const [a, b] = read(first);
  const [c, d] = read(second);
  const rx = b[0] - a[0];
  const ry = b[1] - a[1];
  const sx = d[0] - c[0];
  const sy = d[1] - c[1];
  const qx = c[0] - a[0];
  const qy = c[1] - a[1];
  const denom = rx * sy - ry * sx;
  const order = (p: number[], q: number[]) => p[0] - q[0] || p[1] - q[1];
  const reduce = (top: number, bottom: number) => {
    let x = Math.abs(top);
    let y = bottom;
    while (y !== 0) {
      const rest = x % y;
      x = y;
      y = rest;
    }
    const step = x === 0 ? 1 : x;
    const num = top / step;
    return [num === 0 ? 0 : num, bottom / step];
  };
  if (denom === 0) {
    if (qx * ry - qy * rx !== 0) {
      return { kind: "apart" };
    }
    const mine = [a, b].sort(order);
    const yours = [c, d].sort(order);
    const low = order(mine[0], yours[0]) >= 0 ? mine[0] : yours[0];
    const high = order(mine[1], yours[1]) <= 0 ? mine[1] : yours[1];
    const gap = order(low, high);
    if (gap > 0) {
      return { kind: "apart" };
    }
    if (gap === 0) {
      return { kind: "point", x: [low[0], 1], y: [low[1], 1] };
    }
    return { kind: "stretch", from: low, to: high };
  }
  let bottom = denom;
  let along = qx * sy - qy * sx;
  let across = qx * ry - qy * rx;
  if (bottom < 0) {
    bottom = -bottom;
    along = -along;
    across = -across;
  }
  if (along < 0 || along > bottom || across < 0 || across > bottom) {
    return { kind: "apart" };
  }
  return {
    kind: "point",
    x: reduce(a[0] * bottom + along * rx, bottom),
    y: reduce(a[1] * bottom + along * ry, bottom),
  };
}
