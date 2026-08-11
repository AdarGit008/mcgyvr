export function wireText(text: string): string {
  if (typeof text !== "string") {
    throw new Error("wireText expects a string");
  }
  if (text.includes("\n")) {
    throw new Error("a wire text cannot hold a newline");
  }
  return "s" + text.length + ":" + text;
}

export function wireValue(value: unknown): string {
  if (typeof value === "string") {
    return wireText(value);
  }
  if (typeof value === "boolean") {
    throw new Error("a boolean is not a wire value");
  }
  if (typeof value === "number") {
    if (!Number.isInteger(value)) {
      throw new Error("only whole numbers go on the wire");
    }
    return "n" + value + ";";
  }
  if (Array.isArray(value)) {
    let rendered = "[";
    for (const item of value) {
      rendered += wireValue(item);
    }
    return rendered + "]";
  }
  throw new Error("unsupported wire value");
}
