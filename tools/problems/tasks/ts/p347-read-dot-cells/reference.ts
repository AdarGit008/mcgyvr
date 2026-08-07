function weightOf(cell: string): number {
  if (!/^[1-6]+$/.test(cell)) {
    throw new Error("a cell must be 0 or a run of the digits 1 to 6");
  }
  for (let i = 1; i < cell.length; i += 1) {
    if (cell[i] === cell[i - 1]) {
      throw new Error("a cell may not name a dot twice");
    }
    if (cell[i] < cell[i - 1]) {
      throw new Error("the dots of a cell must rise");
    }
  }
  let weight = 0;
  for (const dot of cell) {
    weight += 1 << (Number(dot) - 1);
  }
  return weight;
}

export function readDotCells(cells: string): string {
  if (typeof cells !== "string") {
    throw new Error("the argument must be a string");
  }
  if (cells.length === 0) {
    throw new Error("the argument must not be empty");
  }
  const parts = cells.split("-");
  let out = "";
  let counting = false;
  let i = 0;
  while (i < parts.length) {
    const cell = parts[i];
    if (cell === "0") {
      out += " ";
      counting = false;
      i += 1;
      continue;
    }
    const weight = weightOf(cell);
    if (counting) {
      if (weight < 1 || weight > 10) {
        throw new Error("a cell inside a count may not weigh more than 10");
      }
      out += String(weight % 10);
      i += 1;
      continue;
    }
    if (weight === 48) {
      counting = true;
      i += 1;
      continue;
    }
    if (weight === 32) {
      if (i + 1 >= parts.length) {
        throw new Error("a shift sign may not end the line");
      }
      const next = parts[i + 1];
      if (next === "0") {
        throw new Error("a shift sign must be followed by a letter");
      }
      const letter = weightOf(next);
      if (letter < 1 || letter > 26) {
        throw new Error("a shift sign must be followed by a letter");
      }
      out += String.fromCharCode(64 + letter);
      i += 2;
      continue;
    }
    if (weight < 1 || weight > 26) {
      throw new Error("this weight spells nothing");
    }
    out += String.fromCharCode(96 + weight);
    i += 1;
  }
  return out;
}
