export function hotStreak(scores: number[], bar: number): number[] {
  let best: number[] = [-1, 0];
  let start = -1;
  for (let i = 0; i < scores.length; i++) {
    if (scores[i] > bar) {
      if (start === -1) {
        start = i;
      }
      const length = i - start + 1;
      if (length > best[1]) {
        best = [start, length];
      }
    } else {
      start = -1;
    }
  }
  return best;
}
