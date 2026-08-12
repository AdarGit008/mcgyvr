export function trimTo(line: string, limit: number): string {
  if (limit < 4) {
    throw new Error("limit must leave room");
  }
  if (line.length <= limit) {
    return line;
  }
  return line.slice(0, limit - 3) + "...";
}
