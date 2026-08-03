#!/usr/bin/env python3
"""Count 3, the JS/TypeScript half — a candidate resolver over code that shipped.

    python tools/reach/count3_jsts.py --run
    python tools/reach/count3_jsts.py --summarise

#129 measured a candidate resolver for Python and could not measure one for
JS/TS, because none had been identified (``count3.py``: "Two of three frames, and
the JS/TS half of the launch languages has no candidate measured"). #133 is that
gap. This is its measurement, over the third frame of the same pinned corpus.

**The candidate is the TypeScript compiler, driven through its own API** —
``ts.createProgram`` followed by ``getSemanticDiagnostics``, with the verdict
read off the diagnostic code. It is here because the survey found nothing
lighter that answers the question at all; what was rejected and why is in
``records/measurements/reach-jsts-2026-08-03/README.md``. It is emphatically not
a like-for-like swap for ghostcall: ghostcall is four stdlib-only files resolving
against a live interpreter, and this is a 4.4 MB type-checker resolving against a
type graph. That difference is the finding, not an inconvenience in reporting it.

**Counted the same way as Counts 1-3** — same corpus, per change, restricted to
the lines the change added, with the whole-file rate recorded beside it. A flag
on a line the change did not touch is not a verdict the rung would render.

**Why a flag counts as a false positive, and the limit of that.** Identical to
``count3.py``: every measured file shipped through a declared, human-gated check,
so a flag on it is a *presumptive* false positive, and each one is written out
with its path and line so the presumption can be checked by hand.

**The denominator does not transfer, and pretending it does would be the error.**
CLM-0009's 358 is *resolved call chains*, because ghostcall resolves calls. A
TypeScript diagnostic lands on any expression — a type reference, a property
access in a type position, an identifier in a declaration — and immer's accepted
changes are heavily type-level, so several of them contain no call expression at
all. Three denominators are therefore recorded per change (call expressions,
property accesses, identifiers), and the rate is reported against each rather
than against one picked after the fact.

**Three arms, because "what it needs to run" is a number here, not an adjective.**
ghostcall's cost was established by reading ``check()``; this candidate's cost has
to be measured, because the whole question is what happens to its verdicts when
the environment is not fully provisioned:

- ``target-ts`` — the frame's own ``node_modules`` installed, resolving with the
  frame's own ``typescript``. Both the environment and the checker are the
  target's, which is the arrangement ADR-0006 describes.
- ``staged-ts`` — the frame's ``node_modules`` installed, resolving with a
  version-pinned ``typescript`` staged into the container the way ADR-0011 stages
  a resolver. The environment is the target's, the checker is ours. This is the
  arm that tests version drift.
- ``bare`` — no ``node_modules`` at all, staged checker. This is what a rung that
  declined to provision the target would actually see.

**The environment/verdict split is kept, because it is the difference between a
wrong rung and a vacuous one.** ``count3.py`` counts ``module_missing``
separately from ``hallucinated`` on the grounds that failing to import a root is
an environment outcome. TypeScript spends distinct codes on the same
distinction — 2307 and 2580 name a missing module or a missing ``@types``
package, while 2339 and 2304 assert that a named thing does not exist — so the
same split is available here and is applied at :data:`EXISTENCE` /
:data:`ENVIRONMENT`. The table is not taken from documentation: the driver
extracts each code's message template from the bytes of the resolver it loaded,
and writes it beside the rows.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import frames
from frames import FrameContainer, ReachError

OUT_DIR = frames.REPO / "records" / "measurements" / "reach-jsts-2026-08-03"
ROWS = OUT_DIR / "count3-jsts-falsepos.jsonl"
CODE_TABLE = OUT_DIR / "diagnostic-codes.json"
CONTROL = OUT_DIR / "positive-control.json"
CLONES = Path("/tmp/reach-clones")
BARE_CLONES = Path("/tmp/reach-clones-bare")
SCRATCH = Path("/tmp/reach-jsts")

JS_FRAME = "immerjs/immer"

# The staged resolver, pinned by the sha512 of its published tarball and
# verified in the container before it is unpacked. ADR-0011's rule: a resolver
# that is staged rather than installed still has to be the bytes that were
# measured, and the check fails closed.
STAGED_TS_VERSION = "5.9.3"
STAGED_TS_TARBALL = (
    f"https://registry.npmjs.org/typescript/-/typescript-{STAGED_TS_VERSION}.tgz"
)
STAGED_TS_INTEGRITY = (
    "sha512-jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4"
    "vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw=="
)

# A verdict that a named thing does not exist — the class the rung would act on,
# and therefore the class a false positive can belong to.
EXISTENCE = frozenset({2304, 2305, 2339, 2551, 2552, 2694, 2724})
# Not a verdict about the code: the resolver could not see a module, a types
# package or a lib. The `module_missing` analogue, counted separately and
# loudly, because a rung whose every lookup fails flags nothing and passes
# everything.
ENVIRONMENT = frozenset({2307, 2318, 2580, 2583, 2688, 2792})

ARMS = ("target-ts", "staged-ts", "bare")

# Runs inside the container. Kept as a file rather than a -c string so a failure
# has a traceback with line numbers, for the same reason count3.py does it.
_DRIVER = r"""
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const require = createRequire("/work/");
const ts = require(process.argv[2]);
const targets = JSON.parse(readFileSync(process.argv[3], "utf8"));
const repo = "/work";

// The repository's own tsconfig, read the way tsc reads it — the compiler
// options are the target's, which is the half of ADR-0006 that survives here.
const configPath = ts.findConfigFile(repo, ts.sys.fileExists, "tsconfig.json");
const configFile = configPath
  ? ts.readConfigFile(configPath, ts.sys.readFile)
  : { config: {}, error: undefined };
const parsed = ts.parseJsonConfigFileContent(configFile.config ?? {}, ts.sys, repo);

// Every measured file must be in the program or its lines go unjudged: immer's
// tsconfig names four `files` entries and reaches the rest by import, which is
// not guaranteed to cover a file some change touched. Adding the targets is a
// deliberate divergence from `tsc -p .` and is recorded as one.
const rootNames = Array.from(
  new Set([...parsed.fileNames, ...targets.map((t) => path.resolve(repo, t))])
);
const program = ts.createProgram({
  rootNames,
  options: { ...parsed.options, noEmit: true },
});

const diagnostics = [];
for (const d of program.getSemanticDiagnostics()) {
  const file = d.file ? path.relative(repo, d.file.fileName) : null;
  let line = null;
  if (d.file && typeof d.start === "number") {
    line = d.file.getLineAndCharacterOfPosition(d.start).line + 1;
  }
  diagnostics.push({
    code: d.code,
    category: d.category,
    file,
    line,
    message: ts.flattenDiagnosticMessageText(d.messageText, " "),
  });
}

const sites = {};
for (const t of targets) {
  const sf = program.getSourceFile(path.resolve(repo, t));
  if (!sf) {
    sites[t] = null; // not in the program — recorded, never a silent zero
    continue;
  }
  const perLine = { calls: {}, properties: {}, identifiers: {} };
  const bump = (bucket, node) => {
    const line = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
    perLine[bucket][line] = (perLine[bucket][line] || 0) + 1;
  };
  const walk = (node) => {
    if (ts.isCallExpression(node) || ts.isNewExpression(node)) bump("calls", node);
    if (ts.isPropertyAccessExpression(node)) bump("properties", node);
    if (ts.isIdentifier(node)) bump("identifiers", node);
    ts.forEachChild(node, walk);
  };
  walk(sf);
  sites[t] = perLine;
}

// The classification table, read out of the bytes of the resolver that produced
// the verdicts above rather than from documentation about it.
const wanted = JSON.parse(process.argv[5]);
const pkg = require.resolve(process.argv[2] + "/package.json");
const lib = readFileSync(
  path.join(path.dirname(pkg), "lib/typescript.js"),
  "utf8"
);
const re =
  /(\w+):\s*diag\((\d+),\s*(\d+)\s*\/\*[^*]*\*\/,\s*"([^"]+)",\s*"((?:[^"\\]|\\.)*)"/g;
const table = {};
let m;
while ((m = re.exec(lib))) {
  const code = Number(m[2]);
  if (wanted.includes(code)) table[code] = { key: m[1], message: m[5] };
}

writeFileSync(
  process.argv[4],
  JSON.stringify({
    typescript_version: ts.version,
    config_path: configPath ? path.relative(repo, configPath) : null,
    config_errors: parsed.errors.map((e) =>
      ts.flattenDiagnosticMessageText(e.messageText, " ")
    ),
    root_count: rootNames.length,
    diagnostics,
    sites,
    code_table: table,
  })
);
"""

_STAGE = f"""
set -e
mkdir -p /cache/staged
cd /cache/staged
if [ ! -d node_modules/typescript ]; then
  node -e '
    const fs=require("fs"), c=require("crypto");
    fetch("{STAGED_TS_TARBALL}").then(r=>r.arrayBuffer()).then(b=>{{
      const buf=Buffer.from(b);
      const got="sha512-"+c.createHash("sha512").update(buf).digest("base64");
      if (got !== "{STAGED_TS_INTEGRITY}") {{
        console.error("staged resolver integrity mismatch: "+got);
        process.exit(1);
      }}
      fs.writeFileSync("/cache/typescript.tgz", buf);
    }});
  '
  npm install --no-save --silent /cache/typescript.tgz
fi
node -e 'console.log(require("/cache/staged/node_modules/typescript").version)'
"""


def _frame() -> Mapping:
    for frame in frames.load_corpus()["frames"]:
        if frame["repo"] == JS_FRAME:
            return frame
    raise ReachError(f"{JS_FRAME} is not in the corpus")


def bare_clone(source: Path, workdir: Path) -> Path:
    """A second working copy that never gets ``node_modules``.

    The ``bare`` arm needs a tree with no install in it, and the provisioned
    clone cannot be it: deleting ``node_modules`` there would force a reinstall
    for every commit of the other two arms. Cloned from the local copy rather
    than refetched, so both arms are the same objects at the same commits.
    """
    dest = workdir / JS_FRAME.replace("/", "_")
    if dest.exists():
        return dest
    workdir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--quiet", "--no-hardlinks", str(source), str(dest)],
        check=True,
        capture_output=True,
    )
    return dest


def _digest(clone: Path, runtime: frames.FrameRuntime) -> str:
    import hashlib

    digest = hashlib.sha256()
    for name in runtime.manifests:
        path = clone / name
        digest.update(name.encode())
        digest.update(path.read_bytes() if path.is_file() else b"<absent>")
    return digest.hexdigest()


def _run_arm(
    container: FrameContainer,
    arm: str,
    resolver: str,
    out: Path,
    env: Mapping[str, str],
) -> dict:
    result = out / f"{arm}.json"
    result.unlink(missing_ok=True)
    codes = json.dumps(sorted(EXISTENCE | ENVIRONMENT))
    code, output = container.run(
        f"node /cache/driver.mjs {resolver} /cache/targets.json /out/{arm}.json "
        f"'{codes}'",
        env,
    )
    if not result.is_file():
        return {"error": f"driver produced no output (exit {code}): {output[-400:]}"}
    return json.loads(result.read_text())


def _row(
    frame: Mapping,
    change: Mapping,
    arm: str,
    added: Mapping[str, frozenset[int]],
    report: Mapping,
    environment: str,
) -> dict:
    """One change under one arm.

    ``environment`` records what the tree the resolver saw actually was, which
    matters when an install fails: the ``staged-ts`` arm still produces verdicts
    against whatever ``node_modules`` the previous commit left behind, and a
    verdict read against a mismatched environment is not evidence about this
    commit. Recording it is what keeps that out of the pooled rate.
    """
    if "error" in report:
        return {
            "frame": frame["repo"],
            "commit": change["commit"],
            "date": change["date"],
            "arm": arm,
            "measured": False,
            "environment": environment,
            "note": report["error"],
        }

    totals = dict.fromkeys(
        (
            "calls_in_files",
            "calls_on_added_lines",
            "properties_in_files",
            "properties_on_added_lines",
            "identifiers_in_files",
            "identifiers_on_added_lines",
            "existence_in_files",
            "existence_on_added_lines",
            "environment_in_files",
            "environment_on_added_lines",
            "other_in_files",
            "other_on_added_lines",
        ),
        0,
    )

    missing_from_program = []
    for path, per_line in report["sites"].items():
        if per_line is None:
            missing_from_program.append(path)
            continue
        lines = added.get(path, frozenset())
        for bucket in ("calls", "properties", "identifiers"):
            for line_text, count in per_line[bucket].items():
                totals[f"{bucket}_in_files"] += count
                if int(line_text) in lines:
                    totals[f"{bucket}_on_added_lines"] += count

    flags: list[dict] = []
    for diagnostic in report["diagnostics"]:
        path = diagnostic["file"]
        # Only the frame's own source is the rung's territory. A diagnostic
        # inside node_modules or a test tree is not a verdict about the change,
        # and folding it in would inflate every arm by the same ambient noise.
        if path is None or not frames.matches(path, frame["source_glob"]):
            continue
        code = diagnostic["code"]
        klass = (
            "existence"
            if code in EXISTENCE
            else "environment"
            if code in ENVIRONMENT
            else "other"
        )
        on_added = diagnostic["line"] in added.get(path, frozenset())
        totals[f"{klass}_in_files"] += 1
        if on_added:
            totals[f"{klass}_on_added_lines"] += 1
        # EVERY diagnostic in the frame's source is written out, whatever its
        # class and whether or not it sits on an added line, for count3.py's
        # reason: the flags off the added lines are the only evidence this
        # corpus yields about what the resolver actually objects to, and a bare
        # total asks to be taken on trust. `other` is included because the
        # difference between the arms lives there — a compiler version the
        # repository did not pin reports type errors on code that shipped, and
        # a total with no diagnostics behind it could not show that.
        flags.append(
            {
                "path": path,
                "line": diagnostic["line"],
                "code": code,
                "class": klass,
                "message": diagnostic["message"],
                "on_added_line": on_added,
            }
        )

    return {
        "frame": frame["repo"],
        "commit": change["commit"],
        "date": change["date"],
        "arm": arm,
        "measured": True,
        "environment": environment,
        "resolver_version": report["typescript_version"],
        "added_source_lines": change["added_source_lines"],
        "files": len(report["sites"]),
        "files_missing_from_program": missing_from_program,
        "config_path": report["config_path"],
        "config_errors": report["config_errors"],
        **totals,
        "flags": flags,
    }


def measure(frame: Mapping) -> list[dict]:
    runtime = frames.FRAME_RUNTIME[frame["repo"]]
    clone = frames.prepare_clone(frame, CLONES)
    bare = bare_clone(clone, BARE_CLONES)
    tag = "reach-immer"
    frames.build_image(runtime, tag)

    slug = frame["repo"].replace("/", "_")
    cache = SCRATCH / "cache" / slug
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "driver.mjs").write_text(_DRIVER, encoding="utf-8")
    targets_path = cache / "targets.json"

    env = dict(runtime.env)
    rows: list[dict] = []
    code_table: dict = {}

    for label, tree, arm_names in (
        ("provisioned", clone, ("target-ts", "staged-ts")),
        ("bare", bare, ("bare",)),
    ):
        out = SCRATCH / "out" / label
        out.mkdir(parents=True, exist_ok=True)
        print(f"{frame['repo']} — {label} pass", file=sys.stderr)
        with FrameContainer(tag, tree, out, cache) as container:
            code, output = container.run(_STAGE, env)
            if code != 0:
                raise ReachError(f"could not stage the resolver: {output[-600:]}")

            provisioned: str | None = None
            for index, change in enumerate(frame["changes"], start=1):
                commit = change["commit"]
                keep = runtime.keep if label == "provisioned" else ()
                frames.checkout(tree, commit, keep)
                added = frames.added_lines(
                    tree, commit, frame["unit"], frame["source_glob"]
                )
                install_failed: str | None = None
                if label == "provisioned":
                    digest = _digest(tree, runtime)
                    if digest != provisioned:
                        code, output = container.run(runtime.provision, env)
                        provisioned = digest if code == 0 else None
                        if code != 0:
                            install_failed = (
                                f"provision failed (exit {code}): {output[-300:]}"
                            )

                targets_path.write_text(json.dumps(sorted(added)), encoding="utf-8")
                if label == "bare":
                    environment = "none"
                elif install_failed:
                    environment = "stale"
                else:
                    environment = "installed"

                for arm in arm_names:
                    if arm == "target-ts":
                        resolver = "/work/node_modules/typescript"
                        if install_failed:
                            rows.append(
                                _row(
                                    frame,
                                    change,
                                    arm,
                                    added,
                                    {"error": install_failed},
                                    environment,
                                )
                            )
                            continue
                    else:
                        resolver = "/cache/staged/node_modules/typescript"
                    report = _run_arm(container, arm, resolver, out, env)
                    if "code_table" in report:
                        code_table.update(report["code_table"])
                    rows.append(_row(frame, change, arm, added, report, environment))
                    last = rows[-1]
                    if last["measured"]:
                        print(
                            f"  [{index:>2}/{len(frame['changes'])}] {commit[:9]} "
                            f"{arm:<10} existence {last['existence_on_added_lines']}"
                            f"/{last['existence_in_files']:<3} "
                            f"environment {last['environment_on_added_lines']}"
                            f"/{last['environment_in_files']}",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            f"  [{index:>2}/{len(frame['changes'])}] {commit[:9]} "
                            f"{arm:<10} NOT MEASURED",
                            file=sys.stderr,
                        )

    if code_table:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        CODE_TABLE.write_text(
            json.dumps(
                {
                    "_note": (
                        "Extracted by the driver from lib/typescript.js of the "
                        "resolver that produced the verdicts, so the "
                        "classification and the measurement come from the same "
                        "bytes. `class` is this repository's assignment, not "
                        "TypeScript's."
                    ),
                    "resolver": f"typescript@{STAGED_TS_VERSION}",
                    "tarball": STAGED_TS_TARBALL,
                    "integrity": STAGED_TS_INTEGRITY,
                    "codes": {
                        code: {
                            **entry,
                            "class": (
                                "existence" if int(code) in EXISTENCE else "environment"
                            ),
                        }
                        for code, entry in sorted(
                            code_table.items(), key=lambda kv: int(kv[0])
                        )
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return rows


# A file of deliberately non-existent references, one per existence code the
# count is willing to charge. It exists because the measurement's headline is a
# zero, and a zero from an instrument that never fires is not a result. Each
# entry pairs a line of TypeScript with the code it is expected to provoke; the
# control passes only if every one of them is actually provoked, in every arm.
_PROBE_NAME = "src/__mcgyvr_probe_133.ts"
_PROBE = """// Written by count3_jsts.py --control, then deleted. Never committed.
import {produce} from "./immer"
import {nonExistentExport133} from "./immer"

export function probe(s: string) {
    nonExistentGlobalFunction133()      // expect 2304: Cannot find name
    s.nonExistentStringMethod133()      // expect 2339: Property does not exist
    s.lenght                            // expect 2551: ... Did you mean 'length'?
    nonExistentExport133()              // expect 2305: no exported member
    return produce({a: 1}, (d: any) => {d.a = 2})   // correct: must NOT be flagged
}
"""
_PROBE_EXPECT = frozenset({2304, 2339, 2551, 2305})


def control(frame: Mapping) -> dict:
    """Fire the resolver at references that certainly do not exist.

    The rate this tool reports is zero in every arm. That is only evidence about
    the resolver if the resolver would have said otherwise given something to
    object to — the failure mode ``count3.py`` names for ``module_missing`` (a
    rung whose lookups all fail flags nothing and passes everything) applies to
    a whole measurement, not just to one status. This is the check that
    separates the two readings, and it is run in each arm because the ``bare``
    arm is exactly where a silent resolver would be most plausible.
    """
    runtime = frames.FRAME_RUNTIME[frame["repo"]]
    clone = frames.prepare_clone(frame, CLONES)
    bare = bare_clone(clone, BARE_CLONES)
    tag = "reach-immer"
    frames.build_image(runtime, tag)

    cache = SCRATCH / "cache" / frame["repo"].replace("/", "_")
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "driver.mjs").write_text(_DRIVER, encoding="utf-8")
    (cache / "targets.json").write_text(json.dumps([_PROBE_NAME]), encoding="utf-8")
    env = dict(runtime.env)
    pinned = frame["pinned_commit"]
    results: dict[str, dict] = {}

    for label, tree, arm_names in (
        ("provisioned", clone, ("target-ts", "staged-ts")),
        ("bare", bare, ("bare",)),
    ):
        out = SCRATCH / "out" / f"control-{label}"
        out.mkdir(parents=True, exist_ok=True)
        frames.checkout(tree, pinned, runtime.keep if label == "provisioned" else ())
        probe = tree / _PROBE_NAME
        probe.write_text(_PROBE, encoding="utf-8")
        try:
            with FrameContainer(tag, tree, out, cache) as container:
                code, output = container.run(_STAGE, env)
                if code != 0:
                    raise ReachError(f"could not stage the resolver: {output[-600:]}")
                if label == "provisioned":
                    container.run(runtime.provision, env)
                for arm in arm_names:
                    resolver = (
                        "/work/node_modules/typescript"
                        if arm == "target-ts"
                        else "/cache/staged/node_modules/typescript"
                    )
                    report = _run_arm(container, arm, resolver, out, env)
                    hits = [
                        {
                            "line": d["line"],
                            "code": d["code"],
                            "message": d["message"],
                        }
                        for d in report.get("diagnostics", [])
                        if d["file"] == _PROBE_NAME
                    ]
                    codes = {h["code"] for h in hits}
                    results[arm] = {
                        "resolver_version": report.get("typescript_version"),
                        "expected_codes": sorted(_PROBE_EXPECT),
                        "codes_seen": sorted(codes),
                        "missing": sorted(_PROBE_EXPECT - codes),
                        "fires": codes >= _PROBE_EXPECT,
                        "diagnostics": hits,
                    }
        finally:
            probe.unlink(missing_ok=True)

    return {
        "_note": (
            "The zero this measurement reports is a property of the code "
            "measured, not of a silent instrument: given references that do not "
            "exist, on the same frame at the same commit through the same "
            "driver, the resolver flags every one of them in every arm. The "
            "probe file is written, measured and deleted; it is never committed "
            "and is not part of any counted change."
        ),
        "frame": frame["repo"],
        "commit": pinned,
        "probe": _PROBE,
        "arms": results,
    }


def summarise(rows: list[dict]) -> dict:
    keys = (
        "calls_in_files",
        "calls_on_added_lines",
        "properties_in_files",
        "properties_on_added_lines",
        "identifiers_in_files",
        "identifiers_on_added_lines",
        "existence_in_files",
        "existence_on_added_lines",
        "environment_in_files",
        "environment_on_added_lines",
        "other_in_files",
        "other_on_added_lines",
    )
    by_arm: dict[str, dict] = {}
    sites: dict[str, dict[str, set]] = {}
    for row in rows:
        arm = by_arm.setdefault(
            row["arm"],
            {
                "changes": 0,
                "measured": 0,
                "environments": {},
                "flags": [],
                **dict.fromkeys(keys, 0),
            },
        )
        arm["changes"] += 1
        if not row.get("measured"):
            continue
        arm["measured"] += 1
        environment = row.get("environment", "unknown")
        arm["environments"][environment] = arm["environments"].get(environment, 0) + 1
        for key in keys:
            arm[key] += row[key]
        arm["flags"].extend(
            {**f, "commit": row["commit"][:9]}
            for f in row["flags"]
            if f["on_added_line"] and f["class"] != "other"
        )
        # A site touched by two changes is counted twice in the totals above —
        # the same double-count CLM-0009 had to unpick by hand, which is why the
        # deduplicated figure is computed here rather than left to the reader.
        for flag in row["flags"]:
            sites.setdefault(row["arm"], {}).setdefault(flag["class"], set()).add(
                (flag["code"], flag["path"], flag["line"])
            )

    for name, arm in by_arm.items():
        arm["distinct_sites"] = {
            klass: len(found) for klass, found in sorted(sites.get(name, {}).items())
        }
        for bucket in ("calls", "properties", "identifiers"):
            denominator = arm[f"{bucket}_on_added_lines"]
            arm[f"existence_per_100_{bucket}_on_added_lines"] = (
                round(100 * arm["existence_on_added_lines"] / denominator, 3)
                if denominator
                else None
            )
    return by_arm


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--summarise", action="store_true")
    parser.add_argument("--control", action="store_true")
    args = parser.parse_args()
    if sum((args.run, args.summarise, args.control)) != 1:
        parser.error("pass exactly one of --run / --summarise / --control")

    if args.summarise:
        rows = [json.loads(line) for line in ROWS.read_text().splitlines() if line]
        print(json.dumps(summarise(rows), indent=2, sort_keys=True))
        return 0

    if args.control:
        report = control(_frame())
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        CONTROL.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        for arm, result in sorted(report["arms"].items()):
            state = "FIRES" if result["fires"] else f"SILENT on {result['missing']}"
            print(f"{arm:<10} {state}  codes={result['codes_seen']}", file=sys.stderr)
        return 0 if all(a["fires"] for a in report["arms"].values()) else 1

    rows = measure(_frame())
    frames.write_jsonl(ROWS, rows)
    print(json.dumps(summarise(rows), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
