export function shelfSort(labels: string[]): string[] {
  const ranked = labels.map((label, index) => ({
    label,
    order: Number(label.replace(/^[^0-9]*/, "")),
    index,
  }));
  ranked.sort((a, b) => a.order - b.order || a.index - b.index);
  return ranked.map((entry) => entry.label);
}
