const SQUARES = "ABCDEFGHJKLMNPQRSTUV";

export function decodeGridReference(reference: string): number[] {
  if (typeof reference !== "string") {
    throw new Error("a reference is a string");
  }
  if (reference.length < 2) {
    throw new Error("a reference opens with two capitals");
  }
  const column = SQUARES.indexOf(reference[0]);
  const row = SQUARES.indexOf(reference[1]);
  if (column < 0 || row < 0) {
    throw new Error("that capital is not on the projection");
  }
  const figures = reference.slice(2);
  if (!/^[0-9]*$/.test(figures)) {
    throw new Error("only decimal figures may trail the capitals");
  }
  if (figures.length % 2 !== 0) {
    throw new Error("the figures must split evenly between the two axes");
  }
  if (figures.length > 10) {
    throw new Error("ten figures is the finest the projection carries");
  }
  const half = figures.length / 2;
  const side = 100000 / 10 ** half;
  let easting = column * 100000;
  let northing = row * 100000;
  if (half > 0) {
    easting += Number(figures.slice(0, half)) * side;
    northing += Number(figures.slice(half)) * side;
  }
  return [easting, northing];
}
