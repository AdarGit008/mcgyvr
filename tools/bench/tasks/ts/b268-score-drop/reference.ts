export function scoreDrop(scores: number[]): number {
  if (scores.length < 2) {
    return 0;
  }
  let lowest = scores[0];
  let total = 0;
  for (const score of scores) {
    total += score;
    if (score < lowest) {
      lowest = score;
    }
  }
  return total - lowest;
}
