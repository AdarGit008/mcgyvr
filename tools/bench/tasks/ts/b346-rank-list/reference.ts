export function rankOf(score: number, scores: number[]): number {
  let above = 0;
  for (const other of scores) {
    if (other > score) {
      above += 1;
    }
  }
  return above + 1;
}

/** Each score's rank, in the order the scores were given. */
export function rankAll(scores: number[]): number[] {
  return scores.map((score) => rankOf(score, scores));
}
