"""m69b ordering TEST_SANITY: mutants of the sanity variant (variant_order_sanity.diff over 6225cd5's src),
each one plan decision broken, run against the recorder rows of tests/frozen/m69b/test_service_order.py.

usage: python mutants_order_sanity.py <variant tree> <python>; prints one line per mutant: KILLED/SURVIVED and
the failing ids."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

B = "src/graphed_executors/htcondor_backend/backend.py"
L = "src/graphed_executors/htcondor_backend/launch.py"
T = "tests/frozen/m69b/test_service_order.py::"

MUTANTS = {
    # a hold per service call (plan 3 holds twice)
    "hold-per-service": (B, "                if not self._held:\n                    self.launcher.hold_queued()\n",
                         "                if True:\n                    self.launcher.hold_queued()\n",
                         "test_service_jobs_go_before_the_pilots_and_later_plans_hold_them"),
    # rv1's dispatch: each host_service call releases its own hold when it returns
    "release-at-return": (B, "        return self._host_service_held(spec, scope, machines, key, secret, own)\n",
                          "        try:\n            return self._host_service_held(spec, scope, machines, key, secret, own)\n"
                          "        finally:\n            if self._held:\n                self._held = False\n"
                          "                self.launcher.release_held()\n",
                          "test_service_jobs_go_before_the_pilots_and_later_plans_hold_them"),
    "hold-without-reason": (L, ",\n                         reason=self.HOLD_REASON)", ")",
                            "test_service_jobs_go_before_the_pilots_and_later_plans_hold_them"),
    "release-any-user-hold": (L, ' && HoldReason == "{self.HOLD_REASON}"', "",
                              "test_service_jobs_go_before_the_pilots_and_later_plans_hold_them"),
    "hold-running-too": (L, 'f"{self._constraint} && JobStatus == 1",', 'f"{self._constraint}",',
                         "test_service_jobs_go_before_the_pilots_and_later_plans_hold_them"),
    "no-hold": (B, "                    self.launcher.hold_queued()\n", "",
                "test_service_jobs_go_before_the_pilots_and_later_plans_hold_them"),
    "pilots-after-service-submit": (B, "            job.submit(on_submit=lambda: self._services.__setitem__(key, job))\n",
                                    "            job.submit(on_submit=lambda: self._services.__setitem__(key, job))\n"
                                    "            self._submit_pilots()\n",
                                    "test_service_jobs_go_before_the_pilots_and_later_plans_hold_them"),
    "first-need-no-wait": (B, "            self.wait_for_pilots(self.min_pilots)\n", "",
                           "test_the_first_need_waits_for_pilots_past_a_service_s_timeout"),
    "defer-driver-hosted": (B, '(in_job is None and "cluster" in self.service_hosts)', "(in_job is None)",
                            "test_only_a_backend_whose_services_are_jobs_defers_its_pilots"),
    "announced-not-deferred": (B, "bool(self._announced) or (in_job", "(in_job",
                               "test_only_a_backend_whose_services_are_jobs_defers_its_pilots"),
    "close-keeps-secret": (B, '                stack.callback(release_quietly, "the pilots\' secret", launcher._secret.unlink, True)\n',
                           "",
                           "test_a_deferred_spool_failure_removes_its_cluster_and_close_drops_the_secret"),
    "close-ends-wait": (B, "    def close(self) -> None:  # SANITY VARIANT: the backend closes whether",
                        "    def close(self) -> None:  # SANITY VARIANT: the backend closes whether\n"
                        "        self.backend.stop_waiting()\n        # ",
                        "test_close_waits_for_a_waiting_server_and_an_error_in_the_block_ends_the_wait"),
    "exit-no-stop": (B, "        if exc[0] is not None:\n            self.backend.stop_waiting()\n", "",
                     "test_close_waits_for_a_waiting_server_and_an_error_in_the_block_ends_the_wait"),
}


def main(tree: str, python: str) -> None:
    root = Path(tree)
    for name, (rel, old, new, test) in MUTANTS.items():
        path = root / rel
        src = path.read_text()
        assert src.count(old) == 1, (name, src.count(old))
        path.write_text(src.replace(old, new))
        try:
            out = subprocess.run(
                [python, "-m", "pytest", "-p", "no:cacheprovider", "-q", "-x", "-o", "faulthandler_timeout=300",
                 T + test], cwd=root, capture_output=True, text=True, timeout=900,
            ).stdout
        finally:
            path.write_text(src)
        failed = [line.split(" - ")[0] for line in out.splitlines() if line.startswith(("FAILED", "ERROR"))]
        first_e = next((line.strip() for line in out.splitlines() if line.startswith("E ")), "")
        verdict = "KILLED" if failed else "SURVIVED"
        print(f"{name}: {verdict} {failed} {first_e[:160]}", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
