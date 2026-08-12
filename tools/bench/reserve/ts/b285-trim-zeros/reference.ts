export function trimZeros(text: string): string {
  const sign = text.startsWith("-") ? "-" : "";
  const digits = sign === "-" ? text.slice(1) : text;
  if (!/^[0-9]+$/.test(digits)) {
    return text;
  }
  const trimmed = digits.replace(/^0+/, "");
  return sign + (trimmed === "" ? "0" : trimmed);
}
