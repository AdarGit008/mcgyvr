function table(value: unknown, what: string): Record<string, string[]> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${what} must be a table`);
  }
  return value as Record<string, string[]>;
}

export function selectByImpact(
  imports: Record<string, string[]>,
  suites: Record<string, string[]>,
  edited: string[],
): string[] {
  const graph = table(imports, "the module graph");
  const drives = table(suites, "the suite table");
  if (!Array.isArray(edited)) {
    throw new Error("the edited modules must be a list");
  }

  const known = new Set(Object.keys(graph));
  const importers = new Map<string, string[]>();
  for (const module of known) {
    importers.set(module, []);
  }
  for (const [module, targets] of Object.entries(graph)) {
    if (!Array.isArray(targets)) {
      throw new Error(`${module} must list its imports`);
    }
    const seen = new Set<string>();
    for (const target of targets) {
      if (typeof target !== "string" || !known.has(target)) {
        throw new Error(`${module} imports the undeclared ${String(target)}`);
      }
      if (target === module) {
        throw new Error(`${module} imports itself`);
      }
      if (seen.has(target)) {
        throw new Error(`${module} imports ${target} twice`);
      }
      seen.add(target);
      importers.get(target)!.push(module);
    }
  }

  const disturbed = new Set<string>();
  const queue: string[] = [];
  for (const name of edited) {
    if (typeof name !== "string" || !known.has(name)) {
      throw new Error(`edited module ${String(name)} is not declared`);
    }
    if (!disturbed.has(name)) {
      disturbed.add(name);
      queue.push(name);
    }
  }
  while (queue.length > 0) {
    const module = queue.shift() as string;
    for (const importer of importers.get(module) ?? []) {
      if (!disturbed.has(importer)) {
        disturbed.add(importer);
        queue.push(importer);
      }
    }
  }

  const running: string[] = [];
  let total = 0;
  for (const [suite, modules] of Object.entries(drives)) {
    if (suite === "") {
      throw new Error("a suite name cannot be empty");
    }
    if (!Array.isArray(modules)) {
      throw new Error(`${suite} must drive a list of modules`);
    }
    for (const module of modules) {
      if (typeof module !== "string" || !known.has(module)) {
        throw new Error(`${suite} drives the undeclared ${String(module)}`);
      }
    }
    total += 1;
    if (modules.some((module) => disturbed.has(module))) {
      running.push(suite);
    }
  }
  if (running.length * 2 > total) {
    return ["ALL"];
  }
  return running.sort();
}
