type Booking = {
  id: string;
  start: number;
  end: number;
  fixed: boolean;
};

function byId(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

export function planRoomMoves(bookings: any[]): string[] {
  if (!Array.isArray(bookings)) {
    throw new Error("planRoomMoves expects a list of bookings");
  }
  const seen = new Set<string>();
  for (const row of bookings) {
    if (row === null || typeof row !== "object" || Array.isArray(row)) {
      throw new Error("each booking must be a record");
    }
    if (typeof row.id !== "string" || row.id === "") {
      throw new Error("id must be a non-empty string");
    }
    if (!Number.isInteger(row.start) || !Number.isInteger(row.end)) {
      throw new Error("start and end must be integers");
    }
    if (row.start >= row.end) {
      throw new Error("start must come strictly before end");
    }
    if (typeof row.fixed !== "boolean") {
      throw new Error("fixed must be a boolean");
    }
    if (seen.has(row.id)) {
      throw new Error("repeated booking id: " + row.id);
    }
    seen.add(row.id);
  }

  const rows = bookings as Booking[];
  const nailed = rows
    .filter((row) => row.fixed)
    .slice()
    .sort((a, b) => a.start - b.start || a.end - b.end);
  for (let i = 1; i < nailed.length; i++) {
    if (nailed[i].start < nailed[i - 1].end) {
      throw new Error("two fixed bookings overlap and cannot be repaired");
    }
  }

  const moved: Booking[] = [];
  const loose: Booking[] = [];
  for (const row of rows) {
    if (row.fixed) {
      continue;
    }
    const clashes = nailed.some(
      (nail) => row.start < nail.end && nail.start < row.end,
    );
    if (clashes) {
      moved.push(row);
    } else {
      loose.push(row);
    }
  }

  loose.sort((a, b) => a.end - b.end || a.start - b.start || byId(a.id, b.id));
  const kept = new Set<string>();
  let last: number | null = null;
  for (const row of loose) {
    if (last === null || row.start >= last) {
      kept.add(row.id);
      last = row.end;
    }
  }
  for (const row of loose) {
    if (!kept.has(row.id)) {
      moved.push(row);
    }
  }

  moved.sort((a, b) => a.start - b.start || byId(a.id, b.id));
  return moved.map((row) => row.id);
}
