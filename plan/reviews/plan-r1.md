# Plan review r1 (whole artifact) — `lanes/htcondor/plan.md`

**Verdict: 8 design findings** (2 High, 5 Medium, 1 Low).

Assumption: D1–D7 are the issuer's list in the dispatch (the plan names them but does not list them);
D1 = copy the m42 helpers into the m66 harness.

## Findings

**1. High — a leaf's `WorkerLost` escapes the engine untranslated on any plan with ≥2 leaves.**
Plan §2 `backend.py`: `submit` "resolves `_ParslFuture` args on the driver (parsl verbatim)", i.e.
`a.result()` inside `submit`. In `SubmitRunner._run_fixed` the combine is submitted with
`backend.submit(_combine_task, …, futs[a], futs[b])`, which is outside `_result`/`_translate`, so a
leaf failure raised during that resolution skips `describe_failure`. Probe
(`reviews/plan-r1-probe_escape.py`: a floor backend copying parsl's resolution, leaf 0 fails with a
`WorkerLost(key, pilot)`, and `describe_failure` is as in the plan):
`n=1: StageError … KilledWorker` / `n=2: WorkerLost: ('graphed-…-leaf-0', 'host:1')`.
The implementer has to decide how a dependent task gets its inputs: it cannot block on them inside
`submit`, and an input's exception must land on the dependent's future, so that `_result(futs[root])`
translates it with the leaf key. The test that shows it closed: test 4's `exit_process` case on a
plan with ≥2 leaves through the fixed (non-windowed) path, asserting `type(err) is StageError` and the
poisoned leaf's uri in `err.partition`. Test 4 does not fix `n` today. (`ParslBackend.submit` has
the same latent defect. m46 tests `describe_failure` only directly. That is outside this lane.)

**2. High — §3 contradicts settled D1.** Lines 186–189 choose pyproject `pythonpath += "tests/frozen/m42"`
with a bare-basename import, "a deliberate reading of D1 that does not copy m46". Line 192
(`LocalPilots(pythonpath=[m42, m66])`) and line 270 (`user_modules=[submit_backends.py, …]`) follow
from that choice. Settled D1 is to copy the helpers, as `m46/parsl_harness.py` did. The test that
shows it closed: `grep -rn "m42\|submit_backends" tests/frozen/m66 pyproject.toml` finds no
cross-directory import and no new m42 pythonpath entry.

**3. Medium — the requeue path calls `set_running_or_notify_cancel()` a second time.** Plan
`/next` calls it "first" on every lease. A requeued task's future is already RUNNING, and stdlib
raises on the second call. Probe in the venv: `f.set_running_or_notify_cancel()` → True, then
`RuntimeError Future in unexpected state`. Only the first lease may call it. The test that shows it
closed: test 4 `DieOnceProcess` already exercises this path. The defect is in the design line.

**4. Medium — frozen `n_workers() == 2` races the plan's `n_workers`.** Plan: `n_workers()` returns
"after a bounded wait for at least one pilot". The copied direct-seam body asserts
`backend.n_workers() == 2` (`m42/test_submit_protocol_conformance.py:167`, `m46/test_parsl_submit_conformance.py:68`)
on `local_backend(2)`, whose pilots register one at a time. So a missing decision remains: either the
harness waits until n pilots have said hello, or `n_workers` waits for the requested count within its
bound. The test that shows it closed: the direct-seam body passes with one `LocalPilots` pilot's
start delayed by ≥1 s.

**5. Medium — test 2 cannot catch a dropped duty-cycle term.** The weight terms computed from
`probes/recorded-ads/lpc-schedd-ads.json` put schedd4 at 1416.46 with the full formula and 1408.92
without the 0.7·DC·100 term, and schedd5 at 1426.98 full and 1421.62 without it. Schedd4 wins
either way, and no perturbation touches `RecentDaemonCoreDutyCycle`, yet the plan says the test
"Fails on: a formula missing a term". The test that shows it closed: a mutant `schedd_weight` with
the DC term removed fails test 2. Either a DC perturbation flips the winner (+0.2 on schedd4 adds 14)
or per-ad weights are pinned.

**6. Medium — the test 2 secret-leak check cannot fail.** "The secret bytes appear in no value" is
checked on `submit_description(url, n)`, which never receives the secret (plan line 69). A leak that
`start` adds (for example, the secret in `arguments`) is invisible to it. The test that shows it
closed: test 8 reads the submitted job ads (full ad, not a projection) and asserts the secret is
absent in both raw and hex form. A mutant that puts the secret in `arguments` inside `start` fails it.

**7. Medium — `spool=True` is exercised by no CI test.** Test 8(b)'s `SiteProfile(ship_env=True, schedd_query=…)`
leaves `spool` undecided, although every `SiteProfile` field is required (line 43). With
`spool=False`, three steps run in no CI test and are covered by nothing: `schedd.spool(result)`, the
`retrieve` in `stop()`, and removing the lingering spooled job. That is the LPC/lxplus path, the one
with the measured traps. Decision needed: 8(b) runs with `spool=True`, then asserts that
`pilot.0.out` was retrieved into `log_dir` and that the queue is empty after `close()`. Premise
unmeasured: the minicondor accepting spooled submits (`grep -il spool probes/ci-minicondor/*` is
empty). The implementer's first CI step measures it.

**8. Low — commit 3 mixes two concerns.** It combines the CI leg and the docs. Split it into
`ci(htcondor)` and `docs(htcondor)`; each is well under the band.

## Exit-round constraints (for the implementer/test author; not findings)
- Plan line 4 says D1–D7 bind, but it never lists them. State them in one line each.
- `HEARTBEAT_S = 5.0` is dead: `/hello` returns `LEASE_S / 6`. Keep one source.
- `monkeypatch LEASE_S=2.0` works only if the server and reaper read `server.LEASE_S` at call time
  (not a default argument, and not a value copied at construction).
- The test 3 per-route marker control needs every route to `pickle.loads` its body. State the codec
  per route (`/hello` returns JSON).
- Pilot behaviour on 403 is unspecified. Exit nonzero with a message.
- `close()` must wake long-polling `/next` handlers so they return 410 at once. Otherwise every run's
  close waits up to `POLL_S`.
- `.coveragerc-htcondor`: set `sigterm = true` (the parsl precedent) if `LocalPilots.stop()`
  terminates pilots.
- The copied helpers live in `htcondor_harness.py`. Never add a second `submit_backends.py` basename
  (the per-mXX basename-collision trap).
- Collector over `FERMIHTC_REMOTE_POOL`: split the list and fail over per node, as
  `lpcjobqueue/schedd.py:acquire_schedd` and `probes/site-common/submit_probe.py` do.
- The formula's "DutyCycle" is `RecentDaemonCoreDutyCycle`.
- "The first result wins": guard `set_result`/`set_exception` against a done future (`InvalidStateError`).
- `pilot.sh`'s `<python>`: with `ship_env` it is the unpacked venv's interpreter, otherwise the
  driver's `sys.executable`. Test 8(b)'s `pilot_prefix()` pins this.
- Test 8(a)'s `schedd.history` rows appear asynchronously. Poll within a bound.
- "The implementer's first step is the CI leg" conflicts with the CI leg being commit 3. Pick one
  order.
