"""close() against a stand-in pool (the extra row's ``Pool``): (a) a service job spooling (5/16) and one in
JobStatus 6; (b) two submitted plans whose service jobs never get a slot; (c) ``stop_waiting()`` (what
``HTCondorRunner.close`` does first) while a service job is idle at its first poll and would run 1.5 s after
submit. PYTHONPATH=<tree>/src:<df4d059>/tests/extra/m69b; argv[1] names the tree."""

from __future__ import annotations

import logging
import re
import sys
import threading
import time
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import pytest
import test_m69b_schedulable as T
from graphed.core.execution import Partition, Plan, Task

from graphed_executors.htcondor_backend import HTCondorRunner
from graphed_executors.htcondor_backend import server as server_mod

logs: list[str] = []


class Keep(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        logs.append(record.getMessage())


logging.getLogger("graphed_executors").addHandler(Keep())
logging.getLogger("graphed_executors").setLevel(logging.INFO)


class Scripted(T.Pool):
    """Each service job answers ``script(age_s)``; pilots answer idle; a removed job is gone."""

    def __init__(self, script: Any) -> None:
        super().__init__(1)
        self.script = script
        self.born: dict[int, tuple[str, float]] = {}
        self.removed: set[int] = set()

    def submit(self, desc: dict[str, str], count: int = 0, spool: bool = False) -> Any:
        got = super().submit(desc, count, spool)
        self.born[got.cluster()] = (desc["JobBatchName"], time.monotonic())
        return got

    def query(self, constraint: str = "", projection: Any = None) -> list[dict[str, Any]]:
        m = re.search(r"ClusterId == (\d+)", constraint)
        if self.status is None or m is None or int(m.group(1)) in self.removed:
            return []
        batch, t = self.born.get(int(m.group(1)), ("", 0.0))
        if not batch.startswith("graphed-service-"):
            return [{"JobStatus": 1}]
        ad = self.script(time.monotonic() - t)
        return [] if ad is None else [ad]

    def act(self, action: str, constraint: str, reason: str = "") -> None:
        super().act(action, constraint, reason)
        m = re.search(r"ClusterId == (\d+)", constraint)
        if m:
            self.removed.add(int(m.group(1)))


def plan(name: str) -> Plan[int]:
    tasks = (Task(0, Partition(f"mem://rv2-{name}/0", "", 0, 1)),)
    return Plan(process=T.leaf, combine=T.add, empty=T.zero, tasks=tasks, services=(T.spec(name, 64),))


def backend_over(pool: Scripted, mp: pytest.MonkeyPatch) -> Any:
    mp.setattr(T.launch, "_htcondor", lambda: pool)
    mp.setattr(T.launch, "CLOSE_WAIT_S", 0.0)
    pilots = T.CondorPilots("generic", log_dir=Path(mkdtemp()))
    return T.HTCondorBackend(pilots, 1, host="127.0.0.1", service_hosts=("cluster",))


def wait_log(text: str, n: int = 1, bound: float = 10.0) -> bool:
    end = time.monotonic() + bound
    while sum(text in line for line in logs) < n and time.monotonic() < end:
        time.sleep(0.05)
    return sum(text in line for line in logs) >= n


def outcome(fut: Any) -> str:
    try:
        return f"value={fut.result(0).value!r}"
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"[:200]


def close_in_thread(runner: Any, bound: float) -> float | None:
    t0 = time.monotonic()
    closer = threading.Thread(target=runner.close, daemon=True)
    closer.start()
    closer.join(bound)
    return None if closer.is_alive() else time.monotonic() - t0


def case_a(state: dict[str, Any], label: str) -> None:
    logs.clear()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(server_mod, "POLL_S", 0.2)
        pool = Scripted(lambda age: dict(state))
        runner = HTCondorRunner(backend_over(pool, mp), min_pilots=0)
        fut = runner.submit(plan(f"a-{label}"))
        waited = wait_log("waits for a slot", bound=3.0)
        took = close_in_thread(runner, 10.0)
        removes = sum(kind == "act" for kind, _ in pool.log)
        print(f"(a) {label}: logged-wait={waited} close-returned-after={took and round(took, 2)} s "
              f"removes={removes} secrets-left={runner.backend._server._announce_secrets} | {outcome(fut)}")
        pool.status = None


def case_b() -> None:
    logs.clear()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(server_mod, "POLL_S", 0.2)
        pool = Scripted(lambda age: {"JobStatus": 1})
        runner = HTCondorRunner(backend_over(pool, mp), min_pilots=0)
        first, second = runner.submit(plan("b-first")), runner.submit(plan("b-second"))
        wait_log("waits for a slot", bound=3.0)
        took = close_in_thread(runner, 10.0)
        services = [e for k, e in pool.log if k == "submit" and "graphed-service-" in e]
        print(f"(b) two idle plans: close-returned-after={took and round(took, 2)} s service-jobs={len(services)} "
              f"removed={len(pool.removed & {int(e.rsplit(' ', 1)[1]) for e in services})}")
        print(f"    first:  {outcome(first)}")
        print(f"    second: {outcome(second)}")
        pool.status = None


def case_c() -> None:
    """The job runs 1.5 s after submit and announces 0.3 s later; POLL_S 1.0, so the first poll sees it idle."""
    logs.clear()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(server_mod, "POLL_S", 1.0)
        pool = Scripted(lambda age: {"JobStatus": 1 if age < 1.5 else 2})
        backend = backend_over(pool, mp)
        real_wait = backend._server.wait_announce

        def wait(key: str, timeout: float) -> Any:
            if timeout == 0.0:
                return real_wait(key, timeout)
            (age,) = [time.monotonic() - t for b, t in pool.born.values() if b == f"graphed-service-{key}"]
            if age >= 1.8:
                return ("127.0.0.1:10007", "node7")
            time.sleep(min(timeout, 1.8 - age))
            return None

        mp.setattr(backend._server, "wait_announce", wait)
        got: list[str] = []

        def host() -> None:
            try:
                endpoint, _identity, key = backend.host_service(T.spec("c-soon", 64), "scope")
                got.append(f"endpoint={endpoint}")
                backend.release_service(key)
            except Exception as exc:
                got.append(f"{type(exc).__name__}: {exc}"[:200])

        hosting = threading.Thread(target=host, daemon=True)
        hosting.start()
        if len(sys.argv) > 2 and sys.argv[2] == "stop":
            time.sleep(0.1)
            backend.stop_waiting()
        hosting.join(10.0)
        print(f"(c) job idle at its first poll, running at 1.5 s, stop_waiting={'stop' in sys.argv}: {got}")
        pool.status = None
        backend.close()


if __name__ == "__main__":
    print("tree:", sys.argv[1], "| graphed_executors from", T.HTCondorBackend.__module__,
          sys.modules["graphed_executors"].__file__)
    if sys.argv[1] != "pre":
        case_a({"JobStatus": 5, "HoldReasonCode": 16}, "spooling 5/16")
        case_a({"JobStatus": 6}, "JobStatus 6")
        case_b()
    case_c()
