export function voteLead(ballots: string[]): string {
  if (ballots.length === 0) {
    throw new Error("no ballots cast");
  }
  const tally: Record<string, number> = {};
  for (const name of ballots) {
    tally[name] = (tally[name] ?? 0) + 1;
  }
  const names = Object.keys(tally).sort();
  return names.reduce((best, name) => (tally[name] > tally[best] ? name : best));
}
