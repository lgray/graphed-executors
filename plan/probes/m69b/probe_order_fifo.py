"""Does submit order alone keep a run's own pilots off the room its service needs? (one-slot personal pool)

Run as submituser inside m68b-minicondor:local with the pool up. Each case submits sleep jobs through
condor_submit in the order named, waits for the queue to settle, and prints who runs. Sizes are fractions of
the slot's TotalSlotMemory, so the cases mean the same on any one-slot pool.
  A  service, then 2 pilots that fill what it leaves                        (the ruling's order)
  B  2 pilots, then the service                                             (today's order; control)
  C  a blocker (another job) holds half; service (too big beside it), then 2 pilots that fit beside the
     blocker; then the blocker leaves                                       (FIFO with the room busy)
"""

from __future__ import annotations

import subprocess
import time


def sh(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def submit(name: str, mem: int, count: int = 1) -> int:
    desc = (
        f"executable = /bin/sleep\narguments = 600\nrequest_cpus = 1\nrequest_memory = {mem}\n"
        f"JobBatchName = {name}\nqueue {count}\n"
    )
    out = subprocess.run(["condor_submit", "-terse"], input=desc, check=True, capture_output=True, text=True).stdout
    return int(out.split(".")[0])


def states() -> list[tuple[str, int, int, int]]:
    rows = sh("condor_q", "-af", "JobBatchName", "ClusterId", "ProcId", "JobStatus", "QDate").splitlines()
    return [(r.split()[0], int(r.split()[1]), int(r.split()[2]), int(r.split()[3])) for r in rows if r.strip()]


def settle() -> list[tuple[str, int, int, int]]:
    """The queue once its (name, status) multiset held for 20 s (NEGOTIATOR_INTERVAL is 2 s), within 120 s."""
    last, since, deadline = None, time.monotonic(), time.monotonic() + 120.0
    while time.monotonic() < deadline and time.monotonic() - since < 20.0:
        now = sorted((n, st) for n, _, _, st in states())
        if now != last:
            last, since = now, time.monotonic()
        time.sleep(1.0)
    return states()


def show(case: str, rows: list[tuple[str, int, int, int]]) -> None:
    running = sorted(f"{n}.{p}" for n, _, p, st in rows if st == 2)
    idle = sorted(f"{n}.{p}" for n, _, p, st in rows if st == 1)
    print(f"{case}: running={running} idle={idle}", flush=True)


def clean() -> None:
    subprocess.run(["condor_rm", "-all"], capture_output=True)
    while states():
        time.sleep(1.0)
    time.sleep(6.0)  # the slot's dynamic claims return to the partitionable slot


total = int(sh("condor_status", "-af", "TotalSlotMemory").split()[0])
print(f"pool: one partitionable slot, TotalSlotMemory={total}", flush=True)
svc, pilot = total // 8, (total - total // 8) // 2 + 64  # svc + 1 pilot fit; svc + 2 pilots do not
print(f"A/B sizes: service={svc} pilot={pilot} (2 pilots alone fit: {2 * pilot <= total})", flush=True)

clean()
submit("service", svc)
submit("pilots", pilot, 2)
show("A service-then-pilots", settle())
clean()
submit("pilots", pilot, 2)
submit("service", svc)
show("B pilots-then-service (control)", settle())
clean()

blocker, big = total // 2, total // 2 + total // 8  # the service fits the slot, not beside the blocker
small = (total - blocker) // 2 - 16  # 2 pilots fit beside the blocker
print(f"C sizes: blocker={blocker} service={big} pilot={small}", flush=True)
b = submit("blocker", blocker)
while not any(st == 2 for n, _, _, st in states() if n == "blocker"):
    time.sleep(1.0)
submit("service", big)
submit("pilots", small, 2)
show("C with the blocker running", settle())
subprocess.run(["condor_rm", str(b)], capture_output=True)
show("C after the blocker left", settle())
clean()
