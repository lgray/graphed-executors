"""close() while a need's pilot submit is in flight, over the frozen OrderSchedd recorder whose pilot submit takes
1.5 s (a schedd round trip, or a spool). `_move_pilots` checks `_closing` before `launcher.start`, under
`_pilots_lock`; `close()` sets `_closing` under `_lock` and then stops the launcher. Is a cluster whose submit began
before the close removed by it? Cases: a direct `backend.close()` beside a `wait_for_pilots` thread; a runner whose
no-service plan is in its first need when a real SIGINT lands in the block's `close()`.
PYTHONPATH=<tree>/src:<tree>/tests/frozen/m69b:<tree>/tests/frozen/m68a; argv[1] = a scratch dir."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

import pytest
from m69b_order import OrderSchedd, order_bindings, order_plan
from services_harness import CountingHTTPServer

from graphed_executors.htcondor_backend import HTCondorBackend, launch
from graphed_executors.htcondor_backend import backend as backend_mod
from graphed_executors.htcondor_backend import server as server_mod

signal.signal(signal.SIGINT, signal.default_int_handler)
root = Path(sys.argv[1])
SUBMIT_S = 1.5


def slow_pilot_submit(schedd: OrderSchedd, on_start: threading.Event) -> None:
    submit = schedd.submit

    def slow(description, count=0, spool=False, **kwargs):  # type: ignore[no-untyped-def]
        if str(dict(description).get("JobBatchName", "")).startswith("graphed-pilots-"):
            schedd.mark("pilot submit begins")
            on_start.set()
            time.sleep(SUBMIT_S)
        return submit(description, count, spool, **kwargs)

    schedd.submit = slow  # type: ignore[method-assign]


def report(name: str, schedd: OrderSchedd, extra: str = "") -> None:
    t0 = schedd.events[0].t
    print(f"== {name} {extra}")
    for e in schedd.events:
        print(f"  {e.t - t0:6.2f}s {e.kind:15} {e.cluster or ''} {e.text[:80]}")
    pilots = {e.cluster for e in schedd.events if e.kind == "submit-pilots"}
    removed = {e.cluster for e in schedd.events if e.kind == "act" and e.text.startswith("Remove")}
    print(f"  pilot clusters submitted={sorted(pilots)} left in the queue={sorted(pilots - removed)}", flush=True)


def direct() -> None:
    with CountingHTTPServer() as service, pytest.MonkeyPatch.context() as mp:
        mp.setattr(server_mod, "POLL_S", 0.5)
        schedd = OrderSchedd(service.port)
        order_bindings(mp, schedd)
        began = threading.Event()
        slow_pilot_submit(schedd, began)
        backend = HTCondorBackend(launch.CondorPilots("generic", log_dir=root / "direct"), 1, host="127.0.0.1")
        errs: list[str] = []

        def need() -> None:
            try:
                backend.wait_for_pilots(1)
            except BaseException as exc:
                errs.append(f"{type(exc).__name__}: {exc}"[:100])

        n = threading.Thread(target=need, daemon=True)
        n.start()
        began.wait(10)
        time.sleep(0.3)
        schedd.mark("backend.close()")
        backend.close()
        schedd.mark("close() returned")
        n.join(5.0)
        time.sleep(SUBMIT_S + 1.0)
        report("direct", schedd, f"need raised={errs}")


def runner_close_sigint() -> None:
    with CountingHTTPServer() as service, pytest.MonkeyPatch.context() as mp:
        mp.setattr(server_mod, "POLL_S", 0.5)
        schedd = OrderSchedd(service.port)
        order_bindings(mp, schedd)
        began = threading.Event()
        slow_pilot_submit(schedd, began)
        threading.Thread(
            target=lambda: began.wait(30) and (time.sleep(0.3), os.kill(os.getpid(), signal.SIGINT)), daemon=True
        ).start()
        runner = backend_mod.htcondor_runner(
            n_pilots=1, site="generic", service_hosts=("cluster",), log_dir=root / "runner", host="127.0.0.1"
        )
        try:
            with runner:
                runner.submit(order_plan("rv5-start-close"))  # no services: its first task is the first need
                schedd.mark("block left normally: close() drains")
        except KeyboardInterrupt:
            schedd.mark("KeyboardInterrupt left close()")
        time.sleep(SUBMIT_S + 1.0)
        report("runner-close-sigint", schedd)


which = sys.argv[2] if len(sys.argv) > 2 else "all"
if which in ("all", "direct"):
    direct()
if which in ("all", "runner"):
    runner_close_sigint()
sys.stdout.flush()
os._exit(0)
