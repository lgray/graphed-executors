"""A later plan's two-service ServiceSet over the frozen OrderSchedd recorder (pilots submitted, none started), with a
need of a worker every 0.1 s from another thread. The gate counts one host_service call; between the set's two calls
(here widened by service 2's site leg, a listener that never answers, tried for its timeout_s) is a need free to
release the pilots? §5.2 "Later plans": the hold lasts "across all of that plan's services".
PYTHONPATH=<tree>/src:<tree>/tests/frozen/m69b:<tree>/tests/frozen/m68a; argv[1] = a scratch dir."""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import pytest
from m69b_order import OrderSchedd, order_bindings
from services_harness import CountingHTTPServer, hosted_spec

from graphed_executors.htcondor_backend import HTCondorBackend, launch
from graphed_executors.htcondor_backend import server as server_mod
from graphed_executors.submit.services import ServiceSet

root = Path(sys.argv[1])
silent = socket.socket()
silent.bind(("127.0.0.1", 0))
silent.listen(8)  # connects, never answers
with CountingHTTPServer() as service, pytest.MonkeyPatch.context() as mp:
    mp.setattr(server_mod, "POLL_S", 0.5)
    schedd = OrderSchedd(service.port, pilots=True)  # each service announces 2 s after its submit; pilots answer the probe
    order_bindings(mp, schedd)
    backend = HTCondorBackend(launch.CondorPilots("generic", log_dir=root), 2, host="127.0.0.1")
    backend.min_pilots = 0
    backend.wait_for_pilots(0)  # a first plan ran: the pilots are submitted, none has started
    backend.site_services = {"web2": f"http://127.0.0.1:{silent.getsockname()[1]}"}
    done = threading.Event()

    def needs() -> None:
        while not done.is_set():
            backend.n_workers()
            time.sleep(0.1)

    threading.Thread(target=needs, daemon=True).start()
    specs = [hosted_spec("web", kind="web"), hosted_spec("web2", kind="web2", timeout_s=2.0)]
    schedd.mark("plan B's ServiceSet starts")
    try:
        with ServiceSet(specs, backend, scope="planB"):
            schedd.mark("plan B's ServiceSet started")
    finally:
        done.set()
        schedd.finish_pilots()
        backend.close()
        schedd.stop_pilots()
    t0 = schedd.events[0].t
    for e in schedd.events:
        print(f"  {e.t - t0:6.2f}s {e.kind:15} {e.cluster or ''} {e.text[:100]}")
    inside = schedd.events[
        [e.text for e in schedd.events].index("plan B's ServiceSet starts") : [e.text for e in schedd.events].index(
            "plan B's ServiceSet started"
        )
    ]
    holds = [e for e in inside if e.kind == "act" and e.text.startswith("Hold")]
    releases = [e for e in inside if e.kind == "act" and e.text.startswith("Release")]
    print(f"inside the set: Holds={len(holds)} Releases={len(releases)} service submits={sum(e.kind == 'submit-service' for e in inside)}")
silent.close()
