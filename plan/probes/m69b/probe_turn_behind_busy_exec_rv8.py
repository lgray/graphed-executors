"""On a real pool (m68b-minicondor, one slot), at ce39e42: plan A's server (2000 MiB) waits for room a blocker holds,
holding the set lock; plan B's server (512 MiB) would fit beside the blocker now. How long does B wait for its turn,
and does it end once A's wait ends (the blocker removed at BLOCK_S)?
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

BLOCK_S = 45
root, leg = Path(sys.argv[1]), sys.argv[2]
server_mod.POLL_S = 2.0
schedd = htc.Schedd()
t0 = time.monotonic()


def say(msg: str) -> None:
    print(f"{time.monotonic() - t0:7.1f}s {msg}", flush=True)


def served(tag: str, mb: int) -> Any:
    spec = recipes.http_server(f"{tag}1")
    assert spec.launch is not None
    spec = dataclasses.replace(spec, timeout_s=120.0, launch=dataclasses.replace(spec.launch, resources={"memory_mb": mb}))
    return dataclasses.replace(plain_plan(1, f"rv8-turn-{tag}"), services=(spec,))


def servers() -> str:
    ads = schedd.query('regexp("^graphed-service-", JobBatchName)', ["ClusterId", "JobStatus", "RequestMemory"])
    return ", ".join(f"{a['ClusterId']}({a['RequestMemory']} MiB): JobStatus={a['JobStatus']}" for a in ads) or "none"


ads = htc.Collector().query(htc.AdType.Startd, projection=["SlotType", "TotalSlotMemory", "Memory"])
largest = max(int(a.get("TotalSlotMemory", a.get("Memory", 0))) for a in ads if a.get("SlotType") != "Dynamic")
blocker = int(schedd.submit(htc.Submit({
    "executable": "/bin/sleep", "arguments": "900", "request_memory": str(largest - 1200), "request_cpus": "1",
    "JobBatchName": "rv8-blocker"})).cluster())
while [a["JobStatus"] for a in schedd.query(f"ClusterId == {blocker}", ["JobStatus"])] != [2]:
    time.sleep(1)
say(f"blocker {blocker} runs ({largest - 1200} of {largest} MiB): 1200 MiB free")
runner = htcondor_runner(n_pilots=1, site="generic", service_hosts=("cluster",), log_dir=root / leg,
                         request_memory_mb=512, user_modules=[HARNESS_FILE])
ended: dict[str, float] = {}
try:
    future_a = runner.submit(served("a", 2000))
    future_a.add_done_callback(lambda _: ended.setdefault("a", time.monotonic() - t0))
    time.sleep(4)

    def run_b() -> None:
        try:
            got = f"value {runner.run(served('b', 512)).value}"
        except BaseException as exc:  # noqa: BLE001
            got = f"{type(exc).__name__}: {exc}"
        ended["b"] = time.monotonic() - t0
        say(f"plan b ended: {got}")

    thread = threading.Thread(target=run_b, daemon=True)
    thread.start()
    say("plan b calls run")
    while time.monotonic() - t0 < BLOCK_S:
        time.sleep(10)
        say(f"servers: {servers()}")
    schedd.act(htc.JobAction.Remove, f"ClusterId == {blocker}")
    say("blocker removed")
    deadline = time.monotonic() + 120
    while (thread.is_alive() or not future_a.done()) and time.monotonic() < deadline:
        time.sleep(2)
    say(f"plan a: {future_a.exception() or future_a.result().value}; ended at {ended}")
finally:
    schedd.act(htc.JobAction.Remove, f"ClusterId == {blocker}")
    runner.backend.stop_waiting()
    runner.close()
    say(f"closed; servers: {servers()}")
