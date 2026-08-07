#!/usr/bin/env bash
# Context-size experiment runner (issue #27).
# Sequences both models through llama-server per docs/llama_cpp_cuda_gotchas.md.
# No `set -e` on purpose — pkill returns non-zero when nothing matches.

HERE="$(cd "$(dirname "$0")" && pwd)"
PORT=8080
CTX=4096
LOG=/tmp/llama-ctxexp.log

export LD_LIBRARY_PATH="/usr/local/lib/ollama/cuda_v13:/usr/local/lib/ollama:$LD_LIBRARY_PATH"
export GGML_BACKEND_PATH="/usr/local/lib/ollama/cuda_v13/libggml-cuda.so"

QWEN3_GGUF=$(ls /home/adaramir/.cache/huggingface/hub/models--unsloth--Qwen3-Coder-30B-A3B-Instruct-GGUF/snapshots/*/Qwen3-Coder-30B-A3B-Instruct-Q2_K.gguf 2>/dev/null | head -1)
Q3B_GGUF=$(ollama show qwen2.5-coder:3b --modelfile 2>/dev/null | awk '/^FROM/{print $2; exit}')

if [ -z "$QWEN3_GGUF" ] || [ -z "$Q3B_GGUF" ]; then
    echo "FATAL: model path missing (qwen3='$QWEN3_GGUF' q3b='$Q3B_GGUF')"
    exit 1
fi

start_server() {  # $1=gguf $2=ngl
    pkill -9 -f llama-server 2>/dev/null || true
    sleep 2
    /usr/local/lib/ollama/llama-server \
        -m "$1" --host 127.0.0.1 --port "$PORT" \
        -ngl "$2" --ctx-size "$CTX" --batch-size 512 \
        > "$LOG" 2>&1 &
    SERVER_PID=$!
    echo "llama-server pid=$SERVER_PID ngl=$2 model=$(basename "$1")"
    for i in $(seq 1 120); do
        sleep 2
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then
            echo "FATAL: server died; last log lines:"
            tail -20 "$LOG"
            return 1
        fi
        if curl -s "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"ok"'; then
            echo "server healthy after $((i * 2))s, VRAM: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"
            return 0
        fi
    done
    echo "FATAL: server never became healthy"
    tail -20 "$LOG"
    return 1
}

stop_server() {
    kill "$SERVER_PID" 2>/dev/null
    sleep 2
    pkill -9 -f llama-server 2>/dev/null || true
}

echo "=== context experiment $(date -Iseconds) ==="

# Free the GPU: unload any Ollama-resident models (service itself stays up).
ollama ps 2>/dev/null | tail -n +2 | awk '{print $1}' | xargs -r -n1 ollama stop

echo "--- phase A: qwen2.5-coder:3b (full offload) ---"
if start_server "$Q3B_GGUF" 99; then
    python3 "$HERE/context_exp.py" --model q3b --base-url "http://127.0.0.1:$PORT/v1"
    echo "phase A exit=$?"
    stop_server
else
    echo "phase A skipped: server failed"
fi

echo "--- phase B: qwen3-coder-30b-a3b (-ngl 10) ---"
if start_server "$QWEN3_GGUF" 10; then
    python3 "$HERE/context_exp.py" --model qwen3 --base-url "http://127.0.0.1:$PORT/v1"
    echo "phase B exit=$?"
    stop_server
else
    echo "phase B skipped: server failed"
fi

pkill -9 -f llama-server 2>/dev/null || true
echo "final VRAM: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"
echo "=== done $(date -Iseconds) ==="
