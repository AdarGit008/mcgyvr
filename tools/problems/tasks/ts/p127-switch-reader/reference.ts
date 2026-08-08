export function readSwitches(
  kinds: Record<string, string>,
  tokens: string[],
): { found: Record<string, boolean | string>; extra: string[] } {
  const found: Record<string, boolean | string> = {};
  const extra: string[] = [];
  let i = 0;
  while (i < tokens.length) {
    const token = tokens[i];
    i += 1;
    if (!token.startsWith("--")) {
      extra.push(token);
      continue;
    }
    const body = token.slice(2);
    const eq = body.indexOf("=");
    const name = eq === -1 ? body : body.slice(0, eq);
    if (!Object.prototype.hasOwnProperty.call(kinds, name)) {
      throw new Error(`unknown option ${name}`);
    }
    if (kinds[name] === "switch") {
      if (eq !== -1) {
        throw new Error(`switch ${name} takes no text`);
      }
      found[name] = true;
    } else if (eq !== -1) {
      found[name] = body.slice(eq + 1);
    } else {
      if (i >= tokens.length) {
        throw new Error(`value option ${name} has nothing following`);
      }
      found[name] = tokens[i];
      i += 1;
    }
  }
  return { found, extra };
}
