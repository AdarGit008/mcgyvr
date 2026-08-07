const HEADINGS: number[][] = [
  [0, 1],
  [1, 0],
  [1, 1],
  [-1, 1],
];

export function findLineOfFour(board: string[]): {
  winner: string;
  cells: number[][];
} {
  if (!Array.isArray(board)) {
    throw new Error("the board must be a list of lines");
  }
  if (board.length === 0) {
    throw new Error("the board must hold at least one line");
  }
  let width = -1;
  for (const line of board) {
    if (typeof line !== "string") {
      throw new Error("every line must be a string");
    }
    if (line.length === 0) {
      throw new Error("a line must not be empty");
    }
    if (width === -1) {
      width = line.length;
    } else if (line.length !== width) {
      throw new Error("the lines are not all one length");
    }
    for (const mark of line) {
      if (mark !== "r" && mark !== "y" && mark !== ".") {
        throw new Error("a mark is outside r, y and the dot");
      }
    }
  }
  const height = board.length;
  for (let column = 0; column < width; column++) {
    for (let row = 0; row + 1 < height; row++) {
      if (board[row][column] !== "." && board[row + 1][column] === ".") {
        throw new Error("a disc hangs over an empty square");
      }
    }
  }
  for (let row = 0; row < height; row++) {
    for (let column = 0; column < width; column++) {
      const colour = board[row][column];
      if (colour === ".") {
        continue;
      }
      for (const heading of HEADINGS) {
        const cells: number[][] = [];
        for (let step = 0; step < 4; step++) {
          const nearRow = row + heading[0] * step;
          const nearColumn = column + heading[1] * step;
          if (nearRow < 0 || nearRow >= height) {
            break;
          }
          if (nearColumn < 0 || nearColumn >= width) {
            break;
          }
          if (board[nearRow][nearColumn] !== colour) {
            break;
          }
          cells.push([nearRow, nearColumn]);
        }
        if (cells.length === 4) {
          return { winner: colour, cells };
        }
      }
    }
  }
  return { winner: "none", cells: [] };
}
