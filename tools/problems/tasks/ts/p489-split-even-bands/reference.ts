function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function splitEvenBands(entries: any[], bands: number): any[] {
  if (!Array.isArray(entries) || entries.length === 0) {
    throw new Error("entries must be a list holding at least one entry");
  }
  const seen = new Set<string>();
  const held: { who: string; mark: number }[] = [];
  for (const entry of entries) {
    if (!isRecord(entry)) {
      throw new Error("each entry must be a record");
    }
    if (typeof entry.who !== "string" || entry.who.length === 0) {
      throw new Error("who must be a non-empty string");
    }
    if (seen.has(entry.who)) {
      throw new Error(`two entries answer to ${entry.who}`);
    }
    seen.add(entry.who);
    if (
      typeof entry.mark !== "number" ||
      !Number.isInteger(entry.mark) ||
      entry.mark < 0
    ) {
      throw new Error("mark must be a whole number of nought or more");
    }
    held.push({ who: entry.who, mark: entry.mark });
  }
  if (
    typeof bands !== "number" ||
    !Number.isInteger(bands) ||
    bands < 1 ||
    bands > held.length
  ) {
    throw new Error("bands must be a whole number from one up to the entry count");
  }

  const seated = [...held].sort((a, b) => {
    if (a.mark !== b.mark) {
      return b.mark - a.mark;
    }
    return a.who < b.who ? -1 : a.who > b.who ? 1 : 0;
  });

  const lowest = new Map<number, number>();
  seated.forEach((member, seat) => {
    const band = Math.floor((seat * bands) / seated.length) + 1;
    const soFar = lowest.get(member.mark);
    if (soFar === undefined || band < soFar) {
      lowest.set(member.mark, band);
    }
  });

  return held.map((member) => ({
    who: member.who,
    band: lowest.get(member.mark),
  }));
}
