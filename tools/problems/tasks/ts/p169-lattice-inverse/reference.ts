function minorOf(frame: number[][], skipRow: number, skipColumn: number): number {
  const kept: number[][] = [];
  for (let row = 0; row < 3; row++) {
    if (row === skipRow) {
      continue;
    }
    const line: number[] = [];
    for (let column = 0; column < 3; column++) {
      if (column !== skipColumn) {
        line.push(frame[row][column]);
      }
    }
    kept.push(line);
  }
  return kept[0][0] * kept[1][1] - kept[0][1] * kept[1][0];
}

export function latticeInverse(frame: number[][]): number[][] {
  if (!Array.isArray(frame) || (frame.length !== 2 && frame.length !== 3)) {
    throw new Error("a frame stands exactly two or three rows tall");
  }
  for (const row of frame) {
    if (!Array.isArray(row) || row.length !== frame.length) {
      throw new Error("every row must match the frame's height");
    }
    for (const entry of row) {
      if (typeof entry !== "number" || !Number.isInteger(entry)) {
        throw new Error("every entry must be a whole number");
      }
    }
  }
  if (frame.length === 2) {
    const determinant = frame[0][0] * frame[1][1] - frame[0][1] * frame[1][0];
    if (determinant !== 1 && determinant !== -1) {
      return [];
    }
    return [
      [frame[1][1] / determinant, -frame[0][1] / determinant],
      [-frame[1][0] / determinant, frame[0][0] / determinant],
    ];
  }
  const cofactor: number[][] = [];
  for (let row = 0; row < 3; row++) {
    const line: number[] = [];
    for (let column = 0; column < 3; column++) {
      const sign = (row + column) % 2 === 0 ? 1 : -1;
      line.push(sign * minorOf(frame, row, column));
    }
    cofactor.push(line);
  }
  const determinant =
    frame[0][0] * cofactor[0][0] +
    frame[0][1] * cofactor[0][1] +
    frame[0][2] * cofactor[0][2];
  if (determinant !== 1 && determinant !== -1) {
    return [];
  }
  const undoing: number[][] = [];
  for (let row = 0; row < 3; row++) {
    const line: number[] = [];
    for (let column = 0; column < 3; column++) {
      line.push(cofactor[column][row] / determinant);
    }
    undoing.push(line);
  }
  return undoing;
}
