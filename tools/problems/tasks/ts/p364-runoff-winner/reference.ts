export function runoffWinner(ballots: string[][]): string {
  if (!Array.isArray(ballots) || ballots.length === 0) {
    throw new Error("there must be at least one ballot");
  }
  const papers: string[][] = [];
  for (const ballot of ballots) {
    if (!Array.isArray(ballot) || ballot.length === 0) {
      throw new Error("a ballot must be a non-empty list");
    }
    const seen = new Set<string>();
    for (const name of ballot) {
      if (typeof name !== "string" || name.length === 0) {
        throw new Error("an option must be a non-empty string");
      }
      if (seen.has(name)) {
        throw new Error("a ballot names one option twice");
      }
      seen.add(name);
    }
    papers.push([...ballot]);
  }

  const standing = new Set<string>();
  for (const ballot of papers) {
    for (const name of ballot) {
      standing.add(name);
    }
  }

  for (;;) {
    const tally = new Map<string, number>();
    for (const name of standing) {
      tally.set(name, 0);
    }
    let counted = 0;
    for (const ballot of papers) {
      const top = ballot.find((name) => standing.has(name));
      if (top !== undefined) {
        tally.set(top, (tally.get(top) as number) + 1);
        counted += 1;
      }
    }
    for (const [name, votes] of tally) {
      if (votes * 2 > counted) {
        return name;
      }
    }
    if (standing.size === 1) {
      return [...standing][0];
    }
    let doomed = "";
    let fewest = Number.POSITIVE_INFINITY;
    for (const [name, votes] of tally) {
      if (votes < fewest || (votes === fewest && name > doomed)) {
        fewest = votes;
        doomed = name;
      }
    }
    standing.delete(doomed);
  }
}
