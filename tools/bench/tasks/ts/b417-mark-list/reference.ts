/** Scores written out, with a star against those that reach a floor. */
export function markList(scores: number[], floor: number): string[] {
  const out: string[] = [];
  for (const score of scores) {
    out.push(score >= floor ? String(score) + "*" : String(score));
  }
  return out;
}
