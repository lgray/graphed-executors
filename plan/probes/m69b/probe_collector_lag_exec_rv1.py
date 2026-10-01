"""How soon after a job reaches JobStatus 2 does the collector's partitionable slot ad show the memory it took?
(The frozen busy-pool row queries the collector right after its blocker runs.) Submit-side, minicondor pool."""
import time

import htcondor2 as htc

schedd = htc.Schedd()


def pslot_memory() -> int:
    (slot,) = [a for a in htc.Collector().query(htc.AdType.Startd) if a.get("SlotType") == "Partitionable"]
    return int(slot["Memory"])


before = pslot_memory()
blocker = schedd.submit(htc.Submit({"executable": "/bin/sleep", "arguments": "120", "request_memory": "8000",
                                    "JobBatchName": "rv-lag-blocker"}))
mine = f"ClusterId == {blocker.cluster()}"
try:
    while [int(a["JobStatus"]) for a in schedd.query(constraint=mine, projection=["JobStatus"])] != [2]:
        time.sleep(0.2)
    t0 = time.monotonic()
    seen = []
    while time.monotonic() - t0 < 30:
        seen.append((round(time.monotonic() - t0, 1), pslot_memory()))
        if seen[-1][1] <= before - 8000:
            break
        time.sleep(0.5)
    print(f"pslot Memory before the blocker: {before}; after JobStatus==2 (t s, Memory): {seen[0]} ... {seen[-1]} ({len(seen)} reads)")
finally:
    schedd.act(htc.JobAction.Remove, mine)
