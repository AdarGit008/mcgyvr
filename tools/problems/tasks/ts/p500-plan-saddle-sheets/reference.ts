function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function planSaddleSheets(pages: number, binding: string): string[] {
  if (!whole(pages)) {
    throw new Error("the page count is not a whole number");
  }
  if (pages < 1 || pages > 4000) {
    throw new Error("the page count falls outside one through four thousand");
  }
  if (binding !== "left" && binding !== "right") {
    throw new Error("the binding is neither left nor right");
  }

  const padded = pages + ((4 - (pages % 4)) % 4);
  const sheets = padded / 4;
  const face = (number: number): string => (number > pages ? "blank" : String(number));

  const lines: string[] = [];
  for (let sheet = 1; sheet <= sheets; sheet++) {
    const frontLeft = padded + 2 - 2 * sheet;
    const frontRight = 2 * sheet - 1;
    const backLeft = 2 * sheet;
    const backRight = padded + 1 - 2 * sheet;
    const front = binding === "left" ? [frontLeft, frontRight] : [frontRight, frontLeft];
    const back = binding === "left" ? [backLeft, backRight] : [backRight, backLeft];
    lines.push(`${sheet} front ${face(front[0])} ${face(front[1])}`);
    lines.push(`${sheet} back ${face(back[0])} ${face(back[1])}`);
  }
  return lines;
}
