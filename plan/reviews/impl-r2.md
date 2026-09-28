# m66 implementation review, round 2: the r1 repairs, 89a2eac..f9253fa (PR #34)

**Verdict: APPROVE-READY.** The delta has 0 design findings, and so does the whole-diff pass.

## Delta: each r1 finding is closed
- **H1 (lost driver).** `_Driver.post` sends its own process SIGTERM from whichever thread finds the driver
  gone for a lease. The pilot's code runs only in pilot subprocesses: grep finds no driver-side import of
  `_Driver`, and the only launches are `-m …pilot` or `-c`. So the signal cannot reach the driver or pytest.
  LocalPilots teardown is unaffected: the full m66 suite passed, and no pilot process was left afterwards.
  Coverage still saves: `pilot.py` is at 99% frozen+extra on macOS, with the `os.kill` line hit.
- **M1 (pilot id).** The id is `hostname:pid:token`. The frozen lost-pilot test pins
  `f"{gethostname()}:" in err.cause_message`, which still passes. The docs now say `host:pid:token`.
- **L1 (malformed signature).** The header is compared as latin-1 bytes. http.server decodes headers as
  latin-1, so the encode cannot fail, and `compare_digest` on bytes stays constant-time.

Discrimination: I swapped 89a2eac's `pilot.py` and `server.py` into a scratch worktree and restored them
afterwards; `git status` was clean. All 4 witnesses fail on the old files and pass on f9253fa:
- `exits_at_once[idle]` and `[mid-task]`: `assert 1 in (-15, SIGTERM)`;
- `sharing_a_hostname_and_pid`: `assert 1 == 2`;
- `malformed_signature_header`: the reply is `b''`.

Full m66 frozen+extra on macOS at f9253fa: 60 passed. The 2 live-pool tests run only on CI (62 there).

## Whole-diff pass (freeze-m66..f9253fa)
Nothing new. Every r1 item is either closed above or found clean in r1: intent, auth before unpickle, the
lease state machine, the launcher, and proportion.

## Exit-round constraints (not findings)
- SIGTERM is ignored by a process that is PID 1 of its PID namespace, which is the docker universe without
  `--init`. None of the profiles reaches that case: on the LPC, apptainer runs the pilot as pid 14.
  Unmeasured elsewhere.
- The mid-task witness fails the old code on the exit-code assert before it reaches the timing assert. The
  timing assert still catches a SIGTERM sent only after the task ends.

## Owner decision (unchanged from r1)
Frozen-only diff coverage is 94.9% (542/571 at 89a2eac). On frozen hits alone, `pilot.py` stays under the
90% per-file gate. The r2 witnesses are all in `tests/extra`.
