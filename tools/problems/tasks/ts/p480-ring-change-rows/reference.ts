function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function ringChangeRows(
  bells: number,
  changes: number[][],
  count: number,
): number[][] {
  if (!whole(bells) || bells < 2 || bells > 12) {
    throw new Error("the bells are not whole or fall outside two to twelve");
  }
  if (!Array.isArray(changes) || changes.length === 0) {
    throw new Error("the changes are not a list or are empty");
  }
  if (!whole(count) || count < 1) {
    throw new Error("the count is not whole or falls below one");
  }

  const standing: Set<number>[] = [];
  for (const change of changes) {
    if (!Array.isArray(change)) {
      throw new Error("a change is not a list");
    }
    const places = new Set<number>();
    let highest = 0;
    for (const place of change) {
      if (!whole(place) || place < 1 || place > bells) {
        throw new Error("a place is not whole or falls outside one to the bells");
      }
      if (place <= highest) {
        throw new Error("a change's places do not climb strictly");
      }
      highest = place;
      places.add(place);
    }
    let at = 1;
    while (at <= bells) {
      if (places.has(at)) {
        at += 1;
        continue;
      }
      if (at + 1 > bells || places.has(at + 1)) {
        throw new Error("a change's movers do not pair off");
      }
      at += 2;
    }
    standing.push(places);
  }

  let row: number[] = [];
  for (let bell = 1; bell <= bells; bell++) {
    row.push(bell);
  }
  const rows: number[][] = [row];
  for (let rung = 1; rung < count; rung++) {
    const places = standing[(rung - 1) % standing.length];
    const next = row.slice();
    let at = 1;
    while (at <= bells) {
      if (places.has(at)) {
        at += 1;
        continue;
      }
      next[at - 1] = row[at];
      next[at] = row[at - 1];
      at += 2;
    }
    rows.push(next);
    row = next;
  }

  return rows;
}
