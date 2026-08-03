/** One parsed semantic version: three numbers plus optional prerelease and build. */
export interface Semver {
  major: number;
  minor: number;
  patch: number;
  prerelease: string | null;
  build: string | null;
}

const PATTERN =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$/;

/** Parse MAJOR.MINOR.PATCH with optional -prerelease and +build. */
export function parseSemver(version: string): Semver {
  if (typeof version !== "string") {
    throw new Error(`version must be a string, got ${typeof version}`);
  }
  const match = PATTERN.exec(version);
  if (match === null) {
    throw new Error(`not a semantic version: ${version}`);
  }
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
    prerelease: match[4] ?? null,
    build: match[5] ?? null,
  };
}
