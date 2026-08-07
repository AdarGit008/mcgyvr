function readAdvice(lines: unknown, side: string): Map<string, number> {
  if (!Array.isArray(lines)) {
    throw new Error(`the ${side} advice must be a list`);
  }
  const amounts = new Map<string, number>();
  for (const pair of lines) {
    if (!Array.isArray(pair) || pair.length !== 2) {
      throw new Error(`a ${side} line is a label and an amount`);
    }
    const [label, cents] = pair;
    if (typeof label !== "string" || label === "") {
      throw new Error(`a ${side} label must be a non-empty string`);
    }
    if (!Number.isInteger(cents)) {
      throw new Error(`${label} carries an amount that is not whole`);
    }
    if (amounts.has(label)) {
      throw new Error(`the ${side} advice repeats ${label}`);
    }
    amounts.set(label, cents as number);
  }
  return amounts;
}

export function compareRemitLines(
  ours: unknown[][],
  theirs: unknown[][],
): { agreed: string[]; queried: string[]; ourSide: string[]; theirSide: string[] } {
  const mine = readAdvice(ours, "our");
  const yours = readAdvice(theirs, "their");
  const agreed: string[] = [];
  const queried: string[] = [];
  const ourSide: string[] = [];
  const theirSide: string[] = [];
  for (const [label, cents] of mine) {
    if (!yours.has(label)) {
      ourSide.push(label);
    } else if (yours.get(label) === cents) {
      agreed.push(label);
    } else {
      queried.push(label);
    }
  }
  for (const label of yours.keys()) {
    if (!mine.has(label)) {
      theirSide.push(label);
    }
  }
  return {
    agreed: agreed.sort(),
    queried: queried.sort(),
    ourSide: ourSide.sort(),
    theirSide: theirSide.sort(),
  };
}
