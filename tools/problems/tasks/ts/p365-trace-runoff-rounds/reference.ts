export function traceRunoffRounds(papers: string[][]): string[] {
  if (!Array.isArray(papers) || papers.length === 0) {
    throw new Error("there must be at least one paper");
  }
  const sheets: string[][] = [];
  const met: string[] = [];
  for (const paper of papers) {
    if (!Array.isArray(paper) || paper.length === 0) {
      throw new Error("a paper must be a non-empty list");
    }
    const seen = new Set<string>();
    for (const name of paper) {
      if (typeof name !== "string" || name.length === 0) {
        throw new Error("a runner must be a non-empty string");
      }
      if (name.includes("|") || name.includes(",") || name.includes("=")) {
        throw new Error("a runner name may not hold a bar, comma or equals");
      }
      if (seen.has(name)) {
        throw new Error("a paper names one runner twice");
      }
      seen.add(name);
      if (!met.includes(name)) {
        met.push(name);
      }
    }
    sheets.push([...paper]);
  }

  let standing = [...met];
  let prior: Map<string, number> | null = null;
  const lines: string[] = [];
  let round = 1;

  for (;;) {
    const tally = new Map<string, number>();
    for (const name of standing) {
      tally.set(name, 0);
    }
    let handed = 0;
    for (const sheet of sheets) {
      const top = sheet.find((name) => tally.has(name));
      if (top !== undefined) {
        tally.set(top, (tally.get(top) as number) + 1);
        handed += 1;
      }
    }
    const shown = [...standing].sort((a, b) => {
      const gap = (tally.get(b) as number) - (tally.get(a) as number);
      return gap === 0 ? met.indexOf(a) - met.indexOf(b) : gap;
    });
    const body = shown.map((name) => `${name}=${tally.get(name)}`).join(",");

    const winner = standing.find(
      (name) => (tally.get(name) as number) * 2 > handed,
    );
    if (winner !== undefined || standing.length === 1) {
      lines.push(`${round}|${body}|won:${winner ?? standing[0]}`);
      return lines;
    }

    const fewest = Math.min(...standing.map((name) => tally.get(name) as number));
    let doomedSet = standing.filter((name) => tally.get(name) === fewest);
    if (doomedSet.length > 1 && prior !== null) {
      const past = prior;
      const lowest = Math.min(...doomedSet.map((name) => past.get(name) as number));
      doomedSet = doomedSet.filter((name) => past.get(name) === lowest);
    }
    const doomed = doomedSet.reduce((a, b) =>
      met.indexOf(a) > met.indexOf(b) ? a : b,
    );
    lines.push(`${round}|${body}|out:${doomed}`);
    standing = standing.filter((name) => name !== doomed);
    prior = tally;
    round += 1;
  }
}
