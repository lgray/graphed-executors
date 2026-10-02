"""HTCondor premises of §5.2 "Ordering" and of its rejected alternative, on a one-slot personal pool.

Run as submituser inside m68b-minicondor:local (pool up, queue empty):
  1. ``schedd.act(Hold, ...)`` whose constraint matches no job (a later plan with no queued pilot) returns or raises;
  2. a job submitted with ``hold = True`` into a free slot stays held (and unstarted) for 15 s, then a Release of
     ``HoldReasonCode == 15`` starts it;
  3. the same with ``spool=True`` and ``schedd.spool(result)`` (lpc and lxplus spool): submitted, or refused;
  4. a spooled job without ``hold`` left idle by a blocker: a Hold of ``JobStatus == 1`` keeps it unstarted after
     the blocker leaves, and a Release of ``HoldReasonCode == 1`` starts it (the later-plan hold on a spool site).
"""

from __future__ import annotations

import time

import htcondor2 as htc

schedd = htc.Schedd()


def submit(name: str, *, hold: bool, spool: bool = False, mem: int = 256) -> int:
    desc = {"executable": "/bin/sleep", "arguments": "600", "request_cpus": "1", "request_memory": str(mem),
            "JobBatchName": name, "should_transfer_files": "YES", "transfer_output_files": '""'}
    if hold:
        desc["hold"] = "True"
    result = schedd.submit(htc.Submit(desc), count=1, spool=spool)
    if spool:
        schedd.spool(result)
    return int(result.cluster())


def state(cluster: int) -> list[tuple[int, object, object]]:
    ads = schedd.query(f"ClusterId == {cluster}", ["JobStatus", "HoldReasonCode", "NumJobStarts"])
    return [(int(a["JobStatus"]), a.get("HoldReasonCode"), a.get("NumJobStarts")) for a in ads]


def wait(pred, s: float = 60.0) -> bool:  # type: ignore[no-untyped-def]
    end = time.monotonic() + s
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(1.0)
    return False


try:
    got = schedd.act(htc.JobAction.Hold, "ClusterId == 999999 && JobStatus == 1")
    print(f"1. Hold matching no job: returned {dict(got) if got is not None else None}")
except Exception as exc:  # the premise under test
    print(f"1. Hold matching no job: raised {type(exc).__name__}: {exc}")

for spool in (False, True):
    try:
        c = submit(f"held-spool{int(spool)}", hold=True, spool=spool)
    except Exception as exc:  # the premise under test
        print(f"{2 + spool}. hold=True spool={spool}: submit raised {type(exc).__name__}: {exc}")
        continue
    time.sleep(15.0)
    print(f"{2 + spool}. hold=True spool={spool}: 15 s after submit (slot free): {state(c)}")
    schedd.act(htc.JobAction.Release, f"ClusterId == {c} && JobStatus == 5 && HoldReasonCode == 15")
    started = wait(lambda: state(c)[0][0] == 2, 30.0)
    print(f"   after Release of HoldReasonCode == 15: running within 30 s = {started}; {state(c)}")
    schedd.act(htc.JobAction.Remove, f"ClusterId == {c}")

total = int(next(a for a in htc.Collector().query(constraint='MyType == "Machine"') if a.get("PartitionableSlot"))
            ["TotalSlotMemory"])
blocker = submit("blocker", hold=False, mem=total - 1024)
assert wait(lambda: state(blocker)[0][0] == 2), state(blocker)
c = submit("spooled-pilot", hold=False, spool=True, mem=2048)
assert wait(lambda: state(c)[0][0] == 1, 30.0), state(c)
time.sleep(5.0)
print(f"4. spooled job behind the blocker: {state(c)}")
schedd.act(htc.JobAction.Hold, f"ClusterId == {c} && JobStatus == 1")
schedd.act(htc.JobAction.Remove, f"ClusterId == {blocker}")
time.sleep(15.0)
print(f"   held, 15 s after the blocker left: {state(c)}")
schedd.act(htc.JobAction.Release, f"ClusterId == {c} && JobStatus == 5 && HoldReasonCode == 1")
print(f"   after Release of HoldReasonCode == 1: running within 30 s = {wait(lambda: state(c)[0][0] == 2, 30.0)}; "
      f"{state(c)}")
schedd.act(htc.JobAction.Remove, f"ClusterId == {c}")
