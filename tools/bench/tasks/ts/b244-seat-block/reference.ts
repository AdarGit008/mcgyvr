export function seatBlock(label: string): (number | string)[] {
  const found = /^(\d+)([A-Z])$/.exec(label);
  if (found === null) {
    throw new Error("not a seat label: " + label);
  }
  return [Number(found[1]), found[2]];
}
