function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function inRange(value: number): boolean {
  return Math.abs(value) <= 1000000;
}

function divisor(a: number, b: number): number {
  let left = a;
  let right = b;
  while (right !== 0) {
    const rest = left % right;
    left = right;
    right = rest;
  }
  return left;
}

function render(num: number, den: number): string {
  if (num === 0) {
    return "0";
  }
  const shared = divisor(Math.abs(num), den);
  const top = num / shared;
  const bottom = den / shared;
  return bottom === 1 ? String(top) : `${top}/${bottom}`;
}

export function calibrateRawCount(table: number[][], raw: number): string {
  if (!whole(raw)) {
    throw new Error("the raw count is not a whole number");
  }
  if (!inRange(raw)) {
    throw new Error("the raw count reaches beyond a million away from nought");
  }
  if (!Array.isArray(table)) {
    throw new Error("calibrateRawCount expects a list of rows");
  }
  if (table.length < 2) {
    throw new Error("the table holds fewer than two rows");
  }
  for (const row of table) {
    if (!Array.isArray(row) || row.length !== 2) {
      throw new Error("a row is not a list of exactly two entries");
    }
    for (const entry of row) {
      if (!whole(entry)) {
        throw new Error("a row entry is not a whole number");
      }
      if (!inRange(entry)) {
        throw new Error("a row entry reaches beyond a million away from nought");
      }
    }
  }
  for (let i = 1; i < table.length; i++) {
    if (table[i][0] <= table[i - 1][0]) {
      throw new Error("the counts do not climb strictly from row to row");
    }
  }

  const first = table[0];
  const last = table[table.length - 1];
  if (raw <= first[0]) {
    return render(first[1], 1);
  }
  if (raw >= last[0]) {
    return render(last[1], 1);
  }

  let index = 0;
  while (table[index + 1][0] <= raw) {
    index++;
  }
  const lo = table[index];
  const hi = table[index + 1];
  const den = hi[0] - lo[0];
  const num = lo[1] * den + (raw - lo[0]) * (hi[1] - lo[1]);
  return render(num, den);
}
