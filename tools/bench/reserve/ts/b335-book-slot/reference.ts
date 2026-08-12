export function slotFree(slot: number, booked: number[]): boolean {
  return !booked.includes(slot);
}

export function freeSlots(last: number, booked: number[]): number[] {
  const free: number[] = [];
  for (let slot = 1; slot <= last; slot += 1) {
    if (slotFree(slot, booked)) {
      free.push(slot);
    }
  }
  return free;
}
