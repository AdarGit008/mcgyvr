export function hullEdgeStops(pegs: number[][]): number {
  if (!Array.isArray(pegs) || pegs.length === 0) {
    throw new Error("hullEdgeStops expects a non-empty list of pegs");
  }
  const whole = (value: any) =>
    typeof value === "number" && Number.isInteger(value);
  const points: number[][] = [];
  for (const peg of pegs) {
    if (
      !Array.isArray(peg) ||
      peg.length !== 2 ||
      !whole(peg[0]) ||
      !whole(peg[1])
    ) {
      throw new Error("a peg must be a pair of two whole numbers");
    }
    if (Math.abs(peg[0]) > 1000000 || Math.abs(peg[1]) > 1000000) {
      throw new Error("a coordinate magnitude passes one million");
    }
    points.push([peg[0] + 0, peg[1] + 0]);
  }
  points.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const spots: number[][] = [];
  for (const point of points) {
    const last = spots[spots.length - 1];
    if (last === undefined || last[0] !== point[0] || last[1] !== point[1]) {
      spots.push(point);
    }
  }
  const turn = (o: number[], a: number[], b: number[]) =>
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const chainOf = (order: number[][]) => {
    const chain: number[][] = [];
    for (const point of order) {
      while (
        chain.length >= 2 &&
        turn(chain[chain.length - 2], chain[chain.length - 1], point) <= 0
      ) {
        chain.pop();
      }
      chain.push(point);
    }
    return chain;
  };
  const posts =
    spots.length === 1
      ? [spots[0]]
      : chainOf(spots)
          .slice(0, -1)
          .concat(chainOf(spots.slice().reverse()).slice(0, -1));
  const rungs = (a: number, b: number) => {
    let x = Math.abs(a);
    let y = Math.abs(b);
    while (y !== 0) {
      const rest = x % y;
      x = y;
      y = rest;
    }
    return x;
  };
  if (posts.length === 1) {
    return 1;
  }
  if (posts.length === 2) {
    return rungs(posts[1][0] - posts[0][0], posts[1][1] - posts[0][1]) + 1;
  }
  let stops = 0;
  for (let i = 0; i < posts.length; i++) {
    const here = posts[i];
    const next = posts[(i + 1) % posts.length];
    stops += rungs(next[0] - here[0], next[1] - here[1]);
  }
  return stops;
}
