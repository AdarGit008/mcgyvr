const LADDER = ["int", "long", "text"];
const NAME = /^[a-z][a-z0-9_]*$/;

function isMapping(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readName(value: unknown): string {
  if (typeof value !== "string" || !NAME.test(value)) {
    throw new Error("a column name must be a lowercase word starting with a letter");
  }
  return value;
}

function readKind(value: unknown): string {
  if (typeof value !== "string" || LADDER.indexOf(value) === -1) {
    throw new Error("a kind must be one of int, long and text");
  }
  return value;
}

export function applySchemaSteps(
  columns: Array<Record<string, unknown>>,
  steps: Array<Record<string, unknown>>,
): Array<Record<string, string>> {
  if (!Array.isArray(columns) || columns.length === 0) {
    throw new Error("the table must be a non-empty list of columns");
  }
  if (!Array.isArray(steps)) {
    throw new Error("the steps must be a list");
  }
  const table: Array<Record<string, string>> = [];
  for (const entry of columns) {
    if (!isMapping(entry)) {
      throw new Error("every column must be a mapping");
    }
    const name = readName((entry as Record<string, unknown>).name);
    const kind = readKind((entry as Record<string, unknown>).kind);
    if (table.some((held) => held.name === name)) {
      throw new Error("two columns share the name " + name);
    }
    table.push({ name, kind });
  }
  for (const raw of steps) {
    if (!isMapping(raw)) {
      throw new Error("every step must be a mapping");
    }
    const step = raw as Record<string, unknown>;
    const op = step.op;
    if (op === "add") {
      const name = readName(step.name);
      const kind = readKind(step.kind);
      if (table.some((held) => held.name === name)) {
        throw new Error("the name " + name + " is already carried");
      }
      table.push({ name, kind });
    } else if (op === "drop") {
      const name = readName(step.name);
      const at = table.findIndex((held) => held.name === name);
      if (at === -1) {
        throw new Error("no column called " + name);
      }
      if (table.length === 1) {
        throw new Error("the last column may not be dropped");
      }
      table.splice(at, 1);
    } else if (op === "rename") {
      const name = readName(step.name);
      const to = readName(step.to);
      const at = table.findIndex((held) => held.name === name);
      if (at === -1) {
        throw new Error("no column called " + name);
      }
      if (table.some((held) => held.name === to)) {
        throw new Error("the name " + to + " is already carried");
      }
      table[at] = { name: to, kind: table[at].kind };
    } else if (op === "retype") {
      const name = readName(step.name);
      const kind = readKind(step.kind);
      const at = table.findIndex((held) => held.name === name);
      if (at === -1) {
        throw new Error("no column called " + name);
      }
      if (LADDER.indexOf(kind) <= LADDER.indexOf(table[at].kind)) {
        throw new Error("a retype must widen the kind");
      }
      table[at] = { name, kind };
    } else {
      throw new Error("an op must be one of add, drop, rename and retype");
    }
  }
  return table;
}
