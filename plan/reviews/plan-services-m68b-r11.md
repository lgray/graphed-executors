**NOT CLEAN**

# Review r11: `plan-services.md` §3.3 executors m68b, whole-unit read

Scope: the whole m68b unit, read end to end as the implementer and the test author would.
- §3.3.
- The lines of the §3 preamble, D1–D10, §6, §7, §8 and §9 that bind m68b.
- §3.1 (m68a) is taken as given.

Snapshot: `reviews/plan-services-m68b-r11-snapshot.md`, identical to the plan at review time. Line numbers below refer to it.
Code: graphed-executors main `c2298d7`; graphed main `6e9e55e` (`ServiceSpec` is merged there).

Evidence added this round is under `probes/m68b/probe_r11_*.txt`.
- **Re-runs** (`probe_r11_reruns.txt`):
  - `probe_service_job.py` on `htcondor/mini` 25.13.2 reproduces A–D.
  - `probe_announce_rules.py`, run locally, reproduces L1–L7. L7 gives `[1]*10` starts.
  - `probe_dag_service.py` reproduces R, X and U: node and exit codes, `RemoveReason`, and `.old` rescue files. Exit item 5 covers one probe defect in R.
- **New measurements:**
  - `probe_r11_coverage.txt`: coverage attribution for a module run by path.
  - `probe_r11_dag_names.txt`: a SERVICE node named `driver`.
  - `probe_r11_fromdag_versions.txt`: the `from_dag` description under the 25.13.2 bindings and the 25.14.1 PyPI wheel.
- **Cleanup:** every container is removed and no process from this review is left running.

## Design findings

**M25 · §3.3 L451-453 and the `test_cluster_service_job.py` row (L551), with §6 L760-773 · the frozen subprocess legs do
not say how `announce.py` is invoked. The job's form (a file run by path) is never measured by test-htcondor's
coverage, so the per-file and diff gates cannot pass on `announce.py`.**
- **The measurement:**
  - `.coveragerc-htcondor:8-9` gives `source = graphed_executors.htcondor_backend`, which is a package name, not a
    path.
  - test-htcondor gates every file in that package at ≥90% (`ci.yml:308`, `scripts/coverage_gate.py`). It also gates
    changed lines at 98% (`ci.yml:319-320`, `--include "src/graphed_executors/htcondor_backend/**/*.py"`).
  - `announce.py` (~130 lines) lives in that package.
  - `probe_r11_coverage.txt` uses the same setup (coverage 7.16.2, a `source = pkg.sub` rc, `COVERAGE_PROCESS_START`
    plus the `.pth` hook that ci.yml writes):
    - running the module file by path gives "No data to report";
    - running a transferred copy gives the same;
    - positive control: `python -m pkg.sub.ann` measures the file (73%).
  - An unimported file in a source package is reported at 0%.
- **What the plan leaves open:**
  - L453 has the job run `announce.py service.json` by path, as a transferred copy.
  - L551 says only "run as a subprocess".
  - The row's only other `announce.py` check is an AST parse, which executes nothing.
- **Why it changes code:**
  - The test author writes the subprocess argv. The natural choice is to mirror `service.sh`: `[python, <path>/announce.py, service.json]`.
  - That leaves `announce.py` at about 0% from the frozen suite. The implementer cannot raise it without editing
    frozen tests: B.3 requires covering hits to come from the frozen suite, and the live legs run the job's
    unmeasured copy.
  - The result is a TEST_DISPUTE or gate-stuck, from a decision the plan did not make.
- **Closed when the plan fixes the invocation:**
  - The frozen subprocess legs run
    `[sys.executable, "-m", "graphed_executors.htcondor_backend.announce", "service.json"]`. This is the same code
    the job runs by path, because `announce.py` has a `__main__` guard and imports only the stdlib.
  - `announce.py`'s SIGTERM handler leaves through `sys.exit`, so the coverage data is saved.
  - The alternative is to name the file's path in `.coveragerc-htcondor`'s `source`. The plan picks one.
- **Test:** the row's subprocess legs use that argv. test-htcondor's per-file report lists
  `htcondor_backend/announce.py` at ≥90% from `tests/frozen/m68b`.

**M26 · §3.3 L509-512, L519 and L495-499 · the DAG takes node names, file names and the announce key verbatim from
`ServiceSpec.name`, which is a free string. A service named `driver` fails the DAG at parse time, and a name with
whitespace can never be announced.**
- **The measurement:**
  - graphed's `ServiceSpec` (`python/graphed/services.py:84-97`, main `6e9e55e`) puts no constraint on `name`.
  - The plan writes:
    - `SERVICE <name> <name>.sub` beside `JOB driver driver.sub`;
    - `<name>.sub` beside `driver.sub` in the same directory;
    - `key` = the name in `service.json`;
    - `wait_announce(spec.name, …)` in the job.
  - `probe_r11_dag_names.txt` submits `JOB driver driver.sub` / `SERVICE driver driver.sub` through
    `from_dag(…, {usedagdir, force})`:
    - DAGMan logs "ERROR: Node driver already exists in DAG. Processing error at run.dag:2";
    - it `condor_rm`s itself and exits 1 with no driver start, so there is no `result.pkl`.
    - Before that, `<name>.sub` would already have overwritten `driver.sub`.
  - The plan's own `/announce` rule is exactly three whitespace-separated fields, else 400 (L481). So a name with a
    space is a 400 forever. DAG mode has no orphan rule, so the driver times out three times before the DAG fails.
- **Why it changes code:** the implementer following L511 writes the name straight into `run.dag`, the file names and
  the key. None of the refusals at L505-507 sees it.
- **Closed when the plan picks one of these:**
  - **(a)** `submit_driverless` refuses before any bindings call an `announce_only` name that is `driver` or is not
    `[A-Za-z0-9_-]+`, naming it and the rule.
  - **(b)** Nodes, files and keys use a derived id (for example `svc<i>`). `run.json.announce_only` then maps each
    name to its key, and the in-job `host_service` waits on that key.
- **Test:** `test_driverless_dag` covers each case.
  - For (a): names `driver` and `a b` are refused with the recorder empty, and `web` submits (the existing control).
  - For (b): a spec named `driver` yields two distinct node names and two `.sub` files, and `driver.sub` keeps the
    driver's keys.

**M27 · §3.3 L502-507 (`announce_only`), against D2 L36-43, D4 L63-65 and §3.1 L314-318 · submit-time DAG routing
skips leg 2. A driverless LPC run with a launchable Triton spec is refused naming `job_root`, although the job's own
leg 2 (the EAF row) would serve it, and m68a serves it today.**
- **The measurement:**
  - D4 and m68a give lpc `services={"triton": "grpcs://triton.fnal.gov:443"}`. m68a's in-job backend has
    `site_services` = that row's `services` (L317-318), so after m68a the driver job resolves `kind="triton"` by leg 2.
  - m68b's rule (L502-504) puts a spec in `announce_only` iff all of these hold:
    - it has a `launch`;
    - no `services=` endpoint names it;
    - it has an `image` or `gpus > 0`.
  - `recipes.triton(...)` has both an image and a GPU. So `announce_only = {triton}` and the submission becomes a DAG.
  - L505-507 then refuse it at lpc naming `job_root`, whose value there is `None` (L428).
  - D2 orders the legs user → site → managed. This rule decides on leg 3 before leg 2 is tried.
  - The §3 preamble's premise is one set of Triton params across the CI container, lxplus and EAF, so reusing the
    lxplus analysis (L531-536) at LPC is the expected use.
  - r8's note (L528-530, exit items) covers only the waste case, a row with both a `services` entry and a
    `job_root`. It does not cover this refusal, which lands on the one row that has a `services` entry.
- **Why it changes code:**
  - The `announce_only` predicate is a line the implementer writes.
  - As written, m68b regresses m68a's driverless leg 2 at LPC for any spec that carries a recipe.
- **Closed when the plan does one of these:**
  - **(a)** `announce_only` also excludes a spec whose `kind` is a key of the site row's `services`. Leg 2 is then
    tried in the job. If it fails there, leg 3 has no host and gives `ServiceUnavailable`, which exits 1 and is
    retried. This also retires the L528-530 waste note.
  - **(b)** The plan states that the refusal is intended and names `services=` as the workaround in the refusal
    text and in `htcondor.rst`.
- **Test:** `test_driverless_dag`.
  - For (a): on lpc, a plan declaring `recipes.triton(...)` submits one plain job with `announce_only == []`. The
    control is an lpc copy with `services={}`, which is refused naming `job_root` with the recorder empty.
  - For (b): the lpc refusal names `services=`.

## Checked and not raised
- **The `job_root` fold and m67's frozen suite:**
  - The refusal order (jobs_can_submit, then worker_ports, then job_root) keeps `test_driverless_payload.py:191-236`
    green, because it matches `worker_ports` and `/afs`.
  - `root == "/"` keeps the all-OS generic self-submit cases green (`:143`, `test_driver_entry.py:181`).
  - No frozen test pins `SiteProfile`'s field list.
- **The in-job DAG backend:**
  - The outer `ServiceSet` pops the announce, and `runner.run`'s set sees the name as leg 1.
  - The identity is the announced one (L500-501, m68a's handover item).
  - A timeout exits 1 and `RETRY` reruns the driver.
  - With `pilots="local"`, the pilots dial `Machine:port`, and the server binds all interfaces (`server.py:306-311`).
- **The attached lease and beat values:** `beat_s=POLL_S=10` against `lease_s=LEASE_S=30` gives three beats per lease.
  A record re-added by beats after `wait_announce` pops it stays until `release_service` pops it.
- **`from_dag` version drift:** the 25.14.1 wheel's description equals 25.13.2's, apart from `CsdVersion` and the
  `condor_dagman` path (`probe_r11_fromdag_versions.txt`). The fixture only needs the substitutions in exit item 2.
- **§7 and commits:** 650 + 400 + 170 src+ci+docs, with a freeze of about 1k. Every commit is ≤2k and consistent with
  §7's ~1.2k/~1k.
- **§6 simulated GPU:** it is measured on minicondor 25.13.2 (`probe_sim_gpu.txt`). The CI pool comes from
  get.htcondor.org under the same config.d mechanism.
- **D3, D6 and D10 against §3.3:** these are consistent. The in-job keying by name is the stated exception to D10's
  per-call key (L498-499).

## Exit items
These are appended to `reviews/m68b-exit-items.md` under "## r11 exit items":
1. `_runner` accepts a run dict without the new keys.
2. The fixture needs `condor_dagman` on PATH, and it carries the bindings' own `CsdVersion`.
3. The discriminating form of the `RunHandle(dag=True)` no-retrieve leg.
4. DAG-mode wording: the announce repeats until the pair takes a 200.
5. The same-port match flaw in the `probe_dag_service` stand-in.
6. `announce.py`'s runtime compatibility with 3.9 under ruff's py311 UP rules.
7. The macOS `getfqdn` identity in the subprocess legs.
8. `log_dir=None` under the root rule.
9. r10's "stock" wording still stands.

## Verdict
**NOT CLEAN**, with three design findings: M25, M26 and M27.
- **M25** would leave `announce.py` below test-htcondor's coverage gates, with no fix open to the implementer.
- **M26** is a DAG that fails at parse, or never announces, for legal service names.
- **M27** is a submit-time refusal that contradicts D2's leg order and regresses m68a at LPC.

Each finding closes with a one-sentence decision and one test leg.
