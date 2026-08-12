/** Resolve a dispatcher's typed fragment against the station names on file. */
export function matchStation(names: string[], fragment: string): string | null {
  if (fragment === "") {
    throw new Error("the fragment must not be empty");
  }
  const needle = fragment.toLowerCase();
  let best: string | null = null;
  let bestRank: [number, number, string] = [0, 0, ""];
  for (const name of names) {
    const plain = name.toLowerCase();
    let kind = 0;
    if (plain === needle) kind = 1;
    else if (plain.startsWith(needle)) kind = 2;
    else if (plain.includes(needle)) kind = 3;
    else continue;
    const rank: [number, number, string] = [kind, plain.length, plain];
    const wins =
      best === null ||
      rank[0] < bestRank[0] ||
      (rank[0] === bestRank[0] &&
        (rank[1] < bestRank[1] ||
          (rank[1] === bestRank[1] && rank[2] < bestRank[2])));
    if (wins) {
      best = name;
      bestRank = rank;
    }
  }
  return best;
}
