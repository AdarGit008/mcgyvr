"""The RAM side of a host-staged collective, and the root complex under two cards.

HOSTMEM  one pinned host->host copy of 1 GiB, five times: srv1's memory bandwidth
         as a copy sees it (every SHM all-reduce crosses it twice)
H2D2     both cards pulling 512 MiB from pinned host memory at the same time:
         whether the pair gets twice one card's rate or shares one root port
Printed as `KIND\tk=v...` lines for 7-nccl.sh to file.
"""

import threading
import time

import torch

N = 1 << 30
a = torch.ones(N, dtype=torch.uint8).pin_memory()
b = torch.empty_like(a).pin_memory()
b.copy_(a)
t = time.perf_counter()
for _ in range(5):
    b.copy_(a)
print(f"HOSTMEM\tgibs={5 * N / (time.perf_counter() - t) / 2**30:.2f}", flush=True)

src = torch.ones(N // 2, dtype=torch.uint8).pin_memory()
dst = [torch.empty(N // 2, dtype=torch.uint8, device=f"cuda:{i}") for i in (0, 1)]
for d in dst:
    d.copy_(src)
torch.cuda.synchronize()
out = [0.0, 0.0]
go = threading.Barrier(2)


def pull(i: int) -> None:
    torch.cuda.set_device(i)
    s = torch.cuda.Stream()
    go.wait()
    t0 = time.perf_counter()
    with torch.cuda.stream(s):
        for _ in range(10):
            dst[i].copy_(src, non_blocking=True)
    s.synchronize()
    out[i] = 10 * (N // 2) / (time.perf_counter() - t0) / 2**30


th = [threading.Thread(target=pull, args=(i,)) for i in (0, 1)]
for x in th:
    x.start()
for x in th:
    x.join()
print(f"H2D2\tgibs0={out[0]:.2f}\tgibs1={out[1]:.2f}\tsum={sum(out):.2f}", flush=True)
