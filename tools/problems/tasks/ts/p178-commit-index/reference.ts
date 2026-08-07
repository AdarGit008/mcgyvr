function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function commitIndex(
  log: number[],
  matches: number[],
  currentTerm: number,
): { commit: number; safe: number; behind: number[] } {
  if (!Array.isArray(log) || !Array.isArray(matches)) {
    throw new Error("the log and the copied numbers must both be lists");
  }
  if (!whole(currentTerm) || currentTerm < 1) {
    throw new Error("the current term must be a whole number of one or more");
  }
  let previous = 0;
  for (const term of log) {
    if (!whole(term) || term < 1) {
      throw new Error("a term must be a whole number of one or more");
    }
    if (term < previous) {
      throw new Error("terms never fall as the log grows");
    }
    if (term > currentTerm) {
      throw new Error("no entry may be stamped above the current term");
    }
    previous = term;
  }
  for (const copied of matches) {
    if (!whole(copied) || copied < 0 || copied > log.length) {
      throw new Error("a copied number must lie between zero and the log length");
    }
  }
  const quorum = Math.floor((matches.length + 1) / 2) + 1;
  let commit = 0;
  for (let entry = log.length; entry >= 1; entry--) {
    if (log[entry - 1] !== currentTerm) {
      continue;
    }
    let copiers = 1;
    for (const copied of matches) {
      if (copied >= entry) {
        copiers += 1;
      }
    }
    if (copiers >= quorum) {
      commit = entry;
      break;
    }
  }
  let safe = commit;
  for (const copied of matches) {
    if (copied < safe) {
      safe = copied;
    }
  }
  const behind: number[] = [];
  for (let at = 0; at < matches.length; at++) {
    if (matches[at] < commit) {
      behind.push(at);
    }
  }
  return { commit, safe, behind };
}
