const MARKS = "vwxyz";

export function corvidRender(value: number): string {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new Error("corvidRender expects a whole number");
  }
  if (value === 0) {
    return "x";
  }
  let rest = value;
  const marks: string[] = [];
  while (rest !== 0) {
    let lean = ((rest % 5) + 5) % 5;
    if (lean > 2) {
      lean -= 5;
    }
    marks.push(MARKS[lean + 2]);
    rest = (rest - lean) / 5;
  }
  return marks.reverse().join("");
}
