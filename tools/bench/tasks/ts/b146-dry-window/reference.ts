export function driestWindow(rain: number[], width: number): number {
  if (!Array.isArray(rain)) throw new Error("rain must be a list of daily readings");
  if (rain.some((r) => !Number.isInteger(r) || r < 0)) {
    throw new Error("every reading must be a non-negative integer");
  }
  if (!Number.isInteger(width) || width < 1) throw new Error("width must be a positive whole number");
  if (width > rain.length) throw new Error("width exceeds the number of days");
  let best = 0;
  let bestTotal = Infinity;
  for (let start = 0; start + width <= rain.length; start += 1) {
    let total = 0;
    for (let day = start; day < start + width; day += 1) total += rain[day];
    if (total < bestTotal) {
      bestTotal = total;
      best = start;
    }
  }
  return best;
}
