  contract's ``output_schema`` and belongs to #25's parser, "never a constant in
  a runner". So there is no ``stop`` parameter on :class:`Request` to fill in;
  the absence is the decision, and a test holds it.
* **A response schema is asked for where it can be honoured, never assumed.**
  ``response_schema`` on a :class:`Request` is a JSON Schema the answer should
  conform to. The OpenAI-compatible path sends it as ``response_format``, and a
  server that implements it answers with the object instead of prose — a whole
  class of parse failure that then never happens
  (``archive/docs/port-from-local-ai.md``,
  D13). Ollama's native path does not carry it: ``/api/generate`` spells the
  same idea ``format``, which older builds accept only as the string ``json``,
  so sending a schema there turns a working dispatch into a rejected request on
  exactly the machines that path exists to reach. A pinned request still runs
  there and still answers; it answers in prose, and the completion says so in a
  note rather than leaving a caller to infer it from the shape of the text.
* **Truncation is read, never inferred.** Ollama's ``done_reason`` and the
  OpenAI-compatible ``finish_reason`` are the only evidence used. Output that
  merely *looks* cut off is not truncation, and a response whose stop reason is
  absent or unrecognised becomes :attr:`StopReason.UNKNOWN` — which is not read
  as a complete answer. Guessing from output shape is how a truncated patch
  gets applied as a whole one.
* **Every dispatch is measured.** Latency is wall-clock and host-side, so it is
  the same quantity on both protocols; token counts are the backend's own, and
  are ``None`` when it did not report them. An absent count never becomes zero —
  a zero would average into telemetry as a real measurement of nothing.

**CAV-01, which is why this module has an opinion about Ollama.** Ollama's
native ``/api/generate`` returned invalid HumanEval+ scores — 32.3% against a
true 84.1% for Qwen2.5-Coder 7B (``data/README.md``, CLM-0002). The path is
implemented here because it is what a default Ollama install offers, but it is
marked: every completion from it carries ``quality_safe=False`` and a note, and
a :class:`Request` that declares itself ``quality_sensitive`` is refused
outright with :class:`QualityCaveatError`. That is the whole of #21's third
acceptance bullet — the dependency is allowed, the *silence* is not. The remedy
is a config edit rather than a code change, because Ollama also serves the
OpenAI-compatible shape: point the same host at ``api: openai``.

**On credentials.** The key is resolved from the environment at the moment of
dispatch through :meth:`~mcgyvr.pool.Endpoint.credential` and lives only in the
``Authorization`` header of one request. A keyless endpoint — the ordinary case
for a local backend — gets no header at all rather than an empty one, so a
