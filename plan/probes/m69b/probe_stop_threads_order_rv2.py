"""``ServiceJob.stop()`` (executors 40470e6, its source compiled from argv[1]) called from two threads: the waiter's
exit stack and ``close()``. Its removal is the ``release_quietly(..., _remove)`` callback ``_submit`` registers.

  race:  both threads released by one Barrier, removal instantaneous; N trials: how many raised, how many removals.
  early: thread A stops (removal takes 0.2 s, an act's round trip), thread B stops 0.05 s later: whether B returns
         before A's removal completes (B on the exit path would let the process exit with the Remove unsent).
"""

from __future__ import annotations

import ast
import sys
import sysconfig
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any

src = Path(sys.argv[1], "src/graphed_executors/htcondor_backend/services.py").read_text()
(cls,) = [n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "ServiceJob"]
(stop_def,) = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "stop"]
ns: dict[str, Any] = {"SECRET_FILE": "graphed-secret"}
exec(compile(ast.Module([stop_def], []), "services.py:ServiceJob.stop", "exec"), ns)
stop = ns["stop"]


def release_quietly(what: str, fn: Any, *args: Any) -> None:  # submit/services.py's, as _submit registers it
    try:
        fn(*args)
    except Exception:
        pass


def job(remove: Any) -> Any:
    stack = ExitStack()
    stack.callback(release_quietly, "cluster ClusterId == 71", remove)
    return SimpleNamespace(_stack=stack, dir=None)


N = 20000
raised: dict[str, int] = {}
removals = []
for _ in range(N):
    count = [0]
    j = job(lambda: count.__setitem__(0, count[0] + 1))
    gate = threading.Barrier(2)

    def call() -> None:
        gate.wait()
        try:
            stop(j)
        except BaseException as exc:
            raised[type(exc).__name__] = raised.get(type(exc).__name__, 0) + 1

    ts = [threading.Thread(target=call) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    removals.append(count[0])
gil = "free-threaded" if sysconfig.get_config_var("Py_GIL_DISABLED") else "GIL"
print(f"{sys.version.split()[0]} ({gil}) race x{N}: raised={raised or 0}; removals per trial: "
      f"{ {k: removals.count(k) for k in sorted(set(removals))} }")

done: list[float] = []


def slow_remove() -> None:
    time.sleep(0.2)
    done.append(time.monotonic())


j = job(slow_remove)
t0 = time.monotonic()
a = threading.Thread(target=stop, args=(j,))
a.start()
time.sleep(0.05)
stop(j)
b_returned = time.monotonic() - t0
a.join()
print(f"   early: B returned at {b_returned:.3f} s, A's removal completed at {done[0] - t0:.3f} s -> "
      f"B returned {'BEFORE' if b_returned < done[0] - t0 else 'after'} the removal")
