import assert from "node:assert/strict";
import { cutRoll } from "./solution.ts";

assert.deepEqual(cutRoll(4, [[2, 5]]), { takings: 10, pieces: [2, 2] }, "a roll is filled with as many paying pieces as it holds");
assert.deepEqual(cutRoll(5, [[3, 7]]), { takings: 7, pieces: [3] }, "metres no piece can use are left as scrap");
assert.deepEqual(cutRoll(2, [[1, 3], [2, 6]]), { takings: 6, pieces: [2] }, "a tie in takings goes to the longer piece");
assert.deepEqual(cutRoll(7, [[3, 8], [4, 9]]), { takings: 17, pieces: [4, 3] }, "mixed pieces beat repeating the best-paying one");
assert.deepEqual(cutRoll(0, [[2, 5]]), { takings: 0, pieces: [] }, "a roll of no metres fetches nothing");
assert.deepEqual(cutRoll(2, [[5, 9]]), { takings: 0, pieces: [] }, "a roll no piece fits fetches nothing");
assert.throws(() => cutRoll(-1, [[2, 5]]), Error, "a negative roll length is rejected");
console.log("ok");
