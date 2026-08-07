export function runEditor(ops: (string | number)[][]): string {
  const past: string[] = [];
  let future: string[] = [];
  let text = "";
  for (const op of ops) {
    const kind = op[0];
    if (kind === "type") {
      const piece = op[1];
      if (typeof piece !== "string" || piece.length === 0) {
        throw new Error("type needs a non-empty string");
      }
      past.push(text);
      future = [];
      text = text + piece;
    } else if (kind === "erase") {
      const count = op[1];
      if (typeof count !== "number" || !Number.isInteger(count) || count < 1 || count > text.length) {
        throw new Error("erase count out of range");
      }
      past.push(text);
      future = [];
      text = text.slice(0, text.length - count);
    } else if (kind === "undo") {
      if (past.length > 0) {
        future.push(text);
        text = past.pop()!;
      }
    } else if (kind === "redo") {
      if (future.length > 0) {
        past.push(text);
        text = future.pop()!;
      }
    } else {
      throw new Error(`unknown operation ${String(kind)}`);
    }
  }
  return text;
}
