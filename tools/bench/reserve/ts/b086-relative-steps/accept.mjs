import assert from "node:assert/strict";
import { relativeSteps, splitAbsolute } from "./solution.ts";

assert.equal(
  relativeSteps("/srv/app", "/srv/static/logo.png"),
  "../static/logo.png",
  "climb once then descend",
);
assert.equal(relativeSteps("/data/sets/raw", "/data"), "../..", "pure climb to an ancestor");
assert.equal(relativeSteps("/home/kim", "/home/kim"), ".", "same directory is a dot");
assert.equal(relativeSteps("/", "/etc/motd"), "etc/motd", "descent from the root");
assert.equal(relativeSteps("/var/tmp", "/"), "../..", "climb all the way to the root");
assert.deepEqual(splitAbsolute("/usr/local/bin"), ["usr", "local", "bin"], "helper splits segments");
assert.deepEqual(splitAbsolute("/"), [], "helper yields nothing for the root");
assert.throws(() => relativeSteps(7, "/x"), Error, "non-string is rejected");
assert.throws(() => relativeSteps("srv/app", "/x"), Error, "relative origin is rejected");
assert.throws(() => relativeSteps("/a//b", "/x"), Error, "doubled slash is rejected");
assert.throws(() => relativeSteps("/a/b/", "/x"), Error, "trailing slash is rejected");
assert.throws(() => relativeSteps("/a/../b", "/x"), Error, "dot-dot segment is rejected");
console.log("ok");
