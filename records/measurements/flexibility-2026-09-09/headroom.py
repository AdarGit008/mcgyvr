"""Q11 — the card headroom the geometry path needs, from Q4, Q10 and Q13.

**No arm recorded a prediction, and none had to.** ``vramfit.predict`` is
arithmetic on the GGUF header plus one measured constant, so every prediction
in this campaign can be recomputed from the compose file and the geometry that
was already on disk. What the arms contributed is the *measured* side.

The claim under test is not "``predict`` is accurate" but the one the module
rests on: **``C`` — everything on the card that is not expert weight — does not
move with ``--n-cpu-moe``**. `emit` probes it once and predicts every other
placement from it. If C drifts with the placement, every prediction but the
probe's own is wrong by that drift, and the headroom G1 asks for is exactly its
worst signed value.

Three groups have two or more distinct placements of one checkpoint on one rig,
which is what makes a drift visible at all:

* the 80B on srv2 at ``--n-cpu-moe`` 35, 36, 38, 40, 41  (Q10, n=2 each)
* Qwen3.6 on srv1 at 28, 29, 32                          (Q4 + Q1, n=2 each)
* Qwen3.6 on srv2 at 7, 20, 40                           (Q13, n=2 each)

Only *mapped* placements are read. Q5 and Q6 ran the unmapped compose under a
balloon, where the card figure is a different measurement.

``memory.used`` is card-wide, so every reading here is net of the rig's idle
baseline — 17 MiB on srv1, 1 MiB on srv2, both taken from the arm's own
``vram_idle_free_mib`` rather than assumed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/adaramir/claude/mcgyvr/src")

from mcgyvr.serving import vramfit  # noqa: E402

SCR = Path(__file__).resolve().parent
MIB = 1024 * 1024

#: Card totals, read from the rigs on 2026-09-10. Used only to turn an arm's
#: `vram_idle_free_mib` into the idle *used* baseline the constant is net of.
CARD_TOTAL_MIB = {"srv1": 5744, "srv2": 11912}

GEOM = {
    ("srv2", "Qwen3-Next-80B-A3B-Instruct-Q3_K_M"):
        SCR.parent / "ram-headroom-2026-09-09/qwen80b.geometry.json",
    ("srv1", "Qwen3.6-35B-A3B-UD-IQ3_XXS"):
        SCR / "emit/srv1-Qwen3.6-35B-A3B-UD-IQ3_XXS/Qwen3.6-35B-A3B-UD-IQ3_XXS.geometry.json",
    ("srv2", "Qwen3.6-35B-A3B-UD-IQ3_XXS"):
        SCR / "emit/srv2-Qwen3.6-35B-A3B-UD-IQ3_XXS/Qwen3.6-35B-A3B-UD-IQ3_XXS.geometry.json",
}

GROUPS = {
    ("srv2", "Qwen3-Next-80B-A3B-Instruct-Q3_K_M"): ["results-arms-q10-80b.json"],
    ("srv1", "Qwen3.6-35B-A3B-UD-IQ3_XXS"): ["results-q1-srv1.json", "results-q4q5q6-srv1.json"],
    ("srv2", "Qwen3.6-35B-A3B-UD-IQ3_XXS"): ["results-q13-srv2.json"],
}

#: Q5 and Q6 balloon the host and run `--load-mode none`; their card figure is
#: not a geometry-path prediction and is not read here.
SKIP = re.compile(r"^q[56]-")


def load_geometry(path: Path) -> dict:
    g = json.loads(path.read_text())
    return g[0] if isinstance(g, list) else g


def ncmoe_of(compose: Path) -> int | None:
    """`--n-cpu-moe` as the compose actually spells it, not as a label claims."""
    lines = compose.read_text().splitlines()
    for i, line in enumerate(lines[:-1]):
        if line.strip().strip("-").strip() == "-n-cpu-moe" or "--n-cpu-moe" in line:
            return int(lines[i + 1].strip().strip("'\"- "))
    return None


def arms_for(host: str, model: str) -> list[dict]:
    out = []
    for name in GROUPS[(host, model)]:
        for row in json.loads((SCR / name).read_text()):
            if row.get("failed") or SKIP.match(row["label"]):
                continue
            compose = Path(row["compose"])
            if model not in row.get("container", "") and model not in compose.read_text():
                continue
            n = ncmoe_of(compose)
            if n is None:
                continue
            idle_used = CARD_TOTAL_MIB[host] - row["vram_idle_free_mib"]
            out.append({
                "label": row["label"],
                "ncmoe": n,
                "measured_net_mib": row["vram_steady_used_mib"] - idle_used,
                "peak_net_mib": row["vram_peak_used_mib"] - idle_used,
            })
    return out


def main() -> None:
    report: dict = {"groups": [], "worst": None}
    worst: tuple[float, str] | None = None

    for (host, model), geom_path in GEOM.items():
        geom = load_geometry(geom_path)
        arms = arms_for(host, model)
        if not arms:
            continue
        for a in arms:
            a["experts_mib"] = vramfit.experts_on_card(geom, a["ncmoe"]) / MIB
            a["C_mib"] = a["measured_net_mib"] - a["experts_mib"]

        # `emit` probes C once. The probe here is the LOWEST placement in the
        # group -- the one a floor search reaches first -- and every other arm
        # is predicted from it, which is exactly what emit does in production.
        probe = min(arms, key=lambda a: a["ncmoe"])
        c_ref = int(round(probe["C_mib"] * MIB))

        rows = []
        for a in arms:
            predicted = vramfit.predict(geom, a["ncmoe"], c_ref) / MIB
            residual = a["measured_net_mib"] - predicted
            rows.append({**a, "predicted_mib": predicted, "residual_mib": residual})
            tag = f"{host} {model} ncmoe {a['ncmoe']} ({a['label']})"
            if worst is None or abs(residual) > abs(worst[0]):
                worst = (residual, tag)

        c_vals = [a["C_mib"] for a in arms]
        group = {
            "host": host,
            "model": model,
            "probe_arm": probe["label"],
            "probe_ncmoe": probe["ncmoe"],
            "C_probe_mib": probe["C_mib"],
            "C_min_mib": min(c_vals),
            "C_max_mib": max(c_vals),
            "C_spread_mib": max(c_vals) - min(c_vals),
            "arms": rows,
        }
        report["groups"].append(group)

        print(f"\n=== {host}  {model}")
        print(f"    C probed at ncmoe {probe['ncmoe']} = {probe['C_mib']:.2f} MiB;"
              f" C across the group spans {min(c_vals):.2f}..{max(c_vals):.2f}"
              f" ({max(c_vals) - min(c_vals):.2f} MiB)")
        for r in sorted(rows, key=lambda r: (r["ncmoe"], r["label"])):
            print(f"    ncmoe {r['ncmoe']:>2}  {r['label']:<22} "
                  f"predicted {r['predicted_mib']:8.2f}  measured {r['measured_net_mib']:6}  "
                  f"residual {r['residual_mib']:+8.2f} MiB")

    report["worst"] = {"residual_mib": worst[0], "at": worst[1]} if worst else None
    (SCR / "results-q11-headroom.json").write_text(json.dumps(report, indent=2))
    print(f"\nWORST SIGNED RESIDUAL: {worst[0]:+.2f} MiB at {worst[1]}")
    print(f"wrote {SCR / 'results-q11-headroom.json'}")


if __name__ == "__main__":
    main()
