export function smallestFreeWord(
  n: number,
  k: number,
  banned: string[]
): string {
  if (!Number.isInteger(n) || n < 1 || n > 12) {
    throw new Error("n must be a positive integer of at most 12");
  }
  if (!Number.isInteger(k) || k < 1 || k > 6) {
    throw new Error("k must be an integer from 1 to 6");
  }
  if (!Array.isArray(banned)) {
    throw new Error("banned must be a list");
  }
  const letters: string[] = [];
  for (let i = 0; i < k; i++) {
    letters.push(String.fromCharCode(97 + i));
  }
  const blocked = new Set<string>();
  for (const pair of banned) {
    if (
      typeof pair !== "string" ||
      pair.length !== 2 ||
      !letters.includes(pair[0]) ||
      !letters.includes(pair[1])
    ) {
      throw new Error("banned entries are two-letter strings in the alphabet");
    }
    blocked.add(pair);
  }

  const memo = new Map<string, boolean>();
  const extendable = (previous: string, remaining: number): boolean => {
    if (remaining === 0) {
      return true;
    }
    const key = previous + ":" + remaining;
    const cached = memo.get(key);
    if (cached !== undefined) {
      return cached;
    }
    let possible = false;
    for (const letter of letters) {
      if (previous !== "" && blocked.has(previous + letter)) {
        continue;
      }
      if (extendable(letter, remaining - 1)) {
        possible = true;
        break;
      }
    }
    memo.set(key, possible);
    return possible;
  };

  let word = "";
  let previous = "";
  for (let position = 0; position < n; position++) {
    let chosen = "";
    for (const letter of letters) {
      if (previous !== "" && blocked.has(previous + letter)) {
        continue;
      }
      if (extendable(letter, n - position - 1)) {
        chosen = letter;
        break;
      }
    }
    if (chosen === "") {
      throw new Error("every candidate word is blocked");
    }
    word += chosen;
    previous = chosen;
  }
  return word;
}
