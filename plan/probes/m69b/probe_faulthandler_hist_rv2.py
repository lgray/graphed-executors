"""pytest's built-in faulthandler_timeout over the frozen run_bounded call with a server stalled after
the driver's channel connected (probe_rpc_stall_hist_rv2.py "connected"). Run:
pytest -p no:cacheprovider -o addopts= -o faulthandler_timeout=10 <this> --rootdir <worktree>"""
import os, pickle, signal, sys
WT = os.environ["WT"]
sys.path[:0] = [f"{WT}/tests/frozen/m69b", f"{WT}/src"]
from graphed.core.execution import SequentialRunner
from histserv_harness import bind, run_bounded, start_server, write_events
from test_histserv_lazy_init import _plan

def test_stalled_fill(tmp_path):
    plan = _plan(write_events(str(tmp_path / "e.parquet")), "fh", weight="wi")
    started = [start_server() for _ in plan.services]
    try:
        bound, _ = bind(plan, started)
        pickle.dumps(bound.process)
        os.kill(started[0].proc.pid, signal.SIGSTOP)
        run_bounded(lambda: SequentialRunner().run(bound).value, timeout_s=20.0)
    finally:
        for s in started:
            os.kill(s.proc.pid, signal.SIGCONT); s.kill()
