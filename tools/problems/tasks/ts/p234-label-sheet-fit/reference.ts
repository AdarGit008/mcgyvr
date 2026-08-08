function positive(record: any, key: string): number {
  const value = record === null ? undefined : record[key];
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(key + " must be a positive integer");
  }
  return value;
}

function offset(record: any, key: string): number {
  const value = record === null ? undefined : record[key];
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(key + " must be a non-negative integer");
  }
  return value;
}

function along(field: number, size: number, gap: number): number {
  if (field < size) {
    return 0;
  }
  return Math.floor((field + gap) / (size + gap));
}

export function fitLabelSheet(sheet: any, label: any): any {
  if (sheet === null || typeof sheet !== "object" || Array.isArray(sheet)) {
    throw new Error("the sheet must be a record");
  }
  if (label === null || typeof label !== "object" || Array.isArray(label)) {
    throw new Error("the label must be a record");
  }
  const sheetWidth = positive(sheet, "width");
  const sheetHeight = positive(sheet, "height");
  const marginX = offset(sheet, "marginX");
  const marginY = offset(sheet, "marginY");
  const gapX = offset(sheet, "gapX");
  const gapY = offset(sheet, "gapY");
  const labelWidth = positive(label, "width");
  const labelHeight = positive(label, "height");
  if (typeof label.turn !== "boolean") {
    throw new Error("turn must be a boolean");
  }

  const fieldWidth = sheetWidth - 2 * marginX;
  const fieldHeight = sheetHeight - 2 * marginY;

  const grids: any[] = [];
  const upAcross = fieldWidth < 1 ? 0 : along(fieldWidth, labelWidth, gapX);
  const upDown = fieldHeight < 1 ? 0 : along(fieldHeight, labelHeight, gapY);
  grids.push({
    across: upAcross,
    down: upDown,
    total: upAcross * upDown,
    turned: false,
  });
  if (label.turn) {
    const sideAcross = fieldWidth < 1 ? 0 : along(fieldWidth, labelHeight, gapX);
    const sideDown = fieldHeight < 1 ? 0 : along(fieldHeight, labelWidth, gapY);
    grids.push({
      across: sideAcross,
      down: sideDown,
      total: sideAcross * sideDown,
      turned: true,
    });
  }

  let best = grids[0];
  for (const grid of grids) {
    if (grid.total > best.total) {
      best = grid;
    }
  }
  if (best.total < 1) {
    throw new Error("not one label fits on this sheet");
  }
  return best;
}
