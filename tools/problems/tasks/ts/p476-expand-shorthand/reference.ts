export function expandShorthand(
  text: string,
  table: Record<string, string>,
): string {
  if (typeof text !== "string") {
    throw new Error("expandShorthand expects a string of text");
  }
  if (typeof table !== "object" || table === null || Array.isArray(table)) {
    throw new Error("the table is not a mapping");
  }

  const book = new Map<string, string>();
  for (const key of Object.keys(table)) {
    if (!/^[a-z][a-z0-9]*$/.test(key)) {
      throw new Error("a key is not lowercase letters and digits after a letter");
    }
    const value = table[key];
    if (typeof value !== "string" || value.length === 0) {
      throw new Error("a value is not a non-empty string");
    }
    book.set(key, value);
  }

  return text.replace(/[A-Za-z0-9]+/g, (word) => {
    const lowered = word.toLowerCase();
    const value = book.get(lowered);
    if (value === undefined) {
      return word;
    }
    if (word === lowered) {
      return value;
    }
    if (word === word.toUpperCase()) {
      return value.toUpperCase();
    }
    if (word === lowered.charAt(0).toUpperCase() + lowered.slice(1)) {
      return value.charAt(0).toUpperCase() + value.slice(1);
    }
    return word;
  });
}
