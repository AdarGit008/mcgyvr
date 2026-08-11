/** Wildcard label rules: compile once, then pick the most specific action. */

type CompiledRule = { pattern: string; action: string; literals: number };

function segmentMatches(segment: string, text: string, from: number): boolean {
  for (let i = 0; i < segment.length; i += 1) {
    const wanted = segment[i];
    if (wanted !== "?" && wanted !== text[from + i]) {
      return false;
    }
  }
  return true;
}

export function compileRules(pairs: [string, string][]): CompiledRule[] {
  const rules: CompiledRule[] = [];
  const seen = new Set<string>();
  for (const [pattern, action] of pairs) {
    if (typeof pattern !== "string" || pattern === "") {
      throw new Error("pattern must be a non-empty string");
    }
    if (typeof action !== "string" || action === "") {
      throw new Error("action must be a non-empty string");
    }
    const star = pattern.indexOf("*");
    if (star !== -1 && pattern.indexOf("*", star + 1) !== -1) {
      throw new Error("at most one * per pattern");
    }
    if (seen.has(pattern)) {
      throw new Error(`pattern repeated: ${pattern}`);
    }
    seen.add(pattern);
    let literals = 0;
    for (const piece of pattern) {
      if (piece !== "?" && piece !== "*") {
        literals += 1;
      }
    }
    rules.push({ pattern, action, literals });
  }
  return rules;
}

function ruleFits(pattern: string, text: string): boolean {
  const star = pattern.indexOf("*");
  if (star === -1) {
    return pattern.length === text.length && segmentMatches(pattern, text, 0);
  }
  const head = pattern.slice(0, star);
  const tail = pattern.slice(star + 1);
  if (text.length < head.length + tail.length) {
    return false;
  }
  return (
    segmentMatches(head, text, 0) &&
    segmentMatches(tail, text, text.length - tail.length)
  );
}

export function bestAction(rules: CompiledRule[], text: string): string | null {
  if (typeof text !== "string") {
    throw new Error("candidate must be a string");
  }
  let best: CompiledRule | null = null;
  for (const rule of rules) {
    if (!ruleFits(rule.pattern, text)) {
      continue;
    }
    if (best === null || rule.literals > best.literals) {
      best = rule;
    }
  }
  return best === null ? null : best.action;
}
