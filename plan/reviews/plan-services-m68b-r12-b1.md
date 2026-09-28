**NOT CLEAN**

# Review r12-B1: `plan-services.md` §3.3 part B1 (attached cluster hosting), whole-part read

Scope: B1 only.
- The §3.3 preamble and the ladder rows tagged B1 (L415–427).
- "#### B1 — attached cluster hosting" (L431–497).
- The frozen harness line, the B1 rows, "Fails on (B1)" and the B1 commits (L568–594).
- The D2, D3 and D10 lines that bind the attached condor path.

§3.1 (m68a) is taken as given, and B2 is read only where B1 touches it (watch mode).

Snapshot: `reviews/plan-services-m68b-r12-b1-snapshot.md`, identical to the plan at review time. Line numbers below refer to it.
Code: graphed-executors main `c2298d7`; graphed main `6e9e55e`.

Evidence added this round:
- **New measurements:**
  - `probes/m68b/probe_r12_b1_pool.{py,txt}` on `htcondor/mini` 25.13.2.
  - `probes/m68b/probe_r12_b1_secret_served.{py,txt}`, POSIX, no pool, with a control.
- **Re-run:** `probe_announce_rules.py`, run locally, reproduces L1–L7. L7 gives `[1]*10` child starts and exit 3 naming 7.
- **Cleanup:** the container `r12b1-pool` is removed, and no `http.server`, `announce_proto` or `receiver_proto` process is left running.

## Design finding

**M28-B1 · §3.3 L432–438 and L472 (the `ServiceJob` inputs and the announce signature), with D10 L114–117 · the
task server's secret sits in the service's own working directory. The shipped `http_server` recipe serves that
directory to the network. Anyone who can reach a worker port can read the secret and sign pickles to the driver.**
- **What B1 writes:**
  - `graphed-secret` (the backend's task-server secret, the pilots' secret too) is transferred into the job's
    scratch dir beside `announce.py` and `service.json` (L433–438).
  - `announce.py` signs "with the hex secret as pilots read it" (L472). The prototype re-reads the file on every
    POST (`announce_proto.py:148`), so the file stays in scratch for the job's life.
  - The child is `Popen`ed with no `cwd` (L460–461; `announce_proto.py:99`), so it inherits the scratch dir. That is
    also where its relative `inputs` land (L439–441), so it cannot simply move elsewhere.
  - The generic recipe `recipes.http_server` (`{python} -m http.server {port}`, §3.1 L239–240) is "the third recipe
    every hosting test runs". It serves its cwd on a `worker_ports` port, and those ports are reachable from other
    batch nodes by design (D4; lxplus P7 is a shared pool).
- **The measurement** (`probe_r12_b1_pool.txt`): a job shaped like B1's `ServiceJob` announced
  `0f244e794cde:10001`.
  - `GET /` → 200, and the listing names `graphed-secret`.
  - `GET /graphed-secret` → 200, and the body equals the task server's secret.
  - Locally (`probe_r12_b1_secret_served.txt`), a POST signed with the stolen secret passes the signature check:
    the stand-in answers 400, where 403 means refused.
  - The real `TaskServer` unpickles every correctly signed body (`server.py:580-584`). So the stolen secret lets
    anyone run code in the driver process, as the user, on the login node. It also lets them register as a pilot
    and lease the run's tasks.
  - Control, same file: with the child's directory holding no secret, `GET /graphed-secret` → 404.
- **Why it changes code:** the implementer following L472 reads the secret file when signing, as the prototype and
  the pilots do, and leaves it in place. Nothing in B1's frozen rows would catch the exposure:
  - "no secret or url in any value" checks the ad only;
  - "Fails on (B1)" names "a secret in a job ad" but not a secret served from the job.
- **Closed when the plan picks one of these:**
  - **(a)** In attached mode, `announce.py` reads `graphed-secret` into memory and unlinks it before the first
    `Popen`. Condor transfers it again if the job restarts, and `ServiceJob.stop()` still unlinks the submit-side
    copy.
  - **(b)** The announce is signed with a per-call announce secret. `TaskServer` accepts that secret only on
    `/announce` and never for a pickled route, so the pilots' secret is never transferred to a `ServiceJob`.
  - Either way, "Fails on (B1)" gains "the task server's secret readable through the service".
- **Test:** a `test_cluster_service_job.py` subprocess leg on the `{python} -m http.server {port}` spec against a
  real `TaskServer`.
  - Its setup mirrors the job: `service.json` and `graphed-secret` in the child's cwd.
  - After the announce, `GET /graphed-secret` on the announced endpoint → 404.
  - For (a), the file is also gone from the job dir, while the beats still take 200. The lease leg stays green.
  - For (b), a pickle signed with the announce secret to `/result` → 403.
  - Against B1 as written, and against the prototype, it gives 200 with the secret (`probe_r12_b1_pool.txt`).

## Checked and not raised
- **The `ServiceJob` keys against `launch.py`:**
  - `_stage`'s interpreter choice is `launch.py:215`.
  - The absolute executable is needed, as `launch.py:204-205` shows.
  - `_submit` submits and then spools in one call (`:226-231`), which r8's pre-spool hook item covers.
  - `CLOSE_WAIT_S` = 20 s (`:31`), the drain `stop()` skips.
  - `counts_as_alive` treats a hold with code 16 as spooling (`sites.py:35-38`).
- **`/announce` before `pickle.loads`:** today a signed plain body is a 400 from `pickle.loads` (`server.py:583-586`).
  The three-field rule and the pop-on-return are consistent with the `test_announce_route` row.
- **Keys and scope:** `run_nonce` is `uuid4().hex[:8]` (`engine.py:299`). So `f"{scope}-{token_hex(8)}"` has no
  whitespace, and it is safe as a directory name, a `JobBatchName` and an announce field.
- **Identity:** `probe_service_job.txt` A shows the slot `Machine` equals `FULL_HOSTNAME` on minicondor, which is
  what live leg (a) needs.
- **The attribute rule:** `host_service` is present iff the launcher is `CondorPilots` and `"cluster"` is in
  `service_hosts`. This agrees with §3.1:
  - L321: the in-job backend is `("driver",)`, so it gets no attached `host_service`.
  - L345: a GPU recipe on a backend without the attribute is refused.
  - B2's `announced=` binding is separate.
  - m68a's live leg (a) stays driver-hosted on generic, because driver-hosted comes first in D2.
- **Two announce scripts racing for one port:** two `announce.py` processes scanning at once, where one child fails
  to bind while the other's answers its self-check, is the cross-process race §3.1 L266–268 already accepts ("only
  the post-check poll guards"). It is not new to B1.
- **A `ServiceJob` evicted mid-run:** it re-announces a new endpoint the plan never rebinds. That is D6's mid-run
  service failure, an owner item, which exits 3.
- **Commit sizes:** the freeze is ~650 and commit 1 is ~650 (src ~430). Both are ≤2k.
- **D3 and D10 against B1:** consistent.

## Exit items
These are appended to `reviews/m68b-exit-items.md` under "## r12-B1 exit items".

## Verdict
**NOT CLEAN**, with one design finding: M28-B1. It is a network-readable task-server secret, and so code execution
in the driver, on the generic recipe B1's own tests run. One decision and one test leg close it.
