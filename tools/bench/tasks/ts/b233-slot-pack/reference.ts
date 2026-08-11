export function slotPack(items: string[], capacity: number): string[][] {
  const slots: string[][] = [];
  for (let i = 0; i < items.length; i += capacity) {
    slots.push(items.slice(i, i + capacity));
  }
  return slots;
}
