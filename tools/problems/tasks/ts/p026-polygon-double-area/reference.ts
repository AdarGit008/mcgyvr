export function polygonDoubleArea(vertices: number[][]): number {
  if (!Array.isArray(vertices) || vertices.length < 3) {
    throw new Error("a polygon needs at least three vertices");
  }
  for (const vertex of vertices) {
    if (
      !Array.isArray(vertex) ||
      vertex.length !== 2 ||
      !Number.isInteger(vertex[0]) ||
      !Number.isInteger(vertex[1])
    ) {
      throw new Error("each vertex must be a pair of two integers");
    }
  }
  for (let i = 0; i < vertices.length; i++) {
    const [ax, ay] = vertices[i];
    const [bx, by] = vertices[(i + 1) % vertices.length];
    if (ax === bx && ay === by) {
      throw new Error("adjacent vertices must be distinct");
    }
  }
  let doubled = 0;
  for (let i = 0; i < vertices.length; i++) {
    const [ax, ay] = vertices[i];
    const [bx, by] = vertices[(i + 1) % vertices.length];
    doubled += ax * by - bx * ay;
  }
  return Math.abs(doubled);
}
