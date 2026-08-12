/**
 * Apply a keep/drop/add edit script to a document, verifying that every
 * keep and drop names the exact text it walks over.
 */
export function applyEditScript(doc: string, script: string[][]): string {
  if (typeof doc !== "string") {
    throw new Error("applyEditScript expects a string document");
  }
  if (!Array.isArray(script)) {
    throw new Error("applyEditScript expects a list of edits");
  }
  const out: string[] = [];
  let cursor = 0;
  for (const pair of script) {
    if (!Array.isArray(pair) || pair.length !== 2) {
      throw new Error("each edit is a [tag, text] pair");
    }
    const [tag, text] = pair;
    if (typeof text !== "string" || text.length === 0) {
      throw new Error("edit text must be a non-empty string");
    }
    if (tag === "add") {
      out.push(text);
      continue;
    }
    if (tag !== "keep" && tag !== "drop") {
      throw new Error(`unknown edit tag: ${String(tag)}`);
    }
    const end = cursor + text.length;
    if (end > doc.length) {
      throw new Error("edit runs past the end of the document");
    }
    const piece = doc.slice(cursor, end);
    if (piece !== text) {
      throw new Error("edit text does not match the document at the cursor");
    }
    if (tag === "keep") {
      out.push(piece);
    }
    cursor = end;
  }
  if (cursor !== doc.length) {
    throw new Error("the script leaves document characters unconsumed");
  }
  return out.join("");
}
