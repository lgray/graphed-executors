"""Surface area L: job lifecycle — JobStatus transitions, queue->history hand-off, condor_rm/condor_hold signal
delivery and grace, orphaned children, periodic_remove/periodic_hold timing, max_retries/retry_until, spooled jobs,
act() on absent jobs.

Pool: `echo 'NUM_CPUS = 40' > /etc/condor/config.d/98-cpus` + `condor_restart -daemon startd` in surf-life first (4 real CPUs would
starve concurrent jobs/SERVICE nodes).
Run: docker exec -u submituser -w /home/submituser surf-life python3 /probes/condor_surface/probe_surface_lifecycle.py
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from surface_lib import (base, final, fresh, header, hist, htc, listdir, q, read, rm, say, schedd, script, short, submit,
                         wait, wait_gone, wait_status, write)

header("probe_surface_lifecycle")
for k in ("MachineMaxVacateTime", "KILLING_TIMEOUT", "GRACEFULLY_REMOVE_JOBS", "MAX_PERIODIC_EXPR_INTERVAL"):
    say("#", k, "=", htc.param.get(k))

# ---------- L1 transitions and the queue -> history hand-off (does a finished job ever vanish from both?)
d = fresh("l1")
cl = [submit(base(d, executable="/bin/sleep", arguments="2", output="o$(Cluster)", error="e$(Cluster)")) for _ in range(8)]
seen = {c: [] for c in cl}
gaps = {c: 0.0 for c in cl}
t_end = time.monotonic() + 180
pending = set(cl)
while pending and time.monotonic() < t_end:
    for c in list(pending):
        a = q(c, ("JobStatus",))
        s = a.get("JobStatus") if a else None
        if s is None:
            h = hist(c, ("JobStatus",))
            if h:
                s = "hist:%s" % h[0].get("JobStatus")
                pending.discard(c)
            else:
                s = "NEITHER"
                gaps[c] += 0.2
        if not seen[c] or seen[c][-1] != s:
            seen[c].append(s)
    time.sleep(0.2)
say("L1 status sequences (queue JobStatus..., then history):", {c: seen[c] for c in cl})
say("L1 seconds a finished job was in neither queue nor history (0.2 s polls):", {c: round(g, 1) for c, g in gaps.items()})

# ---------- L2 condor_rm of a running job: who gets SIGTERM, when does SIGKILL come, is a child reaped
PROC = r'''
import os, signal, subprocess, sys, time
role, log, mode = sys.argv[1], sys.argv[2], sys.argv[3]
def w(msg):
    with open(log, "a") as f: f.write("%.2f %s pid=%d %s\n" % (time.time(), role, os.getpid(), msg))
def on_term(sig, frm):
    w("got SIGTERM")
    if role == "parent" and mode == "exit-on-term":
        w("exiting without touching child"); os._exit(0)
    if role == "parent" and mode == "reap":
        child.terminate(); child.wait(); w("reaped child"); sys.exit(0)
signal.signal(signal.SIGTERM, on_term if mode != "ignore-all" else signal.SIG_IGN)
w("start pgid=%d" % os.getpgid(0))
if role == "parent":
    child = subprocess.Popen([sys.executable, __file__, "child", log, mode if mode == "ignore-all" else "ignore"])
if role == "child" and mode == "ignore":
    signal.signal(signal.SIGTERM, lambda s, f: w("got SIGTERM (ignored)"))
if role == "parent" and mode == "exit-normally":
    time.sleep(8); w("parent exits normally, child still running"); sys.exit(0)
while True:
    time.sleep(0.5)
    with open(log + "." + role, "w") as f: f.write(str(time.time()))
'''
d = fresh("l2")
write(os.path.join(d, "proc.py"), PROC)
modes = {"reap": {}, "exit-on-term": {}, "ignore-all": {}, "ignore-all-jmvt5": {"job_max_vacate_time": "5"}, "exit-normally": {}}
cls = {}
for m, kw in modes.items():
    log = os.path.join(d, "log-" + m)
    script(os.path.join(d, "run-%s.sh" % m), "exec /usr/bin/python3 %s parent %s %s\n" % (os.path.join(d, "proc.py"), log, m.replace("-jmvt5", "")))
    cls[m] = submit(base(d, executable=os.path.join(d, "run-%s.sh" % m), output="o-" + m, error="e-" + m, **kw))
wait(lambda: all(os.path.exists(os.path.join(d, "log-%s.child" % m)) for m in modes), 120)
time.sleep(3)
t_rm = time.time()
for m, c in cls.items():
    if m != "exit-normally":
        rm(c, "probe L2 remove")
say("L2 condor_rm sent at", "%.2f" % t_rm)
wait(lambda: all(q(c) is None for m, c in cls.items() if not m.startswith("ignore-all") or m.endswith("jmvt5")), 90)
time.sleep(15)
for m, c in cls.items():
    log = os.path.join(d, "log-" + m)
    lines = [l.split(" ", 1) for l in read(log).splitlines()]
    rel = ["%+.1fs %s" % (float(t) - t_rm, rest) for t, rest in lines]
    alive = {r: (time.time() - float(read(log + "." + r))) < 2.0 if os.path.exists(log + "." + r) else None for r in ("parent", "child")}
    say("L2 %-18s queue=%s events=%s | heartbeat fresh now (+%.0fs): %s" % (m, (q(c) or {}).get("JobStatus"), rel, time.time() - t_rm, alive))
c = cls["ignore-all"]
gone = wait_gone(c, 700)
say("L2 ignore-all (default MachineMaxVacateTime): left the queue %s s after rm; history" % (None if gone is None else round(time.time() - t_rm)),
    final(c, ("JobStatus", "ExitCode", "ExitBySignal", "ExitSignal", "RemoveReason")))
for m in ("reap", "exit-on-term", "exit-normally"):
    say("L2 %-14s history:" % m, final(cls[m], ("JobStatus", "ExitCode", "ExitBySignal", "ExitSignal", "RemoveReason")))
say("L2 any probe process left on the host:", subprocess.run(["pgrep", "-af", os.path.join(d, "proc.py")], capture_output=True, text=True).stdout.strip() or "none")

# ---------- L3 condor_hold of a running job, release; periodic_remove / periodic_hold timing
d = fresh("l3")
write(os.path.join(d, "proc.py"), PROC)
script(os.path.join(d, "run.sh"), "exec /usr/bin/python3 %s parent %s reap\n" % (os.path.join(d, "proc.py"), os.path.join(d, "log")))
c = submit(base(d, executable=os.path.join(d, "run.sh")))
wait(lambda: os.path.exists(os.path.join(d, "log.child")), 90)
t = time.time()
schedd.act(htc.JobAction.Hold, "ClusterId == %d" % c, reason="probe hold")
a = wait_status(c, (5,), 30)
time.sleep(5)
say("L3a condor_hold running job: JobStatus", a.get("JobStatus"), "HoldReasonCode", a.get("HoldReasonCode"), "|",
    ["%+.1fs %s" % (float(x.split(" ", 1)[0]) - t, x.split(" ", 1)[1]) for x in read(os.path.join(d, "log")).splitlines()])
schedd.act(htc.JobAction.Release, "ClusterId == %d" % c)
seq, t_rel = [], time.time()
while time.time() - t_rel < 60:
    a = q(c, ("JobStatus", "NumJobStarts")) or {}
    r_ = (a.get("JobStatus"), a.get("NumJobStarts"))
    if not seq or seq[-1][1] != r_:
        seq.append(("%+.0fs" % (time.time() - t_rel), r_))
    time.sleep(1)
say("L3b after release, (JobStatus, NumJobStarts) over 60 s:", seq)
rm(c)
# periodic_remove = JobStatus == 5 on a job held (a) at input transfer, (b) by condor_hold
c1 = submit(base(d, executable="/bin/sleep", arguments="600", transfer_input_files="/nonexistent/x", periodic_remove="JobStatus == 5", output="p1"))
c2 = submit(base(d, executable="/bin/sleep", arguments="600", periodic_remove="JobStatus == 5", output="p2"))
c3 = submit(base(d, executable="/bin/sleep", arguments="600", periodic_hold="(time() - EnteredCurrentStatus) > 5 && JobStatus == 2",
                 periodic_hold_reason='"probe periodic hold"', output="p3"))
wait_status(c2, (2,), 60)
schedd.act(htc.JobAction.Hold, "ClusterId == %d" % c2, reason="probe user hold")
th = {}
for c in (c1, c2):
    wait_status(c, (5,), 60)
    th[c] = time.time()
for c in (c1, c2):
    g = wait_gone(c, 200)
    say("L3c periodic_remove=JobStatus==5, held (%s): removed %.0f s after the hold;" % ("input" if c == c1 else "user", time.time() - th[c]),
        final(c, ("JobStatus", "HoldReasonCode", "RemoveReason")))
a = wait_status(c3, (5,), 200, ("JobStatus", "HoldReasonCode", "HoldReason", "EnteredCurrentStatus", "JobCurrentStartDate"))
say("L3d periodic_hold after 5 s running:", a and {k: a.get(k) for k in ("JobStatus", "HoldReasonCode", "HoldReason")},
    "held %s s after start" % (a and (a.get("EnteredCurrentStatus") - a.get("JobCurrentStartDate"))))
rm(c3)

# ---------- L4 max_retries / retry_until (m67 plain job)
d = fresh("l4")
cases = {"exit1-always": "exit 1", "exit3": "exit 3", "kill9": "kill -9 $$", "exit1-then-0": '[ -f %s/marker ] && exit 0; touch %s/marker; exit 1' % (d, d)}
cl = {}
for n, body in cases.items():
    script(os.path.join(d, n + ".sh"), body + "\n")
    cl[n] = submit(base(d, executable=os.path.join(d, n + ".sh"), max_retries="2", retry_until="3", output="o-" + n, error="e-" + n))
states = {n: [] for n in cl}
end = time.monotonic() + 240
while time.monotonic() < end and any(q(c) is not None for c in cl.values()):
    for n, c in cl.items():
        a = q(c, ("JobStatus", "NumJobStarts"))
        if a:
            s = (a.get("JobStatus"), a.get("NumJobStarts"))
            if not states[n] or states[n][-1] != s:
                states[n].append(s)
    time.sleep(0.5)
c0 = cl["exit1-always"]
say("L4 OnExitRemove generated:", str(schedd.history("ClusterId == %d" % c0, ["OnExitRemove"], match=1)[0].get("OnExitRemove")))
for n, c in cl.items():
    say("L4 %-13s (JobStatus, NumJobStarts) seen in queue: %s; history %s" % (n, states[n], final(c, ("JobStatus", "ExitCode", "ExitBySignal", "ExitSignal", "NumJobStarts", "JobMaxRetries"))))

# ---------- L5 spooled jobs (lpc/lxplus profiles spool)
d = fresh("l5")
script(os.path.join(d, "s.sh"), "echo out-line; echo r > result.pkl\n")
write(os.path.join(d, "in.txt"), "in\n")
r = schedd.submit(htc.Submit(base(d, executable=os.path.join(d, "s.sh"), transfer_input_files=os.path.join(d, "in.txt"),
                                   transfer_output_files="result.pkl")), spool=True)
c = int(r.cluster())
a = q(c, ("JobStatus", "HoldReasonCode", "HoldReason", "LeaveJobInQueue"))
say("L5a spool=True before spool():", {k: str(a.get(k)) for k in ("JobStatus", "HoldReasonCode", "HoldReason", "LeaveJobInQueue")})
schedd.spool(r)
a = wait_status(c, (4,), 120, ("JobStatus", "ExitCode"))
time.sleep(5)
say("L5b completed spooled job:", "in queue JobStatus", (q(c, ("JobStatus",)) or {}).get("JobStatus"), "| initialdir holds:", listdir(d))
schedd.retrieve("ClusterId == %d" % c)
say("L5c after retrieve: initialdir holds:", listdir(d), "| queue:", q(c, ("JobStatus",)))
time.sleep(10)
say("L5d 10 s after retrieve: queue:", q(c, ("JobStatus",)))
if q(c):
    rm(c)
    wait_gone(c, 30)
    say("L5e removed after retrieve; history:", final(c, ("JobStatus", "ExitCode", "RemoveReason")))
# spooled job removed at JobStatus 4 WITHOUT retrieve: are outputs lost?
d2 = fresh("l5-noretr")
script(os.path.join(d2, "s.sh"), "echo out-line; echo r > result.pkl\n")
r = schedd.submit(htc.Submit(base(d2, executable=os.path.join(d2, "s.sh"), transfer_output_files="result.pkl")), spool=True)
c = int(r.cluster()); schedd.spool(r)
wait_status(c, (4,), 120)
rm(c)
wait_gone(c, 30)
say("L5f spooled, removed at JobStatus 4 without retrieve: initialdir holds", listdir(d2), "history", final(c, ("JobStatus", "ExitCode", "RemoveReason")))

# ---------- L6 act() on absent / finished jobs
for label, spec in (("nonexistent cluster", "ClusterId == 999999"), ("finished cluster", "ClusterId == %d" % cl["exit3"])):
    try:
        res = schedd.act(htc.JobAction.Remove, spec, reason="probe")
        say("L6 act(Remove) on %s: returned" % label, {k: res.get(k) for k in res.keys() if res.get(k)})
    except Exception as e:
        say("L6 act(Remove) on %s: raised" % label, type(e).__name__, short(str(e)))
# ---------- L7 does act(..., reason=) reach RemoveReason/HoldReason? (host_service/RunHandle read them back)
import classad2
d = fresh("l7")
for label, spec in (("constraint str", lambda c: "ClusterId == %d" % c), ("int cluster", lambda c: c), ("'c.0' str", lambda c: "%d.0" % c),
                    ("ExprTree", lambda c: classad2.ExprTree("ClusterId == %d" % c))):
    c = submit(base(d, executable="/bin/sleep", arguments="300"))
    wait_status(c, (2,), 60)
    schedd.act(htc.JobAction.Remove, spec(c), reason="graphed: via %s" % label)
    wait_gone(c, 60)
    say("L7 act(Remove, %-14s reason=...) -> history" % label, final(c, ("JobStatus", "RemoveReason", "ExitReason")))
c = submit(base(d, executable="/bin/sleep", arguments="300"))
wait_status(c, (2,), 60)
schedd.act(htc.JobAction.Hold, "ClusterId == %d" % c, reason="graphed: hold reason")
a = wait_status(c, (5,), 30, ("JobStatus", "HoldReasonCode", "HoldReason"))
say("L7 act(Hold, reason=...) -> queue", {k: a.get(k) for k in ("JobStatus", "HoldReasonCode", "HoldReason")})
rm(c)
c = submit(base(d, executable="/bin/sleep", arguments="300"))
wait_status(c, (2,), 60)
p = subprocess.run(["condor_rm", "-reason", "graphed: via condor_rm -reason", str(c)], capture_output=True, text=True)
wait_gone(c, 60)
say("L7 condor_rm -reason (CLI) -> history", final(c, ("JobStatus", "RemoveReason")))
say("L-done")
