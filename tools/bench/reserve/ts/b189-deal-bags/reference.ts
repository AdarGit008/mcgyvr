/** Deal parcels round the courier bags, skipping the ones already full. */
export function dealBags(parcels: string[], caps: number[]): { loads: string[][]; spare: string[] } {
  if (!Array.isArray(parcels) || !Array.isArray(caps) || caps.length === 0) {
    throw new Error("dealBags expects a parcel list and a non-empty cap list");
  }
  for (const cap of caps) {
    if (!Number.isInteger(cap) || cap < 1) {
      throw new Error("every bag capacity must be a positive whole number");
    }
  }
  const loads: string[][] = caps.map(() => []);
  const spare: string[] = [];
  let bag = 0;
  for (const parcel of parcels) {
    // Pass over full bags; a whole round of them means the depot is out of room.
    let passed = 0;
    while (passed < caps.length && loads[bag].length === caps[bag]) {
      bag = (bag + 1) % caps.length;
      passed += 1;
    }
    if (passed === caps.length) {
      spare.push(parcel);
      continue;
    }
    loads[bag].push(parcel);
    bag = (bag + 1) % caps.length;
  }
  return { loads, spare };
}
