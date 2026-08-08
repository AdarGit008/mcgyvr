export function firstRotationBreach(
  log: string[][],
  permits: string[][],
): string {
  if (!Array.isArray(log) || log.length === 0) {
    throw new Error("the record must be a non-empty list");
  }
  let seasons = -1;
  for (const record of log) {
    if (!Array.isArray(record) || record.length === 0) {
      throw new Error("every plot row must be a non-empty list");
    }
    if (seasons === -1) {
      seasons = record.length;
    } else if (record.length !== seasons) {
      throw new Error("plot rows run to unequal lengths");
    }
    for (const crop of record) {
      if (typeof crop !== "string" || crop.length === 0) {
        throw new Error("every recorded entry is a crop name");
      }
    }
  }
  if (!Array.isArray(permits)) {
    throw new Error("the table must be a list");
  }
  const licensed = new Set<string>();
  for (const row of permits) {
    if (!Array.isArray(row) || row.length !== 2) {
      throw new Error("every table row is a pair");
    }
    for (const crop of row) {
      if (typeof crop !== "string" || crop.length === 0) {
        throw new Error("every table entry is a crop name");
      }
    }
    licensed.add(row[0] + ">" + row[1]);
  }

  for (let season = 1; season < seasons; season++) {
    for (let plot = 0; plot < log.length; plot++) {
      const record = log[plot];
      const crop = record[season];
      const lifted = record[season - 1];
      let breached = !licensed.has(lifted + ">" + crop);
      if (!breached && crop === lifted) {
        breached = true;
      }
      if (!breached && season >= 2 && crop === record[season - 2]) {
        breached = true;
      }
      if (breached) {
        return "plot " + (plot + 1) + " season " + (season + 1);
      }
    }
  }
  return "clear";
}
