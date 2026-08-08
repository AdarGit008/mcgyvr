const SLANTS: number[][] = [
  [0, 1],
  [1, 0],
  [1, 1],
  [1, -1],
];

export function playDropContest(
  columns: number,
  rows: number,
  moves: number[],
): { winner: string; played: number; board: string[] } {
  for (const size of [columns, rows]) {
    if (typeof size !== "number" || !Number.isInteger(size) || size < 1) {
      throw new Error("the board sides must be whole numbers of one or more");
    }
  }
  if (!Array.isArray(moves)) {
    throw new Error("the moves must be a list");
  }
  const grid: string[][] = [];
  for (let row = 0; row < rows; row++) {
    grid.push(new Array(columns).fill("."));
  }
  let winner = "none";
  let played = 0;
  const runsFour = (row: number, column: number, mark: string): boolean => {
    for (const slant of SLANTS) {
      let total = 1;
      for (const sense of [1, -1]) {
        let step = 1;
        for (;;) {
          const nearRow = row + slant[0] * step * sense;
          const nearColumn = column + slant[1] * step * sense;
          if (nearRow < 0 || nearRow >= rows) break;
          if (nearColumn < 0 || nearColumn >= columns) break;
          if (grid[nearRow][nearColumn] !== mark) break;
          total += 1;
          step += 1;
        }
      }
      if (total >= 4) return true;
    }
    return false;
  };
  for (const move of moves) {
    if (winner !== "none") break;
    if (typeof move !== "number" || !Number.isInteger(move)) {
      throw new Error("every move must be a whole number");
    }
    if (move < 0 || move >= columns) {
      throw new Error("the move names no column");
    }
    let landing = -1;
    for (let row = rows - 1; row >= 0; row--) {
      if (grid[row][move] === ".") {
        landing = row;
        break;
      }
    }
    if (landing < 0) {
      throw new Error("the column is already full");
    }
    const mark = played % 2 === 0 ? "r" : "y";
    grid[landing][move] = mark;
    played += 1;
    if (runsFour(landing, move, mark)) {
      winner = mark;
    }
  }
  return { winner, played, board: grid.map((row) => row.join("")) };
}
