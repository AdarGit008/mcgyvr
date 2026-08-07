export function firstClueClash(line: string, clues: number[]): number {
  if (typeof line !== "string" || line.length === 0) {
    throw new Error("the line must be a non-empty string");
  }
  for (const cell of line) {
    if (cell !== "#" && cell !== ".") {
      throw new Error(`unusable cell: ${cell}`);
    }
  }
  if (!Array.isArray(clues)) {
    throw new Error("clues must be a list");
  }
  for (const clue of clues) {
    if (!Number.isInteger(clue) || clue < 1) {
      throw new Error("every clue must be a whole number above zero");
    }
  }
  let needed = 0;
  for (const clue of clues) {
    needed += clue;
  }
  if (clues.length > 0) {
    needed += clues.length - 1;
  }
  if (needed > line.length) {
    throw new Error("the clues cannot fit on a line this short");
  }

  const runs: number[] = [];
  let held = 0;
  for (const cell of line) {
    if (cell === "#") {
      held += 1;
    } else if (held > 0) {
      runs.push(held);
      held = 0;
    }
  }
  if (held > 0) {
    runs.push(held);
  }

  const reach = Math.max(runs.length, clues.length);
  for (let place = 0; place < reach; place++) {
    if (place >= runs.length || place >= clues.length) {
      return place;
    }
    if (runs[place] !== clues[place]) {
      return place;
    }
  }
  return -1;
}
