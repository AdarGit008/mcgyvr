export function freeTrailParcels(depth: number, issued: string[]): string[] {
  if (typeof depth !== "number" || !Number.isInteger(depth)) {
    throw new Error("the depth must be a whole number");
  }
  if (depth < 1 || depth > 8) {
    throw new Error("the depth must lie between 1 and 8");
  }
  if (!Array.isArray(issued)) {
    throw new Error("the issued parcels must be a list");
  }
  for (const parcel of issued) {
    if (typeof parcel !== "string") {
      throw new Error("a parcel must be a string");
    }
    if (parcel.length > depth) {
      throw new Error("a parcel may not be longer than the depth");
    }
    for (const letter of parcel) {
      if (letter !== "L" && letter !== "R") {
        throw new Error("a parcel carries only the letters L and R");
      }
    }
  }
  for (let one = 0; one < issued.length; one += 1) {
    for (let two = 0; two < issued.length; two += 1) {
      if (one !== two && issued[two].startsWith(issued[one])) {
        throw new Error("one issued parcel holds another");
      }
    }
  }

  const free: string[] = [];
  const walk = (path: string): void => {
    if (issued.some((parcel) => path.startsWith(parcel))) {
      return;
    }
    if (issued.some((parcel) => parcel.startsWith(path))) {
      walk(`${path}L`);
      walk(`${path}R`);
      return;
    }
    free.push(path);
  };
  walk("");
  return free;
}
