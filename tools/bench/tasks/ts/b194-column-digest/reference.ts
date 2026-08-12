type Digest = { count: number; min: number; max: number; mean: number; median: number };

/** Summarize one column of a ragged sheet. */
export function columnDigest(rows: number[][], column: number): Digest {
  const cells: number[] = [];
  for (const row of rows) {
    if (row.length > column) {
      cells.push(row[column]);
    }
  }
  if (cells.length === 0) {
    return { count: 0, min: 0, max: 0, mean: 0, median: 0 };
  }
  const sorted = [...cells].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 === 1 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  const total = cells.reduce((sum, cell) => sum + cell, 0);
  const twoPlaces = (value: number): number => Math.floor(value * 100 + 0.5) / 100;
  return {
    count: cells.length,
    min: sorted[0],
    max: sorted[sorted.length - 1],
    mean: twoPlaces(total / cells.length),
    median: twoPlaces(median),
  };
}
