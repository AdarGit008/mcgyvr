export function plotterPose(program: string): {
  x: number;
  y: number;
  facing: string;
} {
  if (typeof program !== "string") {
    throw new Error("the program must be a string");
  }
  if (!/^(?:F\d+|B\d+|L|R)*$/.test(program)) {
    throw new Error("malformed program");
  }
  const headings = ["N", "E", "S", "W"];
  const dx = [0, 1, 0, -1];
  const dy = [1, 0, -1, 0];
  let heading = 0;
  let x = 0;
  let y = 0;
  for (const token of program.matchAll(/([FB])(\d+)|([LR])/g)) {
    if (token[3] === "L") {
      heading = (heading + 3) % 4;
    } else if (token[3] === "R") {
      heading = (heading + 1) % 4;
    } else {
      const distance = Number(token[2]);
      if (distance === 0) {
        throw new Error("a drive distance of zero is malformed");
      }
      const sign = token[1] === "F" ? 1 : -1;
      x += sign * distance * dx[heading];
      y += sign * distance * dy[heading];
    }
  }
  return { x, y, facing: headings[heading] };
}
