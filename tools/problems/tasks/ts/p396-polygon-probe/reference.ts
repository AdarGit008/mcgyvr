export function polygonProbe(outline: number[][], probes: number[][]): any {
  const whole = (value: any) =>
    typeof value === "number" && Number.isInteger(value);
  const spot = (given: any, what: string): number[] => {
    if (
      !Array.isArray(given) ||
      given.length !== 2 ||
      !whole(given[0]) ||
      !whole(given[1])
    ) {
      throw new Error(`a ${what} must be a pair of two whole numbers`);
    }
    if (Math.abs(given[0]) > 100000 || Math.abs(given[1]) > 100000) {
      throw new Error("a measure magnitude passes one hundred thousand");
    }
    return [given[0] + 0, given[1] + 0];
  };
  if (!Array.isArray(outline) || !Array.isArray(probes)) {
    throw new Error("polygonProbe expects two lists");
  }
  if (outline.length < 3) {
    throw new Error("a ring carries at least three corners");
  }
  const ring = outline.map((corner) => spot(corner, "corner"));
  for (let i = 1; i < ring.length; i++) {
    if (ring[i][0] === ring[i - 1][0] && ring[i][1] === ring[i - 1][1]) {
      throw new Error("neighbouring corners repeat");
    }
  }
  const head = ring[0];
  const tail = ring[ring.length - 1];
  if (head[0] === tail[0] && head[1] === tail[1]) {
    throw new Error("the tail corner equals the opening one");
  }
  let sweep = 0;
  for (let i = 0; i < ring.length; i++) {
    const here = ring[i];
    const next = ring[(i + 1) % ring.length];
    sweep += here[0] * next[1] - next[0] * here[1];
  }
  const doubled = Math.abs(sweep);
  const marks: string[] = [];
  for (const given of probes) {
    const [px, py] = spot(given, "sample spot");
    let verdict = "";
    for (let i = 0; i < ring.length && verdict === ""; i++) {
      const u = ring[i];
      const v = ring[(i + 1) % ring.length];
      const side = (v[0] - u[0]) * (py - u[1]) - (v[1] - u[1]) * (px - u[0]);
      if (
        side === 0 &&
        px >= Math.min(u[0], v[0]) &&
        px <= Math.max(u[0], v[0]) &&
        py >= Math.min(u[1], v[1]) &&
        py <= Math.max(u[1], v[1])
      ) {
        verdict = "edge";
      }
    }
    if (verdict === "") {
      let held = false;
      for (let i = 0; i < ring.length; i++) {
        const u = ring[i];
        const v = ring[(i + 1) % ring.length];
        if (u[1] > py !== v[1] > py) {
          const rise = v[1] - u[1];
          const left = (px - u[0]) * rise;
          const right = (py - u[1]) * (v[0] - u[0]);
          if (rise > 0 ? left < right : left > right) {
            held = !held;
          }
        }
      }
      verdict = held ? "inside" : "outside";
    }
    marks.push(verdict);
  }
  return { doubled: doubled + 0, marks };
}
