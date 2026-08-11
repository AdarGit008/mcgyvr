/** The three highest scores, highest first. */
export function topThree(scores: number[]): number[] {
  return [...scores].sort((a, b) => b - a).slice(0, 3);
}
