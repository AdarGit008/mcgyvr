type Entry = { name: string; kind: string; alias?: string };

export function parseInvocation(
  catalogue: Entry[],
  tokens: string[],
): { options: Record<string, unknown>; operands: string[] } {
  const byName = new Map<string, Entry>();
  const byAlias = new Map<string, Entry>();
  const options: Record<string, unknown> = {};
  for (const entry of catalogue) {
    byName.set(entry.name, entry);
    if (entry.alias !== undefined) {
      byAlias.set(entry.alias, entry);
    }
    if (entry.kind === "toggle") {
      options[entry.name] = false;
    } else if (entry.kind === "single") {
      options[entry.name] = null;
    } else {
      options[entry.name] = [];
    }
  }
  const operands: string[] = [];
  const seenSingle = new Set<string>();
  let optionsDone = false;
  let i = 0;
  while (i < tokens.length) {
    const token = tokens[i];
    if (optionsDone) {
      operands.push(token);
      i += 1;
      continue;
    }
    if (token === "--") {
      optionsDone = true;
      i += 1;
      continue;
    }
    let entry: Entry | undefined;
    let inline: string | undefined;
    if (token.startsWith("--")) {
      const eq = token.indexOf("=");
      const name = eq === -1 ? token.slice(2) : token.slice(2, eq);
      inline = eq === -1 ? undefined : token.slice(eq + 1);
      entry = byName.get(name);
      if (entry === undefined) {
        throw new Error(`unknown option ${name}`);
      }
    } else if (token.startsWith("-") && token.length === 2) {
      entry = byAlias.get(token[1]);
      if (entry === undefined) {
        throw new Error(`unknown alias ${token}`);
      }
    } else {
      operands.push(token);
      i += 1;
      continue;
    }
    i += 1;
    if (entry.kind === "toggle") {
      if (inline !== undefined) {
        throw new Error(`toggle ${entry.name} takes no value`);
      }
      options[entry.name] = true;
      continue;
    }
    let value: string;
    if (inline !== undefined) {
      value = inline;
    } else {
      if (i >= tokens.length) {
        throw new Error(`option ${entry.name} is missing its value`);
      }
      value = tokens[i];
      i += 1;
    }
    if (entry.kind === "single") {
      if (seenSingle.has(entry.name)) {
        throw new Error(`single option ${entry.name} mentioned twice`);
      }
      seenSingle.add(entry.name);
      options[entry.name] = value;
    } else {
      (options[entry.name] as string[]).push(value);
    }
  }
  return { options, operands };
}
