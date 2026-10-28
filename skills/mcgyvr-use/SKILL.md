---
name: mcgyvr-use
description: "Switch mcgyvr between mcgyvr-code (every stage on) and a raw model: code, chat or agent."
disable-model-invocation: true
---

<!-- Code generated from src/mcgyvr/contract.py and src/mcgyvr/docgen.py by `make docs`. DO NOT EDIT. -->

# /mcgyvr-use

Switch the use case of the setup mcgyvr reads. NAME is one of `mcgyvr-code`, `code`, `chat`, `agent`.

```
mcgyvr use NAME [--config PATH]
```

It rewrites the `use_case:` line of the setup's `policy.yaml` and
nothing else, then prints the use case before and after and the stages
that are now on or off. Show the user what it printed.

- `mcgyvr-code` opts in: contracts are proposed, vetted, run up the
  ladder, gated, repaired, reviewed and re-planned, each under its own
  switch in the policy, every one on by default.
- `code`, `chat` and `agent` serve the model raw: no stage runs, and
  `mcgyvr PROMPT` and `mcgyvr direct` refuse until `mcgyvr use
  mcgyvr-code`.

Each switch, and what off means, is listed under *Use cases and
switches* in `skills/mcgyvr/SETUP.md`. `coding` is not a use case: the
command refuses it and names `mcgyvr-code` and `code`.
