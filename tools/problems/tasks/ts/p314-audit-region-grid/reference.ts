export function auditRegionGrid(
  digits: string[],
  territories: string[],
): string {
  if (!Array.isArray(digits) || !Array.isArray(territories)) {
    throw new Error("both boards must be lists of rows");
  }
  const side = digits.length;
  if (side < 1 || side > 9) {
    throw new Error("the side must be between one and nine");
  }
  if (territories.length !== side) {
    throw new Error("the two boards differ in height");
  }

  const value: number[][] = [];
  const label: string[][] = [];
  for (let row = 0; row < side; row++) {
    const digitRow = digits[row];
    const labelRow = territories[row];
    if (typeof digitRow !== "string" || digitRow.length !== side) {
      throw new Error(`digit row ${row + 1} is not ${side} characters wide`);
    }
    if (typeof labelRow !== "string" || labelRow.length !== side) {
      throw new Error(`label row ${row + 1} is not ${side} characters wide`);
    }
    const values: number[] = [];
    const labels: string[] = [];
    for (let file = 0; file < side; file++) {
      const digit = digitRow.charCodeAt(file) - 48;
      if (digit < 1 || digit > side) {
        throw new Error(
          `square ${row + 1},${file + 1} is not a digit from 1 to ${side}`,
        );
      }
      const mark = labelRow[file];
      if (mark < "A" || mark > "Z") {
        throw new Error(`square ${row + 1},${file + 1} carries no uppercase label`);
      }
      values.push(digit);
      labels.push(mark);
    }
    value.push(values);
    label.push(labels);
  }

  const held = new Map<string, number[]>();
  for (let row = 0; row < side; row++) {
    for (let file = 0; file < side; file++) {
      const mark = label[row][file];
      if (!held.has(mark)) {
        held.set(mark, []);
      }
      held.get(mark)!.push(value[row][file]);
    }
  }
  const marks = [...held.keys()].sort();
  if (marks.length !== side) {
    throw new Error(`the labelling makes ${marks.length} territories, not ${side}`);
  }
  for (const mark of marks) {
    if (held.get(mark)!.length !== side) {
      throw new Error(`territory ${mark} does not hold ${side} squares`);
    }
  }

  const complete = (group: number[]): boolean => new Set(group).size === side;

  for (let row = 0; row < side; row++) {
    if (!complete(value[row])) {
      return `row ${row + 1}`;
    }
  }
  for (let file = 0; file < side; file++) {
    const column: number[] = [];
    for (let row = 0; row < side; row++) {
      column.push(value[row][file]);
    }
    if (!complete(column)) {
      return `file ${file + 1}`;
    }
  }
  for (const mark of marks) {
    if (!complete(held.get(mark)!)) {
      return `territory ${mark}`;
    }
  }
  return "ok";
}
