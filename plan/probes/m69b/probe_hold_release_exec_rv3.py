"""Two plans on one backend, over the frozen OrderSchedd recorder: plan B's server waits for a slot (its pilots
already submitted, one queued), and plan A, running beside it, submits a task. Is the queued pilot released
while B's server still waits? §5.2 "Later plans": the hold lasts "across all of that plan's services and [is]
released at that plan's next need of a worker ... no pilot of its runner is matchable while it waits".
PYTHONPATH=<tree>/src:<tree>/tests/frozen/m69b:<tree>/tests/frozen/m68a; argv[1] = a scratch dir."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest
from m69b_order import OrderSchedd, order_bindings
from services_harness import CountingHTTPServer, hosted_spec

from graphed_executors.htcondor_backend import HTCondorBackend, launch
from graphed_executors.htcondor_backend import server as server_mod

root = Path(sys.argv[1])
with CountingHTTPServer() as service, pytest.MonkeyPatch.context() as mp:
    mp.setattr(server_mod, "POLL_S", 0.5)
    schedd = OrderSchedd(service.port, announce_after_s=None, service_status=1)  # B's server stays idle
    order_bindings(mp, schedd)
    backend = HTCondorBackend(launch.CondorPilots("generic", log_dir=root), 2, host="127.0.0.1")
    backend.min_pilots = 0
    backend.wait_for_pilots(0)  # the pilots are submitted (a first plan ran); none starts: both queued
    schedd.mark("pilots submitted, both queued")
    got: list[str] = []

    def plan_b() -> None:
        try:
            backend.host_service(hosted_spec("web"), "planB")
        except BaseException as exc:
            got.append(f"{type(exc).__name__}: {exc}"[:160])

    waiter = threading.Thread(target=plan_b, daemon=True)
    waiter.start()
    deadline = time.monotonic() + 10
    while not [e for e in schedd.events if e.kind == "submit-service"] and time.monotonic() < deadline:
        time.sleep(0.05)
    time.sleep(1.0)
    schedd.mark("plan B's server waits; plan A submits a task")
    backend.submit(time.sleep, 0, key="graphed-planA-leaf-0")
    time.sleep(1.0)
    schedd.mark(f"plan B's server still waiting: {waiter.is_alive()}")
    backend.stop_waiting()
    backend.close()
    waiter.join(10)
    t0 = schedd.events[0].t
    for e in schedd.events:
        print(f"  {e.t - t0:6.2f}s {e.kind:15} {e.cluster or ''} {e.text[:110]} {e.reason or ''}")
    print("plan B:", got)
