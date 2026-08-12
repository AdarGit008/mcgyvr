/** The labels that are not empty, in order. */
export function dropBlank(labels: string[]): string[] {
  return labels.filter((label) => label !== "");
}
