export function rollbackJournal(
  lines: string[],
  journal: (string | number)[][],
  count: number,
): string[] {
  if (!Array.isArray(lines) || lines.some((line) => typeof line !== "string")) {
    throw new Error("lines must be a list of strings");
  }
  if (!Array.isArray(journal)) {
    throw new Error("journal must be a list");
  }
  if (!Number.isInteger(count) || count < 0 || count > journal.length) {
    throw new Error("count must be an integer from 0 to the journal length");
  }
  const arity: Record<string, number> = { insert: 3, delete: 3, replace: 4 };
  const doc = lines.slice();
  for (let i = journal.length - 1; i >= journal.length - count; i -= 1) {
    const entry = journal[i];
    if (
      !Array.isArray(entry) ||
      typeof entry[0] !== "string" ||
      arity[entry[0]] !== entry.length ||
      entry.slice(2).some((text) => typeof text !== "string")
    ) {
      throw new Error("malformed journal entry");
    }
    const kind = entry[0];
    const index = entry[1] as number;
    const limit = kind === "delete" ? doc.length : doc.length - 1;
    if (!Number.isInteger(index) || index < 0 || index > limit) {
      throw new Error("entry index is outside the document");
    }
    if (kind === "insert") {
      if (doc[index] !== entry[2]) {
        throw new Error("journal disagrees with the document");
      }
      doc.splice(index, 1);
    } else if (kind === "delete") {
      doc.splice(index, 0, entry[2] as string);
    } else {
      if (doc[index] !== entry[3]) {
        throw new Error("journal disagrees with the document");
      }
      doc[index] = entry[2] as string;
    }
  }
  return doc;
}
