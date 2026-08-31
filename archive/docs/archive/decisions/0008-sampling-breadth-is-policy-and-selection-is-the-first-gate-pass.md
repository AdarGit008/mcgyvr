# ADR-0008 — sampling breadth is policy and selection is the first gate pass

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-01

## Context

DEC-6 of the architecture document inherited from local-ai (#109) proposes N=5
draws from every cheap tier, executed against generated test inputs, with the
winner chosen by Functional Majority Voting over execution fingerprints. #99
carries it: `num_samples` and `selection_strategy` added to "pool config",
`execution_consensus` implemented in a `verifier.py`, five draws each for the
1.5B and 3B at temperature 0.7. The selection half does not survive contact with
the gate mcgyvr already has. The sentence underneath it does.

**The economic objection is not the one the document argues.** DEC-6 frames its
case in time — five 1.5B draws deliver 7B single-pass quality "at ~60% of the
time cost", the 1.5B at 130 tok/s against the 7B's 68 — and the obvious counter
is cost: five draws for the price of one. Both are wrong about mcgyvr.
ADR-0001's north star counts accepted work per unit of **expensive-token**
spend, and a local draw contributes nothing to that denominator. Extra local
draws are close to free in the currency the north star measures; what they buy
is a higher chance of clearing the gate without crossing into the API family,
the only crossing the north star charges for. What breadth spends is wall
clock — each candidate costs a full `Gate.run` (`gate/runner.py:78`) plus the
contract's declared suite, against `budgets.task_timeout_s`, default 900
(`config.py:269`).

**Consensus has nothing to rank here.** The gate's last rung *is* execution —
the contract's declared commands, in the sandbox, with a green-on-base
precondition that earns the interpretation (`gate/acceptance.py:116`). Every
candidate that survives the gate has already passed the exact suite consensus
would rank it by, and `GateResult.accepted` is `not self.findings`
(`gate/runner.py:58`) — binary, no score, nothing to sort on. Where consensus
would have inputs the gate has already decided; where the gate cannot decide,
consensus has no inputs either. Only three of the catalog's seven evidence kinds
carry commands at all (`data/task-catalog.json:28`–`:63`), and five of the nine
task types require none of them; four of those five start on the deterministic
family (`:68`–`:98`), which gets exactly one attempt by construction (#24). That
leaves `docstring` (`:100`) as the single model-executed type whose gate is
silent about behaviour, and it is silent for consensus too.

**The headline number is not about the models it names.** DEC-6's load-bearing
claim is that Qwen2.5-Coder 1.5B at pass@5 (0.65) equals Qwen2.5-Coder 7B at
pass@1 (0.65); re-verifying it against the alphaxiv paper #99 links finds that
figure for neither model. mcgyvr's own vendored table measures the 7B at 0.829
HumanEval+ on rig_a and 0.841 on rig_b (`data/capability-table.json:111`,
`:112`). 0.652 is what that table measures for the **1.5B's** own single draw
(`:77`) — the score the document assigns to the 7B is, on this hardware, the
small model's pass@1. Five draws to reach 0.65 therefore competes with one free
local escalation to the 3B at 0.805 (`:94`), and the table prices that step
itself: "The 1.5B→3B step is +15.3pp HumanEval+; the 3B→7B step is +2.4pp on the
same rig" (`:101`). pass@5 is also an oracle upper bound — it scores a problem
solved if *any* draw is correct, presuming a selector that is never wrong.
Realised selection accuracy is strictly below it, so #99's criterion ("N=5 1.5B
samples selected via execution consensus achieve pass@5 ≥ 0.62 on HumanEval
(matching 3B single-pass)") would pass while missing the 3B's measured single
draw by 18 points on HumanEval+ and 22 on the HumanEval it names (`:94`).

The throughput half mixes rigs and backends. 130.6 tok/s is the 1.5B on rig_a
under ollama (`:81`); the only 68 in mcgyvr's data is the 7B AWQ's
single-request figure under vLLM on rig_b (`:260`). On rig_b alone the 1.5B runs
54.29 against the 7B's 57.59 (`:82`, `:116`) — the small model is slower.

None of which makes breadth worthless, and the strongest argument for it is one
the document mangled rather than made. Its "T² Scaling Laws" citation belongs to
Snell et al., arXiv:2408.03314, which finds that test-time compute can beat a
14× larger model — but only "on problems where a smaller base model attains
somewhat non-trivial success rates". The document drops that condition; it is
the interesting part. On this hardware the condition is *met*: the 1.5B's 0.652
(`data/capability-table.json:77`) is not a trivial success rate, so the regime
the paper describes is the regime a local ladder actually runs in. That is why
breadth is a setting rather than a prohibition. What the paper does not license
is a fixed N=5 wired to a parameter count, which is the form DEC-6 proposed and
the only form this record rejects.

## Decision

**How many draws a rung gets is configuration policy the orchestrator applies
from rules and config. The default is 1. When a rung takes more than one draw,
the winner is the first candidate to pass the gate.**

There is no consensus selection, no ranking, and no generated test inputs.
Candidates are gated in order; the first accepted result ends the rung; if none
passes, the rung is exhausted and escalation proceeds exactly as #24 and #43
already specify. Keeping the draws independent needs nothing new:
`Sandbox.reset()` (`sandbox/base.py:222`) already makes N candidates cost one
sandbox and N−1 resets.

The default of 1 is not a preference. It is the closest thing to evidence anyone
in this lineage has: #24 records that "worker-tier remediation rescued 2 of 35
failures, so a retry is usually spend without a result". Be precise about what
that measures — a retry on the same rung after a verdict, not N independent
draws at temperature; the two differ in whether the second attempt sees the
first one's failure. It nonetheless points at 1, and everything else on offer is
a pass@k bound on a public benchmark, a ceiling on what selection could achieve
rather than a measurement of what it does.

Breadth is policy rather than a constant because #24's own acceptance criterion
already says so — "Attempt budgets are policy in config, not constants in code".
Its home is `TIER_FIELDS` (`config.py:148`), where the tier `name` is documented
as "how this rung is referred to elsewhere — risk floors, routing policy,
telemetry" (`config.py:152`): policy references a rung by name. The document's
`TIER_SAMPLE_CONFIG`, keyed on `tier.model_size`, cannot be expressed — no
`model_size` exists anywhere in `src/`, and ADR-0003 fixed tier names as
`<locality>_<model>` with no size token. Keying breadth on a parameter count
re-introduces the per-model routing constant the configuration refuses to carry.

"Never more than one draw" is therefore a legitimate setting, not a degenerate
one. CAV-04 records that "a model that fits VRAM only marginally thrashes rather
than failing" (`data/capability-table.json:62`); on a machine where throughput
is that scarce, the right place to spend it is one escalation, and the config
has to be able to say so.

## Rejected: Functional Majority Voting over execution fingerprints

FMV (arXiv:2604.15618) and SemanticVote (arXiv:2605.08680) are both real and
both check out at the figures the document quotes — the two citations in DEC-6
that survived re-verification intact. Execution-grounded selection genuinely
does beat output-pattern majority voting for code, for a reason easy to believe:
every code sample is textually unique, so agreement on tokens measures almost
nothing while agreement on behaviour measures the thing being asked for. Taking
the cluster medoid rather than the majority is the right statistic when no
single answer dominates. If mcgyvr had N candidates and no way to execute them,
FMV is what it should build.

It loses because mcgyvr does have a way to execute them and runs it first.
Selection would receive only candidates that already passed the contract's
declared commands in the sandbox, so the discriminating signal is consumed
before selection begins: FMV would re-execute a suite whose verdict is already
recorded and cluster candidates that are all, by construction, in the passing
cluster. The only ranking left is behaviour on inputs the suite does not cover —
generated test inputs, rejected below.

The published implementation is also not a working artifact. `select_consensus`
calls `exec(result.output, *args, **kwargs)` over a `test_inputs` list of
`(args, kwargs)` pairs; on the repository's floor of Python 3.12
(`pyproject.toml:7`) `exec` rejects an arbitrary keyword argument outright and
requires its second and third positional arguments to be dicts, so the call
raises `TypeError` for every candidate. Repaired faithfully — execute the
module, record `("ok", None)` or the exception type — the fingerprint stops
depending on the test input at all: every candidate that imports cleanly
fingerprints identically, every pairwise score ties, and `max(range(n), key=...)`
returns index 0. The algorithm, made to run, is "take the first one". That is
the decision above, without the module. That it would run that `exec` in the
orchestrator process is separately fatal under ADR-0005.

## Rejected: LLM-generated test inputs

This is the honest answer to the objection just made. If the gap FMV needs to
fill is behaviour the declared suite does not cover, generating inputs is
precisely how to cover it. The document's technique is sketch-based — name
abstract input categories first, instantiate them second — and it is the right
shape for the job, since the categories are what a hand-written suite is missing
rather than more instances of what it has. It would extend selection to the task
types whose contracts declare no commands, where the gate is weakest, and on a
local generator it costs no expensive tokens. Its case has to be taken on that
reasoning alone: the margins the document reports over direct generation and
random fuzzing cite a research brief under `.pi-subagents/`, which ADR-0004
records as never having been committed and unreadable on any ref.

It loses because it puts a model inside the deterministic gate, and ADR-0001
boundary 3 makes that gate the entire acceptance bar for a keyless install — "it
runs tools and local models with the deterministic gate as the acceptance bar".
A generated input is not a checked fact; a suite of them is a model's opinion
about correctness wearing the gate's authority. The keyless install is v1's
definition of done, so this is not a corner case.

The circularity is worse than the boundary. The only generator a keyless install
has is a local model — plausibly the same model whose candidates are being
judged, on the same contract, so a wrong shared premise generates the inputs
that confirm it. DEC-6 names this failure twice, as "false positive consensus"
and "shared hallucinations", without noticing that its own mitigation is drawn
from the distribution it is mitigating.

Where inputs really are missing, mcgyvr already puts them somewhere that is not
the gate: `test_scaffold` is a catalog task type (`data/task-catalog.json:124`)
and `failing_test_first` an evidence kind (`:60`) that `bug_fix` requires
(`:132`). Both produce tests that land in the pull request and get read.

## Consequences

- No consensus module, no test-input generator. #99 as written is not
  buildable: `src/mcgyvr/` has no `verifier.py` and E6 (#40) is unstarted, and
  there is no "pool config" for its fields to go in — the schema's blocks are
  sources, ladder, orchestrator, verifier, sandbox, delivery and budgets, while
  `src/mcgyvr/pool.py` is #20's source map (`source_map()` at `:257`,
  `SourceMap.bind()` at `:215`) and holds no sampling. The surviving sentence —
  a rung may get more than one draw before it is exhausted — folds into #43 as
  an amendment, which is the shape #43 already carries amendments in.
- Sampling parameters live in `TIER_FIELDS` (`config.py:148`) with breadth
  defaulting to 1, and reach `docs/config-reference.md` by generation rather
  than restatement, which is the property #12 exists to hold.
- Breadth above 1 stays deferred until v1 telemetry exists. CLM-0003 registers
  the north star itself as `assumed-unmeasured` with existential blast radius; a
  feature whose whole benefit is "fewer crossings into the API family" cannot be
  evaluated before the thing that counts crossings is built.
- The measurement that would settle it is cheap and nobody has proposed it:
  given that a gate-passing candidate exists among N, at what index does it
  first appear? Concentrated at 0 retires breadth outright — and serial draws
  with early exit produce that distribution as a by-product of running.
- Parallel draws are unbuilt, not forbidden. They need a backend that batches,
  whose returns CON-04 measures as sublinear and plateauing at memory bandwidth
  (`data/capability-table.json:260`, `:261`). Whether a given source batches is
  not something config can be asked to declare — `SOURCE_FIELDS` carries
  base_url, api, max_parallel and api_key_env and no capability field
  (`config.py:109`) — so it has to be discovered from the source, which is
  #22's ground even though #22's scope today is liveness alone.
- Given up: the pass@k headroom is real, and first-pass-wins captures it only in
  proportion to how often the gate can tell one candidate from another — for
  `docstring`, never. Ranked selection on a tiebreaker the gate does not own,
  smallest diff say, would capture a little more. It was not taken because it is
  a style preference asserted as a quality signal, and this record would rather
  name the gap than fill it with an unmeasured number.
