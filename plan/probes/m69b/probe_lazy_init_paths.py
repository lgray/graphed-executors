"""Where a bound plan's process is first used in the driver process, per runner (graphed d0ad16b, executors db8fb0a).

Run: python probe_lazy_init_paths.py > probe_lazy_init_paths.txt
A lazily created, lock-guarded state (standing in for the server-side histograms) is created on first __call__ in
the driver process or on first pickle (__reduce__), whichever comes first; each creation logs its pid. The m69b
premise: every runner creates it exactly once, in the driver process, and a worker never creates it.
"""
from __future__ import annotations

import operator
import os
import tempfile
import threading
from dataclasses import dataclass

from graphed.core import Partition
from graphed.core.execution import Plan, SequentialRunner, Task

LOG = os.path.join(tempfile.mkdtemp(), "init.log")


class Handles:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ids: dict[str, int] | None = None

    def ids(self) -> dict[str, int]:
        with self._lock:
            if self._ids is None:
                with open(LOG, "a") as f:
                    f.write(f"{os.getpid()}\n")
                self._ids = {"slot": 1}
            return self._ids

    def __reduce__(self):
        return (Resolved, (self.ids(),))


class Resolved:
    def __init__(self, ids: dict[str, int]) -> None:
        self._ids = ids

    def ids(self) -> dict[str, int]:
        return self._ids


@dataclass(frozen=True)
class Proc:
    handles: object

    def __call__(self, partition: Partition, resources: object) -> int:
        self.handles.ids()
        return 1


def plan() -> Plan[int]:
    tasks = tuple(Task(i, Partition(f"f{i}.root", "Events", 0, 10)) for i in range(8))
    return Plan(process=Proc(Handles()), combine=operator.add, empty=int, tasks=tasks)


if __name__ == "__main__":
    from graphed_executors.local import ProcessPoolExecutor, ThreadExecutor
    from graphed_executors.submit import SubmitRunner, ThreadBackend

    runners = [
        ("SequentialRunner", SequentialRunner),
        ("SubmitRunner(ThreadBackend(4))", lambda: SubmitRunner(ThreadBackend(4))),
        ("ThreadExecutor(4)", lambda: ThreadExecutor(max_workers=4)),
        ("ProcessPoolExecutor(2)", lambda: ProcessPoolExecutor(max_workers=2)),
    ]
    for name, make in runners:
        open(LOG, "w").close()
        runner = make()
        value = runner.run(plan()).value
        close = getattr(runner, "close", None)
        if callable(close):
            close()
        pids = open(LOG).read().split()
        print(f"{name}: value={value} creations={len(pids)} in_driver={all(int(p) == os.getpid() for p in pids)}")
