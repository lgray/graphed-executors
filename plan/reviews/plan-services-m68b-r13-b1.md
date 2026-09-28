**NOT CLEAN**

# Review r13-B1: `plan-services.md` §3.3 part B1 (attached cluster hosting), delta round

Scope: the B1 delta between `reviews/plan-services-m68b-r12-b1-snapshot.md` and the plan, plus the minimum context around it. The delta covers:
- the §3.3 preamble (L415–421);
- "#### B1" (L432–517): the new **Secrets** bullet, `ServiceJob.files`, `/announce` secret selection, the announce `Condition`, `forget_announce`;
- the B1 frozen rows (L603–604), "Fails on (B1)" (L609–614), and the B1 commits (L619–621).

B2 is not reviewed. m68a §3.1 is taken as given.

Snapshot: `reviews/plan-services-m68b-r13-b1-snapshot.md`, identical to the plan at review time. Line numbers below refer to it.
Code: graphed-executors main `c2298d7`.

## M28-B1: closed for the task-server secret

- **The fix works for the secret it was aimed at.** The plan now makes both changes r12 offered:
  - **(b), a scoped secret:** a per-call announce secret. The `ServiceJob` never gets the pilots' secret (L433–436).
  - **(a), unlinking:** `announce.py` reads the file into memory and unlinks it before `Popen` (L436). The prototype does this at `announce_proto.py:120-124`.
  - "Fails on (B1)" gains the matching line (L610–611).
- **The re-run backs it up.** `probe_announce_rules.py` was run again locally. It reproduces L1–L8 exactly as recorded, including:
  - L8: `GET /graphed-secret` → 404, the file is gone, and 7 beats took 200;
  - L7: `[1]*10` child starts, then exit 3 naming 7.
- **The secret selection on `/announce` checks out against the current server** (L498–506):
  - **Today every body is unpickled.** `do_POST` (`server.py:274-285`) verifies every body against `tasks.secret` (`server.py:99`, `:279`) and then calls `pickle.loads` (`:283`).
  - **The plan's change sits in one place.** It routes `/announce` before that check. Every other path, including any `/announce?...` variant, which falls through to the `/result` route (`:297-299`), still reaches `:279` and needs the pilots' secret. So an announce secret never reaches `pickle.loads`.
  - **Choosing the secret from the body is safe.** The key comes from the unauthenticated text, but it only picks the registered secret. An unknown key has no secret, so the request gets 403. The comparison stays `hmac.compare_digest` over the hex HMAC-SHA256, which pilots use (`server.py:54-55`).
  - **The file format matches.** `write_secret` writes hex (`launch.py:52-55`), and `announce_proto.py:77` reads it with `bytes.fromhex`, as `pilot.py:84` does.
- **Giving announces their own `Condition` is correct.** `add()` wakes one waiter with `notify()` (`server.py:139`, `:246`). A shared condition could hand a pilot's wake-up to `wait_announce`.
- **The new tests tell the fixes apart:**
  - In `test_announce_route`:
    - "pilots' secret → 403 on `/announce`" fails a single-secret server;
    - "another key's secret → 403" fails a server that accepts any registered secret;
    - "announce secret to `/result` → 403" fails a server that accepts an announce secret everywhere;
    - "after `forget_announce` → 403" fails a server that never drops secrets.
  - In `test_cluster_service_job`, "GET `/graphed-secret` → 404, file gone" fails an `announce.py` that leaves the file in place.
  - "`graphed-secret` ≠ pilot secret" is discriminated end to end anyway: a `host_service` that passed the pilots' secret would get 403 on every announce, so `test_cluster_services_live` (a) would time out.
- **No new contradictions or invented decisions.** Each change traces to the round-6 decisions in `m68b-exit-items.md`.

The cause M28 named, "the service's cwd is the job's scratch dir and the child may serve it" (L437), is still open for a credential that B1 itself puts there. See M29-B1.

## Design finding

**M29-B1 · L456 ("then the profile keys") with L436–437 and "Fails on (B1)" L610 · on lxplus every `ServiceJob` carries `MY.SendCredential = True`, so condor drops the user's Kerberos ticket cache into the scratch dir. That dir is the child's cwd, and the plan itself says the child may serve it.**

- **What B1 writes:**
  - The `ServiceJob` keys include "then the profile keys" (L456). lxplus's `submit` has `"MY.SendCredential": "True"` (`sites.py:74`).
  - lxplus is `service_hosts == ("cluster",)` (L66, L347). So on lxplus every declared service, `recipes.http_server` included, runs as a B1 `ServiceJob`.
  - The child is started in the job's scratch dir (L437).
- **The measurement:**
  - `probes/site-lxplus/m67-driverless.txt` (runs 1 and 2) records, for a job with the lxplus profile keys:
    - `_CONDOR_SCRATCH_DIR=/srv` and `pwd=/srv`;
    - `KRB5CCNAME=FILE:/srv/lgray.cc`;
    - `klist`: `Default principal: lgray@CERN.CH`.
  - So the user's CERN TGT is a file in the child's cwd.
  - `probe_r12_b1_pool.txt` shows that a `ServiceJob`-shaped `http.server` child answers `GET /` with a listing of its scratch dir and serves any file in it with 200.
  - Taken together: anyone who can reach an lxplus worker port can `GET /lgray.cc` and get the user's Kerberos ticket. That port range is 10000–10100, and lxplus is a shared pool by design (D4, P7). The ticket gives AFS and SSO access as the user, which is worse than what M28 closed.
  - Unlinking the file, as done for `graphed-secret`, does not help: condor's credd refreshes the cache in place.
- **Why it changes code:**
  - The implementer copies the profile keys verbatim, as L456 says, and nothing in B1's rows looks at them for credentials:
    - "no secret or url in any value" checks values, not this key;
    - "Fails on (B1)" names only "the task server's secret".
  - The fix is a line the implementer writes. The plan must say which of these it is:
    - **(a)** `ServiceJob` drops `MY.SendCredential` from the profile keys. A service gets its inputs by transfer, not AFS, so it has no use for a ticket.
    - **(b)** `announce.py` starts the child in a subdirectory that holds only what the recipe needs. This needs care: an image-less recipe's interpreter is the relative `./env/bin/python` (L461–462), and `inputs` land in scratch under relative names (L451–452).
- **Closed when:**
  - The plan picks (a) or (b) at L456 or L437.
  - "Fails on (B1)" gains "a user credential in the service's cwd".
  - Site check (1) (L586–587) records, for the lxplus Triton `ServiceJob`, `ls -a` of the scratch dir, or `env | grep KRB5CCNAME`, showing no ticket cache there.
  - If (a) is chosen, site check (1) also records that the job is accepted and starts without `SendCredential`. This is unmeasured: the m67 probes always sent the key.
- **Test** (`test_cluster_service_job.py`):
  - For (a), a `ServiceJob` built on `SITES["lxplus"]` has no `MY.SendCredential` key. As a control, the pilots' own keys on the same profile keep it.
  - For (b), a subprocess leg with a file standing in for the ticket in the job dir: `GET /<that file>` on the announced `http.server` → 404.

## Exit items

These are appended under "## r13-B1 exit items" in `m68b-exit-items.md`.

## Evidence

- `probe_announce_rules.py` was re-run locally, output in `/tmp/claude-0/review-r13-b1/rerun.txt`. It reproduces L1–L8.
- `probes/site-lxplus/m67-driverless.txt` is existing lxplus evidence, re-read for M29-B1.
- **Cleanup:** no containers were started this round. No `announce_proto`, `receiver_proto` or `http.server` process was left running.
