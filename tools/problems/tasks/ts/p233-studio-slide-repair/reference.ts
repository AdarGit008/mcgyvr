export function slideSessions(
  sessions: any[],
  opensAt: number,
  closesAt: number,
): string[] {
  if (!Number.isInteger(opensAt) || !Number.isInteger(closesAt)) {
    throw new Error("the day's bounds must be integers");
  }
  if (opensAt >= closesAt) {
    throw new Error("the studio must close after it opens");
  }
  const seen = new Set<string>();
  for (const row of sessions) {
    if (row === null || typeof row !== "object" || Array.isArray(row)) {
      throw new Error("each request must be a record");
    }
    if (typeof row.id !== "string" || row.id === "") {
      throw new Error("id must be a non-empty string");
    }
    if (!Number.isInteger(row.want)) {
      throw new Error("want must be an integer");
    }
    if (!Number.isInteger(row.span) || row.span < 1) {
      throw new Error("span must be a positive integer");
    }
    if (seen.has(row.id)) {
      throw new Error("repeated request id: " + row.id);
    }
    seen.add(row.id);
  }

  const placed: number[][] = [];
  const booked: string[] = [];
  for (const row of sessions) {
    const earliest = Math.max(row.want, opensAt);
    const tries = new Set<number>([earliest]);
    for (const span of placed) {
      if (span[1] >= earliest) {
        tries.add(span[1]);
      }
    }
    let granted = -1;
    for (const moment of [...tries].sort((a, b) => a - b)) {
      if (moment + row.span > closesAt) {
        break;
      }
      const clash = placed.some(
        (span) => moment < span[1] && span[0] < moment + row.span,
      );
      if (!clash) {
        granted = moment;
        break;
      }
    }
    if (granted < 0) {
      booked.push(row.id + " away");
    } else {
      placed.push([granted, granted + row.span]);
      booked.push(row.id + " " + granted);
    }
  }
  return booked;
}
