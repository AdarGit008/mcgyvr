export function describeAncestry(
  history: Record<string, string[]>,
  one: string,
  other: string,
): string {
  if (
    typeof history !== "object" ||
    history === null ||
    Array.isArray(history)
  ) {
    throw new Error("the history must be a mapping of checkpoint to predecessors");
  }
  for (const name of Object.keys(history)) {
    const listed = history[name];
    if (!Array.isArray(listed)) {
      throw new Error(`checkpoint ${name} does not list its predecessors`);
    }
    for (const earlier of listed) {
      if (typeof earlier !== "string") {
        throw new Error(`checkpoint ${name} lists a predecessor that is not a name`);
      }
      if (!Object.hasOwn(history, earlier)) {
        throw new Error(`checkpoint ${name} lists the unknown ${earlier}`);
      }
    }
  }
  for (const name of [one, other]) {
    if (typeof name !== "string" || !Object.hasOwn(history, name)) {
      throw new Error(`the history carries no checkpoint ${name}`);
    }
  }

  if (one === other) {
    return "same";
  }

  const stepsBack = (start: string, goal: string): number => {
    let ring = [start];
    const walked = new Set<string>([start]);
    let steps = 0;
    while (ring.length > 0) {
      steps += 1;
      const onward: string[] = [];
      for (const name of ring) {
        for (const earlier of history[name]) {
          if (earlier === goal) {
            return steps;
          }
          if (!walked.has(earlier)) {
            walked.add(earlier);
            onward.push(earlier);
          }
        }
      }
      ring = onward;
    }
    return -1;
  };

  const back = stepsBack(other, one);
  if (back > 0) {
    return `behind:${back}`;
  }
  const forward = stepsBack(one, other);
  if (forward > 0) {
    return `ahead:${forward}`;
  }
  return "apart";
}
