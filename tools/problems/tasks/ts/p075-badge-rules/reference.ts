export function evaluateRules(
  rules: Array<Record<string, string>>,
  request: Record<string, string>
): string {
  for (const rule of rules) {
    const roleOk = rule.role === request.role || rule.role === "everyone";
    const doorOk = rule.door === request.door || rule.door === "all";
    if (roleOk && doorOk) {
      return rule.effect;
    }
  }
  return "deny";
}
