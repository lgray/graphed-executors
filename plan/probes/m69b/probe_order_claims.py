"""What a later plan's service job can know about its runner's own pilots, on a one-slot personal pool.

Run as submituser inside m68b-minicondor:local with the pool up and the queue empty. A "pilots" cluster of 3
sleep jobs where only 2 fit runs; then:
  1. the collector's dynamic-slot ads name each running pilot's job (the attributes printed), so the room
     beside the runner's running pilots is computable per partitionable slot;
  2. a service job too big for that room but within the slot's total matches the slot counted whole (§5.2's
     substitution) and not the slot counted whole minus those claims; a small control matches both;
  3. holding the idle pilot (constraint: ClusterId and JobStatus == 1) leaves it unmatched, and releasing it
     makes it idle again.
"""

from __future__ import annotations

import time

import classad2
import htcondor2 as htc

schedd, coll = htc.Schedd(), htc.Collector()


def submit(name: str, mem: int, count: int = 1) -> int:
    sub = htc.Submit({"executable": "/bin/sleep", "arguments": "600", "request_cpus": "1",
                      "request_memory": str(mem), "JobBatchName": name})
    return int(schedd.submit(sub, count=count).cluster())


def statuses(cluster: int) -> list[int]:
    return sorted(int(a["JobStatus"]) for a in schedd.query(f"ClusterId == {cluster}", ["JobStatus"]))


def wait(pred, s: float = 90.0) -> bool:  # type: ignore[no-untyped-def]
    end = time.monotonic() + s
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(1.0)
    return False


(pslot,) = [a for a in coll.query(constraint='MyType == "Machine"') if a.get("PartitionableSlot")]
total = int(pslot["TotalSlotMemory"])
pilot = total // 3 + 256  # 2 fit, 3 do not
pilots = submit("pilots", pilot, 3)
assert wait(lambda: statuses(pilots) == [1, 2, 2]), statuses(pilots)
time.sleep(3.0)  # the collector's partitionable ad lags a claim by about 1 s
ads = coll.query(constraint='MyType == "Machine"')
attrs = ["Name", "SlotType", "JobId", "GlobalJobId", "RemoteUser", "Memory", "Cpus", "Disk", "TotalSlotMemory"]
print(f"pool: TotalSlotMemory={total}; pilots cluster {pilots}: 3 x {pilot} MiB, statuses {statuses(pilots)}")
for ad in ads:
    print("  ad:", {k: ad.get(k) for k in attrs if k in ad})
print("  pslot child lists:", {k: pslot_ad.get(k) for pslot_ad in ads if pslot_ad.get("PartitionableSlot")
                               for k in pslot_ad.keys() if k.startswith("Child")})
mine = [a for a in ads if a.get("SlotType") == "Dynamic" and str(a.get("JobId", "")).split(".")[0] == str(pilots)]
held_mb = sum(int(a["Memory"]) for a in mine)
print(f"1. dynamic slots running cluster {pilots}: {len(mine)}, holding {held_mb} MiB; room beside them "
      f"{total - held_mb} MiB")

big, small = total - held_mb + 512, max(128, (total - held_mb) // 2)
for label, mem in (("too big beside the pilots", big), ("control, fits beside them", small)):
    svc = submit(f"service-{mem}", mem)
    (job,) = schedd.query(f"ClusterId == {svc}")
    (p,) = [classad2.ClassAd(str(a)) for a in ads if a.get("PartitionableSlot")]
    whole, beside = classad2.ClassAd(str(p)), classad2.ClassAd(str(p))
    for t, f in (("TotalSlotMemory", "Memory"), ("TotalSlotCpus", "Cpus"), ("TotalSlotDisk", "Disk")):
        whole[f] = p[t]
    beside["Memory"] = int(p["TotalSlotMemory"]) - held_mb
    beside["Cpus"] = int(p["TotalSlotCpus"]) - sum(int(a["Cpus"]) for a in mine)
    beside["Disk"] = int(p["TotalSlotDisk"]) - sum(int(a["Disk"]) for a in mine)
    print(f"2. service {mem} MiB ({label}): matches whole={job.symmetricMatch(whole)} "
          f"whole-minus-own-pilots={job.symmetricMatch(beside)}")
    schedd.act(htc.JobAction.Remove, f"ClusterId == {svc}")

schedd.act(htc.JobAction.Hold, f"ClusterId == {pilots} && JobStatus == 1")
time.sleep(2.0)
print(f"3. after Hold of the idle pilot: {statuses(pilots)}",
      [(int(a["JobStatus"]), a.get("HoldReasonCode")) for a in schedd.query(f"ClusterId == {pilots}",
                                                                              ["JobStatus", "HoldReasonCode"])])
running = [int(a["ProcId"]) for a in schedd.query(f"ClusterId == {pilots} && JobStatus == 2", ["ProcId"])]
schedd.act(htc.JobAction.Remove, f"ClusterId == {pilots} && ProcId == {running[0]}")  # room for the held one
time.sleep(12.0)
print(f"   12 s after a running pilot left, still held: {statuses(pilots)}")
schedd.act(htc.JobAction.Release, f"ClusterId == {pilots} && JobStatus == 5")
print(f"   after Release: started within 30 s = {wait(lambda: statuses(pilots) == [2, 2], 30.0)}; {statuses(pilots)}")
schedd.act(htc.JobAction.Remove, f"ClusterId == {pilots}")
