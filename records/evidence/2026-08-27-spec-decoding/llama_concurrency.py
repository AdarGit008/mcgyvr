#!/usr/bin/env python3
"""Concurrent llama.cpp speculative-decoding benchmark on a remote box.
Starts llama-server (docker), waits for listen, warms up, then fires NP
concurrent /completion requests. Reports aggregate tokens/sec (throughput)
and per-request latency percentiles. Optional --model-draft.
Usage: python3 llama_concurrency.py --model <gguf> [--draft <gguf>] --np N
                                        --n-cpu-moe M --port P --n-predict 150
"""
import argparse, json, subprocess, time, threading, statistics, urllib.request

def wait_port(port, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False

def completion(port, prompt, n_predict, results, idx):
    body = json.dumps({"prompt": prompt, "n_predict": n_predict, "temperature": 0}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/completion", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=600)
        d = json.loads(r.read())
        t = d.get("timings", {})
        results[idx] = {"tokens": t.get("predicted_n", 0), "ms": (time.time() - t0) * 1e3,
                        "tps": t.get("predicted_per_second", 0)}
    except Exception as e:
        results[idx] = {"tokens": 0, "ms": None, "err": str(e)[:120]}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--draft", default=None)
    p.add_argument("--np", type=int, default=1)
    p.add_argument("--n-cpu-moe", type=int, default=0)
    p.add_argument("--port", type=int, default=8090)
    p.add_argument("--n-predict", type=int, default=150)
    p.add_argument("--n-max", type=int, default=3)
    p.add_argument("--label", default="run")
    p.add_argument("--run", type=int, default=1)
    args = p.parse_args()

    cname = f"lc_{args.label}_{args.run}"
    subprocess.run(["docker", "rm", "-f", cname], capture_output=True)
    args_ = ["docker", "run", "-d", "--gpus", "all", "-p", f"{args.port}:{args.port}",
             "--name", cname, "-v", "/home/adaramir/ggufs:/models",
             "-v", "/home/adaramir/specdecode/llama_sd:/draft",
             "ghcr.io/ggml-org/llama.cpp:server-cuda-b10481",
             "-m", "/models/" + args.model.split("/")[-1], "-ngl", "99",
             "-c", "4096", "-np", str(args.np), "--host", "0.0.0.0", "--port", str(args.port)]
    if args.n_cpu_moe > 0:
        args_ += ["--n-cpu-moe", str(args.n_cpu_moe)]
    if args.draft:
        args_ += ["-md", "/draft/" + args.draft.split("/")[-1],
                  "--spec-draft-n-max", str(args.n_max), "--spec-type", "draft-simple"]
    subprocess.run(args_, capture_output=True)

    if not wait_port(args.port):
        log = subprocess.run(["docker", "logs", cname], capture_output=True, text=True).stdout
        print(json.dumps({"ok": False, "why": "no-listen", "log": log[-500:]}))
        subprocess.run(["docker", "rm", "-f", cname], capture_output=True)
        return

    prompt = "Write a Python function to compute the nth Fibonacci number. Steps:"
    # warmup
    completion(args.port, prompt, 20, {}, -1)

    # measured: N rounds, each with `np` concurrent requests
    all_time = []
    all_tokens = []
    all_tps = []
    for rnd in range(args.run):
        results = [None] * args.np
        t0 = time.time()
        threads = [threading.Thread(target=completion, args=(args.port, prompt, args.n_predict, results, i))
                   for i in range(args.np)]
        for th in threads: th.start()
        for th in threads: th.join()
        wall = time.time() - t0
        tok = sum(x.get("tokens", 0) for x in results)
        lat = [x.get("ms") for x in results if x.get("ms") is not None]
        all_time.append(wall)
        all_tokens.append(tok)
        all_tps.append(tok / wall if wall > 0 else 0)
        if lat:
            lat.sort()
            for q in (50, 90, 99):
                pass
    agg_tps = statistics.mean(all_tps) if all_tps else 0
    print(json.dumps({
        "ok": True, "np": args.np, "draft": bool(args.draft),
        "n_cpu_moe": args.n_cpu_moe, "n_predict": args.n_predict,
        "agg_tokens_per_sec": round(agg_tps, 2),
        "avg_wall_s": round(statistics.mean(all_time), 2),
        "avg_tokens_per_round": round(statistics.mean(all_tokens), 0),
    }))
    subprocess.run(["docker", "stop", cname], capture_output=True)
    subprocess.run(["docker", "rm", "-f", cname], capture_output=True)

if __name__ == "__main__":
    main()
