# baseline-orient — Hermes Agent plugin

Opens each [Hermes Agent](https://github.com/NousResearch/hermes-agent) session with `baseline orient` — the baseline skill's derived-state survey (live lanes, backlog, divergence) — so a session starts from **derived** state instead of a hand-maintained status doc (C16). The Hermes twin of the Claude Code SessionStart hook in [`../../../hooks/`](../../../hooks).

It registers, via the standard `register(ctx)` entry point:
- **`/orient`** — a slash command that prints the survey on demand;
- **`on_session_start`** — a hook that runs the survey at session start.

Both shell out to `baseline.mjs orient`; the plugin holds no provider keys and does no network of its own. Orient degrades gracefully when a plane (git / forge) is unreachable, so the hook can never block a session.

## Install

```bash
cp -r <baseline-skill>/integrations/hermes/baseline-orient  ~/.hermes/plugins/
hermes plugins enable baseline-orient
```

The plugin finds the baseline CLI automatically (an installed `~/.hermes/skills/.../baseline` or `~/.claude/skills/baseline`, or `baseline` on `PATH`); override with `BASELINE_CLI=/abs/path/baseline.mjs`. Needs Node ≥ 18 + git for orient's local planes, and `gh` for its forge view.

## Provenance & the one caveat

Authored against the official hermes-agent plugin API — `register(ctx)` with
[`ctx.register_command(name, handler, description, args_hint)`](https://github.com/NousResearch/hermes-agent) and `ctx.register_hook(hook_name, callback)` where `hook_name` ∈ `VALID_HOOKS` (`on_session_start` is a member). It is **not** modelled on any third-party memory plugin: the plan's original `prefetch`/`system_prompt_block` sketch was memory-provider-specific (those are `MemoryProvider` methods, not general hooks), so this plugin uses the correct general surface.

**Verification status:** the `/orient` command surface is spec-confirmed and the plugin is authored to the documented API, but it has **not been runtime-tested in a live Hermes** (none was available at authoring time). The one detail to confirm on a real Hermes install is **how `on_session_start` injects a system-prompt block** — whether returning the survey string is consumed as context, or the hook should mutate a passed session/context object. Enable the plugin, start a session, and adjust `_on_session_start` in `__init__.py` if the injection mechanism differs. The command path (`/orient`) should work as-is.
