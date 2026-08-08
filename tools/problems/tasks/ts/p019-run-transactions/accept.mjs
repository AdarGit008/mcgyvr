import assert from "node:assert/strict";
import { runTransactions } from "./solution.ts";

assert.deepEqual(runTransactions(["set a 1"]), { a: "1" }, "plain set");
assert.deepEqual(runTransactions(["set a 1", "set a 2"]), { a: "2" }, "later set wins");
assert.deepEqual(
  runTransactions(["begin", "set a 1", "commit"]),
  { a: "1" },
  "committed change lands",
);
assert.deepEqual(
  runTransactions(["begin", "set a 1", "rollback"]),
  {},
  "rolled-back change vanishes",
);
assert.deepEqual(
  runTransactions(["set a 1", "begin", "set a 2", "begin", "set a 3", "rollback", "commit"]),
  { a: "2" },
  "inner rollback spares the middle value",
);
assert.deepEqual(
  runTransactions(["begin", "set a 1", "begin", "set b 2", "commit", "rollback"]),
  {},
  "outer rollback swallows an inner commit",
);
assert.deepEqual(
  runTransactions(["set a 1", "begin", "unset a", "commit"]),
  {},
  "a committed removal removes",
);
assert.deepEqual(
  runTransactions(["set a 1", "begin", "unset a", "rollback"]),
  { a: "1" },
  "a rolled-back removal restores",
);
assert.deepEqual(
  runTransactions(["set a 1", "begin", "begin", "unset a", "commit", "commit"]),
  {},
  "a removal survives two commits",
);
assert.deepEqual(runTransactions(["unset ghost"]), {}, "removing an absent key is fine");
assert.throws(() => runTransactions(["commit"]), Error, "bare commit rejected");
assert.throws(() => runTransactions(["rollback"]), Error, "bare rollback rejected");
assert.throws(
  () => runTransactions(["begin", "set a 1"]),
  Error,
  "still-open transaction rejected",
);
assert.throws(() => runTransactions(["set a"]), Error, "set missing its value rejected");
assert.throws(() => runTransactions(["frob x"]), Error, "unknown verb rejected");
console.log("ok");
