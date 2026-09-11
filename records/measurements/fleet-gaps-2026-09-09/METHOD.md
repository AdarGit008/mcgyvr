# How every arm in this campaign was taken

Split out of the README so seven measurements can share one description of the
instrument instead of repeating it seven times.

## One arm

1. **Tear down whatever is up**, through the door, with the compose file that
   *started* it. Not a file that merely names the same containers: the
   sleep-mode pair and the production pair share every container name and
   differ only in argv, so the file is written to `logs/last-up-<host>.txt` at
   every successful `up` and read back at every `down`.
2. **Drop the balloon, drop the page cache** (`sync; echo 3 >
   /proc/sys/vm/drop_caches`), so every wake is genuinely cold and comparable.
3. **Re-balloon** where the arm sets a clearance, with
   `records/measurements/ram-headroom-2026-09-09/balloon.py` — anonymous,
   touched, `mlockall`'d, `oom_score_adj` 1000, so the kernel takes the
   instrument and not the unit under measurement.
4. **Read the idle card and host** before the launch: `nvidia-smi
   --query-gpu=memory.total,memory.used,memory.reserved,memory.free`, and
   `MemAvailable`, `MemFree`, `Cached`, `Shmem`, `SwapFree` off `/proc/meminfo`,
   plus `pgmajfault`, `pswpin`, `pswpout` off `/proc/vmstat`.
5. **Start a 1 Hz sampler on the rig** (`rig.py:SAMPLER`), which records
   `memory.used`, `memory.free`, `MemAvailable` and `Shmem` every second for
   the whole of the load. This is new in this campaign, and it is what makes a
   *peak* card figure available: srv2's 80B fails during load on a CUDA
   allocation, and a steady-state read cannot see a peak.
6. **`serve up` through the door**, then read the wake from the container's own
   `State.StartedAt` with `calendar.timegm` — `time.mktime` reads the UTC stamp
   as local and adds 10,800 s here.
7. **Read the card and host again**, take a decode, and record
   `RestartCount` beside the wake (see the hazards, below).

## Two clocks on every wake, and they are both recorded

`collect_door.py` scrapes the door's own `serve-up: <container> :<port> up
after <t>s` out of every `door-up-*.log`. That clock starts when `docker
compose up -d` returns and polls the compose file's services **in order**, so
for a pair the second figure is "how much longer after the first", not that
unit's own load. `StartedAt` is the other clock. On a clean arm the two differ
by a constant ~7.6 s — the compose-up before the container starts — and they
disagree wildly when a container has restarted, because `StartedAt` is the
*last* start. Both are in the record; where they disagree, the disagreement is
the finding.

## Decode

llama.cpp units report `timings.predicted_per_second` for a 160-token
completion at `temperature 0`, `cache_prompt false`. vLLM's OpenAI surface
reports no such block, so a vLLM decode rate is timed client-side over a
streamed reply as `(tokens - 1) / (last - first)`, with the time to first
token reported separately rather than folded in.

Where a figure is quoted as a throughput it is the mean of three samples after
a discarded warm-up. Where it is quoted only to show a unit serves rather than
merely answers, it is one sample with no warm-up and says so.

## What is deliberately not controlled

* **`vm.swappiness` stayed at 60**, production, for every arm. The
  2026-09-09 headroom sweep ran part of its work at 0; this campaign did not
  touch it, so nothing here needs restoring on that axis.
* **Another agent was editing `src/` throughout.** The product hash moved from
  round `r11` to `r25` during the campaign and the door opened new rounds by
  itself, which is expected. No arm depends on a product hash; the two arms
  that would have been irreproducible for that reason are named in the README.
* **Window is 4096 per slot over 2 slots for every newly-emitted llama.cpp
  unit**, so the blobs being compared share a window. The fleet's existing
  Qwen3.6 point was taken at 8192 per slot. The window moves the card split and
  therefore `--n-cpu-moe`, and the blob is read in full under mmap either way,
  so this is stated rather than corrected for.

## The door lock

srv1's and srv2's arms ran as two processes at once. Two doors on two rigs
take two different rig leases and never collide there, but gate 1 writes
`tools/bench/rounds.json` in this checkout whenever the product hash has moved
— and the hash was moving. So every door call takes one local `flock`
(`/tmp/claude-1000/mcgyvr-door.lock`) and the two hosts serialize at the door
and nowhere else. The visible consequence is that an arm's `idle` reading can
predate its launch by however long the other host held the lock; the rigs were
idle across those gaps, so the readings stand.
