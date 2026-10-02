"""What htcondor2's Schedd.act does with a reason: CondorReason (text, None), a bare str, and (text, 0).
Idle jobs that never match (OpSysMajorVer == 99) are held, released by graphed's HoldReason prefix, and
removed; each step prints the job's hold/remove attributes. As submituser in the m68b-minicondor pool,
PYTHONPATH=<tree>/src."""

import time

import htcondor2 as htc

from graphed_executors.htcondor_backend.launch import HOLD_REASON, CondorReason, CondorPilots

schedd = htc.Schedd()
ATTRS = ["ClusterId", "JobStatus", "HoldReason", "HoldReasonCode", "HoldReasonSubCode", "RemoveReason"]


def job() -> int:
    desc = {"executable": "/bin/true", "requirements": "(TARGET.OpSysMajorVer == 99)", "JobBatchName": "rv3-reason"}
    return int(schedd.submit(htc.Submit(desc)).cluster())


def ad(cluster: int) -> dict:
    for _ in range(50):
        got = list(schedd.query(f"ClusterId == {cluster}", ATTRS)) or list(
            schedd.history(f"ClusterId == {cluster}", ATTRS, match=1)
        )
        if got:
            return {k: got[0].get(k) for k in ATTRS}
        time.sleep(0.2)
    return {}


for label, reason in (("CondorReason", CondorReason(HOLD_REASON)), ("str", HOLD_REASON), ("(text, 0)", (HOLD_REASON, 0))):
    c = job()
    print(f"{label:13} hold  ->", schedd.act(htc.JobAction.Hold, f"ClusterId == {c} && JobStatus == 1", reason=reason)["TotalSuccess"], ad(c))
    ours = f'substr(HoldReason, 0, {len(HOLD_REASON)}) == "{HOLD_REASON}"'
    r = schedd.act(htc.JobAction.Release, f"ClusterId == {c} && JobStatus == 5 && {ours}")
    print(f"{label:13} release by prefix -> TotalSuccess={r['TotalSuccess']}", ad(c))
    schedd.act(htc.JobAction.Remove, f"ClusterId == {c}", reason=CondorReason("graphed: run closed") if label == "CondorReason" else reason)
    time.sleep(1)
    print(f"{label:13} removed ->", ad(c))
print("CondorPilots.alive counts our hold:", hasattr(CondorPilots, "alive"))
