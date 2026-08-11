export function rowWidest(grid: number[][]): number {
  let widest = 0;
  for (const row of grid) {
    if (row.length > widest) {
      widest = row.length;
    }
  }
  return widest;
}

/** Every row padded out to the widest row's width. */
export function foldRows(grid: number[][]): number[][] {
  if (grid.length === 0) {
    return [];
  }
  const width = rowWidest(grid);
  return grid.map((row) => {
    const padded = [...row];
    while (padded.length < width) {
      padded.push(0);
    }
    return padded;
  });
}
