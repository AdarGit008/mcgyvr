export function codeCase(code: string): string {
  const tidy = code.trim();
  if (tidy.length === 0) {
    throw new Error("empty code");
  }
  return tidy.toUpperCase();
}
