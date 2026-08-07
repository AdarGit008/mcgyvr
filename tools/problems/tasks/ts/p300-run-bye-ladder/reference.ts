type Round = { bye: string | null; matches: string[][] };

export function runByeLadder(
  seeds: string[],
  upsets: string[],
): { rounds: Round[]; champion: string } {
  if (!Array.isArray(seeds) || !Array.isArray(upsets)) {
    throw new Error("runByeLadder expects two lists");
  }
  if (seeds.length < 2) {
    throw new Error("a ladder needs at least two entrants");
  }
  const rank = new Map<string, number>();
  for (const name of seeds) {
    if (typeof name !== "string") {
      throw new Error("an entrant name is a string");
    }
    if (rank.has(name)) {
      throw new Error("entered twice: " + name);
    }
    rank.set(name, rank.size);
  }
  const beats = new Set<string>();
  for (const name of upsets) {
    if (typeof name !== "string" || !rank.has(name)) {
      throw new Error("upset names no entrant: " + String(name));
    }
    if (beats.has(name)) {
      throw new Error("upset named twice: " + name);
    }
    beats.add(name);
  }

  const sat = new Set<string>();
  const rounds: Round[] = [];
  let alive = seeds.slice();
  while (alive.length > 1) {
    let bye: string | null = null;
    let playing = alive;
    if (alive.length % 2 === 1) {
      bye = alive[0];
      for (const name of alive) {
        if (!sat.has(name)) {
          bye = name;
          break;
        }
      }
      sat.add(bye);
      playing = alive.filter((name) => name !== bye);
    }
    const matches: string[][] = [];
    const winners: string[] = [];
    for (let at = 0; at < playing.length / 2; at++) {
      const stronger = playing[at];
      const weaker = playing[playing.length - 1 - at];
      matches.push([stronger, weaker]);
      winners.push(beats.has(weaker) ? weaker : stronger);
    }
    if (bye !== null) {
      winners.push(bye);
    }
    winners.sort((one, two) => rank.get(one) - rank.get(two));
    alive = winners;
    rounds.push({ bye, matches });
  }
  return { rounds, champion: alive[0] };
}
