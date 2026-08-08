const PHRASE = /^[a-z0-9]+(?: [a-z0-9]+)*$/;

function runsInside(words: string[], phrase: string[]): boolean {
  for (let start = 0; start + phrase.length <= words.length; start++) {
    let all = true;
    for (let step = 0; step < phrase.length; step++) {
      if (words[start + step] !== phrase[step]) {
        all = false;
        break;
      }
    }
    if (all) return true;
  }
  return false;
}

export function codeOpenAnswers(
  rules: Array<Record<string, unknown>>,
  answers: string[],
): Record<string, unknown> {
  if (!Array.isArray(rules) || rules.length === 0) {
    throw new Error("the rules must be a non-empty list");
  }
  const codes: string[] = [];
  const phrases: string[][] = [];
  const already = new Set<string>();
  for (const rule of rules) {
    if (rule === null || typeof rule !== "object" || Array.isArray(rule)) {
      throw new Error("a rule must be a mapping");
    }
    const code = rule.code;
    const phrase = rule.phrase;
    if (typeof code !== "string" || code.length === 0) {
      throw new Error("a code must be a non-empty string");
    }
    if (typeof phrase !== "string" || !PHRASE.test(phrase)) {
      throw new Error("a phrase must be lowercase words joined by one space");
    }
    if (already.has(phrase)) throw new Error("two rules share a phrase");
    already.add(phrase);
    codes.push(code);
    phrases.push(phrase.split(" "));
  }
  if (!Array.isArray(answers)) {
    throw new Error("the answers must be a list");
  }
  const order: string[] = [];
  const count = new Map<string, number>();
  for (const code of codes) {
    if (!count.has(code)) {
      count.set(code, 0);
      order.push(code);
    }
  }
  const loose: string[] = [];
  for (const answer of answers) {
    if (typeof answer !== "string") {
      throw new Error("an answer must be a string");
    }
    const tidy = answer.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    const words = tidy === "" ? [] : tidy.split(" ");
    let taken = -1;
    for (let at = 0; at < phrases.length; at++) {
      if (runsInside(words, phrases[at])) {
        taken = at;
        break;
      }
    }
    if (taken < 0) {
      loose.push(tidy);
    } else {
      const code = codes[taken];
      count.set(code, (count.get(code) as number) + 1);
    }
  }
  return {
    tally: order.map((code) => ({ code, count: count.get(code) as number })),
    loose,
  };
}
