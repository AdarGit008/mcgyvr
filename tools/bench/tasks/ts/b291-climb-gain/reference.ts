export function legGain(start: number, end: number): number {
  if (end > start) {
    return end - start;
  }
  return 0;
}

export function climbGain(heights: number[]): number {
  let total = 0;
  for (let i = 1; i < heights.length; i += 1) {
    total += legGain(heights[i - 1], heights[i]);
  }
  return total;
}
