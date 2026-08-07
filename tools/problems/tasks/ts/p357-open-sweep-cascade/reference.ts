const AROUND: number[][] = [
  [-1, -1],
  [-1, 0],
  [-1, 1],
  [0, -1],
  [0, 1],
  [1, -1],
  [1, 0],
  [1, 1],
];

export function openSweepCascade(
  board: string[],
  origin: number[],
): { view: string[]; opened: number; struck: boolean } {
  if (!Array.isArray(board)) {
    throw new Error("the board must be a list of lines");
  }
  if (board.length === 0) {
    throw new Error("the board must hold at least one line");
  }
  let span = -1;
  for (const line of board) {
    if (typeof line !== "string") {
      throw new Error("every line must be a string");
    }
    if (line.length === 0) {
      throw new Error("a line must not be empty");
    }
    if (span === -1) {
      span = line.length;
    } else if (line.length !== span) {
      throw new Error("the lines differ in length");
    }
    for (const symbol of line) {
      if (symbol !== "*" && symbol !== "-") {
        throw new Error("a symbol is neither a star nor a dash");
      }
    }
  }
  const tall = board.length;
  if (!Array.isArray(origin) || origin.length !== 2) {
    throw new Error("the origin must be a pair");
  }
  for (const part of origin) {
    if (typeof part !== "number" || !Number.isInteger(part)) {
      throw new Error("the origin must be whole numbers");
    }
  }
  const line = origin[0];
  const spot = origin[1];
  if (line < 0 || line >= tall || spot < 0 || spot >= span) {
    throw new Error("the origin falls off the board");
  }

  const tallyAt = (down: number, across: number): number => {
    let total = 0;
    for (const step of AROUND) {
      const nearDown = down + step[0];
      const nearAcross = across + step[1];
      if (nearDown < 0 || nearDown >= tall) {
        continue;
      }
      if (nearAcross < 0 || nearAcross >= span) {
        continue;
      }
      if (board[nearDown][nearAcross] === "*") {
        total += 1;
      }
    }
    return total;
  };

  const shown: number[][] = [];
  for (let down = 0; down < tall; down++) {
    shown.push(new Array(span).fill(-1));
  }
  if (board[line][spot] === "*") {
    const struckView: string[] = [];
    for (let down = 0; down < tall; down++) {
      let drawn = "";
      for (let across = 0; across < span; across++) {
        drawn += down === line && across === spot ? "!" : "?";
      }
      struckView.push(drawn);
    }
    return { view: struckView, opened: 0, struck: true };
  }
  let opened = 0;
  shown[line][spot] = tallyAt(line, spot);
  const waiting: number[][] = [[line, spot]];
  while (waiting.length > 0) {
    const spotPair = waiting.pop();
    if (spotPair === undefined) {
      break;
    }
    const down = spotPair[0];
    const across = spotPair[1];
    opened += 1;
    if (shown[down][across] !== 0) {
      continue;
    }
    for (const step of AROUND) {
      const nearDown = down + step[0];
      const nearAcross = across + step[1];
      if (nearDown < 0 || nearDown >= tall) {
        continue;
      }
      if (nearAcross < 0 || nearAcross >= span) {
        continue;
      }
      if (shown[nearDown][nearAcross] !== -1) {
        continue;
      }
      if (board[nearDown][nearAcross] === "*") {
        continue;
      }
      shown[nearDown][nearAcross] = tallyAt(nearDown, nearAcross);
      waiting.push([nearDown, nearAcross]);
    }
  }
  const view: string[] = [];
  for (let down = 0; down < tall; down++) {
    let drawn = "";
    for (let across = 0; across < span; across++) {
      drawn += shown[down][across] === -1 ? "?" : String(shown[down][across]);
    }
    view.push(drawn);
  }
  return { view, opened, struck: false };
}
