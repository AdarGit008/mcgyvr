const SWELL_LIMIT = 1000000000;

export function rebuildFromTerms(run: number[]): number[] {
  if (!Array.isArray(run)) {
    throw new Error("the run must be a list");
  }
  if (run.length === 0) {
    throw new Error("an empty run spells no quotient");
  }
  if (run.length > 64) {
    throw new Error("a run may hold at most 64 entries");
  }
  for (let index = 0; index < run.length; index++) {
    const entry = run[index];
    if (!Number.isInteger(entry)) {
      throw new Error("every entry must be a whole number");
    }
    if (index === 0) {
      if (Math.abs(entry) > 1000000) {
        throw new Error("the leading entry is too large");
      }
    } else if (entry < 1 || entry > 1000) {
      throw new Error("an entry behind the leading one must lie in 1..1000");
    }
  }
  if (run.length > 1 && run[run.length - 1] === 1) {
    throw new Error("a run of more than one entry may not end in 1");
  }

  let topBefore = 0;
  let topLatest = 1;
  let bottomBefore = 1;
  let bottomLatest = 0;
  for (const entry of run) {
    const top = entry * topLatest + topBefore;
    const bottom = entry * bottomLatest + bottomBefore;
    if (Math.abs(top) > SWELL_LIMIT || Math.abs(bottom) > SWELL_LIMIT) {
      throw new Error("the quotient swells past the limit");
    }
    topBefore = topLatest;
    topLatest = top;
    bottomBefore = bottomLatest;
    bottomLatest = bottom;
  }
  return [topLatest + 0, bottomLatest + 0];
}
