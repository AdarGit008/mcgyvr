const TOUCHING: number[][] = [
  [-1, -1],
  [-1, 0],
  [-1, 1],
  [0, -1],
  [0, 1],
  [1, -1],
  [1, 0],
  [1, 1],
];

export function countAdjacentHazards(field: string[]): {
  chart: string[];
  hazards: number;
  clear: number;
} {
  if (!Array.isArray(field)) {
    throw new Error("the field must be a list of rows");
  }
  if (field.length === 0) {
    throw new Error("the field must hold at least one row");
  }
  let width = -1;
  for (const row of field) {
    if (typeof row !== "string") {
      throw new Error("every row must be a string");
    }
    if (row.length === 0) {
      throw new Error("a row must not be empty");
    }
    if (width === -1) {
      width = row.length;
    } else if (row.length !== width) {
      throw new Error("the rows are not all the same length");
    }
    for (const symbol of row) {
      if (symbol !== "#" && symbol !== ".") {
        throw new Error("a symbol is neither a hash nor a dot");
      }
    }
  }
  const height = field.length;
  const chart: string[] = [];
  let hazards = 0;
  let clear = 0;
  for (let down = 0; down < height; down++) {
    let drawn = "";
    for (let across = 0; across < width; across++) {
      if (field[down][across] === "#") {
        hazards += 1;
        drawn += "#";
        continue;
      }
      clear += 1;
      let tally = 0;
      for (const step of TOUCHING) {
        const nearDown = down + step[0];
        const nearAcross = across + step[1];
        if (nearDown < 0 || nearDown >= height) {
          continue;
        }
        if (nearAcross < 0 || nearAcross >= width) {
          continue;
        }
        if (field[nearDown][nearAcross] === "#") {
          tally += 1;
        }
      }
      drawn += String(tally);
    }
    chart.push(drawn);
  }
  return { chart, hazards, clear };
}
