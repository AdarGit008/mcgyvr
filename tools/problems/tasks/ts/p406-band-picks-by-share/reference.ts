type Line = { code: string; picks: number };
type Row = { code: string; capacity: number };
type Placement = { code: string; band: string; row: string; slot: number };

function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readLines(lines: { code: string; picks: number }[]): Line[] {
  if (!Array.isArray(lines) || lines.length === 0) {
    throw new Error("the line list must hold at least one line");
  }
  const seen = new Set<string>();
  const held: Line[] = [];
  for (const line of lines) {
    if (!isRecord(line)) {
      throw new Error("a line must be a record");
    }
    const code = line.code;
    if (typeof code !== "string" || code.length === 0) {
      throw new Error("a code must be a non-empty string");
    }
    if (seen.has(code)) {
      throw new Error("code " + code + " appears twice");
    }
    seen.add(code);
    const picks = line.picks;
    if (!Number.isInteger(picks) || picks < 0) {
      throw new Error("picks must be a whole number of nothing or more");
    }
    held.push({ code, picks });
  }
  return held;
}

function readRows(rows: { code: string; capacity: number }[]): Row[] {
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error("the row list must hold at least one row");
  }
  const seen = new Set<string>();
  const shelves: Row[] = [];
  for (const row of rows) {
    if (!isRecord(row)) {
      throw new Error("a row must be a record");
    }
    const code = row.code;
    if (typeof code !== "string" || code.length === 0) {
      throw new Error("a row code must be a non-empty string");
    }
    if (seen.has(code)) {
      throw new Error("row code " + code + " appears twice");
    }
    seen.add(code);
    const capacity = row.capacity;
    if (!Number.isInteger(capacity) || capacity < 1) {
      throw new Error("a capacity must be a whole number above nothing");
    }
    shelves.push({ code, capacity });
  }
  return shelves;
}

export function bandPicksByShare(
  lines: { code: string; picks: number }[],
  cuts: number[],
  rows: { code: string; capacity: number }[],
): { code: string; band: string; row: string; slot: number }[] {
  const held = readLines(lines);
  if (!Array.isArray(cuts) || cuts.length !== 2) {
    throw new Error("the cuts must be two whole percentages");
  }
  const first = cuts[0];
  const second = cuts[1];
  for (const cut of [first, second]) {
    if (!Number.isInteger(cut) || cut < 1 || cut > 99) {
      throw new Error("a cut must be a whole number from 1 to 99");
    }
  }
  if (first >= second) {
    throw new Error("the first cut must fall below the second");
  }
  const shelves = readRows(rows);
  let grand = 0;
  for (const line of held) {
    grand += line.picks;
  }
  if (grand === 0) {
    throw new Error("no line was pulled at all");
  }
  const ranked = held.slice().sort((a, b) => {
    if (b.picks !== a.picks) {
      return b.picks - a.picks;
    }
    return a.code < b.code ? -1 : a.code > b.code ? 1 : 0;
  });
  const banded: { code: string; band: string }[] = [];
  let running = 0;
  for (const line of ranked) {
    let band = "C";
    if (running * 100 < first * grand) {
      band = "A";
    } else if (running * 100 < second * grand) {
      band = "B";
    }
    banded.push({ code: line.code, band });
    running += line.picks;
  }
  const seated: Placement[] = [];
  let rowIndex = 0;
  let slot = 0;
  for (const band of ["A", "B", "C"]) {
    const members = banded.filter((entry) => entry.band === band);
    if (members.length === 0) {
      continue;
    }
    if (slot > 0) {
      rowIndex += 1;
      slot = 0;
    }
    for (const member of members) {
      while (rowIndex < shelves.length && slot === shelves[rowIndex].capacity) {
        rowIndex += 1;
        slot = 0;
      }
      if (rowIndex >= shelves.length) {
        throw new Error("the rows run out before every line is seated");
      }
      slot += 1;
      seated.push({ code: member.code, band, row: shelves[rowIndex].code, slot });
    }
  }
  return seated;
}
