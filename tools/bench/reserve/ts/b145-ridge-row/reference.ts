/** One row of a transect plot: "#" where a station reaches the level. */
export function ridgeRow(heights: number[], level: number): string {
  if (!Array.isArray(heights)) {
    throw new Error("ridgeRow expects a list of elevations");
  }
  if (!Number.isInteger(level) || level < 1) {
    throw new Error("level must be a positive integer");
  }
  let row = "";
  for (const height of heights) {
    if (!Number.isInteger(height) || height < 0) throw new Error("every elevation must be a non-negative integer");
    row += height >= level ? "#" : ".";
  }
  return row;
}
