export function writeSenaryTail(numerator: number, denominator: number): string {
  if (
    typeof numerator !== "number" ||
    typeof denominator !== "number" ||
    !Number.isInteger(numerator) ||
    !Number.isInteger(denominator)
  ) {
    throw new Error("both readings must be whole numbers");
  }
  if (denominator < 1 || denominator > 10000) {
    throw new Error("the lower reading must lie in 1..10000");
  }
  if (numerator < 0 || numerator >= denominator) {
    throw new Error("the upper reading must sit at or above zero and below the lower one");
  }
  if (numerator === 0) {
    return "0";
  }
  const seen = new Map();
  const marks: string[] = [];
  let carry = numerator;
  let opens = -1;
  while (carry !== 0) {
    if (seen.has(carry)) {
      opens = seen.get(carry);
      break;
    }
    seen.set(carry, marks.length);
    const lifted = carry * 6;
    marks.push(String(Math.floor(lifted / denominator)));
    carry = lifted % denominator;
  }
  if (opens === -1) {
    return marks.join("");
  }
  return (
    marks.slice(0, opens).join("") + "|" + marks.slice(opens).join("") + "|"
  );
}
