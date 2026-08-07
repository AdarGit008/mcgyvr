export function orrelDigits(value: number): string {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new Error("orrelDigits expects a whole number");
  }
  if (Math.abs(value) > 1000000) {
    throw new Error("the quantity's magnitude passes one million");
  }
  const marks = "oiy";
  if (value === 0) {
    return "o";
  }
  let rest = value;
  let spelling = "";
  while (rest !== 0) {
    const place = (((rest % 3) + 3) % 3);
    spelling = marks[place] + spelling;
    rest = (rest - place) / -3;
  }
  return spelling;
}
