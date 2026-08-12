export function windowMax(readings: number[], width: number): number[] {
  const out: number[] = [];
  for (let start = 0; start + width <= readings.length; start += 1) {
    let best = readings[start];
    for (let step = 1; step < width; step += 1) {
      if (readings[start + step] > best) {
        best = readings[start + step];
      }
    }
    out.push(best);
  }
  return out;
}
