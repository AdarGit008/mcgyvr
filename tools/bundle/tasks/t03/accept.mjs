import assert from "node:assert/strict";
import { parseSemver } from "./solution.ts";

assert.deepEqual(parseSemver("1.2.3"), {
  major: 1, minor: 2, patch: 3, prerelease: null, build: null,
}, "plain version");
assert.deepEqual(parseSemver("0.0.0"), {
  major: 0, minor: 0, patch: 0, prerelease: null, build: null,
}, "all zeroes");
assert.deepEqual(parseSemver("1.2.3-alpha.1"), {
  major: 1, minor: 2, patch: 3, prerelease: "alpha.1", build: null,
}, "prerelease");
assert.deepEqual(parseSemver("1.2.3+build.5"), {
  major: 1, minor: 2, patch: 3, prerelease: null, build: "build.5",
}, "build metadata");
assert.deepEqual(parseSemver("10.20.30-rc.1+exp.sha.5114f85"), {
  major: 10, minor: 20, patch: 30, prerelease: "rc.1", build: "exp.sha.5114f85",
}, "prerelease and build together");

const parsed = parseSemver("1.2.3");
assert.equal(typeof parsed.major, "number", "numeric parts are numbers, not strings");

for (const bad of ["1.2", "1.2.3.4", "01.2.3", "1.2.x", "", "v1.2.3", "1.2.-3"]) {
  assert.throws(() => parseSemver(bad), Error, `rejects ${JSON.stringify(bad)}`);
}
