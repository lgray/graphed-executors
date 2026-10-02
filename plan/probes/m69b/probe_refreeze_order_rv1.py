"""The §5.2 "Ordering" refreeze edits, run on the full-design variant: each edited id passes unmutated and each
fails under the mutant of the property it guards.

argv[1]: a tree holding the full-design variant (``probe_order_variant_dag.txt`` + hold/release, claims-aware
match, ``close()``/``__exit__`` as §5.2) with the three edits applied to its frozen m68a/m68b copies.
Each leg rewrites one source string, runs the five ids under that tree's ``src``, and restores the file.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

TREE = Path(sys.argv[1])
IDS = [
    "tests/frozen/m68a/test_services_sites.py::test_a_failed_spool_leaves_no_cluster_and_no_port",
    "tests/frozen/m68b/test_cluster_service_job.py::"
    "test_host_service_forgets_its_announce_secret_when_construction_refuses",
    "tests/frozen/m68b/test_cluster_service_job.py::test_host_service_returns_the_announced_endpoint_and_releases_in_order",
]
BACKEND = "src/graphed_executors/htcondor_backend/backend.py"
LAUNCH = "src/graphed_executors/htcondor_backend/launch.py"
MUTANTS: dict[str, tuple[str, str, str]] = {
    "none": (BACKEND, "", ""),
    # pilots submitted at construction (the deferral undone); the secret id then dies on the recorder's
    # JobAction, which has no Hold (the variant's later-plan hold runs once pilots exist)
    "pilots-at-construction": (BACKEND, "cluster = isinstance(launcher, CondorPilots) and (",
                               "cluster = False and isinstance(launcher, CondorPilots) and ("),
    # a failed spool leaves its cluster queued
    "spool-leaves-cluster": (LAUNCH, 'stack.callback(release_quietly, f"cluster {constraint}", self._remove, htc, '
                                     "schedd, constraint)", "pass"),
    # a service job is submitted before its inputs are checked
    "service-before-check": (BACKEND, "            job = ServiceJob(spec, self.launcher, key=key, url=self._server.url, "
                                      "secret=secret)\n",
                             "            self.launcher._submit(_launch._htcondor(), self.launcher._schedd, "
                             '{"JobBatchName": f"graphed-service-{key}"}, 1, stack)\n'
                             "            job = ServiceJob(spec, self.launcher, key=key, url=self._server.url, "
                             "secret=secret)\n"),
    # the service job announces somewhere other than the task server
    "url-not-task-server": (BACKEND, "job = ServiceJob(spec, self.launcher, key=key, url=self._server.url, secret=secret)",
                            'job = ServiceJob(spec, self.launcher, key=key, url=self._server.url.rsplit(":", 1)[0] '
                            '+ ":1", secret=secret)'),
}

for name, (rel, old, new) in MUTANTS.items():
    path = TREE / rel
    original = path.read_text()
    if old:
        assert original.count(old) == 1, (name, original.count(old))
        path.write_text(original.replace(old, new))
    try:
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "-rf", *IDS],
            cwd=TREE, capture_output=True, text=True, env={"PYTHONPATH": str(TREE / "src"),
                                                           "PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
        )
    finally:
        path.write_text(original)
    failed = sorted({re.sub(r"^FAILED tests/frozen/", "", ln).split(" - ")[0]
                     for ln in done.stdout.splitlines() if ln.startswith("FAILED")})
    tail = done.stdout.strip().splitlines()[-1]
    print(f"{name}: {tail}")
    for f in failed:
        cause = re.search(rf"FAILED tests/frozen/{re.escape(f)} - (.{{0,90}})", done.stdout)
        print(f"    FAILED {f}  [{cause.group(1) if cause else ''}]")
