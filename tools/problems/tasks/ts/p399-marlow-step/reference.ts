export function marlowStep(rungs: string, lift: number): string {
  const capitals = "ABCDEFG";
  if (typeof rungs !== "string") {
    throw new Error("marlowStep expects the rung-count as text");
  }
  if (rungs.length === 0) {
    throw new Error("a rung-count is never empty");
  }
  if (rungs.length > 10) {
    throw new Error("a rung-count runs no longer than ten capitals");
  }
  for (const mark of rungs) {
    if (capitals.indexOf(mark) < 0) {
      throw new Error("a rung-count carries only the capitals A through G");
    }
  }
  if (rungs.length > 1 && rungs[0] === "A") {
    throw new Error("a rung-count of two or more never begins with A");
  }
  if (typeof lift !== "number" || !Number.isInteger(lift)) {
    throw new Error("lift must be a whole number");
  }
  if (Math.abs(lift) > 1000) {
    throw new Error("lift's magnitude passes one thousand");
  }
  let quantity = 0;
  for (const mark of rungs) {
    quantity = quantity * -7 + capitals.indexOf(mark);
  }
  quantity += lift;
  if (quantity === 0) {
    return "A";
  }
  let rest = quantity;
  let record = "";
  while (rest !== 0) {
    const column = (((rest % 7) + 7) % 7);
    record = capitals[column] + record;
    rest = (rest - column) / -7;
  }
  return record;
}
