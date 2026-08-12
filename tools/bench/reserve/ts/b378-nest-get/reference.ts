/** What a path of keys finds in nested mappings. */
export function nestGet(tree: unknown, path: string[]): string {
  let here: unknown = tree;
  for (const key of path) {
    if (typeof here !== "object" || here === null) {
      return "";
    }
    here = (here as Record<string, unknown>)[key];
  }
  return typeof here === "string" ? here : "";
}
