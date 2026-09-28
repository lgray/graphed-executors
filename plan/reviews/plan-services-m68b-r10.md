**CLEAN**

# Review r10: `plan-services.md` §3.3 executors m68b, delta round

Scope: the delta from `reviews/plan-services-m68b-r9-snapshot.md` to the plan as it stands now
(`reviews/plan-services-m68b-r10-snapshot.md`), with only the context needed to judge it. §3.1 (m68a) is taken as given.
Code: graphed-executors main `c2298d7`.

The delta has four hunks:
- the "free" rule in `announce.py` start (L458-465);
- site check (2) wording (L542-543);
- a new `test_cluster_service_job` leg and the `test_driverless_dag` fixture comparison (L551-552);
- the §9 "stock" wording (L824).

Probes:
- I re-ran `probes/m68b/probe_announce_rules.py` locally in `/tmp/claude-0/review-r10/`.
  - L1–L7 reproduce `probe_announce_rules.txt`, apart from port numbers.
  - L7 gives `[1, 1, 1, 1, 1, 1, 1, 1, 1, 1]` child starts and `(3, names 7)`.
- `announce_proto.py` `free()` now binds with `SO_REUSEADDR` (L62-71).
- `probe_r9_timewait.txt` measures both sides:
  - B: `[1]*10` starts.
  - C: a live listener still refuses the bind (errno 98).
- I started no container. No process from this review is left running.

## r9 item
**M24: closed at its cause.**
- The rule and where it applies:
  - The plan defines "free" once, as a bind with `SO_REUSEADDR` succeeding.
  - It applies that test to both the scan and the after-exit check (L458-462).
  - It gives the reason: a listener refuses the bind, and the self-check's `TIME_WAIT` does not.
  - It cites `probe_r9_timewait.txt` and L7.
- The prototype matches the rule.
- The rule does not weaken the L3 case (a real taker after the scan):
  - C shows that a listener is still seen.
  - The re-run L3 still moves to the next port ("port 23200 taken after the scan (child exited 1), next").
- The new test leg is the one r9 asked for:
  - `http:` check answered once with a non-2xx, then a nonzero exit.
  - A range of 5 or more ports, repeated ×10.
  - It asserts exit 3 naming the returncode and exactly one start, using a count file.
- The leg discriminates:
  - Under the old plain bind, only 4/10 runs had one start (r9 A). All 10 passing by chance is about 0.4^10.
  - Under the new rule it is deterministic (B, L7).
- The existing held-port leg keeps the positive path.

## Rest of the delta
- **Site check (2) and §9 L824.** Both now name `from_dag` with `usedagdir`/`force`. This matches L513 and
  `probe_dag_service.txt`, whose description carries `-UseDagDir … -force` and `getenv … CONDOR_CONFIG`. The r9 exit
  item is folded in.
- **Fixture comparison.** The fixture is compared after substituting the DAG dir and `CsdVersion`, as the r9 exit
  item asked. The escaped form of `CsdVersion` in `arguments` is an implementer detail, so it is an r10 exit item.
- **Contradictions.** None. The "decisions (round 3)" entries in `m68b-exit-items.md` match the plan text. No new
  decision was invented beyond M24's closure.

## Checked and not raised
- **A recipe's server that binds without `SO_REUSEADDR`.**
  - Under the new rule, such a server fails on a port that holds only a `TIME_WAIT`. The post-exit check then calls
    the port free, and the script exits 3 instead of moving on.
  - Every shipped recipe binds with `SO_REUSEADDR`: `http.server`'s `allow_reuse_address`, and gRPC/Triton's
    default. The m66 `TaskServer` sets it on POSIX (`server.py:81`).
  - The failure is a loud exit 3 naming the returncode. Nothing is restarted and nothing hangs.
  - This is a docs constraint (r10 exit item), not a change to a line of code.

## Design findings
None.

## Exit items
Appended to `reviews/m68b-exit-items.md` under "## r10 exit items":
- the remaining "stock" wording at L420/L525;
- the escaped `CsdVersion` in the fixture;
- the docs note on `SO_REUSEADDR` for custom recipes;
- r10 evidence.

## Verdict
**CLEAN.** There are 0 design findings, and M24 is closed at its cause.
