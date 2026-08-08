const MARKER = "|";

function rankOf(symbol: string): number {
  if (symbol === MARKER) {
    return 0;
  }
  if (symbol === " ") {
    return 1;
  }
  return symbol.charCodeAt(0) - 95;
}

export function foldRibbonRotations(ribbon: string): {
  line: string;
  home: number;
} {
  if (typeof ribbon !== "string") {
    throw new Error("the ribbon must be a string");
  }
  if (ribbon.length === 0) {
    throw new Error("the ribbon must not be empty");
  }
  if (ribbon.includes(MARKER)) {
    throw new Error("the ribbon must not already carry the marker");
  }
  for (const symbol of ribbon) {
    const code = symbol.charCodeAt(0);
    const letter = code >= 97 && code <= 122;
    if (!letter && symbol !== " ") {
      throw new Error("the ribbon holds a symbol outside lowercase and space");
    }
  }
  const glued = ribbon + MARKER;
  const width = glued.length;
  const turns: number[] = [];
  for (let start = 0; start < width; start++) {
    turns.push(start);
  }
  turns.sort((left, right) => {
    for (let step = 0; step < width; step++) {
      const a = rankOf(glued[(left + step) % width]);
      const b = rankOf(glued[(right + step) % width]);
      if (a !== b) {
        return a - b;
      }
    }
    return left - right;
  });
  let line = "";
  let home = 0;
  for (let seat = 0; seat < width; seat++) {
    line += glued[(turns[seat] + width - 1) % width];
    if (turns[seat] === 0) {
      home = seat;
    }
  }
  return { line, home };
}
