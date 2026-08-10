/** A shipment ledger: parse lines, total by site, find the busiest site. */

export function loadLedger(
  lines: string[],
): { site: string; item: string; qty: number }[] {
  const rows: { site: string; item: string; qty: number }[] = [];
  for (const line of lines) {
    const parts = line.split(",");
    if (parts.length !== 3) {
      throw new Error("each ledger line is site,item,qty");
    }
    const [site, item, raw] = parts;
    if (site === "" || item === "") {
      throw new Error("site and item must be non-empty");
    }
    if (!/^\d+$/.test(raw)) {
      throw new Error("qty must be a run of decimal digits");
    }
    rows.push({ site, item, qty: Number(raw) });
  }
  return rows;
}

export function siteTotals(
  rows: { site: string; item: string; qty: number }[],
): [string, number][] {
  const totals = new Map<string, number>();
  for (const row of rows) {
    const qty = row.qty;
    if (typeof qty !== "number" || !Number.isInteger(qty) || qty <= 0) {
      throw new Error("row qty must be a positive integer");
    }
    totals.set(row.site, (totals.get(row.site) ?? 0) + qty);
  }
  const pairs: [string, number][] = [...totals.entries()];
  pairs.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  return pairs;
}

export function busiestSite(
  rows: { site: string; item: string; qty: number }[],
): string | null {
  const totals = siteTotals(rows);
  if (totals.length === 0) {
    return null;
  }
  let best = totals[0];
  for (const pair of totals) {
    if (pair[1] > best[1]) {
      best = pair;
    }
  }
  return best[0];
}
