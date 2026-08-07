function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function countTrimSticks(
  stick: number,
  calls: number[],
  blade: number,
): { sticks: number; tails: number[] } {
  if (!whole(stick) || stick < 1) {
    throw new Error("the stick is not whole or falls below one");
  }
  if (!Array.isArray(calls)) {
    throw new Error("the calls are not a list");
  }
  if (!whole(blade) || blade < 0) {
    throw new Error("the blade is not whole or falls below nought");
  }

  const tails: number[] = [];
  for (const call of calls) {
    if (!whole(call) || call < 1) {
      throw new Error("a call is not whole or falls below one");
    }
    if (call > stick) {
      throw new Error("a call is longer than a fresh stick");
    }
    if (tails.length === 0 || call > tails[tails.length - 1]) {
      tails.push(stick);
    }
    const rest = tails[tails.length - 1] - call - blade;
    tails[tails.length - 1] = rest > 0 ? rest : 0;
  }

  return { sticks: tails.length, tails };
}
