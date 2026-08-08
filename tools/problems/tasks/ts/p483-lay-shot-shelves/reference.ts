/** How deep a strip of fitted prints runs. */
function whole(value: unknown, least: number): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= least;
}

function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function layShotShelves(shots: any[], strip: any): any {
  if (!Array.isArray(shots) || shots.length === 0) {
    throw new Error("shots must be a list holding at least one shot");
  }
  if (!isRecord(strip)) {
    throw new Error("strip must be a record");
  }
  if (!whole(strip.perRow, 1)) {
    throw new Error("strip.perRow must be a whole number above nought");
  }
  if (!whole(strip.cell, 1)) {
    throw new Error("strip.cell must be a whole number above nought");
  }
  if (!whole(strip.lead, 0)) {
    throw new Error("strip.lead must be a whole number of nought or more");
  }

  const seen = new Set<string>();
  const fitted: { name: string; deep: number }[] = [];
  for (const shot of shots) {
    if (!isRecord(shot)) {
      throw new Error("each shot must be a record");
    }
    if (typeof shot.name !== "string" || shot.name.length === 0) {
      throw new Error("name must be a non-empty string");
    }
    if (seen.has(shot.name)) {
      throw new Error(`two shots answer to the name ${shot.name}`);
    }
    seen.add(shot.name);
    if (!whole(shot.across, 1) || !whole(shot.down, 1)) {
      throw new Error("across and down must be whole numbers above nought");
    }
    const scaled = shot.down * strip.cell;
    fitted.push({
      name: shot.name,
      deep: Math.floor((scaled + shot.across - 1) / shot.across),
    });
  }

  const rows: any[] = [];
  for (let i = 0; i < fitted.length; i += strip.perRow) {
    const slice = fitted.slice(i, i + strip.perRow);
    let deep = 0;
    for (const frame of slice) {
      if (frame.deep > deep) {
        deep = frame.deep;
      }
    }
    rows.push({ names: slice.map((frame) => frame.name), deep });
  }

  let deep = 0;
  for (const row of rows) {
    deep += row.deep;
  }
  deep += strip.lead * (rows.length - 1);
  return { rows, deep };
}
