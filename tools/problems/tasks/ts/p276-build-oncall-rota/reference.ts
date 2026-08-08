export function buildOnCallRota(roster: string[], blocked: string[][]): string[] {
  if (!Array.isArray(roster) || roster.length === 0) {
    throw new Error("the roster must hold at least one person");
  }
  const seen = new Set<string>();
  for (const name of roster) {
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a roster name must be a non-empty string");
    }
    if (seen.has(name)) {
      throw new Error("the roster repeats a name");
    }
    seen.add(name);
  }
  if (!Array.isArray(blocked) || blocked.length === 0) {
    throw new Error("there must be at least one shift");
  }

  const bans: Set<string>[] = [];
  for (const entry of blocked) {
    if (!Array.isArray(entry)) {
      throw new Error("a shift's blocked entry must be a list");
    }
    const ban = new Set<string>();
    for (const name of entry) {
      if (!seen.has(name)) {
        throw new Error("a blocked name is not on the roster");
      }
      if (ban.has(name)) {
        throw new Error("a name is blocked twice in one shift");
      }
      ban.add(name);
    }
    bans.push(ban);
  }

  const shifts = bans.length;
  const ceiling = Math.ceil(shifts / roster.length);
  const tally = new Map<string, number>(roster.map((name) => [name, 0]));
  const rota: string[] = [];
  let previous = "";

  for (let shift = 0; shift < shifts; shift++) {
    let chosen = "";
    for (const name of roster) {
      if (bans[shift].has(name) || name === previous) {
        continue;
      }
      const stood = tally.get(name) as number;
      if (stood >= ceiling) {
        continue;
      }
      if (chosen === "" || stood < (tally.get(chosen) as number)) {
        chosen = name;
      }
    }
    if (chosen === "") {
      return [];
    }
    tally.set(chosen, (tally.get(chosen) as number) + 1);
    rota.push(chosen);
    previous = chosen;
  }
  return rota;
}
