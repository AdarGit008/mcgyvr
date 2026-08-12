/** Dotted outline labels for a nested document, "1.2 Heading" style. */
export function numberSections(sections: object[]): string[] {
  if (!Array.isArray(sections)) {
    throw new Error("numberSections expects a list of sections");
  }
  const labels: string[] = [];
  const walk = (nodes: any[], trail: string): void => {
    nodes.forEach((node, index) => {
      if (typeof node !== "object" || node === null || !Array.isArray(node.children)) {
        throw new Error("a section must be a mapping with a children list");
      }
      if (typeof node.heading !== "string" || node.heading.length === 0) {
        throw new Error("a heading must be a non-empty string");
      }
      const label = trail + String(index + 1);
      labels.push(label + " " + node.heading);
      walk(node.children, label + ".");
    });
  };
  walk(sections, "");
  return labels;
}

export function sectionCount(sections: object[]): number {
  return numberSections(sections).length;
}
