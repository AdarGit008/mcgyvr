/** Work stretches of a shift: span-long, rest-separated, short tails dropped. */
export function carveShift(
  start: number,
  end: number,
  span: number,
  rest: number,
  least: number,
): number[][] {
  for (const value of [start, end, span, rest, least]) {
    if (!Number.isInteger(value)) {
      throw new Error("every argument must be an integer");
    }
  }
  if (start >= end) {
    throw new Error("shift start must precede its end");
  }
  if (span < 1 || rest < 1) {
    throw new Error("span and rest must be at least 1");
  }
  if (least < 1 || least > span) {
    throw new Error("least must be between 1 and span");
  }
  const stretches: number[][] = [];
  let cursor = start;
  while (cursor < end) {
    const stop = Math.min(cursor + span, end);
    if (stop - cursor < least) {
      break;
    }
    stretches.push([cursor, stop]);
    cursor = stop + rest;
  }
  return stretches;
}
