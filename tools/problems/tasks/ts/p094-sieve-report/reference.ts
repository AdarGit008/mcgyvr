const OPS = new Set(["eq", "ne", "gt", "lt", "present", "absent"]);

export function sieveReport(
  items: Array<Record<string, unknown>>,
  rules: Array<Record<string, unknown>>,
): string[] {
  const seen = new Set<string>();
  for (const rule of rules) {
    const name = rule.name;
    if (typeof name !== "string" || name === "") {
      throw new Error("rule name must be a non-empty string");
    }
    if (seen.has(name)) {
      throw new Error(`rule name already used: ${name}`);
    }
    seen.add(name);
    if (typeof rule.op !== "string" || !OPS.has(rule.op)) {
      throw new Error(`unknown op: ${String(rule.op)}`);
    }
  }
  return items.map((item) => {
    for (const rule of rules) {
      const field = rule.field as string;
      const has = Object.prototype.hasOwnProperty.call(item, field);
      const value = item[field];
      let ok: boolean;
      switch (rule.op) {
        case "present":
          ok = has;
          break;
        case "absent":
          ok = !has;
          break;
        case "eq":
          ok = has && value === rule.value;
          break;
        case "ne":
          ok = has && value !== rule.value;
          break;
        case "gt":
          ok = has && typeof value === "number" && value > (rule.value as number);
          break;
        default:
          ok = has && typeof value === "number" && value < (rule.value as number);
          break;
      }
      if (!ok) {
        return rule.name as string;
      }
    }
    return "pass";
  });
}
