export function crumbSplit(trail: string): string[] {
  return trail.split("/").filter((part) => part.length > 0);
}

export function crumbJoin(parts: string[]): string {
  return parts.filter((part) => part.length > 0).join("/");
}
