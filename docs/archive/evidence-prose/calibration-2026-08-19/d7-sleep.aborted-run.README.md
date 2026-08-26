# Aborted run — 2026-08-19, phase 1 of 3

`d7-sleep.aborted-run.jsonl` and `d7-campaign.aborted-run.log` are the partial
output of a D7 campaign that was launched and then stopped by the owner ~18
minutes in, during phase 1 (sleep). Phases 2 (survey) and 3 (ramp) never ran.

They are renamed off the live paths on purpose: `calibrate.py --resume` keys on
`d7-sleep.jsonl`, and a fresh campaign must not inherit these records. The plan
is to restart from scratch once the #286 review fixes are in, not to resume.

## What was measured before the stop

Three records. Sleep-on-idle does not actually free VRAM on either rig, and the
endpoint reports that it did:

| cell | awake | asleep | freed | actually_freed | endpoint_lied |
|---|---|---|---|---|---|
| srv1/control_no_flag | 4916 | 4914 | 2 | False | True |
| srv1/enabled | — | — | — | — | — |
| srv2/control_no_flag | 10197 | 10177 | 20 | False | True |

`srv1/enabled` is all-null: it was the cell in flight when the run was stopped.
The `srv2/enabled` cell was never reached.

## Cleanup that the stop did not do

Killing the driver orphaned srv2's vLLM server (`vllm serve
Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ --enable-sleep-mode`, pid 436563), which
held 11,078 MiB until it was killed by hand. It runs as **root**, so SIGTERM
from `adaramir` was silently refused and it took `sudo kill -9`. Both rigs read
1 MiB afterwards. A launcher that cannot signal its own servers is a defect in
the interrupt path, not a property of this run.

## The driver log, verbatim

`d7-campaign.aborted-run.log` is not tracked — `.gitignore:7` ignores `*.log`
repo-wide. It is 282 bytes and survives only in the working tree, so its whole
content is reproduced here:

```
  srv1/control_no_flag: awake=4916 asleep=4914 freed=2 actually_freed=False endpoint_lied=True
  srv1/enabled: awake=None asleep=None freed=None actually_freed=None endpoint_lied=None
  srv2/control_no_flag: awake=10197 asleep=10177 freed=20 actually_freed=False endpoint_lied=True
```
