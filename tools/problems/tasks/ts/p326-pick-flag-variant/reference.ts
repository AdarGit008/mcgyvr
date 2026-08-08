type Test = { trait: string; word: string; value: any };
type Rule = { tests: Test[]; split: [string, number][] };

const WORDS = ["is", "not", "in"];

function record(value: any): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function text(value: any): boolean {
  return typeof value === "string" && value.length > 0;
}

function whole(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function owns(holder: any, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(holder, key);
}

export function pickFlagVariant(
  flag: any,
  subject: any,
): { variant: string; rule: number } {
  if (!record(flag) || !owns(flag, "rules") || !owns(flag, "fallback")) {
    throw new Error("a flag must be a record carrying rules and fallback");
  }
  if (!Array.isArray(flag.rules)) {
    throw new Error("rules must be a list");
  }
  if (!text(flag.fallback)) {
    throw new Error("fallback must be a non-empty string");
  }
  if (!record(subject) || !owns(subject, "traits") || !owns(subject, "bucket")) {
    throw new Error("a subject must be a record carrying traits and bucket");
  }
  if (!record(subject.traits)) {
    throw new Error("traits must be a record");
  }
  for (const value of Object.values(subject.traits)) {
    if (typeof value !== "string") {
      throw new Error("every trait must hold a string");
    }
  }
  if (!whole(subject.bucket) || subject.bucket < 0 || subject.bucket > 99) {
    throw new Error("bucket must be a whole number from 0 to 99");
  }

  const rules: Rule[] = [];
  for (const raw of flag.rules) {
    if (!record(raw) || !owns(raw, "match") || !owns(raw, "split")) {
      throw new Error("a rule must be a record carrying match and split");
    }
    if (!Array.isArray(raw.match)) {
      throw new Error("match must be a list");
    }
    const tests: Test[] = [];
    for (const test of raw.match) {
      if (!Array.isArray(test) || test.length !== 3) {
        throw new Error("a test must be a three-element list");
      }
      const [trait, word, value] = test;
      if (!text(trait)) {
        throw new Error("a trait name must be a non-empty string");
      }
      if (!WORDS.includes(word)) {
        throw new Error("a test word must be is, not or in");
      }
      if (word === "in") {
        if (!Array.isArray(value) || value.length === 0) {
          throw new Error("an in test needs a non-empty list");
        }
        for (const option of value) {
          if (typeof option !== "string") {
            throw new Error("an in test lists strings");
          }
        }
      } else if (typeof value !== "string") {
        throw new Error("an is or not test compares against a string");
      }
      tests.push({ trait, word, value });
    }
    if (!Array.isArray(raw.split) || raw.split.length === 0) {
      throw new Error("split must be a non-empty list");
    }
    const split: [string, number][] = [];
    const named = new Set<string>();
    let total = 0;
    for (const entry of raw.split) {
      if (!Array.isArray(entry) || entry.length !== 2) {
        throw new Error("a split entry must be a two-element list");
      }
      const [variant, share] = entry;
      if (!text(variant)) {
        throw new Error("a variant must be a non-empty string");
      }
      if (named.has(variant)) {
        throw new Error("a split names " + variant + " twice");
      }
      named.add(variant);
      if (!whole(share) || share < 0) {
        throw new Error("a share must be a whole number of zero or more");
      }
      total += share;
      split.push([variant, share]);
    }
    if (total !== 100) {
      throw new Error("the shares of a split must add up to 100");
    }
    rules.push({ tests, split });
  }

  const traits = subject.traits;
  const holds = (test: Test): boolean => {
    const carried = owns(traits, test.trait) ? traits[test.trait] : null;
    if (test.word === "is") {
      return carried !== null && carried === test.value;
    }
    if (test.word === "in") {
      return carried !== null && test.value.includes(carried);
    }
    return carried === null || carried !== test.value;
  };

  for (let index = 0; index < rules.length; index++) {
    if (!rules[index].tests.every(holds)) {
      continue;
    }
    let running = 0;
    for (const [variant, share] of rules[index].split) {
      running += share;
      if (running > subject.bucket) {
        return { variant, rule: index };
      }
    }
  }
  return { variant: flag.fallback, rule: -1 };
}
