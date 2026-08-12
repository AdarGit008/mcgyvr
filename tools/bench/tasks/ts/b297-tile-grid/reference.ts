export function tilesAcross(length: number, tile: number): number {
  return Math.ceil(length / tile);
}

export function tilesNeeded(
  width: number,
  height: number,
  tile: number,
  spare: number,
): number {
  const plain = tilesAcross(width, tile) * tilesAcross(height, tile);
  return Math.ceil((plain * (100 + spare)) / 100);
}
