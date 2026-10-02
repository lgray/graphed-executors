"""Does job priority keep a run's queued pilots off the room its later service needs? (one-slot personal pool)

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


def submit(name: str, mem: int, count: int = 1, prio: int = 0, spool: bool = False) -> int:
    desc = (
        f"executable = /bin/sleep\narguments = 600\nrequest_cpus = 1\nrequest_memory = {mem}\n"
        f"priority = {prio}\nJobBatchName = {name}\nqueue {count}\n"
    )
    argv = ["condor_submit", "-terse"] + (["-spool"] if spool else [])
    out = subprocess.run(argv, input=desc, check=True, capture_output=True, text=True).stdout
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
blocker, big = total // 2, total // 2 + total // 8
small = (total - blocker) // 2 - 16
print(f"pool: TotalSlotMemory={total}; blocker={blocker} service={big} pilot={small}", flush=True)
for case, prio, spool in (("D0 pilots-then-service, equal priority (control)", 0, False),
                          ("D pilots-then-service, service priority=10", 10, False),
                          ("E as D, both -spool", 10, True)):
    clean()
    b = submit("blocker", blocker)
    while not any(st == 2 for n, _, _, st in states() if n == "blocker"):
        time.sleep(1.0)
    submit("pilots", small, 2, 0, spool)
    show(f"{case}, pilots queued beside the blocker", settle())
    submit("service", big, 1, prio, spool)
    print("  JobPrio:", sh("condor_q", "-af", "JobBatchName", "JobPrio").split("\n")[:4], flush=True)
    subprocess.run(["condor_rm", str(b)], capture_output=True)
    show(f"{case}, after the blocker left", settle())
clean()
