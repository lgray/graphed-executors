"""On a real pool (m68b-minicondor): a later plan whose service start fails after it held the runner's queued pilots.
Plan A (one task, `min_pilots=0`) is in flight on a pilot a blocker keeps idle; plan B's service is refused (no slot
could ever run it), after `_host_service` held that pilot. The blocker then leaves. Does plan A finish? Legs:
`control` (no plan B), `failed-set` (plan B, then 90 s), then a need (`n_workers()`) in the same run.
Run as submituser with PYTHONPATH=/work/src:/work/tests/frozen/m68a; argv[1] = a scratch dir, argv[2] = leg."""

from __future__ import annotations

import dataclasses
import sys
import time
from pathlib import Path

import htcondor2 as htc
from graphed.services import Launch, ServiceSpec
from services_harness import HARNESS_FILE, plain_plan

from graphed_executors.htcondor_backend.backend import htcondor_runner
from graphed_executors.submit.services import ServiceUnavailable

root, leg = Path(sys.argv[1]), sys.argv[2]
schedd = htc.Schedd()
t0 = time.monotonic()


def say(msg: str) -> None:
    print(f"{time.monotonic() - t0:7.1f}s {msg}", flush=True)


def pilots(runner) -> str:  # type: ignore[no-untyped-def]
    cluster = runner.backend.launcher.cluster
    if cluster is None:
        return "no pilot cluster"
    ads = schedd.query(f"ClusterId == {cluster[1]}", ["JobStatus", "HoldReason"])
    return f"pilots {cluster[1]}: " + ", ".join(f"JobStatus={a.get('JobStatus')} {a.get('HoldReason', '')}" for a in ads)


ads = htc.Collector().query(htc.AdType.Startd, projection=["SlotType", "TotalSlotMemory", "Memory"])
largest = max(int(a.get("TotalSlotMemory", a.get("Memory", 0))) for a in ads if a.get("SlotType") != "Dynamic")
blocker = int(
    schedd.submit(
        htc.Submit(
            {"executable": "/bin/sleep", "arguments": "900", "request_memory": str(largest - 256),
             "request_cpus": "1", "JobBatchName": "rv6-blocker"}
        )
    ).cluster()
)
while [a["JobStatus"] for a in schedd.query(f"ClusterId == {blocker}", ["JobStatus"])] != [2]:
    time.sleep(1)
say(f"blocker {blocker} runs ({largest - 256} of {largest} MiB): a 512 MiB pilot stays idle")
runner = htcondor_runner(
    n_pilots=1, site="generic", service_hosts=("cluster",), log_dir=root / leg, request_memory_mb=512,
    min_pilots=0, user_modules=[HARNESS_FILE],
)
try:
    future_a = runner.submit(plain_plan(1, f"rv6-{leg}-A"))  # one task: nothing held in its window
    time.sleep(5)
    say(f"plan A in flight, done={future_a.done()}; {pilots(runner)}")
    if leg != "control":
        too_big = Launch(argv=("serve", "{port}"), image="registry.rv6.example/x:1", resources={"memory_mb": 10**7})
        plan_b = dataclasses.replace(
            plain_plan(1, f"rv6-{leg}-B"),
            services=(ServiceSpec("web", "http", check="http:/", ports=(40000, 40010), launch=too_big, timeout_s=20),),
        )
        try:
            runner.run(plan_b)
            say("plan B ran (unexpected)")
        except ServiceUnavailable as exc:
            say(f"plan B refused: {str(exc)[:120]}")
        say(pilots(runner))
    schedd.act(htc.JobAction.Remove, f"ClusterId == {blocker}")
    say("blocker removed: room for the pilot")
    deadline = time.monotonic() + 90
    while not future_a.done() and time.monotonic() < deadline:
        time.sleep(2)
    say(f"90 s later: plan A done={future_a.done()}; {pilots(runner)}")
    if not future_a.done():
        runner.backend.n_workers()  # a need of a worker
        say(f"after one need: {pilots(runner)}")
        deadline = time.monotonic() + 90
        while not future_a.done() and time.monotonic() < deadline:
            time.sleep(2)
        say(f"then: plan A done={future_a.done()}")
    if future_a.done():
        say(f"plan A value: {future_a.result().value}")
finally:
    schedd.act(htc.JobAction.Remove, f"ClusterId == {blocker}")
    runner.close()
    say("runner closed")
