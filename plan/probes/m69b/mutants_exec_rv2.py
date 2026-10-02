"""Reviewer mutants for the executors m69b round-2 delta (d3f2820..df4d059): one per fix (B1, M1, M2, m1, m2).

python mutants_exec_rv2.py ROOT PRISTINE ENV [NAME ...]
ROOT is a scratch copy of the tree (mutated in place, restored from PRISTINE after each mutant); ENV picks the
mutants that run there (mac: .venv-m69b, dask: .venv-m69b-dask, hgg: .venv-m69b-hgg, pool: the minicondor
container). Each mutant's `old` must occur exactly once; a mutant is KILLED when its tests exit non-zero.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

BK = "src/graphed_executors/htcondor_backend/backend.py"
HS = "src/graphed_executors/htcondor_backend/services.py"
SV = "src/graphed_executors/submit/services.py"
LPC = "examples/hgg/run_lpc.py"
X_SC = "tests/extra/m69b/test_m69b_schedulable.py"
X_DK = "tests/extra/m69b/test_m69b_dask_driver_check.py"
X_LPC = "tests/extra/m69b/test_m69b_run_lpc.py"
CLOSE = X_SC + "::test_close_ends_a_wait_for_a_slot_removing_the_job"
NO_ADS = X_SC + "::test_a_pool_whose_collector_lists_no_slot_submits_and_waits"
TOTALS = X_SC + "::test_a_partitionable_slot_is_matched_at_its_totals"
DISK_LIVE = X_SC + "::test_a_job_waiting_only_on_a_busy_node_s_disk_matches"
TIMES = X_LPC + "::test_each_server_s_status_line_names_when_it_was_submitted_and_ready"

# (name, env, file, old, new, tests)
MUTANTS = [
    # M1
    ("runner-close-no-stop", "mac", BK, "        self.backend.stop_waiting()\n        super().close()",
     "        super().close()", [CLOSE]),
    ("closing-check-gone", "mac", BK, "                if self._closing.is_set():", "                if False:",
     [CLOSE]),
    ("backend-close-no-stop", "mac", BK, "        self.stop_waiting()\n        self._stack.close()",
     "        self._stack.close()", [X_SC]),
    # M2
    ("disk-not-whole", "mac", HS, '            ("TotalSlotDisk", "Disk"),\n', "", [TOTALS]),
    ("disk-not-whole-live", "pool", HS, '            ("TotalSlotDisk", "Disk"),\n', "", [DISK_LIVE]),
    # m2
    ("no-ads-guard-gone", "mac", HS,
     "        if not machines:  # a collector that lists no slot says nothing about the pool: submit and wait\n"
     "            return None\n", "", [NO_ADS]),
    # m1
    ("servertimes-gone", "hgg", LPC, "    handler.setFormatter(ServerTimes(logging.BASIC_FORMAT))",
     "    handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))", [TIMES]),
    ("servertimes-ready-dropped", "hgg", LPC,
     'return f"{line} started_at={status.started_at} ready_at={status.ready_at}"',
     'return f"{line} started_at={status.started_at}"', [TIMES]),
    # B1: the dask job's new file discriminates the driver check it gates
    ("driver-limit-ignored", "dask", SV, '        limit = getattr(self.backend, "driver_memory_mb", None)',
     "        limit = None", [X_DK]),
    ("driver-fit-strict", "dask", SV, "        if total <= limit:", "        if total < limit:", [X_DK]),
    ("posix-pages-wrong", "dask", SV,
     'return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // _MIB',
     'return os.sysconf("SC_PHYS_PAGES") // _MIB', [X_DK]),
]

PY = {
    "mac": os.path.expanduser("~/vibe-coding/cloud/.venv-m69b/bin/python"),
    "dask": os.path.expanduser("~/vibe-coding/cloud/.venv-m69b-dask/bin/python"),
    "hgg": os.path.expanduser("~/vibe-coding/cloud/.venv-m69b-hgg/bin/python"),
    "pool": "/opt/venv/bin/python",
}


def main() -> None:
    root, pristine, env = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    only = set(sys.argv[4:])
    environ = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    if env == "hgg":
        environ["GRAPHED_HGG_REQUIRED"] = "1"
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
    # control: the unmutated tree passes the same selections
    sel = sorted({t for n, w, _r, _o, _n, ts in MUTANTS if w == env and (not only or n in only) for t in ts})
    run = subprocess.run([PY[env], "-m", "pytest", "-p", "no:cacheprovider", "-q", *sel], cwd=root, env=environ,
                         capture_output=True, text=True)
    print(f"control (unmutated, {len(sel)} selections) exit={run.returncode} | "
          f"{[ln for ln in run.stdout.splitlines() if ln.strip()][-1]}")


if __name__ == "__main__":
    main()
