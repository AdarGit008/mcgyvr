const SIGN_KINDS: Record<string, string> = { "+": "must", "-": "not" };

export function tokenizeQuery(input: string): string[][] {
  if (typeof input !== "string" || input.trim() === "") {
    throw new Error("tokenizeQuery expects a non-empty query");
  }
  const pairs: string[][] = [];
  let at = 0;
  while (at < input.length) {
    if (input[at] === " ") {
      at += 1;
      continue;
    }
    if (input[at] === '"') {
      const close = input.indexOf('"', at + 1);
      if (close === -1) {
        throw new Error("a phrase is missing its closing quote");
      }
      if (close === at + 1) {
        throw new Error("a phrase may not be empty");
      }
      pairs.push(["phrase", input.slice(at + 1, close)]);
      at = close + 1;
      continue;
    }
    let kind = "word";
    if (input[at] === "+" || input[at] === "-") {
      kind = SIGN_KINDS[input[at]];
      at += 1;
    }
    const from = at;
    while (at < input.length && input[at] !== " ") {
      at += 1;
    }
    if (at === from) {
      throw new Error("a + or - needs a word after it");
    }
    pairs.push([kind, input.slice(from, at)]);
  }
  return pairs;
}
