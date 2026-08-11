import assert from "node:assert/strict";
import { forkPaths } from "./solution.ts";

assert.deepEqual(forkPaths("src/main"), ["src/main"], "a forkless pattern names itself");
assert.deepEqual(forkPaths("src/{lib,app}/main"), ["src/lib/main", "src/app/main"], "one fork in the middle");
assert.deepEqual(forkPaths("{one}"), ["one"], "a fork of a single option");
assert.deepEqual(forkPaths("{a,b,c}"), ["a", "b", "c"], "options keep their written order");
assert.deepEqual(forkPaths("{a,b}/x"), ["a/x", "b/x"], "a fork may open the pattern");
assert.deepEqual(forkPaths("logs/{old,new}"), ["logs/old", "logs/new"], "a fork may close the pattern");
assert.deepEqual(forkPaths("s/{i,j}/{1,2}"), ["s/i/1", "s/i/2", "s/j/1", "s/j/2"], "an earlier fork varies slower");
assert.throws(() => forkPaths(42), Error, "a non-string pattern is rejected");
assert.throws(() => forkPaths(""), Error, "an empty pattern is rejected");
assert.throws(() => forkPaths("a//b"), Error, "an empty segment is rejected");
assert.throws(() => forkPaths("{a,}/x"), Error, "an empty option is rejected");
assert.throws(() => forkPaths("x{y}/z"), Error, "a brace inside a literal is rejected");
console.log("ok");
