/** A sectioned sales report: item lines, subtotals, and a ranked summary. */

function ranked(a: [string, number, number], b: [string, number, number]): number {
  if (a[2] !== b[2]) {
    return b[2] - a[2];
  }
  if (a[0] === b[0]) {
    return 0;
  }
  return a[0] < b[0] ? -1 : 1;
}

export function sectionReport(rows: [string, string, number][]): {
  lines: [string, string, string, number][];
  sections: [string, number, number][];
  grand: number;
} {
  if (!Array.isArray(rows)) {
    throw new Error("rows must be a list");
  }
  const order: string[] = [];
  const items = new Map<string, [string, number][]>();
  for (const row of rows) {
    if (!Array.isArray(row) || row.length !== 3) {
      throw new Error("a row must be a [section, label, amount] triple");
    }
    const [section, label, amount] = row;
    if (typeof section !== "string" || section === "") {
      throw new Error("section must be a non-empty string");
    }
    if (typeof label !== "string" || label === "") {
      throw new Error("label must be a non-empty string");
    }
    if (!Number.isInteger(amount)) {
      throw new Error("amount must be an integer");
    }
    const bucket = items.get(section);
    if (bucket === undefined) {
      order.push(section);
      items.set(section, [[label, amount]]);
    } else {
      bucket.push([label, amount]);
    }
  }
  const lines: [string, string, string, number][] = [];
  const sections: [string, number, number][] = [];
  let grand = 0;
  for (const section of order) {
    const bucket = items.get(section) as [string, number][];
    let subtotal = 0;
    for (const [label, amount] of bucket) {
      lines.push(["item", section, label, amount]);
      subtotal += amount;
    }
    lines.push(["section", section, "", subtotal]);
    sections.push([section, bucket.length, subtotal]);
    grand += subtotal;
  }
  lines.push(["grand", "", "", grand]);
  sections.sort(ranked);
  return { lines, sections, grand };
}
