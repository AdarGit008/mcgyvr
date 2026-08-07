const ROWS: [number[], string][] = [
  [[0, 4, 7], "major"],
  [[0, 3, 7], "minor"],
  [[0, 3, 6], "diminished"],
  [[0, 4, 8], "augmented"],
  [[0, 5, 7], "quartal"],
  [[0, 2, 6], "narrow"],
  [[0, 4, 7, 11], "major seventh"],
  [[0, 4, 7, 10], "dominant seventh"],
  [[0, 3, 7, 10], "minor seventh"],
  [[0, 3, 6, 9], "shrunk seventh"],
];

function fold(value: number): number {
  return ((value % 12) + 12) % 12;
}

export function nameTriadStack(marks: number[]): any {
  if (!Array.isArray(marks) || marks.length === 0) {
    throw new Error("the argument must be a list holding at least one mark");
  }
  const classes = new Set<number>();
  for (const mark of marks) {
    if (typeof mark !== "number" || !Number.isInteger(mark)) {
      throw new Error("a pitch mark must be a whole number");
    }
    classes.add(fold(mark));
  }
  const stack = [...classes].sort((a, b) => a - b);
  if (stack.length < 3) {
    throw new Error("the stack holds fewer than three classes");
  }
  let bestRow = -1;
  let bestBase = -1;
  for (const base of stack) {
    const shape = stack.map((one) => fold(one - base)).sort((a, b) => a - b);
    for (let row = 0; row < ROWS.length; row++) {
      const wanted = ROWS[row][0];
      if (wanted.length !== shape.length) continue;
      let same = true;
      for (let i = 0; i < wanted.length; i++) {
        if (wanted[i] !== shape[i]) {
          same = false;
          break;
        }
      }
      if (!same) continue;
      if (bestRow === -1 || row < bestRow) {
        bestRow = row;
        bestBase = base;
      }
      break;
    }
  }
  if (bestRow === -1) {
    return { base: -1, name: "unknown" };
  }
  return { base: bestBase, name: ROWS[bestRow][1] };
}
