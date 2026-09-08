# A library of named ladder configs

Design only. Nothing here is implemented, and no line of `src/` changes on the
branch that carries this file.

**The owner's request, verbatim:**

> "I want configs not constants, the current live ladder is a config I can
> choose out of many and reload serving on demand. something like
> `srv1-35ba3b-srv2-3b_7b_wake.json`"

Three things are asked for and they are separable: **many** ladder configs on
disk, one of them **chosen**, and the serving units **brought into line** with
the choice on demand. This document takes them in that order and finds that the
first is already built, the second is one filesystem object away, and the third
is the only part with real design in it.

---

## 1. The library already exists. What is missing is names.

Every run files the config it was made under under the journal, by its digest:

```
<journal.dir>/configs/cfg-<sha256>.yaml
```

`config.keep` writes it (`src/mcgyvr/config.py:1049`), `CONFIGS_DIR` names it
(`:53`), `cli._run` refuses a run whose copy cannot be written
(`src/mcgyvr/cli.py:1016-1025` — "a run whose setup cannot be traced is a run
recorded wrong"), and the `journal.dir` schema field already documents how to
run under one again (`src/mcgyvr/config.py:560`):

> `MCGYVR_CONFIG=<dir>/configs/<digest>.yaml` re-selects the exact setup a
> result was produced under.

There are two of them on this machine right now
(`~/.local/state/mcgyvr/journal/configs/`, 2026-09-08). So *selection out of a
set of configs already works, today, with no new code.* The owner can already
run under any config any run has ever used, by naming its file.

What the owner cannot do is **pick one by anything but a 64-character hex
string**, and cannot keep a config that has never been run. Those are the two
gaps, and both are gaps in *naming*, not in mechanism.

This matters for what follows, because it sets the bar: any design that
introduces a registry, an index file, a state directory or a `select` verb that
writes somewhere new is proposing a second selection mechanism beside a working
one. The whole of §5 is an argument that no such thing is needed.

---

## 2. D1 — Two libraries, one authored and one derived, and they do different jobs

**Decision. The named library is a directory of hand-authored config files at
`~/.mcgyvr/config/library/`. The journal's `configs/<digest>.yaml` stays
exactly what it is and is not renamed, indexed, or written to by this feature.**

The two are not competing and it is worth saying why, because the obvious
"simplification" — name the journal's copies and call that the library — is
wrong in a way that is easy to miss.

| | `~/.mcgyvr/config/library/<name>.yaml` | `<journal.dir>/configs/<digest>.yaml` |
| --- | --- | --- |
| written by | a person | `config.keep`, on every run |
| key | a name someone chose | the content's own digest |
| holds | comments, blank lines, the operator's spelling | `Config.canonical()` — defaults filled in, comments gone (`:960`) |
| answers | *what may I run under* | *what was this run made under* |
| may be edited | yes | never — it is content-addressed, so an edit is a different file |
| may be deleted | yes | no |

The derived library cannot be the authored one because `canonical()` is
deliberately lossy: it exists so that "two files that load to the same config
render to the same bytes, whatever their comments, blank lines or key order"
(`:962-964`). Every comment in the live config is a measurement with a date —
`max_parallel: 8` carries "the 2026-09-06 sweep holds 109.6 tok/s per stream at
width 8 against 115.9 at width 1"; `request_timeout_s: 180` carries the
arithmetic from 82 journalled replies. A library whose entries were canonical
copies would be a library of ladders with no record of why any of them is shaped
the way it is, which is precisely the fact an operator needs when *choosing*
between them.

The authored library cannot be the derived one because a hand-edited file has no
stable identity: it is edited, and it should be, and every edit is a new digest.

**The relationship, and the property it buys.** A library entry loads to a
digest; that digest is what a run records; `keep` files the canonical copy under
the journal. So **the named library may be pruned and rewritten freely, because
the digest library is the one that must not lose anything.** Delete
`srv2-only.yaml` and every run ever made under it is still exactly reproducible
from `~/.local/state/mcgyvr/journal/configs/cfg-….yaml`. That is worth stating
because it is what makes a *library* — a thing operators churn — safe to have at
all.

**Where the directory is, and why it is not a schema key.**
`~/.mcgyvr/config/` is already "one directory of mcgyvr's own", the owner's
ruling of 2026-09-05 (`src/mcgyvr/config.py:56-59`), and it already holds the
live config, the emitted compose files, and a geometry JSON. `library/` goes
beside them, as a constant in `config.py` next to `USER_CONFIG_DIR`.

It is not a config key, and the reason is not taste: a config that stated where
configs live would have to be found before it could say where to find configs.
The bootstrap has to be a constant, and the repo already made that call once for
the same reason.

---

## 3. D2 — The name is a filename. It is free-form, and no code path parses it.

The owner's example, `srv1-35ba3b-srv2-3b_7b_wake.json`, encodes four things:
the rigs, the models, the quantisation, and a feature flag. **Every one of them
is already stated inside the file**, and three of them are stated with more
precision than the name can carry — `srv2_vllm_3b`'s model is
`Qwen/Qwen2.5-Coder-3B-Instruct-AWQ` at a pinned image digest, not "3b".

**Decision. The name is an operator's label. Nothing reads it for meaning.**

A parsed or derived name is the same defect this repo has refused twice already:

* `Capacity.of` refuses a declared width that disagrees with a machine's,
  because that is "two answers to one question, and the machine gave one of
  them, so the config is the one that is wrong".
* The sleep/wake design's D1 refuses a `device:` key on a source for exactly
  this reason: "Two statements of one fact… A hand-written `device: cuda:0`
  beside a `base_url: http://srv2:8002` is that situation created deliberately"
  (`records/plans/sleep-wake.md` §3).
* `emit --check` exists at all because a config said `--parallel 2` while srv1
  served 8 for two days.

A name that restates the config is the third instance, and it is the worst of
the three, because a name is the one field with no validator and no measurement
to check it against.

**"So what stops a config named `..._wake` from having the switch off?"**

Nothing does, and the design says so out loud rather than pretending otherwise.
A file named `fix-the-timeout.patch` need not fix the timeout either. The
question is not how to prevent a wrong label — you cannot, short of deriving the
name, which is worse (below) — but **how to keep a wrong label from being
load-bearing for one second longer than it takes to read the next line.** Three
answers, all of them existing surfaces:

1. **The label never decides anything.** No branch, no gate, no schema check
   reads it. A mislabelled config behaves exactly as its contents say. This is
   the whole of the safety property, and it is worth more than any validator:
   the failure mode of a wrong name is *a human is briefly misled*, never *the
   ladder does something other than it says*.
2. **The label is never shown alone.** `mcgyvr config --list` (§10.1) prints, on
   the same row as the name: the digest, the hosts, the rungs, and
   `serving.enable_sleep_wake`. The label sits next to the facts it claims, in
   the one place an operator looks before selecting. A `..._wake` entry with the
   switch off is visibly wrong in the listing, at the moment of choosing.
3. **The contents are checked; the name is not.** `mcgyvr config --select`
   refuses a selection whose `emit --check` fails (§11). That is a check against
   the rigs, which is the only check that has ever caught this class of drift.

**Why a derived name would be worse, not better.** A name derived from the
contents changes whenever the contents change. `request_timeout_s: 180` was
`120` two days ago; `max_parallel` on the top rung was `8` and is now `2`;
`context_window` was absent until 2026-09-08. Every one of those measured edits
would have renamed the file. An operator's shell alias, runbook line, or
`--config` in a script would break on each. **A name whose job is to be a stable
handle cannot be a function of a thing that is edited weekly.** That is the same
argument `Config.digest`'s own docstring makes from the other side — the digest
is over the validated tree and not the bytes, "because an identity that moved
when a comment was added would name the edit and not the setup" (`:1003`, R2).
The digest is the identity that must move with content; the name is the handle
that must not.

**Name reuse.** Editing `srv2-only.yaml` in place keeps the name and changes the
digest. Two runs a week apart can both say "srv2-only" and mean different
ladders. §10.2 rules on what the record does about that: nothing, deliberately.

---

## 4. D3 — YAML, and what the owner's `.json` was actually asking for

**Recommendation: the library is authored in YAML, entries end `.yaml`, and the
loader is not changed. The owner's `.json` is adopted for its *shape* — a
descriptive name with an extension — and declined for its *format*.**

The argument, made rather than assumed:

**1. The repo has already ruled on this, with a reason that is stronger now than
when it was written.** `config.py`'s first paragraph
(`src/mcgyvr/config.py:5-8`):

> It is YAML rather than JSON because it carries policy, and policy needs
> comments to stay hand-editable (ADR-0001, "Known tension").

**2. The live config is the evidence, not a hypothetical.** Of the 4,542 bytes
in `~/.mcgyvr/config/mcgyvr.yaml`, roughly half are comments, and none of them
is decoration. Four examples, all load-bearing:

* `max_parallel: 8` on `srv2_vllm_3b` — "8, not 6: the unit is started
  `--max-num-seqs 8` and the 2026-09-06 sweep holds 109.6 tok/s per stream at
  width 8 against 115.9 at width 1."
* `max_parallel: 2` on the top rung — the 27.2 / 14.0 / 5.1 tok/s figures at
  widths 1, 2 and 8, and "Deleting it does not inherit the source's 8; it drops
  the unit to a derived 2."
* `request_timeout_s: 180` — "82 journalled replies from
  `local_qwen3.6-35b-a3b` on 2026-09-07 ran at a median 17.0 tok/s… The cap, the
  rung's width and this bound are three numbers that decide each other; raising
  one alone buys a timeout instead of a reply."
* `context_window: 4096` — "Read back off the running unit on 2026-09-08, not
  chosen here."

**A library makes this worse, not better.** The point of many configs is that
they differ. *Why* `srv2-only` drops srv1 — because the top rung's 5.1 tok/s at
width 8 does not pay for a task under `budgets.task_timeout_s` — is exactly the
thing an operator needs at the moment of choosing, and it is exactly what JSON
has no place to put. Ten JSON ladders differing in numbers with no stated reason
is ten configs nobody can choose between. The format question is therefore not
neutral: **the feature the owner is asking for is the feature that most needs
comments.**

**3. The mechanical cost is real but smaller than it looks — and it cuts the
other way.** `parse` is `yaml.load` with `_StrictLoader` (`:1481`), `canonical`
dumps YAML through `_CanonicalDumper` (`:1026`), `keep` writes `.yaml` (`:1067`).
Those two loader/dumper halves are what make the digest a function of content
and nothing else; a second authored format is a second path into the one value
in this repo that must have exactly one.

But note what is *already true*: **a `.json` file loads today, unchanged.**
PyYAML parses JSON — verified against this schema's shapes, both minified and
indented, 2026-09-08 — so `load()` accepts `srv1-35ba3b-srv2-3b_7b_wake.json`
now, and `Config.digest()` of it equals the digest of the equivalent YAML,
because the digest is over the loaded tree (`:1003`). So there is nothing to
build to honour the owner's extension, and nothing to refuse either.

**4. The recommendation, and the concession.** Author in YAML; `config --list`
lists `*.yaml` and `*.json` both, because refusing a file the loader accepts
would be a fourth rule about where configs may live. The one case where `.json`
is the right answer is a *generated* library — a sweep that writes forty ladders
across a width × window grid. Those have no comments to lose, and a generator
emitting JSON is not doing anything the loader minds. Hand-authored entries are
YAML; generated ones may be JSON; the digest does not care, which is the point.

**What survives of the owner's example:** the name. `srv1-35ba3b-srv2-3b_7b_wake`
is a good name — it is short, it distinguishes, and it reads at a glance. That
is all a name has to do (D2), and it does it whichever extension follows.

---

## 5. D4 — Selecting is moving the pointer the resolution order already follows

**Decision. Selection makes `~/.mcgyvr/config/mcgyvr.yaml` — the third and last
place `config_path()` looks — a symlink to the chosen library entry.
`config_path()` (`src/mcgyvr/config.py:1462`) is not changed, and no command
learns a new rule.**

Four mechanisms were considered. Three of them fail against something already
written down.

**(a) An exported environment variable.** `config_path()`'s own docstring
refuses this, in terms that were written about `$XDG_CONFIG_HOME` and apply
unchanged (`:1466-1471`):

> A path that depends on an environment variable only some shells export is a
> config that is found from one terminal and not another, which is the same file
> in two places as far as an operator debugging it is concerned.

`$MCGYVR_CONFIG` stays what it is — a per-invocation override, and the thing the
door pins and carries to the gates (`pin_config`,
`src/mcgyvr/serving/run.py:346`). It is not the selection.

**(b) A flag on every run.** `--config` already exists on `run`
(`src/mcgyvr/cli.py:2768`) and `emit` (`:2529`), and `config` and `pool` take
the same thing as a positional (`:2414`, `:2427`). All four honour an explicit
path today. But a flag is a per-invocation choice, not a selection: the next
command without it is back to the default, and "which ladder am I on" has no
answer. Keep the flags; they are how you run one contract against a ladder you
have not selected.

**(c) A copy.** `cp library/srv2-only.yaml ~/.mcgyvr/config/mcgyvr.yaml`. This is
the mechanism that creates the defect this whole feature is about: two files
holding one ladder, edited independently, drifting. It is `emit --check`'s
failure mode moved one layer up.

**(d) A symlink at the default path.** Chosen. What it buys:

* **No command learns anything.** The `--config` flags, the two positionals,
  `mcgyvr --version` (`:2865`), and the door's `pin_config` all follow it for
  free, because the *filesystem* follows it, not mcgyvr. That is the direct
  answer to "a selection mechanism that only some commands honour is worse than
  none": this is not a mechanism, it is the absence of one.
* **It is inspectable with a tool every machine has.** `ls -l
  ~/.mcgyvr/config/` says which ladder is live, with no mcgyvr process running.
* **The digest is unaffected by the indirection.** `canonical()` excludes the
  path — "``path`` is a fact about the caller, not the config" (`:968`) — so the
  entry reached through the link and the same entry named directly are one
  digest. Two ways to name one file, one identity. **That property is what makes
  a symlink safe here, and §6 is the one place it does not hold.**
* **The move is atomic.** A symlink staged under a temp name in the same
  directory and `os.replace`d, as `keep` already stages a config (`:1074`).
  There is no moment at which the default path is absent.

Cost, stated: `Config.path` is the path `load()` was given (`:1598`), so
`mcgyvr config` prints `~/.mcgyvr/config/mcgyvr.yaml` and not the entry's name.
`config --list` prints the link target (§10.1). On a filesystem with no symlinks
this degrades to (c) and the drift is real — a Linux-only concern in a repo
whose rigs are reached by `ssh` and `docker`, and noted as N7.

---

## 6. D5 — The one defect this creates: a relative `geometry_json` has two digests

This is a real bug that the symlink exposes, and it must be ruled on rather than
discovered.

`Config._pinned` makes a relative `geometry_json` absolute against the config's
own directory (`src/mcgyvr/config.py:997-999`), and `canonical()` writes the
absolute form into the text the digest is taken over — for a stated reason
(`:968-973`): "a kept copy that pointed beside itself would re-select a geometry
that is not there."

`self.path` is the path as given. So for a library entry that says
`geometry_json: ./Qwen3.6-35B-A3B-UD-IQ3_XXS.geometry.json` — which is exactly
what the live config says today:

| loaded as | `geometry_json` pins to | digest |
| --- | --- | --- |
| `~/.mcgyvr/config/mcgyvr.yaml` (the link) | `~/.mcgyvr/config/…geometry.json` — where the file is | `cfg-A` |
| `~/.mcgyvr/config/library/srv1-top.yaml` (the entry) | `~/.mcgyvr/config/library/…geometry.json` — nothing there | `cfg-B` |

**One file, two identities, and one of them names a geometry that does not
exist.** Under a single live config this could not happen, because there was one
path to the file.

**Decision. A library entry states `geometry_json` by an absolute path, and
`config --list` reports a relative one as a defect in that entry.** Not a
refusal in `load()` — the relative form is correct for a config that is not in a
library, and `config.py` is not touched by this design.

Two alternatives, both rejected: resolving `self.path` in `load()` changes the
digest of every config reached by a symlink or a relative path anywhere, which
is a `config.py` change with fleet-wide consequences for a library feature; and
putting a copy of each geometry file in `library/` makes the geometry the thing
that drifts instead.

---

## 7. D6 — `mcgyvr serve reload`: the order is not chosen, the door already fixed it

**Decision. `mcgyvr serve reload NAME` is not a new mechanism. It is
`serve down`, `emit`, `emit --check`, `serve up` and the pointer move, in one
order, and the order is forced by two things already in the door.**

`mcgyvr serve` is the noun the sleep/wake design already introduces —
`mcgyvr serve sleep|wake --host H`, "a thin front over the door's two steps"
(`records/plans/sleep-wake.md` §15). `reload` joins it there rather than
inventing a second front.

### 7.1 The sequence

Let **OLD** be the selection now live (readable from the link) and **NEW** the
entry named. Let `H_old` and `H_new` be the hosts each resolves to.

```
1. for H in H_old:   python -m mcgyvr.serving.run serve down --host H
                       --compose <compose_dir>/compose.H.yml --suffix <pid-clock>
2.                   mcgyvr emit --config library/NEW --out <compose_dir>
                       --ctx-per-slot <serving.ctx_per_slot>
3.                   mcgyvr emit --config library/NEW --out <compose_dir> --check
4.  for H in H_old - H_new:   remove <compose_dir>/compose.H.yml
5.  for H in H_new:   python -m mcgyvr.serving.run serve up --host H
                       --compose <compose_dir>/compose.H.yml --suffix <pid-clock>
6.                   os.replace the symlink -> library/NEW
```

### 7.2 Why down comes before emit, and what happens if it does not

Compose files are named by **host**, not by config: `compose.<host>.yml`
(`src/mcgyvr/emit.py:280`). OLD's `compose.srv2.yml` and NEW's are the same path.
So step 2 destroys the only on-disk record of what is currently up.

The failure that causes is not loud, and that is what makes it worth designing
against. `serve-down.py` runs `servelib.compose(compose_file, "down")` — no
`--remove-orphans` — and then checks the rig's daemon against
`RUN_SERVE_EXPECTED`, which the door read out of *the file it was handed*
(`src/mcgyvr/serving/run.py:776`). Hand it NEW's file and it looks for NEW's
container names, finds none of them up, and writes a `serve-down.json` with
`remaining: []` and exit 0. **A clean envelope for a teardown that left OLD's
containers running.** Step 5 then meets gate 2, which refuses a rig whose
`gpu_procs` or `containers` read anything but `none`
(`src/mcgyvr/serving/gate-scripts/02-rig.py:269`), and the operator is left with
the old ladder up, the new config's files on disk, and a written record saying
the old one was stopped.

So: **down first, with the file as it stands.** Gate 2 clears its idle check for
`down` alone — "the one run that opens on a busy rig by design" (`:255`) — which
is the door independently making `down` the only step that *can* go first.

### 7.3 A rig in both selections

srv2 is downed at step 1 with OLD's file and brought up at step 5 with NEW's.
Two existing mechanisms make that a swap rather than a pile-up:

* **The project is pinned.** `servelib.PROJECT = "mcgyvr"`
  (`src/mcgyvr/serving/servelib.py:26`) — "One name, so ``down`` finds exactly
  what ``up`` started and nothing a campaign left." Both files are one project.
* **`up` sweeps.** `serve-up.py` runs `docker compose up -d --remove-orphans`,
  so a container OLD declared and NEW does not is removed at step 5 even if step
  1 missed it. The pinned project is what makes `--remove-orphans` mean the
  right set.

The sleep/wake design leans on the same pin for the same reason. Neither design
needs a second project, a label, or a container-name convention.

### 7.4 A rig in OLD and not in NEW

It is downed at step 1 and never brought up. Its compose file is removed at step
4 — and that removal needs defending, because `check_all`'s docstring argues
directly against it (`src/mcgyvr/emit.py:229-233`):

> Files this config says nothing about are not read and not reported. A
> directory may hold compose files for rigs a ladder no longer binds, and
> calling those a drift would ask an operator to delete evidence of a machine
> that is still serving perfectly well.

That reasoning is right, and it is right *because `check_all` has no evidence
about the rig*. The reload does: it wrote `serve-down.json` for that host thirty
seconds earlier, with `remaining: []` and `card_after` from `nvidia-smi`. It is
not deleting a spec for a machine that is still serving; it is deleting a spec
for a machine it has just confirmed is not. **The two rules are consistent, and
the difference between them is exactly the evidence one has and the other does
not.**

The text is not lost either: `serve-up.json` carries the whole compose document
(`"compose": compose_file.read_text(…)`, `serve-up.py`), so every spec that was
ever brought up is in a write-once envelope under
`records/evidence/live-<host>/`. And the entry that produced it is still in the
library. There are two ways back and neither is the file.

**Why the removal matters, and it is not tidiness.** Per the sleep/wake design's
D2, a card is `asleep` — as against `down` — precisely when "it does not answer,
and this config's `compose_dir` holds a file for its host"
(`records/plans/sleep-wake.md` §4). An orphaned `compose.srv1.yml` left behind
by a reload to an srv2-only ladder would make `mcgyvr.wake` read srv1 as
**asleep** and spend a 50–130 s door run waking a rig the selected ladder does
not name. That is the sharpest place the two features touch, and step 4 is what
keeps `compose_dir` meaning "the selected ladder's launch specs" rather than
"whatever has accumulated".

### 7.5 `compose_dir` stays flat, and one writer keeps it honest

The alternative — a directory per entry, or per digest — was considered and
rejected. It makes `compose.srv2.yml` unambiguous by construction, but it makes
the path an operator types by hand into `~/.mcgyvr/config/compose/cfg-8f3a…/`,
and it changes on every edit. One flat directory with **exactly one writer**
(`serve reload`) and stale files removed gets the same guarantee — at rest, the
files under `compose_dir` are the selected config's and no other's — while
leaving `serve up --compose ~/.mcgyvr/config/compose.srv2.yml` typeable.

`serving.compose_dir` is the sleep/wake design's key (§3 there), reused
unchanged. This design adds no second directory key.

---

## 8. D7 — When the new selection will not come up

`serve-up.py` polls each unit's `/v1/models` for `HEALTH_POLLS = 120` at
`HEALTH_INTERVAL_S = 3.0` (`src/mcgyvr/serving/servelib.py:30-31`) — six minutes
— and returns 1 for a unit that never answered: "a result, not a refusal."

**Decision. The reload stops. The rig is left down, the OLD selection stays
live, and the exit is `MISMATCH` (4). Nothing is rolled back automatically.**

The rollback that suggests itself — re-emit OLD, `serve up` OLD — is rejected on
three grounds:

1. **It is a repair of a machine mcgyvr found wrong.** The run contract §4
   forbids a cell that; whether the sleep/wake algorithm is exempt is already
   left to the owner as that design's N9. A reload that undid itself would take
   that ruling by implication.
2. **The rollback can fail too, and its failure has nowhere to go.** Six more
   minutes per host, a second envelope, and an operator reading two sequences to
   find out which state the fleet is in.
3. **A partial rollback is worse than either end state.** srv2 on NEW and srv1
   back on OLD is a fleet matching no config at all — the precise drift this
   feature makes easy and `emit --check` exists to catch — created
   automatically, by the tool.

**The failure this choice causes, named.** The ladder is off. Every rung's
source stops answering, `mcgyvr.availability` reads them down, and a
non-deterministic contract fails at build; the deterministic floor still runs
and still needs no config. That is loud, immediate and attributable, and there is
a `serve-up.json` per host saying which unit did not answer and after how many
seconds.

**And the rollback command already exists.** OLD is still an entry in the
library and still the live selection, so undoing a failed reload is
`mcgyvr serve reload OLD` — the same command, a different name. No `--rollback`
flag, no saved previous-selection state, no new concept. That the pointer moves
*last* (step 6) is what makes this true: a reload that dies anywhere before step
6 leaves the selection it started from.

**The other refusals, and where they land.** `emit` refuses an unscanned host
(`src/mcgyvr/cli.py:1942-1946`, exit 3) and refuses a model the capability table
does not carry. Both happen at step 2 — *after* the rigs are down. That is the
one genuinely unpleasant consequence of down-first: a reload to an entry naming
a rig nobody has scanned takes the ladder down and then refuses. Ruled on as
N1: `serve reload` runs `emit --check` against NEW **before** step 1 as a
dry-run, so a NEW that cannot be emitted is refused while the old ladder is
still serving.

---

## 9. D8 — Work in flight is not waited for, and the existing verdict is why

A `mcgyvr run` dispatching to srv2 over HTTP holds **no rig lease**. The lease
(`~/.mcgyvr/lease` on the rig, `src/mcgyvr/serving/gatelib.py:360-361`, one run
per rig, live outranks dev, R1 2026-09-06) is taken by *door* runs. So the lease
does not protect in-flight dispatch, and it should not be made to: it is a lock
on the rig as a measurement surface, not on the units as a service.

**Decision. `serve reload` does not wait for in-flight work and does not try to
detect it. Requests against a downed unit fail as dispatch failures.**

What happens to them is already designed and already right: three consecutive
failures take the source out for sixty seconds (`src/mcgyvr/cooldown.py:84`,
`:90`), and `drive` turns the resulting `SlotUnavailableError` into
`Verdict.DECLINED` — "Nothing was asked and nothing answered"
(`src/mcgyvr/drive.py:647-650`). A task in flight loses its rung and escalates or
declines; it does not record a false failure against a model that was never
asked. `Cooldown`'s own docstring already names this case: it ends the removal
after sixty seconds because "a backend restarting, a model being swapped in, or
a machine waking turns a transient fault into a permanent one for the rest of
the run".

**The cost of being wrong**, stated: a long task loses up to
`budgets.task_timeout_s` of work — 900 s on the live ladder — and the operator
who typed `reload` is usually the operator who was running it. The guard that
would close this is a census of held slots on the hosts about to go down, and
`mcgyvr.capacity` is where it belongs; the sleep/wake design already proposes
adding `capacity.busy(bound)` for its own reasons (§15 there). If that lands,
`serve reload` refuses on a non-empty census unless `--force`. It is N3 below,
and it is deliberately not designed here, because building a second census
against work in flight is how this design would grow the concept the sleep/wake
design says is only a lower bound anyway (its §7.2).

---

## 10. D9 — Which config is live, and what a record says it was

### 10.1 What an operator reads

Three surfaces, all of which exist, none of which is new:

* **`ls -l ~/.mcgyvr/config/`** — the link and its target. No mcgyvr process,
  no config parsed. This is the one that still works when the config will not
  load.
* **`mcgyvr --version`** — already prints two lines, "because they are two
  identities (owner's ruling R2): the wheel is the code, and the config is the
  setup, and a result names both" (`src/mcgyvr/cli.py:2865`). The second reads
  `config: cfg-<digest> (<path>)`, and with a symlink at the default path the
  digest is the entry's, because the path is not in the digest (§5).
* **`mcgyvr config`** — `<path>: valid` and `digest: <digest>`
  (`src/mcgyvr/cli.py:96-108`), plus the resolved sources and ladder.

What none of them says is **which named entry that is**, because `Config.path`
is the path `load()` was given (`src/mcgyvr/config.py:1598`). That is the one
thing the library adds and the one line `config --list` exists for (§14): the
selected entry marked, with the digest, hosts, rungs and
`serving.enable_sleep_wake` beside its name — the row that puts a free-form
label next to the facts it claims (§3).

Deliberately **not** added: a `mcgyvr status`, a card column in `mcgyvr pool`, a
selection field in `mcgyvr --version`. The sleep/wake design refuses the same
three for the same reason (its §12) — each is a reader to keep alive, and the
three above are consumed today.

### 10.2 What the record says

**Decision. The journal row and the result file keep carrying
`config_digest` and only `config_digest`
(`src/mcgyvr/telemetry.py:206`, `src/mcgyvr/result.py:79`). No name field is
added, and no `label:` key is added to the schema.**

A name is not an identity: it is mutable, it is per-machine, and it can be
reused for different content (D2). A row carrying `name: srv2-only` beside a
digest that no longer matches any file of that name would be a record that
*lies*, in the one place this repo has decided must not — the same argument
`Config.digest` makes for hashing the tree and not the bytes (`:1003`, R2), and
the same argument `keep` makes for refusing a run whose config copy cannot be
written (`src/mcgyvr/cli.py:1016-1025`).

A `label:` *schema* key would be honest — it would be inside the digest, so
changing it would change the identity — and it is rejected for the opposite
reason: relabelling would fork the digest history, so a config renamed for
clarity would look like a different setup to every query anyone ever runs
against the journal.

**How a digest is resolved to a name, then.** By looking: `mcgyvr config --list`
prints name → digest for what is on disk *now*. A digest in a six-week-old
result that matches no current entry is honestly reported as matching none — the
config is still there, under the journal, under its digest, which is where a
result's `config_digest` was always meant to be followed to (`:560`).

**And the ladder's history is already recorded, per host, keyed by time.** Every
`serve up` and `serve down` the reload performs is a door run under
`RUN_CAMPAIGN = live-<host>` (`src/mcgyvr/serving/run.py:770`), writing
write-once evidence under `records/evidence/live-<host>/<RUN_ID>/`, and
`serve-up.json` carries the full compose text. So "which ladder was up on srv2
on the 8th" is answerable today, from the envelopes, with nothing added. The
row says the digest; the envelope says the units; the compose text is where they
meet.

---

## 11. D10 — `emit --check` keeps its rule, and the library gives it a referent

The question the library raises is "match *which* config". The answer is **the
selected one**, and it is true by construction rather than by a new rule,
because `compose_dir` has exactly one writer and stale files are removed (§7.4,
§7.5). At rest, the files under `compose_dir` are what the live config emits.
`check_all` is not touched. `Drift` is not touched. Nothing in `emit.py` changes.

Two places the check is put to work:

**1. As a step of the reload** (§7.1 step 3), between emit and `serve up`. If the
files this call would write are not the files on disk, no rig is touched. This
is where the check earns its place: the drift it was built to catch —
"the compose files on disk match the config" going stale — is a thing a library
makes easy to cause, and the reload is the moment it is causable.

**2. As the gate on selection without reload.** `mcgyvr config --select NAME`
moves the pointer and nothing else, which is legitimate: you may want the next
run under a different `budgets` block on the same rigs.

**Decision. `config --select NAME` refuses (`REFUSED`, 3) when NEW's
`emit --check` does not pass, and names `mcgyvr serve reload NAME` as the
command that makes it pass. `--anyway` overrides.** Selecting a ladder the rigs
are not serving is precisely the two-configurations defect, and the library
turns it into a one-word mistake. `--anyway` exists because "select a config
whose rigs are deliberately off" is a real thing to want, and a refusal with no
override is a refusal operators route around with `ln -sf`.

**The residue, named and not designed away.** A compose file the reload never
saw — hand-emitted, or left by a reload that died between step 1 and step 4 — is
invisible to `emit --check`, by `check_all`'s stated and correct rule. It is
*not* invisible to sleep/wake, which would read that host as `asleep`. So
`config --list` prints one line per compose file under `compose_dir` whose host
the selected config does not name. A report, in the command that already exists
to answer "what is where", rather than a new rule in the checker.

---

## 12. The one new schema key: `serving.ctx_per_slot`

`mcgyvr emit --ctx-per-slot N` is **required and deliberately not defaulted**
(`src/mcgyvr/cli.py:2541-2556`): "a run that did not say is a run sized against a
number nobody chose — which is what a module constant here was doing until
2026-09-06, against a door that defaulted to a different one."

A reload has to supply it, and it cannot be a flag on `serve reload` for the same
reason `serving.enable_sleep_wake` is not a flag on `mcgyvr run`
(`records/plans/sleep-wake.md` §7.1): a number typed at the command line is a
number that is not in the file whose digest names the run, so two reloads of
one entry can produce two different ladders and nothing records which.

**The live config proves the gap rather than describing it.** Both srv2 sources
carry `context_window: 4096` with the comment "Read back off the running unit on
2026-09-08, **not chosen here**: vLLM was started `--max-model-len 4096` and
reports it." srv1 carries "`/props` on 2026-09-08, after the unit was re-emitted
at 2 slots: `-c` is 8192 across 2 slots" — and the emitted `compose.srv1.yml`
does carry `-c 8192` at `--parallel 2`. **The number that sized every unit on
this fleet lives in a shell history, and the config records only the
observation of it.** With one config, that is survivable. With a library of
configs each sized differently, it means an entry cannot be reloaded into the
ladder it describes.

**Proposed: `serving.ctx_per_slot`, an int, no default, sitting beside
`serving.compose_dir` in the `serving` block the sleep/wake design introduces.**
Absent, `serve reload` refuses naming the key — the loader's rule for anything
that must be bound and has no real working value (`src/mcgyvr/config.py:12-15`).
`emit --ctx-per-slot` stays as the hand override, exactly as `--config` stays
beside the selection.

This is the only schema key this design asks for. It is named, and not written.

---

## 13. How this composes with sleep/wake

Read together, the two designs do not overlap so much as complete each other:
sleep/wake decides *when* a card comes up and down; this decides *which ladder*
comes up. Five contact points, all resolved above:

* **`serving.compose_dir`** — one key, one meaning, defined by sleep/wake §3 and
  reused here. This design adds the invariant that makes it trustworthy: at
  rest it holds exactly the selected config's specs (§7.5).
* **`asleep` vs `down`** — sleep/wake reads a card as `asleep` when it does not
  answer and `compose_dir` holds a file for its host. Step 4's removal is what
  stops a dropped rig from reading `asleep` and being woken into a ladder that
  no longer names it (§7.4).
* **Whole-card eviction** — sleep/wake's D1 finding is that "sleep is
  `serve down`, wake is `serve up`, and the card is the compose file." A reload
  is the same two steps against a *different* file. Same door, same steps, same
  envelopes; nothing here is a second way onto a rig.
* **The door** — sleep/wake's D3 ("waking goes through the door, and nothing
  else") holds unchanged. `serve reload` spawns
  `python -m mcgyvr.serving.run serve up|down` with a `--suffix` derived from
  pid and clock, for the same gate-5 reason (`gatelib.py:322`).
* **`mcgyvr serve`** — sleep/wake §15 already proposes `mcgyvr serve
  sleep|wake --host H`. `reload` is a third verb under that noun, not a new one.

The replacement boundary in sleep/wake §14 covers this design without
amendment — every clause of it is satisfied by a reload, and the "only from a
spec `emit` already wrote" clause is what step 2 and step 3 exist to keep true.

---

## 14. Shape of the change (for the plan that follows this one)

New:
* `config.LIBRARY_DIR = "~/.mcgyvr/config/library"` — a constant beside
  `USER_CONFIG_DIR`. Nothing else in `config.py`.
* `mcgyvr config --list` — name, digest, selected marker, hosts, rungs,
  `enable_sleep_wake`, plus the two reports of §6 (relative `geometry_json`) and
  §11 (orphan compose file).
* `mcgyvr config --select NAME [--anyway]` — the staged-symlink `os.replace`,
  gated on `emit --check`.
* `mcgyvr serve reload NAME [--force]` — §7.1's six steps. Joins the
  `mcgyvr serve` parser the sleep/wake design introduces.
* Config: `serving.ctx_per_slot` (int, no default), beside sleep/wake's
  `serving.compose_dir` and `serving.enable_sleep_wake`.

Untouched, and that is the point:
* `src/mcgyvr/config.py` — no change to `config_path`, `load`, `parse`,
  `canonical`, `digest` or `keep`. The resolution order is the mechanism.
* `src/mcgyvr/emit.py` — no change to `emit_all`, `check_all`, `_planned` or
  `Drift`. It still only writes files.
* `src/mcgyvr/serving/run.py`, the gates, the shims, the lease, `servelib`. A
  new caller of `serve up|down`, no new door.
* `src/mcgyvr/telemetry.py`, `src/mcgyvr/result.py`. The record already carries
  the only identity a config has.

---

## 15. Numbers and rules the owner has not ruled on

One line each. Every one of these was chosen by this document, not by the owner,
and every one is load-bearing.

| | what | proposed | why that, and what it costs to be wrong |
| --- | --- | --- | --- |
| **N1** | Dry-run `emit --check` against NEW before step 1 | **yes** | Without it a reload to an entry naming an unscanned rig takes the ladder down and *then* refuses (§8). Costs one extra emit; being wrong means an outage caused by a refusal that was knowable in advance. |
| **N2** | Failure at `serve up` | **stop, keep OLD selected, exit 4** | §8. Wrong in one direction leaves nothing serving until a human looks; wrong in the other leaves a fleet matching no config, created by the tool. |
| **N3** | Refuse a reload while slots are held on a host it would down | **not in v1** | §9. Depends on `capacity.busy(bound)`, which sleep/wake §15 proposes. Being wrong costs an in-flight task up to `budgets.task_timeout_s` (900 s live) — recoverable, and the operator usually typed both commands. |
| **N4** | A name in the journal row | **no** | §10.2. Wrong here means a record that can lie about which ladder ran; the alternative cost is that a digest is resolved by looking rather than by reading. |
| **N5** | A `label:` schema key | **no** | §10.2. Being wrong means relabelling forks the digest history and every journal query splits. |
| **N6** | `.json` entries | **accepted, not recommended** | §4. The loader parses them today. Wrong means a library of ladders with no stated reason for any of their numbers — unchooseable. |
| **N7** | Symlink for selection | **yes; copy where symlinks are unavailable** | §5. On the fallback, drift between the entry and the live file is real and undetected. Linux-only fleet; noted rather than solved. |
| **N8** | Relative `geometry_json` in a library entry | **report, do not refuse** | §6. A refusal belongs in `config.py`, which this design does not touch. Being wrong means an entry with two digests, one naming a file that is not there. |
| **N9** | Removing the compose file of a dropped host (step 4) | **yes, after `serve-down.json`** | §7.4. Being wrong makes `mcgyvr.wake` read a dropped rig as `asleep` and spend a 50–130 s door run waking it. |
| **N10** | Flat `compose_dir` with one writer, vs a directory per entry | **flat** | §7.5. Being wrong means `compose.srv2.yml` is ambiguous the moment anything but `serve reload` writes there. |
| **N11** | `serving.ctx_per_slot` as a key rather than a `reload` flag | **key** | §12. Being wrong means two reloads of one entry produce two ladders and the digest records neither. |
| **N12** | `--anyway` on `config --select` | **yes** | §11. Without an override operators use `ln -sf` and the check is bypassed silently instead of loudly. |
| **N13** | `mcgyvr init` writing through the selection symlink | **refuse when the default path is a symlink** | `initialize` writes to `resolve_config_path()` and `write_text` follows a link, so `init --force` would silently rewrite a library entry. Cheapest guard; being wrong destroys an authored config with no copy but the journal's canonical one. |

---

## 16. Open questions this design does not settle

* **Whether `config --select` should be able to select a config that is not in
  the library** — an arbitrary path, or a journal `configs/<digest>.yaml`. The
  latter is attractive: "put me back on exactly what run X used" is one command
  away, and D1's whole argument is that those two libraries differ. The
  objection is that a canonical copy has no comments, so selecting one installs
  a ladder whose reasoning is gone. A `config --adopt <digest> --as NAME` that
  copies it into the library is probably the right shape and is not designed
  here.
* **What a reload does on a rig somebody else is also using.** The door's gate 2
  refuses `serve up` on a busy rig and the reload inherits that refusal
  correctly, but `serve down` opens on a busy rig by design (`02-rig.py:255`) —
  so a reload can stop containers that are not mcgyvr's. Sleep/wake's D8 covers
  the same ground for an automatic sleep; whether a *manual* reload should be
  held to the same eviction rule is the owner's.
* **Whether the library should be under version control.** `~/.mcgyvr/config/`
  is not in this repository and deliberately so — the journal never lands in the
  repo a run works on (`src/mcgyvr/config.py:554-556`). But a library of
  measured ladders is exactly the kind of thing that wants a history, and it now
  has none beyond the journal's per-digest copies. A `git init` in
  `~/.mcgyvr/config/` is the operator's to run, and this design neither requires
  nor forbids it.
* **A reload mid-run changes the widths.** The same open question sleep/wake
  ends on: `Capacity` is built once at `src/mcgyvr/cli.py:1370`, and a reload
  that changes `max_parallel` on a source while a run is climbing leaves the
  bound and the units disagreeing. Today a width disagreement is a refusal at
  build time; discovered after a reload it has nowhere to go. The conservative
  answer — a reload does not re-read widths, and the config remains the
  declaration — is consistent with the rest of `capacity`, and is what §9's
  decline-and-escalate behaviour implicitly assumes.
* **How many entries before a flat listing stops working.** Three ladders read
  fine in `config --list`. Forty generated by a sweep do not, and at that point
  something wants filtering or grouping — which is the moment a name earns being
  structured after all, and the moment to revisit D2 with evidence instead of
  against a hypothetical.
