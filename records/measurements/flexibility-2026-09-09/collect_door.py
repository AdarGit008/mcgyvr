"""Every `up after` the door itself printed, per arm.

A second, independent clock on every wake in this campaign. The door times
`serve-up: <container> :<port> up after <t>s` from the moment `docker compose
up -d` returns, polling its services in the order the compose file lists them —
so for a pair the second figure is "how much longer after the first", not that
unit's own load. `StartedAt` is the other clock and the two disagree when a
container restarts; both are recorded rather than one being preferred.
"""
import json, re, sys
from pathlib import Path
LOGS = Path(__file__).resolve().parent / "logs"
PAT = re.compile(r"serve-up: (\S+) :(\d+) up after ([\d.]+)s")
out = {}
for p in sorted(LOGS.glob("door-up-*.log")):
    hits = [{"container": m.group(1), "port": int(m.group(2)), "up_after_s": float(m.group(3))}
            for m in PAT.finditer(p.read_text())]
    if hits:
        out[p.name[len("door-up-"):-len("-up.log")] if p.name.endswith("-up.log") else p.name] = hits
Path(LOGS.parent / "door-up-after.json").write_text(json.dumps(out, indent=2))
for k, v in out.items():
    print(f"{k:34s} " + "  ".join(f"{h['port']}:{h['up_after_s']:.1f}s" for h in v)
          + f"   sum={sum(h['up_after_s'] for h in v):.1f}s")
