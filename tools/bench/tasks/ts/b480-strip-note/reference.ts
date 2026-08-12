export function stripNote(title: string): string {
  if (!title.endsWith(")")) {
    return title;
  }
  const opened = title.lastIndexOf("(");
  if (opened === -1) {
    return title;
  }
  return title.slice(0, opened).trimEnd();
}
