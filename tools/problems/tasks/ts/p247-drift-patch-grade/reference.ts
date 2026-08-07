export function gradeTolerantPatches(plate: number[][], drift: number): any {
  if (!Array.isArray(plate) || plate.length === 0) {
    throw new Error("the plate must hold at least one line");
  }
  if (typeof drift !== "number" || !Number.isInteger(drift) || drift < 0) {
    throw new Error("the drift must be a whole number of zero or more");
  }
  let width = -1;
  for (const line of plate) {
    if (!Array.isArray(line) || line.length === 0) {
      throw new Error("every line must be a list holding at least one cell");
    }
    if (width === -1) width = line.length;
    if (line.length !== width) {
      throw new Error("the lines are not all of one length");
    }
    for (const reading of line) {
      if (typeof reading !== "number" || !Number.isInteger(reading)) {
        throw new Error("every reading must be a whole number");
      }
    }
  }
  const height = plate.length;
  const seen: boolean[][] = [];
  for (let r = 0; r < height; r++) seen.push(new Array(width).fill(false));
  const found: number[][] = [];
  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      if (seen[r][c]) continue;
      seen[r][c] = true;
      let size = 0;
      const pending: number[][] = [[r, c]];
      while (pending.length > 0) {
        const spot = pending.pop();
        if (spot === undefined) break;
        const row = spot[0];
        const col = spot[1];
        size += 1;
        for (let dr = -1; dr <= 1; dr++) {
          for (let dc = -1; dc <= 1; dc++) {
            if (dr === 0 && dc === 0) continue;
            const nr = row + dr;
            const nc = col + dc;
            if (nr < 0 || nr >= height || nc < 0 || nc >= width) continue;
            if (seen[nr][nc]) continue;
            if (Math.abs(plate[nr][nc] - plate[row][col]) > drift) continue;
            seen[nr][nc] = true;
            pending.push([nr, nc]);
          }
        }
      }
      found.push([size, r * width + c]);
    }
  }
  found.sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  return {
    count: found.length,
    sizes: found.map((patch) => patch[0]),
    seeds: found.map((patch) => patch[1]),
  };
}
