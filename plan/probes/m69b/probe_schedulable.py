"""Premises of "can the service be scheduled" on a personal pool (m68b-minicondor:local, htcondor2 25.13.2).

Run as the pool's submit user inside the container:
  docker run -d --rm --name m69b-sched-probe -v "$PWD:/p" m68b-minicondor:local
  docker exec -u submituser -w /tmp m69b-sched-probe /opt/venv/bin/python /p/probe_schedulable.py
A: the startd ads a collector query returns without naming an AdType, idle and with a job running.
B: a job whose request_memory exceeds every slot's total stays idle (what host_service waits on today).
C: a fitting job behind a blocker stays idle while it runs, then starts once the blocker is removed.
D: the driver host's physical memory from the stdlib.
"""

import os
import sys
import time

import htcondor2 as htc

ATTRS = ["Name", "SlotType", "PartitionableSlot", "TotalSlotMemory", "TotalSlotCpus", "TotalSlotGPUs",
         "Memory", "Cpus", "GPUs"]
schedd = htc.Schedd()
coll = htc.Collector()


def slots(label: str) -> list:
    ads = coll.query(constraint='MyType == "Machine"', projection=ATTRS)
    typed = coll.query(htc.AdType.Startd, projection=ATTRS)
    print(f"A {label}: default ad_type + MyType constraint -> {len(ads)} ads; AdType.Startd -> {len(typed)} ads")
    for ad in ads:
        print("   ", {k: ad.get(k) for k in ATTRS})
    return ads


def capacity(ads: list) -> int:
    best = 0
    for ad in ads:
        if ad.get("PartitionableSlot"):
            best = max(best, int(ad.get("TotalSlotMemory", 0)))
        elif ad.get("SlotType") != "Dynamic":
            best = max(best, int(ad.get("Memory", 0)))
    return best


def submit(mem: int, secs: int, batch: str) -> int:
    sub = htc.Submit({"executable": "/bin/sleep", "arguments": str(secs), "request_memory": str(mem),
                      "request_cpus": "1", "JobBatchName": batch, "log": f"/tmp/{batch}.log"})
    return int(schedd.submit(sub).cluster())


def status(cluster: int) -> int | None:
    ads = schedd.query(constraint=f"ClusterId == {cluster}", projection=["JobStatus"])
    return int(ads[0]["JobStatus"]) if ads else None


def main() -> None:
    print("htcondor2", htc.version())
    total = capacity(slots("empty pool"))
    print(f"A largest slot memory (partitionable TotalSlotMemory, static Memory, dynamic skipped): {total} MiB")

    too_big = submit(total + 1, 5, "m69b-toobig")
    time.sleep(20)
    print(f"B request_memory={total + 1}: JobStatus after 20 s = {status(too_big)} (1 = idle)")
    schedd.act(htc.JobAction.Remove, f"ClusterId == {too_big}")

    blocker = submit(total - 1024, 600, "m69b-blocker")
    t0 = time.monotonic()
    while status(blocker) != 2 and time.monotonic() - t0 < 60:
        time.sleep(0.5)
    print(f"C blocker request_memory={total - 1024}: running after {time.monotonic() - t0:.1f} s")
    after = capacity(slots("blocker running"))
    print(f"A largest slot memory with the blocker running: {after} MiB (unchanged = {after == total})")
    svc = submit(4096, 600, "m69b-service")
    time.sleep(25)
    print(f"C service request_memory=4096 behind the blocker: JobStatus after 25 s = {status(svc)}")
    schedd.act(htc.JobAction.Remove, f"ClusterId == {blocker}")
    t1 = time.monotonic()
    while status(svc) != 2 and time.monotonic() - t1 < 120:
        time.sleep(0.5)
    print(f"C blocker removed -> service JobStatus {status(svc)} after {time.monotonic() - t1:.1f} s")
    schedd.act(htc.JobAction.Remove, f"ClusterId == {svc}")

    page = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    print(f"D {sys.platform}: os.sysconf SC_PAGE_SIZE*SC_PHYS_PAGES = {page // 2**20} MiB")


if __name__ == "__main__":
    main()
