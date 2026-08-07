export function foldSchemaEdits(
  fields: string[],
  edits: Array<Record<string, unknown>>,
): string[] {
  if (!Array.isArray(fields) || fields.length === 0) {
    throw new Error("the header must be a non-empty list");
  }
  const header: string[] = [];
  for (const field of fields) {
    if (typeof field !== "string" || field.length === 0) {
      throw new Error("every heading must be a non-empty string");
    }
    if (header.indexOf(field) !== -1) {
      throw new Error("the header repeats " + field);
    }
    header.push(field);
  }
  if (!Array.isArray(edits)) {
    throw new Error("the edits must be a list");
  }
  for (const raw of edits) {
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
      throw new Error("every edit must be a mapping");
    }
    const edit = raw as Record<string, unknown>;
    const field = edit.field;
    if (typeof field !== "string" || field.length === 0) {
      throw new Error("every edit must name a non-empty heading");
    }
    if (edit.op === "add") {
      if (header.indexOf(field) !== -1) {
        throw new Error(field + " is already taken");
      }
      header.push(field);
    } else if (edit.op === "drop") {
      const at = header.indexOf(field);
      if (at === -1) {
        throw new Error("no heading called " + field);
      }
      header.splice(at, 1);
    } else if (edit.op === "rename") {
      const into = edit.into;
      if (typeof into !== "string" || into.length === 0) {
        throw new Error("a rename must give a non-empty into");
      }
      const at = header.indexOf(field);
      if (at === -1) {
        throw new Error("no heading called " + field);
      }
      if (header.indexOf(into) !== -1) {
        throw new Error(into + " is already taken");
      }
      header[at] = into;
    } else {
      throw new Error("an op must be add, drop or rename");
    }
  }
  return header;
}
