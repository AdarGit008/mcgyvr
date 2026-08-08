type Rule = { effect: string; action: string; path: string[] };
type Request = { action: string; path: string[] };

export function resolveAccess(
  rules: Rule[],
  request: Request
): { decision: string; rule: number } {
  for (const rule of rules) {
    if (rule.effect !== "allow" && rule.effect !== "deny") {
      throw new Error("bad effect: " + rule.effect);
    }
    if (rule.action === "") {
      throw new Error("empty action in rule");
    }
  }
  let best = -1;
  let bestKey: [number, number, number, number] | null = null;
  for (let i = 0; i < rules.length; i++) {
    const rule = rules[i];
    if (rule.path.length > request.path.length) continue;
    let prefix = true;
    for (let j = 0; j < rule.path.length; j++) {
      if (rule.path[j] !== request.path[j]) {
        prefix = false;
        break;
      }
    }
    if (!prefix) continue;
    if (rule.action !== request.action && rule.action !== "any") continue;
    const key: [number, number, number, number] = [
      rule.path.length,
      rule.action === "any" ? 0 : 1,
      rule.effect === "deny" ? 1 : 0,
      -i,
    ];
    if (bestKey === null || compare(key, bestKey) > 0) {
      bestKey = key;
      best = i;
    }
  }
  if (best === -1) {
    return { decision: "deny", rule: -1 };
  }
  return { decision: rules[best].effect, rule: best };
}

function compare(a: number[], b: number[]): number {
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return 0;
}
