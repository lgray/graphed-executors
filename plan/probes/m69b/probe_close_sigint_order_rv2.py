"""Ctrl-C inside ``close()``'s drain against the extra row's stand-in pool (every job idle forever), at POLL_S=5:
the 413aa9a repair against its ``close-signals-waiter`` mutant.

The child runs ``with HTCondorRunner(...) as runner: runner.submit(plan)`` and leaves the block normally, so SIGINT
lands in ``PlanQueue.close()``'s join. Legs (patched at run time on executors 40470e6; the stand-in submits its
pilots at construction, cluster 70; the service job is 71):
  repair:               ``_host_service`` records the job in ``_services`` once ``schedd.submit`` returns (popped on
                        failure); ``HTCondorBackend.close()`` sets ``_closing``, stops every recorded job in the calling
                        thread, then closes the server and pilots; ``HTCondorRunner.close()`` = drain in try/finally;
  close-signals-waiter: the same runner, but ``backend.close()`` as on 40470e6 (``stop_waiting()`` only).
The stand-in "queue" is every submitted cluster minus every removed one; a job is never started there, so a removed
job is one removed unrun.
Usage: PYTHONPATH=<tree>/src:<tree>/tests/extra/m69b python probe_close_sigint_order_rv2.py {repair|close-signals-waiter}
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any

POLL_S = 5.0
LEG_BOUND_S = 30.0


def child(leg: str, record: str) -> None:
    import pytest
    import test_m69b_schedulable as T
    from graphed.core.execution import Partition, Plan, Task

    from graphed_executors.htcondor_backend import HTCondorRunner, backend as backend_mod
    from graphed_executors.htcondor_backend import server as server_mod
    from graphed_executors.submit.services import ServiceUnavailable, minted_endpoint, release_quietly

    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    HB = backend_mod.HTCondorBackend

    def host_service_recording(self: Any, spec: Any, scope: str) -> tuple[str, str, str]:
        machines = backend_mod.machine_ads(self.launcher)
        key = f"{scope}-{secrets.token_hex(8)}"
        secret = self._server.announce_secret([key])
        with ExitStack() as stack:
            stack.callback(self._server.forget_announce, [key])
            job = backend_mod.ServiceJob(spec, self.launcher, key=key, url=self._server.url, secret=secret)
            job.submit()
            self._services[key] = job  # recorded from the moment schedd.submit returns
            stack.callback(self._services.pop, key, None)
            stack.callback(release_quietly, f"service job {key}", job.stop)
            refusal = job.match_refusal(machines)
            if refusal is not None:
                raise ServiceUnavailable(spec.name, {"managed": refusal})
            hostport, identity = self._await_announce(job, spec)
            stack.pop_all()
        host, _, port = hostport.rpartition(":")
        return minted_endpoint(spec.check, host, int(port)), identity, key

    def backend_close_repair(self: Any) -> None:
        self._closing.set()
        for key, job in list(self._services.items()):
            release_quietly(f"service job {key}", job.stop)
        self._stack.close()

    def runner_close(self: Any) -> None:
        try:
            self._plans.close()
        finally:
            self.backend.close()

    def runner_exit(self: Any, et: object, e: object, tb: object) -> None:
        if et is not None:
            self.backend.stop_waiting()
        self.close()

    HB._host_service = host_service_recording
    if leg == "repair":
        HB.close = backend_close_repair
    HTCondorRunner.close = runner_close
    HTCondorRunner.__exit__ = runner_exit

    class Recorded(T.Pool):
        def __init__(self) -> None:
            super().__init__(1)
            self.dump()

        def dump(self) -> None:
            with open(record, "w") as f:
                json.dump(self.log, f)

        def submit(self, desc: dict[str, str], count: int = 0, spool: bool = False) -> Any:
            got = super().submit(desc, count, spool)
            self.dump()
            return got

        def act(self, action: str, constraint: str, reason: str = "") -> None:
            super().act(action, constraint, reason)
            self.dump()

    mp = pytest.MonkeyPatch()
    mp.setattr(server_mod, "POLL_S", POLL_S)
    pool = Recorded()
    mp.setattr(T.launch, "_htcondor", lambda: pool)
    mp.setattr(T.launch, "CLOSE_WAIT_S", 0.0)
    pilots = T.CondorPilots("generic", log_dir=Path(tempfile.mkdtemp()))
    backend = HB(pilots, 1, host="127.0.0.1", service_hosts=("cluster",))
    tasks = (Task(0, Partition("mem://rv2-sigint/0", "", 0, 1)),)
    plan = Plan(process=T.leaf, combine=T.add, empty=T.zero, tasks=tasks, services=(T.spec("web", 64),))
    with HTCondorRunner(backend, min_pilots=0) as runner:
        runner.submit(plan)
        print("leaving the with block", flush=True)
    print("close returned", flush=True)


def parent(leg: str) -> None:
    record = tempfile.mktemp(suffix=".json")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.Popen([sys.executable, "-u", __file__, leg, record], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=env)
    assert proc.stdout is not None
    seen = ""
    for line in proc.stdout:
        seen += line
        if "leaving the with block" in seen and "waits for a slot" in line:
            break
    time.sleep(1.0)  # close() is in its drain; the waiter sleeps in its POLL_S=5 wait
    proc.send_signal(signal.SIGINT)
    t0 = time.monotonic()
    try:
        proc.wait(LEG_BOUND_S)
        took = f"exited {proc.returncode} {time.monotonic() - t0:.1f} s after SIGINT"
    except subprocess.TimeoutExpired:
        took = f"STILL RUNNING {LEG_BOUND_S:.0f} s after SIGINT (killed)"
        proc.kill()
        proc.wait()
    seen += proc.stdout.read()
    log = json.load(open(record))
    submitted = {e.rsplit(" ", 1)[1]: e.rsplit(" ", 1)[0].split("-")[1] for k, e in log if k == "submit"}
    removed = {m.group(1) for k, e in log if k == "act" for m in [re.search(r"Remove ClusterId == (\d+)", e)] if m}
    left = {c: kind for c, kind in submitted.items() if c not in removed}
    print(f"leg={leg} POLL_S={POLL_S}: {took}; submitted={submitted} removed={sorted(removed)} queue-left={left}")
    print("   ", [ln for ln in seen.splitlines() if "KeyboardInterrupt" in ln or "close returned" in ln
                  or "Error" in ln][:3])


if __name__ == "__main__":
    if len(sys.argv) > 2:
        child(sys.argv[1], sys.argv[2])
    else:
        parent(sys.argv[1])
