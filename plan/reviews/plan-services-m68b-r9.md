**NOT CLEAN**

# Review r9 — `plan-services.md` §3.3 executors m68b, delta round

Scope: the delta from `reviews/plan-services-m68b-r8-snapshot.md` to the plan as it stands now
(`reviews/plan-services-m68b-r9-snapshot.md`), with only the surrounding context needed to judge it. §3.1 (m68a) is
taken as given. Code: graphed-executors main `c2298d7`.

Probes:
- Re-ran `probe_announce_rules.py` locally. L1–L6 reproduce `probe_announce_rules.txt`; only the port numbers differ.
- Read the pool probes the delta cites, which were already run with the new options:
  - `probe_dag_service.txt` has the `from_dag` description with `-UseDagDir … -force`, run from `~`, and leg U
    (reused dir, rescue file renamed `.old`).
  - `probe_r8_paths.txt` D2 and E, and `probe_r8_fromdag_force.txt`.
- New for this review: `probes/m68b/probe_r9_timewait.{py,txt}`. It is POSIX-only and needs no pool.
- I started no container. No process from this review is left running.

## r8 items
- **M18: closed.**
  - The plan now has `executable=<initialdir>/service.sh` (L438-440), citing `probe_r8_paths.txt` E.
  - The test row asserts `os.path.isabs(executable)` and that it names `service.sh` in the fresh `service-<key>/`.
  - This matches `launch.py:204-205`.
- **M19: closed.**
  - The plan uses `from_dag(<abs run.dag>, {"usedagdir": True, "force": True})`, with node files relative to the
    DAG dir (L509-516).
  - Measured:
    - D2: run from `~`, the node runs and DAGMan exits 0.
    - `probe_r8_fromdag_force.txt`: `force` is accepted on a used dir.
    - `probe_dag_service.txt` U: a reused failed-DAG dir runs from the start, and the rescue file is renamed
      `.old`.
  - The plan removes the stale `driver.url`/`graphed-secret` before submitting.
  - Tests:
    - `test_driverless_dag` asserts the options and has a second-DAG-into-same-`log_dir` leg.
    - Live (c) uses `monkeypatch.chdir(tmp_path)`.
    - The fixture is now the description under those options, and `probe_dag_service.txt` carries it.
- **M20: closed.**
  - The DAG refusal covers `log_dir`, every `user_modules` path and every `announce_only` recipe input. Each
    refusal names the field, the path and the root, and fires before any bindings call (L502-506).
  - The plan states the choice and its reason: refuse, don't copy.
  - The test has the `job_root=<tmp>/root` leg and its control.
  - `driverless.py:187` confirms `user_modules` is transferred as given.
- **M21: closed.**
  - The lease clock starts when the child is ready. A 403 on any POST ends the service, and so does no 200 for
    `lease_s` before the first 200 (L466-470).
  - `probe_announce_rules.txt` L4–L6 measure this, and I reproduced it.
  - `lease_s`/`beat_s` travel in `service.json` as the server's `LEASE_S`/`POLL_S` (`server.py:38-39`).
- **M22: closed as a rule.** `timeout_s` is the total budget, and a child that exits moves on only when its port is
  taken (L458-463, L1–L3). The way the plan says to decide "taken" reintroduces the fault through a measured race.
  That is M24 below.
- **M23: closed.** The subprocess legs are `skipif(sys.platform == "win32")` with the reason, and the key and text
  legs stay all-OS (L548).
- The r8 exit items the planner folded in are all present with correct premises:
  - secret unlink in `stop()`;
  - `history(..., match=1)`, as `driverless.py:66`;
  - `beat_s`;
  - the §6 sim-GPU ordering, as `probe_sim_gpu.py:4` does;
  - the docs notes;
  - the leg-2 note, since D4 gives lxplus and generic `services={}` and lpc `job_root=None`.

## Design findings

**M24 · §3.3 L459-462 `announce.py` start · "its port is no longer free" is judged by the same plain bind as the
scan, so the service's own `http:` self-check makes the port look taken, and the child is restarted per port.**
- The measurement (`probes/m68b/probe_r9_timewait.txt`):
  - The child answers the `http:` self-check once with 503 (a server still loading), then exits 7 (a bad model).
    Nothing else binds the range. By the plan's rule the script should exit 3 at once, naming 7, after one child
    start.
  - A, the prototype as the plan cites it (`announce_proto.py` `free()`, a plain `bind`):
    - Over 10 runs, the child starts per run were `[5, 7, 5, 1, 1, 1, 1, 3, 1, 2]`.
    - The log reads "port 24000 taken after the scan (child exited 7), next" ×4.
    - Cause: after a 503 the HTTP/1.0 server usually closes first, which leaves a server-side `TIME_WAIT` on the
      port. On Linux a bind without `SO_REUSEADDR` refuses that port.
  - B, the same code with `SO_REUSEADDR` set in `free()`: `[1, 1, 1, 1, 1, 1, 1, 1, 1, 1]`.
  - C, the positive control: a port with a live listener still refuses a `SO_REUSEADDR` bind (errno 98), so B still
    sees a real taker. That is the L3 case the rule exists for.
- Why it changes code:
  - The line the implementer writes is the "is it free" test, and the plan's only guide is the scan's "unless a bind
    succeeds" and the prototype.
  - As written it produces the "service restarted per port" failure M22 closed. For a real model server that
    answers 503 while loading and then dies, that means a GPU init on each of up to 101 ports. The Fails-on list
    names this failure.
  - The frozen legs as written ("a child that exits at once") never make a self-check connection, so they cannot
    see it.
  - Any leg whose child answers the check before dying becomes flaky. Across the 10 runs of A, 4 exited after one
    start and 6 restarted.
- Closed when the plan says that "free" is decided by a bind with `SO_REUSEADDR` set. That bind is refused by a
  listener and not by `TIME_WAIT`. The same test is used for the scan and for the after-exit check, and the
  prototype `free()` is updated to match.
- Test: `test_cluster_service_job` (POSIX leg) runs an `http:` spec whose child answers the check once with a
  non-2xx and then exits nonzero, over a ≥5-port range. It asserts exit 3 naming that returncode and exactly one
  child start (a count file the child appends to), repeated ×10 in-test, or with a guaranteed `TIME_WAIT`. The
  existing held-port leg still moves to the next port.

## Checked and not raised
- **`usedagdir` and m67's relative `transfer_input_files` (`PLAN_FILE`, `RUN_FILE`, `driverless.py:187`).** These
  resolve against the node's `initialdir`, not DAGMan's cwd. D2 and U run with the driver node's output landing in
  the DAG dir, so `result()` reading `result.pkl` there holds.
- **`force` on a fresh dir.** It is harmless. It always passes `-force`, so the fixture text is fixed.
- **The attached pre-200 loop against a black-holed URL.** Each POST has a 10 s timeout, and `lease_s=30` still
  ends it.
- **DAG-mode 403s.** They are not orphan signals, and the prototype retries until the pair takes a 200, which is
  consistent with "DAGMan owns the node".
- **§7.** 650 + 400 + 170 ≈ 1.2k src+ci+docs and a ~1k freeze. Every commit is ≤2k.

## Exit items
Appended to `reviews/m68b-exit-items.md` under "## r9 exit items".

## Verdict
**NOT CLEAN**, with one design finding: M24. M18–M23 are closed at their causes. M24 is a one-sentence rule plus one
test leg: decide "free" with a `SO_REUSEADDR` bind.
