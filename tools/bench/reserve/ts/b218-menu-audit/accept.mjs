import assert from "node:assert/strict";
import { auditMenu } from "./solution.ts";

const leaf = (label) => ({ label, items: [] });
assert.deepEqual(auditMenu({ label: "menu", items: [{ label: "drinks", items: [leaf("tea")] }] }, 3), [], "a tidy menu earns no complaints");
assert.deepEqual(auditMenu({ label: "menu", items: [leaf("  ")] }, 3), ["menu >   : blank label"], "a label of nothing but spaces is complained about");
assert.deepEqual(auditMenu({ label: "menu", items: [leaf("tea"), leaf("tea")] }, 3), ["menu > tea: duplicate"], "only the later of two identical labels is complained about");
assert.deepEqual(auditMenu({ label: "menu", items: [{ label: "drinks", items: [leaf("tea")] }] }, 1), ["menu > drinks > tea: too deep"], "a node below the allowed depth is complained about");
assert.deepEqual(auditMenu({ label: "menu", items: [leaf("tea"), leaf("tea")] }, 0), ["menu > tea: too deep", "menu > tea: duplicate", "menu > tea: too deep"], "a node's complaints come in their fixed order, node by node");
assert.deepEqual(auditMenu(leaf("menu"), 0), [], "a root on its own is neither a duplicate nor too deep");
assert.throws(() => auditMenu(leaf("menu"), -1), Error, "a negative maxDepth is rejected");
console.log("ok");
