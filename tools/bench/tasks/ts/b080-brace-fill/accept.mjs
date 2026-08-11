import assert from "node:assert/strict";
import { fillTemplate } from "./solution.ts";

assert.equal(fillTemplate("hi {who}", { who: "crew" }), "hi crew", "a placeholder is replaced");
assert.equal(fillTemplate("{p}{p}!", { p: "go" }), "gogo!", "adjacent and repeated placeholders");
assert.equal(fillTemplate("plain text", {}), "plain text", "text without placeholders is unchanged");
assert.equal(fillTemplate("} {n} }", { n: "q" }), "} q }", "a closing brace outside a placeholder is literal");
assert.throws(() => fillTemplate("tail {open", {}), Error, "an unterminated placeholder is rejected");
assert.throws(() => fillTemplate("{}", {}), Error, "an empty name is rejected");
assert.throws(() => fillTemplate("{a-b}", {}), Error, "a bad character in a name is rejected");
assert.throws(() => fillTemplate("{ghost}", {}), Error, "an unknown name is rejected");
assert.throws(() => fillTemplate(9, {}), Error, "a non-string template is rejected");
console.log("ok");
