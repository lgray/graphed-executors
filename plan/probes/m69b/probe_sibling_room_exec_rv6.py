"""On a real pool (m68b-minicondor, one partitionable slot): one plan with two cluster-hosted servers that each fit
the slot whole but not together. The match subtracts the runner's running pilots' claims, not the plan's own
running servers'. Does server 2 wait forever for room its sibling holds until the set ends? Legs: `fit` (each
server 6000 MiB, control), `sum-over` (each 9000 MiB). After WAIT_S the run is stopped (stop_waiting + close).
Run as submituser with PYTHONPATH=/work/src:/work/tests/frozen/m68a; argv[1] = a scratch dir, argv[2] = leg."""

from __future__ import annotations

import dataclasses
import sys
import time
from pathlib import Path

import htcondor2 as htc
from services_harness import HARNESS_FILE, plain_plan

from graphed_executors.htcondor_backend import server as server_mod
from graphed_executors.htcondor_backend.backend import htcondor_runner
from graphed_executors.submit import recipes

WAIT_S = 120
root, leg = Path(sys.argv[1]), sys.argv[2]
server_mod.POLL_S = 2.0
mb = {"fit": 6000, "sum-over": 9000}[leg]
schedd = htc.Schedd()
t0 = time.monotonic()


def say(msg: str) -> None:
    print(f"{time.monotonic() - t0:7.1f}s {msg}", flush=True)


def servers() -> str:
    ads = schedd.query('regexp("^graphed-service-", JobBatchName)', ["ClusterId", "JobStatus", "RequestMemory"])
    return ", ".join(f"{a['ClusterId']}: JobStatus={a['JobStatus']} RequestMemory={a['RequestMemory']}" for a in ads)


ads = htc.Collector().query(htc.AdType.Startd, projection=["SlotType", "TotalSlotMemory", "Memory"])
say(f"slots: {[(a.get('SlotType'), a.get('TotalSlotMemory', a.get('Memory'))) for a in ads]}")
specs = []
for name in ("web1", "web2"):
    spec = recipes.http_server(name)
    assert spec.launch is not None
    specs.append(dataclasses.replace(spec, timeout_s=120.0,
                                     launch=dataclasses.replace(spec.launch, resources={"memory_mb": mb})))
plan = dataclasses.replace(plain_plan(1, f"rv6-{leg}"), services=tuple(specs))
runner = htcondor_runner(
    n_pilots=1, site="generic", service_hosts=("cluster",), log_dir=root / leg, request_memory_mb=512,
    user_modules=[HARNESS_FILE],
)
future = runner.submit(plan)
try:
    deadline = time.monotonic() + WAIT_S
    while not future.done() and time.monotonic() < deadline:
        time.sleep(10)
        say(f"done={future.done()}; servers: {servers()}")
    say(f"after {WAIT_S}s: done={future.done()}")
    if future.done():
        say(f"value: {future.result().value}")
finally:
    runner.backend.stop_waiting()
    runner.close()
    say(f"closed; future exception: {future.exception() if future.done() else 'not done'}")
    say(f"queue: {servers() or 'no server left'}")
