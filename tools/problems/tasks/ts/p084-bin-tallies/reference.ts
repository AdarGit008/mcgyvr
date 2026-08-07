export function binTallies(
  readings: number[],
  edges: number[],
): { bands: number[]; below: number; above: number } {
  if (edges.length < 2) {
    throw new Error("need at least two edges");
  }
  for (let i = 1; i < edges.length; i++) {
    if (edges[i] <= edges[i - 1]) {
      throw new Error("edges must be strictly increasing");
    }
  }
  const bands = new Array(edges.length - 1).fill(0);
  let below = 0;
  let above = 0;
  for (const reading of readings) {
    if (reading < edges[0]) {
      below += 1;
    } else if (reading >= edges[edges.length - 1]) {
      above += 1;
    } else {
      for (let i = 0; i < bands.length; i++) {
        if (reading < edges[i + 1]) {
          bands[i] += 1;
          break;
        }
      }
    }
  }
  return { bands, below, above };
}
