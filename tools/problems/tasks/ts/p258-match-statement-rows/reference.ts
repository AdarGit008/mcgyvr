type Row = { ref: string; day: number; cents: number };

function readRows(rows: unknown, side: string): Row[] {
  if (!Array.isArray(rows)) {
    throw new Error(`the ${side} must be a list of rows`);
  }
  const seen = new Set<string>();
  const out: Row[] = [];
  for (const row of rows) {
    if (row === null || typeof row !== "object" || Array.isArray(row)) {
      throw new Error(`a ${side} row must be a record`);
    }
    const entry = row as Record<string, unknown>;
    for (const field of ["ref", "day", "cents"]) {
      if (!(field in entry)) {
        throw new Error(`a ${side} row is missing ${field}`);
      }
    }
    const { ref, day, cents } = entry;
    if (typeof ref !== "string" || ref === "") {
      throw new Error(`a ${side} ref must be a non-empty string`);
    }
    if (!Number.isInteger(day)) {
      throw new Error(`${ref} has a day that is not a whole number`);
    }
    if (!Number.isInteger(cents)) {
      throw new Error(`${ref} has cents that are not a whole number`);
    }
    if (cents === 0) {
      throw new Error(`${ref} moves no money`);
    }
    if (seen.has(ref)) {
      throw new Error(`the ${side} repeats ${ref}`);
    }
    seen.add(ref);
    out.push({ ref, day: day as number, cents: cents as number });
  }
  return out;
}

export function matchStatementRows(
  book: Array<Record<string, unknown>>,
  bank: Array<Record<string, unknown>>,
  tolerance: number,
): { pairs: string[][]; bookOnly: string[]; bankOnly: string[] } {
  const bookRows = readRows(book, "cash book");
  const bankRows = readRows(bank, "bank statement");
  if (!Number.isInteger(tolerance) || (tolerance as number) < 0) {
    throw new Error("the tolerance must be a whole number of days, not negative");
  }

  const walk = bookRows.slice().sort((a, b) => (a.day - b.day) || (a.ref < b.ref ? -1 : a.ref > b.ref ? 1 : 0));
  const taken = new Set<string>();
  const pairs: string[][] = [];
  const bookOnly: string[] = [];
  for (const row of walk) {
    let best: Row | null = null;
    let bestGap = 0;
    for (const candidate of bankRows) {
      if (taken.has(candidate.ref) || candidate.cents !== row.cents) {
        continue;
      }
      const gap = Math.abs(candidate.day - row.day);
      if (gap > tolerance) {
        continue;
      }
      if (
        best === null ||
        gap < bestGap ||
        (gap === bestGap &&
          (candidate.day < best.day ||
            (candidate.day === best.day && candidate.ref < best.ref)))
      ) {
        best = candidate;
        bestGap = gap;
      }
    }
    if (best === null) {
      bookOnly.push(row.ref);
    } else {
      taken.add(best.ref);
      pairs.push([row.ref, best.ref]);
    }
  }
  const bankOnly = bankRows
    .filter((row) => !taken.has(row.ref))
    .map((row) => row.ref)
    .sort();
  return { pairs, bookOnly: bookOnly.sort(), bankOnly };
}
