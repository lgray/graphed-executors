# Plan review r2 (delta since r1) — `lanes/htcondor/plan.md`

**Verdict: 1 design finding** (1 Medium; finding 1 withdrawn on evidence). No whole-artifact pass this round, because the delta is
not clean.

Delta read: D1–D7 list, `pilot.sh` python, collector failover, the server's future state machine
(F1/F3), the `LEASE_S` call-time read, the pickle codec, close → 410, pilot 403 → exit 2,
`n_workers`/`wait_for_pilots`/`min_pilots` (F4), harness copy (F2), tests 2/4/8 edits (F5/F6/F7),
four commits (F8), and the parsl owner item.

The F1, F2, F3, F4, F6 and F8 repairs close their r1 findings.
- F1: the dep-callback rule routes a leaf's `WorkerLost` through the root future, and so through
  `_result`/`_translate`. Test 4's 4-leaf fixed-path case discriminates the r1 probe shape.
- F3: the first-lease-only transition is right. The journal records the stdlib probe.
- F4: `engine._task_slots` prefers `task_slots()`. `grep -n n_workers src/graphed_executors/submit/engine.py`
  finds only the fallback (line 607), so a non-waiting `n_workers` changes no engine path. The
  relay engines are reachable only through a per-backend facade, and this PR adds none.

## Findings

**1. WITHDRAWN — the F7 fallback would edit a frozen test.** The spool premise is now measured before the
freeze. `probes/ci-minicondor/spool.transcript` shows `cluster 1 spooled`, the (5,16)→1→2→4 transitions in
11.1 s, `retrieved: ['in.txt', 'pilot.0.err', 'pilot.0.out', 'pilots.log']` and `queue after remove: 0`.
Frozen 8(b) is written with `spool=True`, and the fallback is deleted.

**2. Medium — test 2's per-term ad sets can pass a term-removed mutant by tie-break.** Lines 255–260
build each set "by equalising the other two terms' inputs across the ads". With the deciding term
removed, every weight in that set is equal, so `choose_schedd` returns its tie-break pick.
`min(..., key=…)` returns the first minimal item (probe: `min([('a',1.0),('b',1.0)], key=…)` → `a`).
If the expected winner is first in the set's order, the mutant passes. The same lines also require
"the expected winner differs from the one an ordering on either other term would give". Equalised
terms give no ordering, so that sentence and "equalising" contradict each other, and the test author
has to choose. The test that shows it closed: for each term, `schedd_weight` with that term removed
fails its set with the ad list both in stored order and reversed.

## Exit-round constraints (not findings)
- The enumerated copied helpers (line 228 ff.) are a subset of what the m42 bodies use
  (`sum_plan_over`, `counting_plan`, `mem_partitions`, `Prov`, `raise_stage_error`, …). The rule is
  "copy every helper the suite uses", and the list is illustrative. Test 4 also needs a new
  one-uri-poison process, which m42 does not have.
- 8(b)'s `SiteProfile(...)` omits the required `name` field.
- Call `set_result`/`set_exception` outside the queue `Condition`'s lock. A dep's done-callback runs
  inside `set_result` and enqueues the dependent, so a non-reentrant lock held across it deadlocks.
- `min_pilots=None → all N for LocalPilots` needs an `isinstance` branch on the launcher, and
  `local_backend(n)` already waits for n pilots. A single default of 1 suffices.
