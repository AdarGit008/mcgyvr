export function planCropSuccession(
  lastSown: string[],
  follows: string[][],
  order: string[],
  seasons: number,
): string[][] {
  if (!Array.isArray(lastSown) || lastSown.length === 0) {
    throw new Error("the plot list must be a non-empty list");
  }
  for (const crop of lastSown) {
    if (typeof crop !== "string" || crop.length === 0) {
      throw new Error("every plot carries a crop name");
    }
  }
  if (!Array.isArray(follows)) {
    throw new Error("the table must be a list");
  }
  const edges = new Set<string>();
  for (const row of follows) {
    if (!Array.isArray(row) || row.length !== 2) {
      throw new Error("every table row is a pair");
    }
    for (const crop of row) {
      if (typeof crop !== "string" || crop.length === 0) {
        throw new Error("every table entry is a crop name");
      }
    }
    const key = row[0] + "\u0000" + row[1];
    if (edges.has(key)) {
      throw new Error("the table states one pair twice");
    }
    edges.add(key);
  }
  if (!Array.isArray(order) || order.length === 0) {
    throw new Error("the ranking must be a non-empty list");
  }
  const ranked = new Set<string>();
  for (const crop of order) {
    if (typeof crop !== "string" || crop.length === 0) {
      throw new Error("every ranked entry is a crop name");
    }
    if (ranked.has(crop)) {
      throw new Error("the ranking repeats a crop");
    }
    ranked.add(crop);
  }
  for (const crop of lastSown) {
    if (!ranked.has(crop)) {
      throw new Error("unranked crop on a plot");
    }
  }
  for (const row of follows) {
    for (const crop of row) {
      if (!ranked.has(crop)) {
        throw new Error("unranked crop in the table");
      }
    }
  }
  if (
    typeof seasons !== "number" ||
    !Number.isInteger(seasons) ||
    seasons < 1
  ) {
    throw new Error("the season count must be a whole number above zero");
  }

  const plots = lastSown.length;
  const allowance = Math.ceil(plots / 2);
  const plan: string[][] = lastSown.map(() => [] as string[]);
  for (let season = 0; season < seasons; season++) {
    const drilled = new Map<string, number>();
    for (let plot = 0; plot < plots; plot++) {
      const before = season === 0 ? lastSown[plot] : plan[plot][season - 1];
      const earlier =
        season === 0
          ? null
          : season === 1
            ? lastSown[plot]
            : plan[plot][season - 2];
      let chosen: string | null = null;
      for (const crop of order) {
        if (!edges.has(before + "\u0000" + crop)) continue;
        if (crop === before || crop === earlier) continue;
        if ((drilled.get(crop) ?? 0) >= allowance) continue;
        chosen = crop;
        break;
      }
      if (chosen === null) return [];
      plan[plot].push(chosen);
      drilled.set(chosen, (drilled.get(chosen) ?? 0) + 1);
    }
  }
  return plan;
}
