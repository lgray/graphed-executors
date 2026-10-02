"""Ctrl-C while ``close()`` drains, against the extra row's stand-in pool (every job idle forever).

The documented form ``with htcondor_runner(...) as runner: runner.submit(plan)`` leaves the block normally, so
``__exit__`` gets no exception and ``close()`` waits for the plan, whose service job waits for a slot. SIGINT then
lands inside ``close()``. Legs (HTCondorRunner patched at run time on 40470e6):
  plan: §5.2 "Ordering" as written: ``close()`` = ``SubmitRunner.close`` (no ``stop_waiting``); ``__exit__`` calls
        ``stop_waiting()`` only when an exception leaves the block, then ``close()``;
  fix:  the same, but ``close()`` reaches ``backend.close()`` (which keeps ``stop_waiting``) when the drain raises.
Usage: PYTHONPATH=<tree>/src:<tree>/tests/extra/m69b POLL_S=<s> python probe_close_sigint_order_rv1.py {plan|fix}
(the stand-in submits its pilots at construction, as 40470e6 does; cluster 70 is the pilots', 71 the service's)
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LEG_BOUND_S = 20.0


def child(leg: str, acts_file: str) -> None:
    import pytest
    import test_m69b_schedulable as T
    from graphed.core.execution import Partition, Plan, Task

    from graphed_executors.htcondor_backend import HTCondorRunner
    from graphed_executors.htcondor_backend import server as server_mod
    from graphed_executors.submit import SubmitRunner

    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

    def close_plan(self: HTCondorRunner) -> None:
        SubmitRunner.close(self)

    def close_fix(self: HTCondorRunner) -> None:
        try:
            self._plans.close()
        finally:
            self.backend.close()

    def exit_(self: HTCondorRunner, et: object, e: object, tb: object) -> None:
        if et is not None:
            self.backend.stop_waiting()
        self.close()

    HTCondorRunner.close = close_plan if leg == "plan" else close_fix  # type: ignore[method-assign]
    HTCondorRunner.__exit__ = exit_  # type: ignore[method-assign]

    class Logged(T.Pool):
        def act(self, action: str, constraint: str, reason: str = "") -> None:
            super().act(action, constraint, reason)
            with open(acts_file, "a") as f:
                f.write(f"{action} {constraint}\n")

    mp = pytest.MonkeyPatch()
    mp.setattr(server_mod, "POLL_S", float(os.environ.get("POLL_S", "0.5")))
    pool = Logged(1)
    mp.setattr(T.launch, "_htcondor", lambda: pool)
    mp.setattr(T.launch, "CLOSE_WAIT_S", 0.0)
    pilots = T.CondorPilots("generic", log_dir=Path(tempfile.mkdtemp()))
    backend = T.HTCondorBackend(pilots, 1, host="127.0.0.1", service_hosts=("cluster",))
    tasks = (Task(0, Partition("mem://rv1-sigint/0", "", 0, 1)),)
    plan = Plan(process=T.leaf, combine=T.add, empty=T.zero, tasks=tasks, services=(T.spec("web", 64),))
    with HTCondorRunner(backend, min_pilots=0) as runner:
        runner.submit(plan)
        print("leaving the with block", flush=True)
    print("close returned", flush=True)


def parent(leg: str) -> None:
    acts = tempfile.mktemp(suffix=".acts")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.Popen([sys.executable, "-u", __file__, leg, acts], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=env)
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        lines.append(line.rstrip())
        if "leaving the with block" in "\n".join(lines) and "waits for a slot" in line:
            break
    time.sleep(1.0)  # close() is now in its drain
    proc.send_signal(signal.SIGINT)
    t0 = time.monotonic()
    try:
        proc.wait(LEG_BOUND_S)
        took = f"exited {proc.returncode} {time.monotonic() - t0:.1f} s after SIGINT"
    except subprocess.TimeoutExpired:
        took = f"STILL RUNNING {LEG_BOUND_S:.0f} s after SIGINT (killed)"
        proc.kill()
        proc.wait()
    rest = proc.stdout.read().splitlines()
    removes = [a.strip() for a in open(acts)] if os.path.exists(acts) else []
    print(f"leg={leg} POLL_S={os.environ.get('POLL_S', '0.5')}: {took}; Remove acts={removes}")
    print("   ", [ln for ln in lines + rest if "KeyboardInterrupt" in ln or "close returned" in ln
                  or "still waited" in ln][:4])


if __name__ == "__main__":
    if len(sys.argv) > 2:
        child(sys.argv[1], sys.argv[2])
    else:
        parent(sys.argv[1])
