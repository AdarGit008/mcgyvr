# Restoring srv1's `llama-sweep` container

Stopped 2026-08-26 to free srv1's card for the 12 owed verification cells.
It was the 2026-08-25 serving sweep's shipped winner cell (35B-A3B, ncmoe 28),
started 2026-08-25T17:30:13Z, healthy, restart policy `no`, holding 5,558/6,144 MiB.

Exact restore command:

```bash
ssh srv1 'docker run -d --name llama-sweep --gpus all \
  -v /home/adaramir/ggufs:/models -p 8080:8080 \
  ghcr.io/ggml-org/llama.cpp:server-cuda-b10481 \
  -m /models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf \
  -ngl 99 --n-cpu-moe 28 -t 6 -c 4096 -fa on --host 0.0.0.0 --port 8080'
```

Full inspect JSON was left on the rig at `srv1:/tmp/llama-sweep-spec.json`.
