export function hullCorners(markers: number[][]): number[][] {
  if (!Array.isArray(markers) || markers.length === 0) {
    throw new Error("hullCorners expects a non-empty list of markers");
  }
  const whole = (value: any) =>
    typeof value === "number" && Number.isInteger(value);
  const points: number[][] = [];
  for (const marker of markers) {
    if (
      !Array.isArray(marker) ||
      marker.length !== 2 ||
      !whole(marker[0]) ||
      !whole(marker[1])
    ) {
      throw new Error("a marker must be a pair of two whole numbers");
    }
    if (Math.abs(marker[0]) > 1000000 || Math.abs(marker[1]) > 1000000) {
      throw new Error("a coordinate magnitude passes one million");
    }
    points.push([marker[0] + 0, marker[1] + 0]);
  }
  points.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const spots: number[][] = [];
  for (const point of points) {
    const last = spots[spots.length - 1];
    if (last === undefined || last[0] !== point[0] || last[1] !== point[1]) {
      spots.push(point);
    }
  }
  if (spots.length === 1) {
    return [spots[0]];
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
  const lower = chainOf(spots);
  const upper = chainOf(spots.slice().reverse());
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}
