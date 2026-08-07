export function drawBranchLanes(
  entries: { id: string; branch: string }[],
): string[] {
  if (!Array.isArray(entries) || entries.length === 0) {
    throw new Error("there must be at least one entry to draw");
  }
  const seenIds = new Set<string>();
  for (const entry of entries) {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      throw new Error("every entry must be a mapping");
    }
    for (const field of ["id", "branch"] as const) {
      const held = entry[field];
      if (typeof held !== "string" || held.length === 0) {
        throw new Error(`every entry needs a non-empty ${field}`);
      }
    }
    if (seenIds.has(entry.id)) {
      throw new Error(`two entries share the id ${entry.id}`);
    }
    seenIds.add(entry.id);
  }

  const lastRow = new Map<string, number>();
  entries.forEach((entry, row) => lastRow.set(entry.branch, row));

  const lanes = new Map<string, number>();
  const rows: string[] = [];
  entries.forEach((entry, row) => {
    if (!lanes.has(entry.branch)) {
      const taken = new Set(lanes.values());
      let lane = 0;
      while (taken.has(lane)) {
        lane += 1;
      }
      lanes.set(entry.branch, lane);
    }
    const own = lanes.get(entry.branch)!;
    const held = new Set(lanes.values());
    let highest = 0;
    for (const lane of held) {
      if (lane > highest) {
        highest = lane;
      }
    }
    const marks: string[] = [];
    for (let lane = 0; lane <= highest; lane++) {
      if (lane === own) {
        marks.push("*");
      } else if (held.has(lane)) {
        marks.push("|");
      } else {
        marks.push(" ");
      }
    }
    rows.push(`${marks.join(" ")} ${entry.id}`);
    if (lastRow.get(entry.branch) === row) {
      lanes.delete(entry.branch);
    }
  });
  return rows;
}
