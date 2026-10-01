"""A stalled histserv server (SIGSTOP after bind) under the frozen pool row's call
(lazy_init `_plan(path, tag, weight="wi")`, `ProcessPoolExecutor(max_workers=2)`, `run_bounded`).
argv: <worktree> <leg>. "rpc5" legs set histserv._RPC_TIMEOUT_S = 5 in the driver; "connected" legs stall the
server only after a bound pickle opened the driver's channel, then fill in the driver (SequentialRunner)."""
import os, signal, sys, tempfile, time
WT, LEG = sys.argv[1], sys.argv[2]
sys.path[:0] = [f"{WT}/tests/frozen/m69b", f"{WT}/src"]
import graphed_histogram.histserv as hsmod
from graphed_exec_local import ProcessPoolExecutor
from histserv_harness import bind, run_bounded, start_server, write_events
from test_histserv_lazy_init import _plan
if __name__ == "__main__":
    if LEG.endswith("rpc5"):
        hsmod._RPC_TIMEOUT_S = 5
    path = write_events(os.path.join(tempfile.mkdtemp(), "e.parquet"))
    plan = _plan(path, f"stall-{LEG}", weight="wi")
    started = [start_server() for _ in plan.services]
    try:
        bound, by_name = bind(plan, started)
        if LEG.startswith("connected"):
            import pickle
            from graphed.core.execution import SequentialRunner
            pickle.dumps(bound.process)
            call = lambda: SequentialRunner().run(bound).value
        else:
            call = lambda: ProcessPoolExecutor(max_workers=2).run(bound).value
        os.kill(started[0].proc.pid, signal.SIGSTOP)
        t0 = time.monotonic()
        try:
            run_bounded(call, timeout_s=30.0)
            print(LEG, "no error")
        except BaseException as exc:
            print(LEG, f"{time.monotonic() - t0:.1f}s", type(exc).__name__, str(exc)[:300].replace("\n", " "))
            print(LEG, "stalled endpoint", started[0].endpoint, "named:", started[0].endpoint.split("//")[1] in str(exc))
    finally:
        for s in started:
            os.kill(s.proc.pid, signal.SIGCONT); s.kill()
        sys.stdout.flush(); os._exit(0)
