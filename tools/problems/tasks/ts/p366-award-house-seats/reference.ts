export function awardHouseSeats(
  rolls: Array<[string, number]>,
  seats: number,
): Record<string, number> {
  if (!Array.isArray(rolls) || rolls.length === 0) {
    throw new Error("there must be at least one roll");
  }
  if (typeof seats !== "number" || !Number.isInteger(seats) || seats < 1) {
    throw new Error("the seat count must be a whole number above zero");
  }
  const read: Array<{ name: string; tally: number; held: number; at: number }> =
    [];
  const names = new Set<string>();
  rolls.forEach((roll, at) => {
    if (!Array.isArray(roll) || roll.length !== 2) {
      throw new Error("a roll must be a two-element list");
    }
    const [name, tally] = roll;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a party name must be a non-empty string");
    }
    if (names.has(name)) {
      throw new Error("two rolls share a party name");
    }
    names.add(name);
    if (typeof tally !== "number" || !Number.isInteger(tally) || tally < 0) {
      throw new Error("a tally must be a whole number that is not negative");
    }
    read.push({ name, tally, held: 0, at });
  });

  const total = read.reduce((sum, roll) => sum + roll.tally, 0);
  if (total === 0) {
    throw new Error("every tally is zero");
  }
  const standing = read.filter((roll) => roll.tally * 5 >= total);
  if (standing.length === 0) {
    throw new Error("striking left no roll standing");
  }

  for (let given = 0; given < seats; given += 1) {
    let best = standing[0];
    for (const roll of standing.slice(1)) {
      const mine = roll.tally * (best.held + 1);
      const theirs = best.tally * (roll.held + 1);
      if (mine > theirs || (mine === theirs && roll.tally > best.tally)) {
        best = roll;
      }
    }
    best.held += 1;
  }

  const answer: Record<string, number> = {};
  for (const roll of standing) {
    answer[roll.name] = roll.held;
  }
  return answer;
}
