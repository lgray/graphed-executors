"""A running job's claim as CondorPilots.running_claims reads it (the same projection), and _less_claim over the
collector's slots: which sizes the ad carries, what each evaluates to, and the slot left beside it. As
submituser in the m68b-minicondor pool, PYTHONPATH=<tree>/src."""

import time

import classad2
import htcondor2 as htc

from graphed_executors.htcondor_backend.launch import SLOT_RESOURCES
from graphed_executors.htcondor_backend.services import _as_whole, _less_claim

schedd = htc.Schedd()
desc = {"executable": "/bin/sleep", "arguments": "120", "request_memory": "3000", "request_cpus": "2",
        "JobBatchName": "rv3-claim"}
cluster = int(schedd.submit(htc.Submit(desc)).cluster())
try:
    for _ in range(120):
        if [a for a in schedd.query(f"ClusterId == {cluster} && JobStatus == 2", ["JobStatus"])]:
            break
        time.sleep(0.5)
    time.sleep(3)
    sizes = [f"{r}Provisioned" for r in SLOT_RESOURCES] + [f"Request{r}" for r in SLOT_RESOURCES]
    (claim,) = schedd.query(f"ClusterId == {cluster} && JobStatus == 2", ["RemoteHost", *sizes])
    for attr in ["RemoteHost", *sizes]:
        if attr in claim:
            print(f"{attr:18} expr={claim.lookup(attr)!s:40} eval={claim.eval(attr)!r}")
        else:
            print(f"{attr:18} absent")
    machines = [m for m in htc.Collector().query(htc.AdType.Startd) if m.get("SlotType") != "Dynamic"]
    slots = [_as_whole(classad2.ClassAd(str(m))) for m in machines]
    before = [{r: s.get(r) for r in ("Name", *SLOT_RESOURCES)} for s in slots]
    _less_claim(slots, claim)
    print("slot whole:      ", before)
    print("less the claim:  ", [{r: s.get(r) for r in ("Name", *SLOT_RESOURCES)} for s in slots])
finally:
    schedd.act(htc.JobAction.Remove, f"ClusterId == {cluster}")
