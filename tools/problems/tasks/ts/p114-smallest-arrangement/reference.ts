export function smallestArrangement(counts: number[]): string {
  if (!Array.isArray(counts) || counts.length < 1 || counts.length > 4) {
    throw new Error("counts must be a list of one to four integers");
  }
  for (const count of counts) {
    if (!Number.isInteger(count) || count < 0 || count > 12) {
      throw new Error("each count must be an integer from 0 to 12");
    }
  }
  const total = counts.reduce((sum, count) => sum + count, 0);
  if (total === 0) {
    throw new Error("at least one count must be positive");
  }

  const width = counts.length;
  const memo = new Map<string, boolean>();

  const finishable = (state: number[], last: number, run: number): boolean => {
    if (state.every((count) => count === 0)) {
      return true;
    }
    const key = state.join(",") + "|" + last + "|" + run;
    const cached = memo.get(key);
    if (cached !== undefined) {
      return cached;
    }
    let possible = false;
    for (let i = 0; i < width; i++) {
      if (state[i] === 0 || (i === last && run === 2)) {
        continue;
      }
      const next = state.slice();
      next[i] -= 1;
      if (finishable(next, i, i === last ? run + 1 : 1)) {
        possible = true;
        break;
      }
    }
    memo.set(key, possible);
    return possible;
  };

  let state = counts.slice();
  let last = -1;
  let run = 0;
  const letters: string[] = [];
  for (let position = 0; position < total; position++) {
    let placed = false;
    for (let i = 0; i < width; i++) {
      if (state[i] === 0 || (i === last && run === 2)) {
        continue;
      }
      const next = state.slice();
      next[i] -= 1;
      const nextRun = i === last ? run + 1 : 1;
      if (finishable(next, i, nextRun)) {
        letters.push(String.fromCharCode(97 + i));
        state = next;
        run = nextRun;
        last = i;
        placed = true;
        break;
      }
    }
    if (!placed) {
      throw new Error("no arrangement avoids a triple run");
    }
  }
  return letters.join("");
}
