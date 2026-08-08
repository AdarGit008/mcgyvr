const TABLE: { top: number; allowance: number }[] = [
  { top: 4, allowance: 0 },
  { top: 9, allowance: 3 },
  { top: 14, allowance: 6 },
  { top: 19, allowance: 10 },
  { top: 28, allowance: 15 },
];

type Row = { name: string; gross: number; net: number };

export function rankNetScores(
  field: Record<string, unknown>[],
): Record<string, unknown>[] {
  if (!Array.isArray(field) || field.length === 0) {
    throw new Error("the field must be a list with at least one competitor");
  }

  const rows: Row[] = [];
  const names = new Set<string>();
  for (const entry of field) {
    const name = entry.name;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("every competitor needs a name");
    }
    if (names.has(name)) {
      throw new Error(`${name} is entered twice`);
    }
    names.add(name);

    const gross = entry.gross;
    if (typeof gross !== "number" || !Number.isInteger(gross) || gross < 1) {
      throw new Error(`the gross score of ${name} is not a whole number`);
    }
    const mark = entry.mark;
    if (
      typeof mark !== "number" ||
      !Number.isInteger(mark) ||
      mark < 0 ||
      mark > 28
    ) {
      throw new Error(`the mark of ${name} is outside 0 to 28`);
    }

    const band = TABLE.find((each) => mark <= each.top);
    const allowance = (band as { top: number; allowance: number }).allowance;
    rows.push({ name, gross, net: gross - allowance });
  }

  rows.sort((left, right) => {
    if (left.net !== right.net) {
      return left.net - right.net;
    }
    if (left.gross !== right.gross) {
      return left.gross - right.gross;
    }
    return left.name < right.name ? -1 : 1;
  });

  return rows.map((row, index) => ({
    place: index + 1,
    name: row.name,
    net: row.net,
  }));
}
