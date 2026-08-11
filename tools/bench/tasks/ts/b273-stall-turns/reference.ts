export function stallTurns(counts: number[], limit: number): number {
  let turns = 0;
  for (const count of counts) {
    if (count > 0) {
      turns += Math.ceil(count / limit);
    }
  }
  return turns;
}
