export function loopTurnSense(studs: number[][]): any {
  if (!Array.isArray(studs)) {
    throw new Error("loopTurnSense expects a list of studs");
  }
  if (studs.length < 3) {
    throw new Error("a loop carries at least three studs");
  }
  const whole = (value: any) =>
    typeof value === "number" && Number.isInteger(value);
  const loop: number[][] = [];
  const seen = new Set<string>();
  for (const stud of studs) {
    if (
      !Array.isArray(stud) ||
      stud.length !== 2 ||
      !whole(stud[0]) ||
      !whole(stud[1])
    ) {
      throw new Error("a stud must be a pair of two whole numbers");
    }
    if (Math.abs(stud[0]) > 10000 || Math.abs(stud[1]) > 10000) {
      throw new Error("a measure magnitude passes ten thousand");
    }
    const key = `${stud[0]},${stud[1]}`;
    if (seen.has(key)) {
      throw new Error("a stud shows up more than once");
    }
    seen.add(key);
    loop.push([stud[0] + 0, stud[1] + 0]);
  }
  let sweep = 0;
  for (let i = 0; i < loop.length; i++) {
    const here = loop[i];
    const next = loop[(i + 1) % loop.length];
    sweep += here[0] * next[1] - next[0] * here[1];
  }
  const sense = sweep > 0 ? "counter" : sweep < 0 ? "clockwise" : "flat";
  return { doubled: Math.abs(sweep), sense };
}
