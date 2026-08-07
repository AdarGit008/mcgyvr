const MARKER = [86, 76, 84];

export function readVaultHeader(
  bytes: any,
): { version: number; size: number; sealed: boolean; packed: boolean; stamp: number } {
  if (!Array.isArray(bytes)) {
    throw new Error("bytes must be a list");
  }
  for (const byte of bytes) {
    if (typeof byte !== "number" || !Number.isInteger(byte) || byte < 0 || byte > 255) {
      throw new Error("every byte must be a whole number from 0 through 255");
    }
  }
  if (bytes.length < 4) {
    throw new Error("the run is too short to carry the marker and the edition");
  }
  for (let i = 0; i < MARKER.length; i++) {
    if (bytes[i] !== MARKER[i]) {
      throw new Error("the marker is not the one this reader knows");
    }
  }
  const version = bytes[3];
  if (version !== 1 && version !== 2) {
    throw new Error(`edition ${version} is not one this reader knows`);
  }
  const headerLength = version === 1 ? 7 : 11;
  if (bytes.length < headerLength) {
    throw new Error("the run ends inside the header");
  }
  const size = bytes[4] * 256 + bytes[5];
  const flags = bytes[6];
  if ((flags & ~3) !== 0) {
    throw new Error("a flag this reader does not know is raised");
  }
  let stamp = 0;
  if (version === 2) {
    stamp = ((bytes[7] * 256 + bytes[8]) * 256 + bytes[9]) * 256 + bytes[10];
  }
  if (bytes.length - headerLength !== size) {
    throw new Error("the body is not the length the header declares");
  }
  return {
    version,
    size,
    sealed: (flags & 1) === 1,
    packed: (flags & 2) === 2,
    stamp,
  };
}
