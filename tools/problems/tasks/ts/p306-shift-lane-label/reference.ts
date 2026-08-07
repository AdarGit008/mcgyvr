export function shiftLaneLabel(label: string, step: number): string {
  if (typeof label !== "string") {
    throw new Error("a lane label is a string");
  }
  if (label.length === 0) {
    throw new Error("a lane label needs at least one capital");
  }
  if (label.length > 3) {
    throw new Error("the board stops at three capitals");
  }
  if (!/^[A-Z]+$/.test(label)) {
    throw new Error("a lane label carries capitals only");
  }
  if (typeof step !== "number" || !Number.isInteger(step)) {
    throw new Error("the step must be a whole number");
  }
  let place = 0;
  for (const capital of label) {
    place = place * 26 + (capital.charCodeAt(0) - 64);
  }
  const target = place + step;
  if (target < 1 || target > 18278) {
    throw new Error("that step walks off the board");
  }
  let lettered = "";
  let left = target;
  while (left > 0) {
    const rest = (left - 1) % 26;
    lettered = String.fromCharCode(65 + rest) + lettered;
    left = Math.floor((left - 1) / 26);
  }
  return lettered;
}
