"""Reviewer mutants for the executors m69b round-5 delta (0008028..6877abc): the gate reads a ServiceSet's resolve
phase and the run's end. A hung selection (killed at TIMEOUT_S) counts as KILLED.

python mutants_exec_rv5.py ROOT PRISTINE [NAME ...]   (ROOT a copy of PRISTINE, restored after each mutant)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

BK = "src/graphed_executors/htcondor_backend/backend.py"
SV = "src/graphed_executors/submit/services.py"
X_SC = "tests/extra/m69b/test_m69b_schedulable.py"
X_GATE = "tests/extra/m69b/test_m69b_announce_gate.py"
F_OR = "tests/frozen/m69b/test_service_order.py"
TIMEOUT_S = 240


def x(name: str) -> str:
    return f"{X_SC}::{name}"


def g(name: str) -> str:
    return f"{X_GATE}::{name}"


GATE_O2 = g("test_a_need_beside_a_starting_service_releases_the_held_pilots_only_after_its_announce")
GATE_SET = g("test_a_need_between_a_set_s_services_leaves_the_pilots_held_to_its_last_announce")
GATE_O1 = g("test_a_driver_job_submits_its_pilots_after_its_service_node_announced")
NO_SUBMIT = x("test_a_need_beside_a_starting_service_submits_no_pilot_once_the_run_ends")
RELEASES = x("test_a_need_beside_a_later_plan_s_starting_service_releases_its_pilots_once_the_run_ends")
ONLY_CLOSE = x("test_once_the_pilots_are_submitted_only_close_ends_a_wait_for_them")
FROM_SUBMIT = x("test_a_need_deferred_by_a_service_start_times_its_wait_from_the_pilots_submit")
FROM_CALL = x("test_a_wait_called_after_the_pilots_submit_times_from_the_call")
ORDER_ROW = f"{F_OR}::test_service_jobs_go_before_the_pilots_and_later_plans_hold_them"

PHASE = (
    '            with getattr(self.backend, "starting_services", contextlib.nullcontext)():\n'
    "                resolved = [self._resolve(spec, stack) for spec in self.specs]\n"
    "            self._probe(resolved, stack)  # outside the phase: it needs a worker\n"
)
WAIT_END = "            if self._closing.is_set() and (submitted is None or self._closed):\n"
DEADLINE = "            if submitted is not None and time.monotonic() > max(called, submitted) + timeout:\n"

# (name, file, old, new, tests)
MUTANTS = [
    ("phase-per-resolve", SV, PHASE,
     '            phase = getattr(self.backend, "starting_services", contextlib.nullcontext)\n'
     "            resolved = []\n"
     "            for spec in self.specs:\n"
     "                with phase():\n"
     "                    resolved.append(self._resolve(spec, stack))\n"
     "            self._probe(resolved, stack)\n", [GATE_SET]),
    ("no-phase", SV, PHASE,
     "            resolved = [self._resolve(spec, stack) for spec in self.specs]\n"
     "            self._probe(resolved, stack)\n", [GATE_O2, GATE_SET]),
    ("probe-inside-the-phase", SV, PHASE,
     '            with getattr(self.backend, "starting_services", contextlib.nullcontext)():\n'
     "                resolved = [self._resolve(spec, stack) for spec in self.specs]\n"
     "                self._probe(resolved, stack)\n", [GATE_O1]),
    ("release-on-any-need", BK, "            if self._starting:\n                self._wanted = True\n",
     "            if False:\n                self._wanted = True\n", [GATE_O2, ORDER_ROW]),
    ("submit-while-closing", BK, "        if self._submitted_at is None and not self._closing.is_set():\n",
     "        if self._submitted_at is None:\n", [NO_SUBMIT]),
    ("wait-ignores-the-close", BK, WAIT_END, "            if False:\n", [NO_SUBMIT, ONLY_CLOSE]),
    ("no-release-while-closing", BK, "        if self._held:\n", "        if self._held and not self._closing.is_set():\n",
     [RELEASES]),
    ("last-phase-does-not-move", BK, '                    release_quietly("the pilots", self._move_pilots)\n',
     "                    pass\n", [GATE_O2, GATE_SET, FROM_SUBMIT, RELEASES]),
    ("wait-ends-only-unsubmitted", BK, WAIT_END, "            if self._closing.is_set() and submitted is None:\n",
     [ONLY_CLOSE]),
    ("wait-ends-at-any-close", BK, WAIT_END, "            if self._closing.is_set():\n", [ONLY_CLOSE]),
    ("deadline-from-the-call", BK, DEADLINE,
     "            if submitted is not None and time.monotonic() > called + timeout:\n", [FROM_SUBMIT]),
    ("deadline-from-the-submit", BK, DEADLINE,
     "            if submitted is not None and time.monotonic() > submitted + timeout:\n", [FROM_CALL]),
]

PY = os.path.expanduser("~/vibe-coding/cloud/.venv-m69b/bin/python")


def pytest(root: Path, environ: dict[str, str], tests: list[str], first: bool) -> tuple[int | str, str]:
    stop = ["-x"] if first else []
    try:
        run = subprocess.run(
            [PY, "-m", "pytest", "-p", "no:cacheprovider", "-q", *stop, "--tb=line", *tests],
            cwd=root, env=environ, capture_output=True, text=True, timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return f"hung>{TIMEOUT_S}s", out
    return run.returncode, run.stdout


def main() -> None:
    root, pristine = Path(sys.argv[1]), Path(sys.argv[2])
    only = set(sys.argv[3:])
    environ = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    for name, rel, old, new, tests in MUTANTS:
        if only and name not in only:
            continue
        path = root / rel
        text = path.read_text()
        assert text.count(old) == 1, (name, text.count(old))
        path.write_text(text.replace(old, new))
        try:
            code, out = pytest(root, environ, tests, True)
        finally:
            shutil.copyfile(pristine / rel, path)
        lines = [ln for ln in out.splitlines() if ln.strip()]
        failed = [ln for ln in lines if ln.startswith(("FAILED", "ERROR")) or "Error" in ln[:160]]
        verdict = "SURVIVED" if code == 0 else "KILLED"
        print(f"{verdict:8} {name:28} exit={code} | {' / '.join(lines[-2:])[-220:]}")
        for ln in failed[:2]:
            print(f"           {ln[:240]}")
        sys.stdout.flush()
    sel = sorted({t for n, _r, _o, _n, ts in MUTANTS if not only or n in only for t in ts})
    code, out = pytest(root, environ, sel, False)
    print(f"control (unmutated, {len(sel)} selections) exit={code} | {[ln for ln in out.splitlines() if ln.strip()][-1:]}")


if __name__ == "__main__":
    main()
