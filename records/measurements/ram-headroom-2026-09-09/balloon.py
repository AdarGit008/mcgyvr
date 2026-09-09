"""Hold N GiB of host RAM so a mapped model can be measured at a chosen clearance.

The pages are anonymous, touched, and mlockall'd, so they are neither reclaimable
as page cache nor swappable -- which is what an unmapped co-resident's experts
are. oom_score_adj is pinned at 1000 so that if the host does run out, the kernel
takes this process and not the model under measurement.
"""

import ctypes
import signal
import sys

gib = float(sys.argv[1])
n = int(gib * (1 << 30))

try:
    with open("/proc/self/oom_score_adj", "w") as fh:
        fh.write("1000")
except OSError as exc:  # not fatal: the arm is still valid, the risk is ours
    print("oom_score_adj: %s" % exc, flush=True)

buf = bytearray(n)
mv = memoryview(buf)
for off in range(0, n, 4096):
    mv[off] = 1

libc = ctypes.CDLL("libc.so.6", use_errno=True)
MCL_CURRENT, MCL_FUTURE = 1, 2
rc = libc.mlockall(MCL_CURRENT | MCL_FUTURE)
print("mlockall rc=%d errno=%d" % (rc, ctypes.get_errno()), flush=True)
print("READY %.2f" % gib, flush=True)
signal.pause()
