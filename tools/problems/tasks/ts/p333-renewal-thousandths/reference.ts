export function renewalThousandths(
  squads: Array<[string, number, number[]]>,
): Array<[string, number[]]> {
  if (!Array.isArray(squads)) {
    throw new Error("squads must be a list");
  }
  const used = new Set<string>();
  const out: Array<[string, number[]]> = [];
  for (const squad of squads) {
    if (!Array.isArray(squad) || squad.length !== 3) {
      throw new Error("every squad must be a triple");
    }
    const name = squad[0];
    const seats = squad[1];
    const run = squad[2];
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a squad name must be a non-empty string");
    }
    if (used.has(name)) {
      throw new Error(`two squads answer to ${name}`);
    }
    used.add(name);
    if (!Number.isInteger(seats) || seats < 1 || seats > 1000000) {
      throw new Error("seats must be a whole number from 1 through 1000000");
    }
    if (!Array.isArray(run)) {
      throw new Error("a squad's run must be a list");
    }
    const strengths: number[] = [];
    let previous = seats;
    for (const tally of run) {
      if (!Number.isInteger(tally) || tally < 0 || tally > seats) {
        throw new Error("a cycle tally must be a whole number within seats");
      }
      if (tally > previous) {
        throw new Error("seats are never regained");
      }
      previous = tally;
      strengths.push(Math.floor((tally * 2000 + seats) / (2 * seats)));
    }
    out.push([name, strengths]);
  }
  return out;
}
