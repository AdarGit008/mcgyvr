export function pathClean(path: string): string {
  const kept: string[] = [];
  for (const part of path.split("/")) {
    if (part === "..") {
      if (kept.length > 0) {
        kept.pop();
      }
    } else {
      kept.push(part);
    }
  }
  return kept.join("/");
}
