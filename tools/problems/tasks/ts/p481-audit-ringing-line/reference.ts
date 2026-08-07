function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function isRounds(row: number[]): boolean {
  for (let seat = 0; seat < row.length; seat++) {
    if (row[seat] !== seat + 1) {
      return false;
    }
  }
  return true;
}

function shapely(row: number[], bells: number): boolean {
  if (row.length !== bells) {
    return false;
  }
  const held = new Set(row);
  if (held.size !== bells) {
    return false;
  }
  for (const bell of row) {
    if (bell < 1 || bell > bells) {
      return false;
    }
  }
  return true;
}

function neighbourly(before: number[], row: number[]): boolean {
  let seat = 0;
  while (seat < before.length) {
    if (before[seat] === row[seat]) {
      seat += 1;
      continue;
    }
    if (
      seat + 1 < before.length &&
      before[seat] === row[seat + 1] &&
      before[seat + 1] === row[seat]
    ) {
      seat += 2;
      continue;
    }
    return false;
  }
  return true;
}

export function auditRingingLine(
  rows: number[][],
): { ok: boolean; fault: string; row: number } {
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error("auditRingingLine expects a non-empty list of rows");
  }
  for (const row of rows) {
    if (!Array.isArray(row)) {
      throw new Error("a row is not a list");
    }
    for (const bell of row) {
      if (!whole(bell)) {
        throw new Error("a row entry is not whole");
      }
    }
  }
  const bells = rows[0].length;
  if (bells < 2) {
    throw new Error("the opening row holds fewer than two bells");
  }
  if (!isRounds(rows[0])) {
    throw new Error("the opening row is not rounds");
  }

  const rung = new Set<string>([rows[0].join(",")]);
  for (let seat = 1; seat < rows.length; seat++) {
    const row = rows[seat];
    if (!shapely(row, bells)) {
      return { ok: false, fault: "shape", row: seat + 1 };
    }
    if (!neighbourly(rows[seat - 1], row)) {
      return { ok: false, fault: "jump", row: seat + 1 };
    }
    const mark = row.join(",");
    if (rung.has(mark) && !(isRounds(row) && seat === rows.length - 1)) {
      return { ok: false, fault: "repeat", row: seat + 1 };
    }
    rung.add(mark);
  }
  return { ok: true, fault: "", row: 0 };
}
