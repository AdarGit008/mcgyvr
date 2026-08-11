export function applyEditScript(original: string, script: [string, any][]): string {
  if (typeof original !== "string") {
    throw new Error("applyEditScript expects a string original");
  }
  let cursor = 0;
  let output = "";
  for (const [name, arg] of script) {
    if (name === "insert") {
      if (typeof arg !== "string" || arg === "") {
        throw new Error("insert text must be a non-empty string");
      }
      output += arg;
      continue;
    }
    if (name !== "copy" && name !== "skip") throw new Error("unknown op: " + String(name));
    if (!Number.isInteger(arg) || arg < 1) throw new Error("count must be a positive integer");
    if (cursor + arg > original.length) throw new Error("op reads past the end of the original");
    if (name === "copy") output += original.slice(cursor, cursor + arg);
    cursor += arg;
  }
  if (cursor !== original.length) {
    throw new Error("script must consume the original exactly");
  }
  return output;
}
