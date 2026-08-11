/** A code padded with zeros to a fixed width. */
export function padCode(code: string, width: number): string {
  return code.padStart(width, "0");
}
