"""Reviewer mutants for the executors m69b round-3 delta (40470e6..67ba8f2): the new extra rows and the decisions
the dispatcher named (the _closing check before the ad, wait_for_pilots(n >= min_pilots) as the first need's
wait, a ServiceJob recorded before its submit under the lock).

python mutants_exec_rv3.py ROOT PRISTINE ENV [NAME ...]   (as mutants_exec_rv2.py; ENV mac or pool)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

BK = "src/graphed_executors/htcondor_backend/backend.py"
HS = "src/graphed_executors/htcondor_backend/services.py"
LA = "src/graphed_executors/htcondor_backend/launch.py"
X_SC = "tests/extra/m69b/test_m69b_schedulable.py"
F_OR = "tests/frozen/m69b/test_service_order.py"
F_68B = "tests/frozen/m68b/test_cluster_service_job.py"


def x(name: str) -> str:
    return f"{X_SC}::{name}"


CLOSE_ROW = f"{F_OR}::test_close_waits_for_a_waiting_server_and_an_error_in_the_block_ends_the_wait"
ORDER_ROW = f"{F_OR}::test_service_jobs_go_before_the_pilots_and_later_plans_hold_them"
FIRST_NEED = f"{F_OR}::test_the_first_need_waits_for_pilots_past_a_service_s_timeout"
DEFERS = f"{F_OR}::test_only_a_backend_whose_services_are_jobs_defers_its_pilots"
RECORDER = [CLOSE_ROW, ORDER_ROW, FIRST_NEED, DEFERS]

# (name, env, file, old, new, tests)
MUTANTS = [
    ("backend-close-no-remove", "mac", BK,
     '        for key, job in jobs:\n            release_quietly(f"service job {key}", job.stop)\n', "",
     [x("test_backend_close_removes_a_waiting_service_job_before_it_returns")]),
    ("stop-unserialized", "mac", HS, "        with self._lock:\n            self._stopped = True\n            self._stack.close()",
     "        self._stopped = True\n        self._stack.close()", [x("test_a_second_stop_returns_only_after_the_first_removal")]),
    ("stopped-check-gone", "mac", HS, "            if self._stopped:", "            if False:",
     [x("test_a_job_stopped_before_its_submit_is_never_submitted")]),
    ("closing-submit-check-gone", "mac", BK, "                if self._closing.is_set():\n                    raise RuntimeError(f\"service {spec.name!r} ({key}) not submitted",
     "                if False:\n                    raise RuntimeError(f\"service {spec.name!r} ({key}) not submitted",
     [x("test_no_service_job_is_submitted_once_the_waits_are_stopped")]),
    ("alive-held-not-counted", "mac", LA, ' or str(ad.get("HoldReason", "")).startswith(HOLD_REASON) for ad in ads)',
     " for ad in ads)", [x("test_alive_counts_a_pilot_graphed_held_and_not_one_the_user_held")]),
    ("alive-any-hold", "mac", LA, '.startswith(HOLD_REASON) for ad in ads)', '.startswith("") for ad in ads)',
     [x("test_alive_counts_a_pilot_graphed_held_and_not_one_the_user_held")]),
    ("claim-parent-lost", "mac", HS, '    parent = name.rsplit("_", 1)[0] + at + host', "    parent = remote",
     [x("test_a_running_job_s_claim_leaves_the_slot_it_runs_in")]),
    ("claim-request-first", "mac", HS, '(f"{r}Provisioned", f"Request{r}")', '(f"Request{r}", f"{r}Provisioned")',
     [x("test_a_running_job_s_claim_leaves_the_slot_it_runs_in")]),
    # the dispatcher's three
    ("closing-after-ad-check", "mac", BK,
     "            if deadline is None and self._closing.is_set():  # before the ad check: close() removes the job",
     "            if deadline is None and self._closing.is_set() and counts_as_alive(ad):",
     [X_SC, CLOSE_ROW]),
    ("any-wait-is-the-first-need", "mac", BK, "        self._waited = self._waited or n >= self.min_pilots",
     "        self._waited = True", [X_SC, *RECORDER]),
    ("no-wait-is-the-first-need", "mac", BK, "        self._waited = self._waited or n >= self.min_pilots",
     "        self._waited = self._waited", [X_SC, *RECORDER]),
    ("no-wait-is-the-first-need-m66", "mac", BK, "        self._waited = self._waited or n >= self.min_pilots",
     "        self._waited = self._waited", ["tests/frozen/m66", "tests/frozen/m67", "tests/extra/m66"]),
    ("record-after-submit", "mac", BK,
     "                self._services[key] = job\n            stack.callback(self._services.pop, key, None)\n"
     "            stack.callback(release_quietly, f\"service job {key}\", job.stop)\n            job.submit()\n",
     "            stack.callback(self._services.pop, key, None)\n"
     "            stack.callback(release_quietly, f\"service job {key}\", job.stop)\n            job.submit()\n"
     "            self._services[key] = job\n", [X_SC, *RECORDER]),
    # pool: the real-schedd release row
    ("hold-str-reason", "pool", LA, "reason=CondorReason(HOLD_REASON))", "reason=HOLD_REASON)",
     [x("test_a_real_schedd_releases_graphed_s_hold_and_not_the_user_s")]),
    ("release-any-hold", "pool", LA, '        constraint = f"{self._constraint} && JobStatus == 5 && {ours}"',
     '        constraint = f"{self._constraint} && JobStatus == 5"',
     [x("test_a_real_schedd_releases_graphed_s_hold_and_not_the_user_s")]),
]

PY = {
    "mac": os.path.expanduser("~/vibe-coding/cloud/.venv-m69b/bin/python"),
    "pool": "/opt/venv/bin/python",
}


def main() -> None:
    root, pristine, env = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    only = set(sys.argv[4:])
    environ = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    for name, where, rel, old, new, tests in MUTANTS:
        if where != env or (only and name not in only):
            continue
        path = root / rel
        text = path.read_text()
        assert text.count(old) == 1, (name, text.count(old))
        path.write_text(text.replace(old, new))
        try:
            run = subprocess.run(
                [PY[env], "-m", "pytest", "-p", "no:cacheprovider", "-q", "-x", "--tb=line", "-o",
                 "faulthandler_timeout=600", *tests],
                cwd=root, env=environ, capture_output=True, text=True,
            )
        finally:
            shutil.copyfile(pristine / rel, path)
        tail = [ln for ln in run.stdout.splitlines() if ln.strip()][-3:]
        failed = [ln for ln in run.stdout.splitlines() if ln.startswith(("FAILED", "ERROR")) or ": AssertionError" in ln
                  or "Error" in ln[:120]]
        verdict = "KILLED" if run.returncode != 0 else "SURVIVED"
        print(f"{verdict:8} {name:28} exit={run.returncode} | {' / '.join(tail)[-260:]}")
        for ln in failed[:2]:
            print(f"           {ln[:240]}")
        sys.stdout.flush()
    sel = sorted({t for n, w, _r, _o, _n, ts in MUTANTS if w == env and (not only or n in only) for t in ts})
    run = subprocess.run([PY[env], "-m", "pytest", "-p", "no:cacheprovider", "-q", *sel], cwd=root, env=environ,
                         capture_output=True, text=True)
    print(f"control (unmutated, {len(sel)} selections) exit={run.returncode} | "
          f"{[ln for ln in run.stdout.splitlines() if ln.strip()][-1]}")


if __name__ == "__main__":
    main()
