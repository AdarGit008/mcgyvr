export function graceWindow(counts: number[], goal: number, grace: number): number {
  if (goal <= 0) {
    throw new Error("goal must be positive");
  }
  if (grace < 0) {
    throw new Error("grace must not be negative");
  }
  const kept: number[] = [];
  counts.forEach((count, day) => {
    if (count >= goal) {
      kept.push(day);
    }
  });
  let best = 0;
  let left = 0;
  for (let right = 0; right < kept.length; right++) {
    while (kept[right] - kept[left] - (right - left) > grace) {
      left += 1;
    }
    best = Math.max(best, kept[right] - kept[left] + 1);
  }
  return best;
}
