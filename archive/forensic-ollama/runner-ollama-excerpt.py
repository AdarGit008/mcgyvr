                f"against a cap of {request.max_output_tokens}; it did not "
                f"honour the ceiling it was sent."
            )
        return tuple(notes)

    def _headers(self) -> dict[str, str]:
        """Request headers, with the key read at this moment and not before.

        A keyless endpoint gets no ``Authorization`` header at all — an empty
        one is a different request, and some servers reject it.
        """
        headers = {"Content-Type": "application/json"}
        key = self.endpoint.credential()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    @abstractmethod
    def _payload(self, model: str, request: Request) -> dict[str, Any]:
        """The request body in this protocol's shape, cap included."""

    @abstractmethod
    def _parse(self, document: dict[str, Any]) -> _Parsed:
        """Read an answer, raising :class:`ProtocolError` if it cannot be."""


class OllamaRunner(Runner):
    """Ollama's native generate — implemented, and marked by CAV-01.

    ``/api/generate`` is what a default Ollama install offers and what most
    local setups already have running, so refusing to speak it would refuse the
    common machine. What it cannot do is carry a measurement: CAV-01 records
    this path scoring a model at 32.3% against a true 84.1%, and a table
    regenerated through it would route away from the best model available. So
    ``quality_safe`` is False here, which puts a note on every completion and
    refuses a request that declares itself quality-sensitive.
    """

    protocol: ClassVar[Protocol] = Protocol.OLLAMA
    path: ClassVar[str] = "/api/generate"
    quality_safe: ClassVar[bool] = False

    def _payload(self, model: str, request: Request) -> dict[str, Any]:
        options: dict[str, Any] = {
            "num_predict": request.max_output_tokens,
            "temperature": request.temperature,
        }
        payload: dict[str, Any] = {
            "model": model,
            "prompt": request.prompt,
            # Nothing here streams: a single document is what makes the stop
            # reason and the token counts readable in one place.
            "stream": False,
            "options": options,
        }
        if request.system:
            payload["system"] = request.system
        return payload

    def _parse(self, document: dict[str, Any]) -> _Parsed:
        text = document.get("response")
        if not isinstance(text, str):
            raise ProtocolError(
                f"{self.endpoint.source!r} answered /api/generate without a "
                f"string 'response' field. Keys present: "
                f"{', '.join(sorted(document)) or '(none)'}"
            )
        return _Parsed(
            text=text,
            raw_stop_reason=_as_str(document.get("done_reason")),
            input_tokens=_as_int(document.get("prompt_eval_count")),
            output_tokens=_as_int(document.get("eval_count")),
        )


class OpenAIRunner(Runner):
    """The OpenAI-compatible chat-completions shape — vLLM, llama-server, TGI,
    LM Studio, Ollama's own ``/v1``, and the hosted providers.

    One protocol rather than one integration per vendor, which is what makes
    adding a backend a config entry. It is also the path a measurement must run
