"""On a real pool (m68b-minicondor, one partitionable slot of 15973 MiB), at 7e6e9c5: two plans of one runner start
their services at once (two threads in `runner.run`), each with two 6000 MiB cluster servers. A plan's second server
is matched against the slot less its own sibling only, so it is admitted beside the other plan's first server and
waits for room that server keeps until its own set (also waiting) ends. Legs: `serial` (the plans one after the other,
control), `concurrent`. After WAIT_S the run is stopped (stop_waiting + close).
Run as submituser with PYTHONPATH=/work/src:/work/tests/frozen/m68a; argv[1] = a scratch dir, argv[2] = leg."""

from __future__ import annotations

import dataclasses
import sys
import threading
import time
from pathlib import Path
from typing import Any

import htcondor2 as htc
from services_harness import HARNESS_FILE, plain_plan

from graphed_executors.htcondor_backend import server as server_mod
from graphed_executors.htcondor_backend.backend import htcondor_runner
from graphed_executors.submit import recipes

WAIT_S = 150
root, leg = Path(sys.argv[1]), sys.argv[2]
server_mod.POLL_S = 2.0
schedd = htc.Schedd()
t0 = time.monotonic()


def say(msg: str) -> None:
    print(f"{time.monotonic() - t0:7.1f}s {msg}", flush=True)


def servers() -> str:
    ads = schedd.query('regexp("^graphed-service-", JobBatchName)', ["ClusterId", "JobStatus", "RequestMemory"])
    return ", ".join(f"{a['ClusterId']}: JobStatus={a['JobStatus']}" for a in sorted(ads, key=lambda a: a["ClusterId"]))


def plan(tag: str) -> Any:
    specs = []
    for i in (1, 2):
        spec = recipes.http_server(f"{tag}{i}")
        assert spec.launch is not None
        specs.append(dataclasses.replace(spec, timeout_s=120.0,
                                         launch=dataclasses.replace(spec.launch, resources={"memory_mb": 6000})))
    return dataclasses.replace(plain_plan(1, f"rv7-{leg}-{tag}"), services=tuple(specs))


runner = htcondor_runner(
    n_pilots=1, site="generic", service_hosts=("cluster",), log_dir=root / leg, request_memory_mb=512,
    user_modules=[HARNESS_FILE],
)
results: dict[str, str] = {}


def run(tag: str) -> None:
    try:
        results[tag] = f"value {runner.run(plan(tag)).value}"
    except BaseException as exc:  # noqa: BLE001
        results[tag] = f"{type(exc).__name__}: {str(exc)[:200]}"
    say(f"plan {tag} ended: {results[tag]}")


try:
    if leg == "serial":
        run("x")
        run("y")
    else:
        threads = [threading.Thread(target=run, args=(tag,), daemon=True) for tag in ("x", "y")]
        for t in threads:
            t.start()
        deadline = time.monotonic() + WAIT_S
        while any(t.is_alive() for t in threads) and time.monotonic() < deadline:
            time.sleep(10)
            say(f"servers: {servers()}")
        say(f"after {WAIT_S}s: plans ended {sorted(results)}")
finally:
    runner.backend.stop_waiting()
    runner.close()
    time.sleep(3)
    say(f"closed; results {results}")
    say(f"queue: {servers() or 'no server left'}")
