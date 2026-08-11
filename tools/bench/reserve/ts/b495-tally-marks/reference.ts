export function markValue(mark: string): number {
  if (mark === "a") {
    return 1;
  }
  if (mark === "b") {
    return 2;
  }
  if (mark === "c") {
    return 3;
  }
  return 0;
}

/** A line of marks totalled, doubling a mark that follows its own kind. */
export function tallyMarks(line: string): number {
  let total = 0;
  let previous = "";
  for (const mark of line) {
    const worth = markValue(mark);
    if (mark === previous) {
      total += worth * 2;
    } else {
      total += worth;
    }
    previous = mark;
  }
  return total;
}
