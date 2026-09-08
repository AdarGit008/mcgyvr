    is qualified with the host only when a sweep covers more than one, so an
    ordinary install keeps the bare names it has always had.
    """

    name: str
    base_url: str
    api: str  # how to ASK: "ollama" or "openai"
    host: str = DEFAULT_HOST
    kind: str = ""  # the backend convention: "ollama", "vllm", ... (default: name)
    binds_as: str = ""  # how to DISPATCH later; defaults to `api`

    def __post_init__(self) -> None:
        # `kind` is what the server IS; `name` is what it will be called. They
        # part company the moment a sweep covers two hosts, and the capability
        # table's `requires_backend` matches on the former — a model measured
        # on Ollama is measured on Ollama whether the source is called
        # `ollama` or `srv2_ollama`.
        if not self.kind:
            object.__setattr__(self, "kind", self.name)
        if not self.binds_as:
            object.__setattr__(self, "binds_as", binds_as_for(self.kind, self.api))


# Default ports each backend ships with, and for each: how to ASK it what it
# holds, then how to DISPATCH to it. Identification is by port convention,
# which is a guess about identity but not about capability: what matters
# downstream is the wire protocol and the model list, and both are read from
# the answer rather than assumed.
#
# **Ollama is asked one way and bound another, and that is the point (#164).**
# Its native `/api/tags` is the only endpoint that enumerates models that are
# *pulled but not loaded*, which is exactly the inventory a proposal needs. Its
# native `/api/generate`, though, is the path CAV-01 is a record of — it scored
# `qwen2.5-coder:7b` at 32.3% against a true 84.1%, so every completion from it
# is marked `quality_safe=False` and a quality-sensitive request is refused
# outright. The same port also serves the OpenAI-compatible shape, with the same
# model ids and no caveat. Asking natively and dispatching compatibly is not a
# compromise between the two; it is each protocol used for the thing it is
# actually better at.
PORT_CONVENTIONS: tuple[tuple[str, int, str, str], ...] = (
    ("ollama", 11434, "ollama", "openai"),
    ("llama-server", 8080, "openai", "openai"),
    ("vllm", 8000, "openai", "openai"),
    ("lmstudio", 1234, "openai", "openai"),
    ("tgi", 3000, "openai", "openai"),
)


def binds_as_for(kind: str, api: str) -> str:
    """The protocol to dispatch to ``kind`` on, given how it was asked.

    Reads the one convention table, so every construction path agrees. That
    matters more than it looks: the difference between asking Ollama natively
    and dispatching to it natively is a measured 32.3% against 84.1%, and a
    :class:`Backend` built by hand — in a test, or by a future caller that is
    not :func:`probe` — silently taking the caveated path would be a trap
