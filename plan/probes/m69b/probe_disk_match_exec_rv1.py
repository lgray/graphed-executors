"""Is a partitionable slot's Disk, held by a running job, read as free Disk by the match? A blocker leaves
512 MiB of the slot's Disk (little memory, one CPU); a second job asking 1 GiB of disk (a service job's
shipped env, say) is queued; its
whole ad is matched as ServiceJob.match_refusal does (htcondor_backend.services._as_whole), then with Disk also
at TotalSlotDisk. Run as submituser in the m68b-minicondor pool."""

import time

import classad2
import htcondor2 as htc

from graphed_executors.htcondor_backend.services import _as_whole, machine_ads

schedd = htc.Schedd()
(slot,) = [a for a in htc.Collector().query(htc.AdType.Startd) if a.get("SlotType") == "Partitionable"]
total_disk = int(slot["TotalSlotDisk"])
blocker = schedd.submit(htc.Submit({"executable": "/bin/sleep", "arguments": "300", "request_memory": "64",
                                    "request_cpus": "1", "request_disk": str(total_disk - 524288),
                                    "JobBatchName": "rv-disk-blocker"}))
mine = f"ClusterId == {blocker.cluster()}"
try:
    for _ in range(60):
        if [int(a["JobStatus"]) for a in schedd.query(constraint=mine, projection=["JobStatus"])] == [2]:
            break
        time.sleep(2)
    time.sleep(8)  # the collector's slot ad catches up
    waiting = schedd.submit(htc.Submit({"executable": "/bin/sleep", "arguments": "1", "request_memory": "64",
                                        "request_disk": "1048576", "JobBatchName": "rv-disk-waiting", "hold": "true"}))
    (job,) = schedd.query(constraint=f"ClusterId == {waiting.cluster()}")
    machines = machine_ads(type("L", (), {"schedd_locate": None})())
    slots = [_as_whole(classad2.ClassAd(str(m))) for m in machines]
    print(f"TotalSlotDisk={total_disk} KiB; blocker request_disk={total_disk - 524288}; waiting RequestDisk={job.eval('RequestDisk')}")
    print("slot after _as_whole: Memory", [int(s["Memory"]) for s in slots], "Cpus", [int(s["Cpus"]) for s in slots],
          "Disk", [int(s["Disk"]) for s in slots])
    print("match as shipped (Memory/Cpus/GPUs at totals):", any(job.symmetricMatch(s) for s in slots))
    for s in slots:
        if s.get("PartitionableSlot"):
            s["Disk"] = s["TotalSlotDisk"]
    print("control, Disk also at TotalSlotDisk:", any(job.symmetricMatch(s) for s in slots))
    schedd.act(htc.JobAction.Remove, f"ClusterId == {waiting.cluster()}")
finally:
    schedd.act(htc.JobAction.Remove, mine)
