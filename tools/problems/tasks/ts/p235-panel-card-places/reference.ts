function measure(panel: any, key: string, least: number): number {
  const value = panel[key];
  if (!Number.isInteger(value) || value < least) {
    throw new Error(key + " must be an integer of at least " + least);
  }
  return value;
}

function fitAlong(field: number, size: number, seam: number): number {
  if (field < size) {
    return 0;
  }
  return Math.floor((field + seam) / (size + seam));
}

export function placeCards(panel: any, count: number, taken: any[]): number[][] {
  if (panel === null || typeof panel !== "object" || Array.isArray(panel)) {
    throw new Error("the panel must be a record");
  }
  const width = measure(panel, "width", 1);
  const height = measure(panel, "height", 1);
  const bleed = measure(panel, "bleed", 0);
  const cardWidth = measure(panel, "cardWidth", 1);
  const cardHeight = measure(panel, "cardHeight", 1);
  const seam = measure(panel, "seam", 0);
  if (!Number.isInteger(count) || count < 0) {
    throw new Error("count must be a whole number of zero or more");
  }
  if (!Array.isArray(taken)) {
    throw new Error("the spoken-for cells must be a list");
  }

  const columns = fitAlong(width - 2 * bleed, cardWidth, seam);
  const rows = fitAlong(height - 2 * bleed, cardHeight, seam);
  const cells = columns * rows;
  if (cells < 1) {
    throw new Error("this panel carries no cells");
  }

  const spoken = new Set<number>();
  for (const cell of taken) {
    if (!Number.isInteger(cell) || cell < 1 || cell > cells) {
      throw new Error("cell " + String(cell) + " is not on this panel");
    }
    spoken.add(cell);
  }
  if (cells - spoken.size < count) {
    throw new Error("not enough free cells for " + count + " cards");
  }

  const places: number[][] = [];
  for (let cell = 1; cell <= cells && places.length < count; cell++) {
    if (spoken.has(cell)) {
      continue;
    }
    const column = (cell - 1) % columns;
    const row = Math.floor((cell - 1) / columns);
    places.push([
      bleed + column * (cardWidth + seam),
      bleed + row * (cardHeight + seam),
    ]);
  }
  return places;
}
