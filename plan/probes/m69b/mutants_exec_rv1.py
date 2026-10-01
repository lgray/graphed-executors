"""Reviewer mutants for executors m69b (d3f2820): one or more per load-bearing mechanism of §5.2.

python mutants_exec_rv1.py ROOT PRISTINE ENV [NAME ...]
ROOT is a scratch copy of the tree (mutated in place, restored from PRISTINE after each mutant); ENV picks the
mutants that run there (mac: .venv-m69b, hgg: .venv-m69b-hgg, pool: the minicondor container). Each mutant's
`old` must occur exactly once; a mutant is KILLED when its tests exit non-zero.
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
AN = "examples/hgg/analysis.py"
LPC = "examples/hgg/run_lpc.py"
X_PL = "tests/extra/m69b/test_m69b_placement.py"
X_SC = "tests/extra/m69b/test_m69b_schedulable.py"
F_MG = "tests/frozen/m69b/test_histserv_managed.py"
F_CL = "tests/frozen/m69b/test_histserv_cluster.py"
F_68B = "tests/frozen/m68b/test_cluster_service_job.py"
F_HGG = "tests/frozen/m69b/test_hgg_diagnostics.py"
X_HGG = "tests/extra/m69b/test_m69b_hgg.py"
X_LPC = "tests/extra/m69b/test_m69b_run_lpc.py"

# (name, env, file, old, new, tests)
MUTANTS = [
    ("narrow-refusal-gone", "mac", BK,
     "        if service_hosts is not None and not set(service_hosts) <= set(offered):",
     "        if False:", [F_CL, X_PL]),
    ("narrow-not-gating-cluster", "mac", BK,
     'isinstance(launcher, CondorPilots) and "cluster" in self.service_hosts:',
     'isinstance(launcher, CondorPilots) and "cluster" in profile.service_hosts:', [X_PL]),
    ("driver-each-not-sum", "mac", SV, "                self._driver_mb += size\n", "", [F_MG, X_SC]),
    ("driver-limit-ignored", "mac", SV,
     '        limit = getattr(self.backend, "driver_memory_mb", None)', "        limit = None", [F_MG, X_SC]),
    ("driver-fit-strict", "mac", SV, "        if total <= limit:", "        if total < limit:", [F_MG, X_SC]),
    ("injob-slot-ignored", "mac", BK,
     "            self.driver_memory_mb = None if slot is None else int(slot)",
     "            self.driver_memory_mb = None", [F_MG, X_SC]),
    ("win-dword-c_ulong", "mac", SV,
     '("dwLength", ctypes.c_uint32),  # DWORD', '("dwLength", ctypes.c_ulong),  # DWORD', [X_SC]),
    ("posix-pages-wrong", "mac", SV,
     'return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // _MIB',
     'return os.sysconf("SC_PHYS_PAGES") // _MIB', [F_MG, X_SC]),
    ("refusal-legs-dropped", "mac", SV,
     "            raise ServiceUnavailable(spec.name, {**legs, **exc.legs}) from exc", "            raise",
     [X_SC]),
    ("deadline-from-submit", "mac", BK,
     "        deadline: float | None = None",
     "        deadline: float | None = time.monotonic() + spec.timeout_s", [X_SC, F_68B]),
    ("idle-log-every-poll", "mac", BK, "                if now - logged >= IDLE_LOG_S:", "                if True:",
     [X_SC]),
    ("dynamic-slots-kept", "mac", HS, ' if ad.get("SlotType") != "Dynamic"]', "]", [X_SC]),
    ("as-whole-noop-unit", "mac", HS, '    if slot.get("PartitionableSlot"):', "    if False:", [X_SC]),
    ("no-ads-guard-gone-unit", "mac", BK,
     "            refusal = job.match_refusal(machines) if machines else None",
     "            refusal = job.match_refusal(machines)", [X_SC, X_PL]),
    # pool: the live condor rows
    ("as-whole-noop", "pool", HS, '    if slot.get("PartitionableSlot"):', "    if False:",
     [F_CL + "::test_a_server_behind_a_busy_pool_waits_and_its_timeout_counts_from_its_start"]),
    ("match-always", "pool", HS, "        if any(ads[0].symmetricMatch(slot) for slot in slots):", "        if True:",
     [F_CL + "::test_a_server_no_slot_can_hold_is_removed_unrun_and_refused",
      F_CL + "::test_a_requirement_no_slot_meets_is_removed_unrun_and_refused"]),
    ("match-request-only", "pool", HS,
     "        if any(ads[0].symmetricMatch(slot) for slot in slots):",
     '        if any(int(ads[0].eval("RequestMemory")) <= int(slot.get("Memory", 0)) for slot in slots):',
     [F_CL + "::test_a_requirement_no_slot_meets_is_removed_unrun_and_refused"]),
    ("no-ads-guard-gone", "pool", BK,
     "            refusal = job.match_refusal(machines) if machines else None",
     "            refusal = job.match_refusal(machines)", [F_CL, X_SC, X_PL]),
    ("deadline-from-submit-live", "pool", BK,
     "        deadline: float | None = None",
     "        deadline: float | None = time.monotonic() + spec.timeout_s",
     [F_CL + "::test_a_server_behind_a_busy_pool_waits_and_its_timeout_counts_from_its_start"]),
    # hgg: the diagnostics and the LPC runner
    ("njets-binning", "hgg", AN, '"n_jets": ("n_jets", (8, -0.5, 7.5)),', '"n_jets": ("n_jets", (8, -0.5, 8.5)),',
     [F_HGG]),
    ("unweighted", "hgg", AN, '        hist.fill(record[column], weight=record["weight"])',
     "        hist.fill(record[column])", [F_HGG]),
    ("resolve-skipped", "hgg", AN,
     '        return {**value, "diagnostics": self.histograms.resolve_services(value["diagnostics"])}',
     "        return value", [F_HGG]),
    ("context-not-passed", "hgg", AN,
     "{ds: dataset_plan(ds, files, year=year, out=out, context=context) for ds, files in fileset.items()}",
     "{ds: dataset_plan(ds, files, year=year, out=out) for ds, files in fileset.items()}", [F_HGG]),
    ("lpc-placement-ignored", "hgg", LPC, "            service_hosts=(args.placement,),",
     "            service_hosts=None,", [X_LPC]),
    ("lpc-slot-without-servers", "hgg", LPC,
     "    return DRIVER_MB + pilots * pilot_mb + sum(int(mb) for _name, mb, _predicted, _n in ctx.servers())",
     "    return DRIVER_MB + pilots * pilot_mb", [X_LPC]),
    ("report-drops-histograms", "hgg", "examples/hgg/run_local.py",
     '        json.dump({ds: v["diagnostics"] for ds, v in value.items()}, f, default=uhi.io.json.default)',
     "        json.dump({}, f)", [X_HGG]),
]

PY = {
    "mac": os.path.expanduser("~/vibe-coding/cloud/.venv-m69b/bin/python"),
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
        failed = [ln for ln in run.stdout.splitlines() if ln.startswith(("FAILED", "ERROR")) or ": AssertionError" in ln or "Error" in ln[:120]]
        verdict = "KILLED" if run.returncode != 0 else "SURVIVED"
        print(f"{verdict:8} {name:28} exit={run.returncode} | {' / '.join(tail)[-260:]}")
        for ln in failed[:2]:
            print(f"           {ln[:240]}")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
