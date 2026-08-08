const SQUARES = "ABCDEFGHJKLMNPQRSTUV";

function readBox(reference: string): number[] {
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
  if (figures.length % 2 !== 0 || figures.length > 10) {
    throw new Error("the tally of figures is not readable");
  }
  const tally = figures.length / 2;
  const side = 100000 / 10 ** tally;
  let easting = column * 100000;
  let northing = row * 100000;
  if (tally > 0) {
    easting += Number(figures.slice(0, tally)) * side;
    northing += Number(figures.slice(tally)) * side;
  }
  return [easting, northing, tally];
}

export function commonGridSquare(references: string[]): string {
  if (!Array.isArray(references)) {
    throw new Error("references must be a list");
  }
  if (references.length === 0) {
    throw new Error("there is nothing to enclose");
  }
  const boxes = references.map(readBox);
  let coarsest = boxes[0][2];
  for (const box of boxes) {
    if (box[2] < coarsest) coarsest = box[2];
  }
  for (let tally = coarsest; tally >= 0; tally--) {
    const side = 100000 / 10 ** tally;
    const east = Math.floor(boxes[0][0] / side);
    const north = Math.floor(boxes[0][1] / side);
    let together = true;
    for (const box of boxes) {
      if (
        Math.floor(box[0] / side) !== east ||
        Math.floor(box[1] / side) !== north
      ) {
        together = false;
        break;
      }
    }
    if (!together) continue;
    const originEast = east * side;
    const originNorth = north * side;
    const letters =
      SQUARES[Math.floor(originEast / 100000)] +
      SQUARES[Math.floor(originNorth / 100000)];
    if (tally === 0) return letters;
    const eastFigures = String((originEast % 100000) / side).padStart(
      tally,
      "0",
    );
    const northFigures = String((originNorth % 100000) / side).padStart(
      tally,
      "0",
    );
    return letters + eastFigures + northFigures;
  }
  return "";
}
