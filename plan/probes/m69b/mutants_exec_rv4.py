"""Reviewer mutants for the executors m69b round-4 delta (67ba8f2..0008028): the announce gate, the driver job's wait
inside its ServiceSet, the wait counted from the submit, the r3 exit rows, and ServiceJob.stop() done once.

python mutants_exec_rv4.py ROOT PRISTINE ENV [NAME ...]   (as mutants_exec_rv3.py; ENV mac)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

BK = "src/graphed_executors/htcondor_backend/backend.py"
HS = "src/graphed_executors/htcondor_backend/services.py"
DR = "src/graphed_executors/htcondor_backend/driver.py"
X_SC = "tests/extra/m69b/test_m69b_schedulable.py"
X_GATE = "tests/extra/m69b/test_m69b_announce_gate.py"
F_OR = "tests/frozen/m69b/test_service_order.py"


def x(name: str) -> str:
    return f"{X_SC}::{name}"


def g(name: str) -> str:
    return f"{X_GATE}::{name}"


CLOSE_ROW = f"{F_OR}::test_close_waits_for_a_waiting_server_and_an_error_in_the_block_ends_the_wait"
ORDER_ROW = f"{F_OR}::test_service_jobs_go_before_the_pilots_and_later_plans_hold_them"
FIRST_NEED = f"{F_OR}::test_the_first_need_waits_for_pilots_past_a_service_s_timeout"
DEFERS = f"{F_OR}::test_only_a_backend_whose_services_are_jobs_defers_its_pilots"
RECORDER = [CLOSE_ROW, ORDER_ROW, FIRST_NEED, DEFERS]
GATE_O2 = g("test_a_need_beside_a_waiting_server_releases_the_held_pilots_only_after_its_announce")
GATE_O1 = g("test_a_driver_job_submits_its_pilots_after_its_service_node_announced")
GATE_EXIT1 = g("test_a_driver_job_whose_pilots_never_start_exits_1")
DEADLINE = x("test_a_need_beside_a_waiting_server_counts_its_timeout_from_the_pilots_submit")
BELOW_MIN = x("test_a_wait_below_min_pilots_leaves_the_first_need_s_wait_to_come")
STOP_ROW = x("test_a_second_stop_returns_only_after_the_first_removal")

WAIT_IN_SET = (
    "                with ServiceSet(plan.services, runner.backend, endpoints=given) as endpoints:\n"
    "                    live = runner.wait_for_pilots()  # after the SERVICE nodes' announces; a failure exits 1\n"
    '                    print(f"{live} pilots live after {time.monotonic() - start:.1f}s", file=log, flush=True)\n'
    "                    runner.services = endpoints\n"
    "                    try:\n"
    "                        result, code = runner.run(plan), EXIT_DONE\n"
)
STOP_BODY = (
    "        with self._lock:\n"
    "            if self._stopped:  # Windows refuses an unlink racing another one: access denied\n"
    "                return\n"
    "            self._stopped = True\n"
    "            self._stack.close()\n"
    "            if self.dir is not None:\n"
    "                (self.dir / SECRET_FILE).unlink(missing_ok=True)\n"
)

# (name, file, old, new, tests)
MUTANTS = [
    ("release-on-any-need", BK,
     "            if self._serving:\n                self._wanted = True\n            else:\n                self._move_pilots()\n",
     "            self._move_pilots()\n", [GATE_O2, ORDER_ROW]),
    ("last-server-does-not-move", BK, '                        release_quietly("the pilots", self._move_pilots)\n',
     "                        pass\n", [GATE_O2, DEADLINE, *RECORDER]),
    ("driver-waits-before-services", DR, WAIT_IN_SET,
     "                live = runner.wait_for_pilots()\n"
     '                print(f"{live} pilots live after {time.monotonic() - start:.1f}s", file=log, flush=True)\n'
     "                with ServiceSet(plan.services, runner.backend, endpoints=given) as endpoints:\n"
     "                    runner.services = endpoints\n"
     "                    try:\n"
     "                        result, code = runner.run(plan), EXIT_DONE\n",
     [GATE_O1]),
    ("wait-inside-the-run-try", DR, WAIT_IN_SET,
     "                with ServiceSet(plan.services, runner.backend, endpoints=given) as endpoints:\n"
     "                    runner.services = endpoints\n"
     "                    try:\n"
     "                        live = runner.wait_for_pilots()\n"
     '                        print(f"{live} pilots live after {time.monotonic() - start:.1f}s", file=log, flush=True)\n'
     "                        result, code = runner.run(plan), EXIT_DONE\n",
     [GATE_EXIT1]),
    ("closing-after-ad-check", BK,
     "            if deadline is None and self._closing.is_set():  # before the ad check: close() removes the job",
     "            if deadline is None and self._closing.is_set() and counts_as_alive(ad):",
     [x("test_backend_close_removes_a_waiting_service_job_before_it_returns"), CLOSE_ROW]),
    ("any-wait-is-the-first-need", BK, "        self._waited = self._waited or n >= self.min_pilots",
     "        self._waited = True", [BELOW_MIN]),
    ("no-wait-is-the-first-need", BK, "        self._waited = self._waited or n >= self.min_pilots",
     "        self._waited = self._waited", [BELOW_MIN]),
    ("deadline-from-the-call", BK, "time.monotonic() > max(called, submitted) + timeout",
     "time.monotonic() > called + timeout", [DEADLINE, FIRST_NEED]),
    # 67ba8f2's form: a deadline from the call that runs while the submit is put off
    ("deadline-from-the-call-unguarded", BK,
     "            if submitted is not None and time.monotonic() > max(called, submitted) + timeout:",
     "            if time.monotonic() > called + timeout:", [DEADLINE]),
    # the other side of the max: a later wait on pilots submitted long ago
    ("deadline-from-the-submit", BK, "time.monotonic() > max(called, submitted) + timeout",
     "time.monotonic() > submitted + timeout",
     [X_SC, X_GATE, *RECORDER, "tests/frozen/m66", "tests/frozen/m67", "tests/extra/m66", "tests/extra/m67"]),
    ("unlink-every-stop", HS,
     "            if self._stopped:  # Windows refuses an unlink racing another one: access denied\n                return\n",
     "            if self._stopped:\n                if self.dir is not None:\n"
     "                    (self.dir / SECRET_FILE).unlink(missing_ok=True)\n                return\n", [STOP_ROW]),
    ("unlink-outside-the-lock", HS, STOP_BODY,
     "        with self._lock:\n            self._stopped = True\n            self._stack.close()\n"
     "        if self.dir is not None:\n            (self.dir / SECRET_FILE).unlink(missing_ok=True)\n", [STOP_ROW]),
    # r3 exit item 3, still without a row?
    ("record-after-submit", BK,
     "                self._services[key] = job\n            stack.callback(self._services.pop, key, None)\n"
     "            stack.callback(release_quietly, f\"service job {key}\", job.stop)\n            job.submit()\n",
     "            stack.callback(self._services.pop, key, None)\n"
     "            stack.callback(release_quietly, f\"service job {key}\", job.stop)\n            job.submit()\n"
     "            self._services[key] = job\n", [X_SC, X_GATE, *RECORDER]),
]

PY = os.path.expanduser("~/vibe-coding/cloud/.venv-m69b/bin/python")


def pytest(root: Path, environ: dict[str, str], tests: list[str], first: bool) -> subprocess.CompletedProcess[str]:
    stop = ["-x"] if first else []
    return subprocess.run(
        [PY, "-m", "pytest", "-p", "no:cacheprovider", "-q", *stop, "--tb=line", "-o", "faulthandler_timeout=600", *tests],
        cwd=root, env=environ, capture_output=True, text=True,
    )


def main() -> None:
    root, pristine = Path(sys.argv[1]), Path(sys.argv[2])
    only = set(sys.argv[4:])
    environ = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    for name, rel, old, new, tests in MUTANTS:
        if only and name not in only:
            continue
        path = root / rel
        text = path.read_text()
        assert text.count(old) == 1, (name, text.count(old))
        path.write_text(text.replace(old, new))
        try:
            run = pytest(root, environ, tests, True)
        finally:
            shutil.copyfile(pristine / rel, path)
        tail = [ln for ln in run.stdout.splitlines() if ln.strip()][-3:]
        failed = [ln for ln in run.stdout.splitlines() if ln.startswith(("FAILED", "ERROR")) or "Error" in ln[:160]]
        verdict = "KILLED" if run.returncode != 0 else "SURVIVED"
        print(f"{verdict:8} {name:28} exit={run.returncode} | {' / '.join(tail)[-260:]}")
        for ln in failed[:2]:
            print(f"           {ln[:240]}")
        sys.stdout.flush()
    sel = sorted({t for n, _r, _o, _n, ts in MUTANTS if not only or n in only for t in ts})
    run = pytest(root, environ, sel, False)
    print(f"control (unmutated, {len(sel)} selections) exit={run.returncode} | "
          f"{[ln for ln in run.stdout.splitlines() if ln.strip()][-1]}")


if __name__ == "__main__":
    main()
